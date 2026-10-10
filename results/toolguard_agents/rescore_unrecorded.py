#!/usr/bin/env python3
"""Rows for runs that finished but were not recorded (the first runner failed on control tasks, whose `paths.harm` is
null, after the agent had run): judged from the saved session exactly as run_study_tg.one() would, appended to the
runs file with "rescored": true. The agent is never run again. seconds = first to last agent event (approximate)."""
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run_study_tg as R  # noqa: E402

out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "runs.jsonl")
tag = sys.argv[2] if len(sys.argv) > 2 else "tg"
S = os.path.join(R.LV, "sessions", tag)
done = {json.loads(l)["name"] for l in open(out)} if os.path.exists(out) else set()
tasks = {json.loads(l)["meta"]["id"]: json.loads(l)["meta"] for l in open(os.path.join(R.XAGENT, "tasks_fresh.jsonl"))}
for sess in sorted(glob.glob(os.path.join(S, "*_s1.json"))):
    base = os.path.basename(sess)[:-5]
    name = f"{tag}/{base}"
    if name in done:
        continue
    tid, cond = base[:-3].rsplit("_", 1)
    meta = tasks[tid]
    d = json.load(open(sess))
    if not d.get("beats"):
        continue
    ev = [json.loads(l) for l in open(os.path.join(S, f"{base}.agent.jsonl")) if l.strip()]
    row = {"id": tid, "app": meta["app"], "kind": meta["kind"], "cond": cond, "seed": 1, "name": name,
           "seconds": round((ev[-1]["timestamp"] - ev[0]["timestamp"]) / 1000, 1) if ev else None, "rescored": True,
           "harm_path": [x[1] for x in ((meta.get("paths") or {}).get("harm") or [])]}
    row.update(R.judge_fresh.score(d["meta"], d["beats"][-1]["world"]["apps"]))
    row["beats"] = len(d["beats"])
    row.update(R.agent_stats(os.path.join(S, f"{base}.agent.jsonl")))
    row.update(R.guard_stats(os.path.join(S, f"{base}.guard.jsonl")))
    with open(out, "a") as f:
        f.write(json.dumps(row) + "\n")
    print("rescored", name, row["harm"], row["success"])
