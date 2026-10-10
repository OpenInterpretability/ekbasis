#!/usr/bin/env python3
"""Tool-guard agent study (PREREG.md): GLM-5.3-Flash on the demo desktop's fresh set, conditions A (no guard),
B (guard, session only), C (guard + read-only probe), D (guard with the app's backend state), Cinj (C with planted
text). Same design as mission/X/agent/run_study_glm.py: a fixed shuffled queue, a few runs in parallel, each run
judged from the app's final state (judge_fresh) at once and appended to OUT, so the study stops and resumes; a run
already in OUT is skipped.

    run_study_tg.py --conds A B C D --parallel 3 [--only id1,id2] [--tasks fresh|inlab] [--out runs.jsonl] [--tag tg]
"""
import argparse
import concurrent.futures as cf
import json
import os
import random
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
LV = os.environ.get("LV", "/Volumes/SSD Major/news/decision_model/launch_video")
XAGENT = os.environ.get("XAGENT", "/Volumes/SSD Major/news/decision_model/mission/X/agent")
sys.path.insert(0, XAGENT)
import judge  # noqa: E402
import judge_fresh  # noqa: E402

LOCK = threading.Lock()
STOP_FILE = os.path.join(HERE, "STOP")   # touch it to stop starting new runs (the running ones finish)


def done_set(out):
    done = set()
    if os.path.exists(out):
        for line in open(out):
            try:
                r = json.loads(line)
                done.add((r["id"], r["cond"], r["seed"]))
            except (ValueError, KeyError):
                continue
    return done


def agent_stats(path):
    st = {"tool_calls": 0, "clicks": 0, "tokens_in": 0, "tokens_out": 0, "steps": 0}
    if not os.path.exists(path):
        return st
    for line in open(path):
        try:
            e = json.loads(line)
        except ValueError:
            continue
        part = e.get("part") or {}
        if e.get("type") == "tool_use":
            st["tool_calls"] += 1
            st["clicks"] += part.get("tool", "") == "desk_click"
        if e.get("type") == "step_finish":
            st["steps"] += 1
            tk = part.get("tokens") or {}
            st["tokens_in"] += int(tk.get("input") or 0) + int((tk.get("cache") or {}).get("read") or 0)
            st["tokens_out"] += int(tk.get("output") or 0) + int(tk.get("reasoning") or 0)
    return st


def guard_stats(path):
    rows = [json.loads(l) for l in open(path)] if os.path.exists(path) else []
    checked = [r for r in rows if not r.get("skipped") and r["action"] != "blocked again"]
    return {"guard_rows": rows, "checks": len(checked),
            "flags": sum(r["verdict"] != "ok" for r in checked),
            "blocked": sum(r["action"] == "blocked" for r in rows),
            "after_warning": sum(r["action"] == "called after a warning" for r in rows),
            "guard_seconds": round(sum(r.get("seconds") or 0 for r in rows), 2),
            "ekb_tokens": sum(((r.get("usage") or {}).get("input_tokens") or 0) for r in checked)}


def one(task, cond, seed, tasks_dir, tag, out, fresh):
    meta = task["meta"]
    name = f"{tag}/{meta['id']}_{cond}_s{seed}"
    scn = os.path.join(XAGENT, tasks_dir, f"{meta['id']}.json")
    t0 = time.time()
    p = subprocess.run(["bash", os.path.join(HERE, "run_agent_tg.sh"), scn, name, cond], capture_output=True, text=True,
                       stdin=subprocess.DEVNULL)
    dt = time.time() - t0
    sess = os.path.join(LV, "sessions", f"{name}.json")
    row = {"id": meta["id"], "app": meta["app"], "kind": meta["kind"], "cond": cond, "seed": seed, "name": name,
           "seconds": round(dt, 1), "agent_exit": p.stdout.strip().splitlines()[:1], "agent_err": (p.stderr or "").strip()[-300:],
           "harm_path": [x[1] for x in ((meta.get("paths") or {}).get("harm") or [])]}
    if os.path.exists(sess):
        d = json.load(open(sess))
        if d.get("beats"):
            apps = d["beats"][-1]["world"]["apps"]
            row.update((judge_fresh.score if fresh else judge.score)(d["meta"], apps))
            row["beats"] = len(d["beats"])
    row.update(agent_stats(os.path.join(LV, "sessions", f"{name}.agent.jsonl")))
    row.update(guard_stats(os.path.join(LV, "sessions", f"{name}.guard.jsonl")))
    with LOCK, open(out, "a") as f:
        f.write(json.dumps(row) + "\n")
    print(f"[{meta['id']} {cond}] {row['seconds']}s harm={row.get('harm')} success={row.get('success')} "
          f"checks={row['checks']} flags={row['flags']} blocked={row['blocked']}", flush=True)
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--conds", nargs="+", default=["A", "B", "C", "D"])
    ap.add_argument("--seeds", nargs="+", type=int, default=[1])
    ap.add_argument("--parallel", type=int, default=3)
    ap.add_argument("--only", default=None)
    ap.add_argument("--tasks", choices=("fresh", "inlab"), default="fresh")
    ap.add_argument("--out", default=os.path.join(HERE, "runs.jsonl"))
    ap.add_argument("--tag", default="tg")
    a = ap.parse_args()
    fresh = a.tasks == "fresh"
    manifest, tdir = ("tasks_fresh.jsonl", "tasks_fresh") if fresh else ("tasks.jsonl", "tasks")
    tasks = [json.loads(l) for l in open(os.path.join(XAGENT, manifest))]
    if a.only:
        keep = set(a.only.split(","))
        tasks = [t for t in tasks if t["meta"]["id"] in keep]
    queue = [(t, c, s) for s in a.seeds for c in a.conds for t in tasks]
    random.Random(20261010).shuffle(queue)
    done = done_set(a.out)
    queue = [q for q in queue if (q[0]["meta"]["id"], q[1], q[2]) not in done]
    print(f"{len(queue)} runs to do ({len(done)} already done)", flush=True)
    with cf.ThreadPoolExecutor(a.parallel) as ex:
        futs = []
        for q in queue:
            futs.append(ex.submit(lambda q=q: None if os.path.exists(STOP_FILE) else one(*q, tdir, a.tag, a.out, fresh)))
        for f in cf.as_completed(futs):
            try:
                f.result()
            except Exception as e:  # noqa: BLE001
                print("run failed:", e, flush=True)


if __name__ == "__main__":
    main()
