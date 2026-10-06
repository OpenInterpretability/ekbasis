"""WS-AL runner (from WS-X's run_study.py): every task x condition x seed through run_agent_al.sh (Claude Sonnet via
`claude -p`, the desk tools + the condition's tool or text). Runs go in a fixed shuffled order, a few in parallel; each
finished run is scored at once (judge_al.py) and appended to runs_<prefix>.jsonl, so a study can be stopped and resumed.
No new run is scheduled once the logged Claude spend of ALL AL runs reaches the cap.
    python3 run_al.py --tasks tasks_la.jsonl --task-dir tasks_la --conds blind ahead --seeds 1 2 --prefix la_a --cap 25"""
import argparse
import concurrent.futures as cf
import glob
import json
import os
import random
import subprocess
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
import sys  # noqa: E402
sys.path.insert(0, HERE)
from judge_al import score_session  # noqa: E402

LOCK = threading.Lock()


def spent_all():
    tot = 0.0
    for p in glob.glob(os.path.join(HERE, "runs_*.jsonl")):
        for l in open(p):
            r = json.loads(l)
            tot += r.get("cost_usd") or 0
    return tot


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
                        calls.append(c["name"].split("__")[-1])
    return cost, turns, calls


def one(task, cond, seed, prefix, task_dir, out_path, spent, maxt):
    meta = task["meta"]
    name = f"{prefix}/{meta['id']}_{cond}_s{seed}"
    scn = os.path.join(HERE, task_dir, f"{meta['id']}.json")
    t0 = time.time()
    p = subprocess.run(["bash", "run_agent_al.sh", scn, name, cond, "sonnet"], cwd=HERE, capture_output=True, text=True,
                       env=dict(os.environ, MAXT=str(maxt)))
    dt = time.time() - t0
    sess = os.path.join(HERE, "sessions", f"{name}.json")
    cost, turns, calls = transcript_stats(os.path.join(HERE, "sessions", f"{name}.agent.jsonl"))
    row = {"id": meta["id"], "app": meta["app"], "kind": meta["kind"], "cond": cond, "seed": seed, "name": name,
           "seconds": round(dt, 1), "cost_usd": cost, "turns": turns, "tool_calls": len(calls),
           "advise_calls": calls.count("advise"), "foresee_calls": calls.count("foresee"), "balances_calls": calls.count("balances"),
           "looks": calls.count("look"), "agent_exit": p.stdout.strip().splitlines()[:1]}
    if os.path.exists(sess):
        row.update(score_session(sess))
        fc = json.load(open(sess))["meta"].get("foresee_calls") or []
        row["ekb_ms"] = [c["ms"] for c in fc]
    else:
        row.update({"success": None, "harm": None, "error": (p.stderr or p.stdout)[-400:]})
    with LOCK:
        with open(out_path, "a") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        spent[0] += cost or 0
    print(f"{name:42s} success={row.get('success')} harm={row.get('harm')} actions={row.get('actions')} "
          f"adv={row['advise_calls']} fs={row['foresee_calls']} ${cost} {dt:.0f}s (AL spend ${spent[0]:.2f})", flush=True)
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default="tasks_la.jsonl")
    ap.add_argument("--task-dir", default="tasks_la")
    ap.add_argument("--conds", nargs="+", default=["blind", "ahead"])
    ap.add_argument("--seeds", type=int, nargs="+", default=[1, 2])
    ap.add_argument("--parallel", type=int, default=4)
    ap.add_argument("--cap", type=float, default=25.0)
    ap.add_argument("--prefix", default="la_a")
    ap.add_argument("--only", default="")
    ap.add_argument("--maxt", type=int, default=40)
    a = ap.parse_args()
    tasks = [json.loads(l) for l in open(os.path.join(HERE, a.tasks))]
    if a.only:
        keep = set(a.only.split(","))
        tasks = [t for t in tasks if t["meta"]["id"] in keep]
    out_path = os.path.join(HERE, f"runs_{a.prefix}.jsonl")
    done = set()
    if os.path.exists(out_path):
        for l in open(out_path):
            r = json.loads(l)
            if r.get("success") is not None:
                done.add((r["id"], r["cond"], r["seed"]))
    spent = [spent_all()]
    jobs = [(t, c, s) for t in tasks for c in a.conds for s in a.seeds if (t["meta"]["id"], c, s) not in done]
    random.Random(20261005).shuffle(jobs)
    print(f"{len(jobs)} runs to do, {len(done)} done, AL spend so far ${spent[0]:.2f}, cap ${a.cap}", flush=True)
    with cf.ThreadPoolExecutor(a.parallel) as ex:
        futs = []
        for t, c, s in jobs:
            while len([f for f in futs if not f.done()]) >= a.parallel:
                time.sleep(1)
            if spent[0] >= a.cap:
                print(f"cap reached (${spent[0]:.2f}); no more runs scheduled", flush=True)
                break
            futs.append(ex.submit(one, t, c, s, a.prefix, a.task_dir, out_path, spent, a.maxt))
        for f in futs:
            f.result()
    print(f"finished; AL spend ${spent[0]:.2f}", flush=True)


if __name__ == "__main__":
    main()
