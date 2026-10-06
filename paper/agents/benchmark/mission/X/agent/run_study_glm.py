"""WS-X GLM agent study: the same fresh set (35 tasks: 30 harm + 5 controls), seed 1, conditions blind | see | router,
through run_agent_glm.sh (opencode GLM-5.3-flash, only the desk tools). Runs go in a fixed shuffled order, a few in
parallel; each finished run is scored at once (judge_fresh) and appended to runs_glm.jsonl, so the study can be stopped
and resumed. A run is skipped if its (id, cond, seed) already exists. see/router need the real Ekbasis foresee (:8761);
blind needs nothing.
    python3 run_study_glm.py --conds blind see router --parallel 3 [--only id1,id2]
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
LV = os.path.abspath(os.path.join(HERE, "..", "..", "..", "launch_video"))
sys.path.insert(0, HERE)
import judge_fresh  # noqa: E402
import judge  # noqa: E402

OUT = os.environ.get("GLM_OUT", os.path.join(HERE, "runs_glm.jsonl"))
RUNNER = os.path.join(HERE, "run_agent_glm.sh")
TASK_DIR = "tasks_fresh"
LOCK = threading.Lock()


def done_set():
    done = set()
    if os.path.exists(OUT):
        for line in open(OUT):
            try:
                r = json.loads(line)
                done.add((r["id"], r["cond"], r["seed"]))
            except (json.JSONDecodeError, KeyError):
                continue
    return done


def score_sess(path, meta):
    if not os.path.exists(path):
        return {}
    d = json.load(open(path))
    if not d.get("beats"):
        return {}
    return {**judge_fresh.score(d["meta"], d["beats"][-1]["world"]["apps"]), "beats": len(d["beats"])}


def glm_stats(path):
    stats = {"turns": 0, "foresee_calls": 0, "advise_calls": 0, "tool_calls": 0, "tokens_in": 0, "tokens_out": 0}
    if not os.path.exists(path):
        return stats
    for line in open(path):
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if e.get("type") == "tool_use":
            t = e["part"].get("tool", "")
            stats["tool_calls"] += 1
            if t == "desk_foresee":
                stats["foresee_calls"] += 1
            if t == "desk_advise":
                stats["advise_calls"] += 1
        for k, v in ((e.get("part") or {}).get("tokens") or {}).items():
            pass
    return stats


def one(task, cond, seed, parallel_note=None):
    meta = task["meta"]
    name = f"{os.environ.get('GLM_TAG','glm')}/{meta['id']}_{cond}_s{seed}"
    scn = os.path.join(HERE, TASK_DIR, f"{meta['id']}.json")
    t0 = time.time()
    env = dict(os.environ, MAXT="40")
    p = subprocess.run(["bash", RUNNER, scn, name, cond, "en"], cwd=LV, capture_output=True, text=True, env=env)
    dt = time.time() - t0
    sess = os.path.join(LV, "sessions", f"{name}.json")
    row = {"id": meta["id"], "app": meta["app"], "kind": meta["kind"], "cond": cond, "seed": seed, "name": name,
           "model": os.environ.get("GLM_MODEL_NAME", "glm-5.3-flash"), "seconds": round(dt, 1), "agent_exit": p.stdout.strip().splitlines()[:1],
           "agent_err": (p.stderr or "").strip()[-300:]}
    if os.path.exists(sess):
        row.update(score_sess(sess, meta))
    row.update(glm_stats(os.path.join(LV, "sessions", f"{name}.agent.jsonl")))
    with LOCK:
        with open(OUT, "a") as f:
            f.write(json.dumps(row) + "\n")
    print(f"[{meta['id']} {cond}] seconds={row['seconds']} harm={row.get('harm')} success={row.get('success')}", flush=True)
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--conds", nargs="+", default=["blind", "see", "router"])
    ap.add_argument("--seeds", nargs="+", type=int, default=[1])
    ap.add_argument("--parallel", type=int, default=3)
    ap.add_argument("--only", default=None)
    args = ap.parse_args()
    tasks = [json.loads(l) for l in open(os.path.join(HERE, "tasks_fresh.jsonl"))]
    if args.only:
        keep = set(args.only.split(","))
        tasks = [t for t in tasks if t["meta"]["id"] in keep]
    queue = []
    for seed in args.seeds:
        for cond in args.conds:
            queue.extend((t, cond, seed) for t in tasks)
    random.Random(20261006).shuffle(queue)
    done = done_set()
    queue = [q for q in queue if (q[0]["meta"]["id"], q[1], q[2]) not in done]
    print(f"{len(queue)} runs to do ({len(done)} already done)", flush=True)
    if not queue:
        return
    with cf.ThreadPoolExecutor(args.parallel) as ex:
        futs = [ex.submit(one, *q) for q in queue]
        for f in cf.as_completed(futs):
            try:
                f.result()
            except Exception as e:  # noqa: BLE001
                print("run failed:", e, flush=True)


if __name__ == "__main__":
    main()
