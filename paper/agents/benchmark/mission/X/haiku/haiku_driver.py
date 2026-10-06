"""SPEC Addendum D.1 driver: Claude Haiku on (a) the fresh set (blind, see) and (b) WS-AL's look-ahead tasks (blind, ahead),
seed 1. Tasks go in a fixed shuffled order, alternating between the two studies. Each task runs both of its conditions at
once through the study's own runner (--only <task>). Before a task starts, the driver checks that the Haiku spend logged so
far plus the expected cost of that task stays within the US$ 5 budget (pilots included).
    python3 haiku_driver.py"""
import concurrent.futures as cf
import json
import os
import random
import subprocess
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
X = os.path.dirname(HERE)
PY = os.environ.get("PY312", "/opt/homebrew/bin/python3.12")
BUDGET = 5.0
LOCK = threading.Lock()
RUN_A = os.path.join(X, "agent", "runs_hfresh.jsonl")
RUN_B = os.path.join(HERE, "AL", "runs_hla.jsonl")


def spent():
    s = sum(json.loads(l)["usd"] for l in open(os.path.join(HERE, "spend.jsonl")))
    for p in (RUN_A, RUN_B):
        if os.path.exists(p):
            s += sum(json.loads(l).get("cost_usd") or 0 for l in open(p))
    return s


def mean_cost(path, default):
    if not os.path.exists(path):
        return default
    v = [json.loads(l).get("cost_usd") or 0 for l in open(path)]
    return sum(v) / len(v) if v else default


def run_task(study, tid):
    if study == "a":
        cmd = [PY, "run_study.py", "--runner", "x", "--model", "haiku", "--prefix", "hfresh", "--tasks", "tasks_fresh.jsonl",
               "--task-dir", "tasks_fresh", "--judge", "judge_fresh", "--conds", "blind", "see", "--seeds", "1", "--only", tid,
               "--parallel", "2", "--cap", "99"]
        env = dict(os.environ, FORESEE_URL="http://127.0.0.1:8761/foresee")
        cwd = os.path.join(X, "agent")
    else:
        cmd = ["python3", "run_al.py", "--tasks", "tasks_la.jsonl", "--task-dir", "tasks_la", "--conds", "blind", "ahead", "--seeds", "1",
               "--prefix", "hla", "--only", tid, "--parallel", "2", "--cap", "99"]
        env = dict(os.environ, AL_MODEL="haiku", FORESEE_URL="http://127.0.0.1:8781/foresee")
        cwd = os.path.join(HERE, "AL")
    p = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    tail = (p.stdout.strip().splitlines() or [""])[-3:]
    print(f"[{study}] {tid}: " + " | ".join(tail), flush=True)


def main():
    ta = [json.loads(l)["meta"]["id"] for l in open(os.path.join(X, "agent", "tasks_fresh.jsonl"))]
    tb = [json.loads(l)["meta"]["id"] for l in open(os.path.join(HERE, "AL", "tasks_la.jsonl"))]
    random.Random(20261005).shuffle(ta)
    random.Random(20261005).shuffle(tb)
    queue = []
    for i in range(max(len(ta), len(tb))):
        if i < len(ta):
            queue.append(("a", ta[i]))
        if i < len(tb):
            queue.append(("b", tb[i]))
    inflight = []
    with cf.ThreadPoolExecutor(2) as ex:
        for study, tid in queue:
            while len([f for f in inflight if not f.done()]) >= 2:
                for f in inflight:
                    if not f.done():
                        f.result()
                        break
            with LOCK:
                exp = 2 * max(mean_cost(RUN_A, 0.05), mean_cost(RUN_B, 0.04))
                pending = sum(1 for f in inflight if not f.done())
                if spent() + (pending + 1) * exp > BUDGET:
                    print(f"budget: stopping before {study}:{tid} (spent ${spent():.2f}, {pending} tasks in flight)", flush=True)
                    break
            inflight.append(ex.submit(run_task, study, tid))
        for f in inflight:
            f.result()
    print(f"finished; Haiku spend ${spent():.2f}", flush=True)


if __name__ == "__main__":
    main()
