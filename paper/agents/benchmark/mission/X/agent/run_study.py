"""WS-X agent study runner: every task x condition (blind = no foresee tool, see = foresee asks Ekbasis) x seed, through
launch_video/run_agent.sh (Claude Sonnet via `claude -p`, only the desk tools). Runs go in a fixed shuffled order, a few
in parallel, and each finished run is scored at once (judge.py) and appended to runs.jsonl, so the study can be stopped
and resumed. Stops scheduling new runs once the logged Claude spend reaches the cap.
    python3 run_study.py [--seeds 1 2] [--parallel 4] [--cap 20] [--only id1,id2] [--prefix xstudy]
env: FORESEE_URL (the foresee service the stage calls; default http://127.0.0.1:8761/foresee)"""
import argparse
import concurrent.futures as cf
import json
import os
import random
import subprocess
import sys
import threading
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
LV = os.path.abspath(os.path.join(HERE, "..", "..", "..", "launch_video"))
sys.path.insert(0, HERE)
import importlib  # noqa: E402
import judge  # noqa: E402
score_session = judge.score_session

LOCK = threading.Lock()
RUNNER = "run_agent.sh"   # launch_video/run_agent.sh (blind, see); --runner x uses agent/run_agent_x.sh (all modes)
TASK_DIR = "tasks"


def transcript_stats(path):
    cost = turns = None
    calls = []
    if os.path.exists(path):
        for line in open(path):
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if e.get("type") == "result":
                cost, turns = e.get("total_cost_usd"), e.get("num_turns")
            if e.get("type") == "assistant":
                for c in e.get("message", {}).get("content", []):
                    if c.get("type") == "tool_use":
                        calls.append({"tool": c["name"].split("__")[-1], "input": c.get("input", {})})
    return cost, turns, calls


def foresights(session_path, meta):
    d = json.load(open(session_path))
    harm_el = (meta["paths"]["harm"] or [[None, None]])[-1][1]
    safe_el = meta["paths"]["safe"][-1][1]
    out = []
    for b in d["beats"]:
        if b["kind"] == "hud":
            out.append({"target": b["target"], "on_harmful": b["target"] == harm_el, "on_safe": b["target"] == safe_el,
                        "flagged": any(l["bad"] for l in b["hud"]["lines"]),
                        "lines": [[l["text"], round(l["conf"], 4), l["bad"]] for l in b["hud"]["lines"]]})
    clicks = [b["target"] for b in d["beats"] if b["kind"] in ("click", "type", "open")]
    return out, clicks


MODEL = "sonnet"


