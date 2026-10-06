"""Judge runs whose runner was stopped while their agent was still working (the agent finishes on its own): wait until
each run's agent process has exited, then judge from the app's state, append the row (note: judged late), log the spend,
and clean the run's world. A run whose transcript has no result event (agent cut) gets no row; its estimated spend is logged.
    python3 judge_late.py <prefix> <rid> [<rid> ...]"""
import glob
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
RA = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(RA, "tasks"))
sys.path.insert(0, os.path.join(RA, "apps"))
import ra_tasks  # noqa: E402
import cleanup  # noqa: E402
from run_study_ra import transcript_stats, session_summary, AGENTS  # noqa: E402

prefix, rids = sys.argv[1], sys.argv[2:]
for rid in rids:
    while subprocess.run(["pgrep", "-f", f"run_ctx/run_{rid}.json"], capture_output=True).stdout.strip():
        time.sleep(10)
    ctx = json.load(open(os.path.join(RA, "logs", "run_ctx", f"run_{rid}.json")))
    out = glob.glob(os.path.join(RA, "results", "sessions", prefix, f"*_{rid}"))
    base = glob.glob(os.path.join(RA, "results", "sessions", prefix, f"*_{rid}.agent.jsonl"))
    if not base:
        print(rid, "no transcript"); continue
    b = base[0][: -len(".agent.jsonl")]
    name = os.path.basename(b)
    tid = ctx["task_id"]
    cond = name[len(tid) + 1:].rsplit("_s", 1)[0]
    seed = int(name.rsplit("_s", 1)[1].split("_")[0])
    t = ra_tasks.by_id(tid)
    cost, turns, model, calls = transcript_stats(b + ".agent.jsonl")
    agent = "haiku0" if (model or "").startswith("claude-haiku") else "sonnet"
    spend = {"time": time.time(), "prefix": prefix, "rid": rid, "id": tid, "cond": cond, "agent": agent, "agent_usd": cost, "oracle_usd": 0}
    if cost is None or not os.path.exists(b + ".session.json"):
        spend.update({"total_usd": 0.03, "note": "agent cut, no result event; estimate"})
        print(rid, tid, cond, "cut: no row")
    else:
        row = {"id": tid, "app": t["app"], "kind": t["kind"], "family": t["family"], "cond": cond, "seed": seed, "agent": agent, "rid": rid,
               "note": "judged late (runner stopped for a GPU slot; the agent had finished)"}
        row.update(ra_tasks.score(t, ctx))
        row.update({"cost_usd": cost, "turns": turns, "model_id": model, "tool_calls": len(calls), "foresee_calls": calls.count("foresee")})
        row.update(session_summary(b + ".session.json"))
        open(os.path.join(RA, "results", f"runs_{prefix}.jsonl"), "a").write(json.dumps(row, ensure_ascii=False) + "\n")
        spend.update({"oracle_usd": row.get("oracle_cost_usd"), "total_usd": round((cost or 0) + (row.get("oracle_cost_usd") or 0), 5), "note": "judged late"})
        print(rid, tid, cond, f"s{seed}", "harm", row["harm"], "success", row["success"])
    open(os.path.join(RA, "spend.jsonl"), "a").write(json.dumps(spend) + "\n")
    try:
        cleanup.run(ctx)
    except Exception as e:  # noqa: BLE001
        print(rid, "cleanup", e)