def one(task, cond, seed, prefix, out_path, spent):
    meta = task["meta"]
    name = f"{prefix}/{meta['id']}_{cond}_s{seed}"
    scn = os.path.join(HERE, TASK_DIR, f"{meta['id']}.json")
    t0 = time.time()
    p = subprocess.run(["bash", RUNNER, scn, name, cond, MODEL, "en"], cwd=LV, capture_output=True, text=True,
                       env=dict(os.environ, MAXT=os.environ.get("MAXT", "40")))
    dt = time.time() - t0
    sess = os.path.join(LV, "sessions", f"{name}.json")
    cost, turns, calls = transcript_stats(os.path.join(LV, "sessions", f"{name}.agent.jsonl"))
    row = {"id": meta["id"], "app": meta["app"], "kind": meta["kind"], "cond": cond, "seed": seed, "name": name, "runner": RUNNER, "model": MODEL,
           "seconds": round(dt, 1), "cost_usd": cost, "turns": turns, "tool_calls": len(calls),
           "foresee_calls": sum(c["tool"] == "foresee" for c in calls), "agent_exit": p.stdout.strip().splitlines()[:1]}
    if os.path.exists(sess):
        row.update(score_session(sess))
        row["huds"], row["clicks"] = foresights(sess, meta)
        fc = json.load(open(sess))["meta"].get("foresee_calls") or []
        row["foresee_ms"] = [c["ms"] for c in fc]
        row["oracle_cost_usd"] = round(sum(c.get("cost_usd") or 0 for c in fc), 5)
    else:
        row.update({"harm": None, "success": None, "blocked": None, "error": (p.stderr or p.stdout)[-400:]})
    with LOCK:
        with open(out_path, "a") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        spent[0] += (cost or 0) + (row.get("oracle_cost_usd") or 0)
    print(f"{name:34s} harm={row.get('harm')} success={row.get('success')} blocked={row.get('blocked')} "
          f"foresee={row['foresee_calls']} ${cost} {dt:.0f}s  (spent ${spent[0]:.2f})", flush=True)
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", default=[1, 2])
    ap.add_argument("--parallel", type=int, default=4)
    ap.add_argument("--cap", type=float, default=20.0)
    ap.add_argument("--only", default="")
    ap.add_argument("--prefix", default="xstudy")
    ap.add_argument("--conds", nargs="+", default=["blind", "see"])
    ap.add_argument("--runner", default="lv", choices=["lv", "x"])
    ap.add_argument("--tasks", default="tasks.jsonl")
    ap.add_argument("--task-dir", default="tasks")
    ap.add_argument("--judge", default="judge")
    ap.add_argument("--model", default="sonnet")
    a = ap.parse_args()
    global RUNNER, TASK_DIR, score_session, MODEL
    MODEL = a.model
    score_session = importlib.import_module(a.judge).score_session
    RUNNER = "run_agent.sh" if a.runner == "lv" else os.path.join(HERE, "run_agent_x.sh")
    TASK_DIR = a.task_dir
    fx = os.environ.get("FORESEE_URL", "http://127.0.0.1:8761/foresee")
    os.environ["FORESEE_URL"] = fx
    if "see" in a.conds:
        h = json.load(urllib.request.urlopen(fx.replace("/foresee", "/health"), timeout=20))
        print("foresee health:", h, flush=True)
        if h.get("mock"):
            print("WARNING: mock foresee (plumbing test only)", flush=True)
    if "oracle_llm" in a.conds:
        ou = os.environ.get("ORACLE_URL", "http://127.0.0.1:8762/foresee")
        print("oracle health:", json.load(urllib.request.urlopen(ou.replace("/foresee", "/health"), timeout=20)), flush=True)
    tasks = [json.loads(l) for l in open(os.path.join(HERE, a.tasks))]
    if a.only:
        keep = set(a.only.split(","))
        tasks = [t for t in tasks if t["meta"]["id"] in keep]
    out_path = os.path.join(HERE, f"runs_{a.prefix}.jsonl")
    done = set()
    spent = [0.0]
    if os.path.exists(out_path):
        for l in open(out_path):
            r = json.loads(l)
            done.add((r["id"], r["cond"], r["seed"]))
            spent[0] += (r.get("cost_usd") or 0) + (r.get("oracle_cost_usd") or 0)
    jobs = [(t, c, s) for t in tasks for c in a.conds for s in a.seeds if (t["meta"]["id"], c, s) not in done]
    random.Random(20261005).shuffle(jobs)
    os.makedirs(os.path.join(LV, "sessions", a.prefix), exist_ok=True)
    os.makedirs(os.path.join(LV, "agent_cwd", f"mcp_{a.prefix}"), exist_ok=True)  # run_agent.sh writes agent_cwd/mcp_<name>.json
    print(f"{len(jobs)} runs to do, {len(done)} already done, spent so far ${spent[0]:.2f}, cap ${a.cap}", flush=True)
    with cf.ThreadPoolExecutor(a.parallel) as ex:
        futs = []
        for t, c, s in jobs:
            while len([f for f in futs if not f.done()]) >= a.parallel:
                time.sleep(1)
            if spent[0] >= a.cap:
                print(f"cap reached (${spent[0]:.2f}); not scheduling more runs", flush=True)
                break
            futs.append(ex.submit(one, t, c, s, a.prefix, out_path, spent))
        for f in futs:
            f.result()
    print(f"finished; spent ${spent[0]:.2f}", flush=True)


if __name__ == "__main__":
    main()
