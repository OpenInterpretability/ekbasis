"""WS-X τ-bench agent study runner (SPEC Addendum C). For each task (fixed shuffled order of the 115 retail test tasks) and
each condition (none / placebo / ekbasis, in a per-task shuffled order): τ-bench's user simulator opens the conversation,
then Claude Sonnet runs via `claude -p` with only the tau MCP tools and the retail policy (wiki.md) as its system prompt.
Scored at once with τ-bench's reward, the policy checks and the write checks (score.py); appended to runs_tau.jsonl.
Stops before a new task when the logged spend plus the expected cost of one task exceeds the cap.
    python3 run_tau.py [--n 40] [--cap 10] [--parallel 3] [--pilot]"""
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
sys.path.insert(0, HERE)
import tau_env as E  # noqa: E402
import score  # noqa: E402

PY = os.environ.get("TAU_PYTHON", "python3")
ORDER = list(range(len(E.TASKS)))
random.Random(20261005).shuffle(ORDER)
PILOT = ORDER[-1]
LOCK = threading.Lock()
HARNESS = ("\n\n# How this conversation works\nYou are the retail customer-service agent described above. The customer talks to you "
           "only through the respond tool: call respond with your message and the customer's reply comes back as its result. "
           "Use the tools to look up and change data. When the customer has ended the conversation, stop.")
FORESEE_NOTE = ("\nBefore any tool call that changes the database, call foresee with that tool's name and arguments; it predicts what "
                "the call will do. Use the prediction to decide.")


def run_one(idx, cond, prefix, out_path):
    task = E.TASKS[idx]
    name = f"{prefix}_t{idx:03d}_{cond}"
    os.makedirs(os.path.join(HERE, "episodes"), exist_ok=True)
    ep_path = os.path.join(HERE, "episodes", f"{name}.json")
    hist = [["agent", "Hi! How can I help you today?"]]
    first, ucost = E.user_reply(task.instruction, hist)
    hist.append(["user", first])
    json.dump({"task_index": idx, "mode": cond, "instruction": task.instruction, "history": hist, "actions": [], "foresee": [],
               "events": [{"type": "agent", "text": hist[0][1]}, {"type": "user", "text": first}], "user_cost": ucost,
               "user_calls": 1, "done": False}, open(ep_path, "w"))
    cfg = os.path.join(HERE, "episodes", f"{name}.mcp.json")
    json.dump({"mcpServers": {"tau": {"command": PY, "args": [os.path.join(HERE, "tau_mcp.py")],
                                      "env": {"EPISODE": ep_path, "MODE": cond, "EKBASIS_URL": os.environ.get("EKBASIS_URL", "http://127.0.0.1:18542")}}}},
              open(cfg, "w"))
    tools = [f"mcp__tau__{n}" for n in list(E.TOOLS) + ["respond"] + (["foresee"] if cond != "none" else [])]
    sysp = E.WIKI + HARNESS + (FORESEE_NOTE if cond != "none" else "")
    prompt = f"A customer has just written to you: \"{first}\"\nHelp them, following the policy."
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")}
    t0 = time.time()
    p = subprocess.run(["claude", "-p", prompt, "--model", "sonnet", "--tools", "", "--mcp-config", cfg, "--strict-mcp-config",
                        "--allowedTools", ",".join(tools), "--append-system-prompt", sysp, "--output-format", "stream-json", "--verbose",
                        "--max-turns", "40", "--no-session-persistence", "--setting-sources", "project,local"],
                       cwd=os.path.join(HERE, "episodes"), env=env, capture_output=True, text=True, timeout=1800)
    dt = time.time() - t0
    acost = turns = None
    for line in p.stdout.splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if e.get("type") == "result":
            acost, turns = e.get("total_cost_usd"), e.get("num_turns")
    ep = json.load(open(ep_path))
    row = {"task": idx, "cond": cond, "name": name, "seconds": round(dt, 1), "agent_cost": acost, "user_cost": round(ep["user_cost"], 5),
           "turns": turns, **score.score(task, ep)}
    row["cost"] = round((acost or 0) + ep["user_cost"], 5)
    with LOCK:
        with open(out_path, "a") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"{name:26s} reward={row['reward']} unreq_writes={row['unrequested_writes']} violations={row['violations_total']} "
          f"foresee={row['foresee_calls']} ${row['cost']:.3f} {dt:.0f}s", flush=True)
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--cap", type=float, default=10.0)
    ap.add_argument("--parallel", type=int, default=3)
    ap.add_argument("--pilot", action="store_true")
    ap.add_argument("--conds", nargs="+", default=["none", "placebo", "ekbasis"])
    a = ap.parse_args()
    prefix = "pilot" if a.pilot else "tau"
    out_path = os.path.join(HERE, f"runs_{prefix}.jsonl")
    tasks = [PILOT] if a.pilot else ORDER[: a.n]
    done = {(json.loads(l)["task"], json.loads(l)["cond"]) for l in open(out_path)} if os.path.exists(out_path) else set()
    spent = sum(json.loads(l)["cost"] for l in open(out_path)) if os.path.exists(out_path) else 0.0
    rows = [json.loads(l) for l in open(out_path)] if os.path.exists(out_path) else []
    per_run = (sum(r["cost"] for r in rows) / len(rows)) if rows else 0.12
    print(f"{len(tasks)} tasks x {a.conds}; spent ${spent:.2f}; cap ${a.cap}", flush=True)
    with cf.ThreadPoolExecutor(a.parallel) as ex:
        futs = []
        for idx in tasks:
            conds = [c for c in a.conds if (idx, c) not in done]
            random.Random(idx).shuffle(conds)
            if not conds:
                continue
            with LOCK:
                cur = sum(json.loads(l)["cost"] for l in open(out_path)) if os.path.exists(out_path) else 0.0
                pending = sum(1 for f in futs if not f.done())
            if cur + (pending + len(conds)) * per_run > a.cap:
                print(f"budget: stopping before task {idx} (spent ${cur:.2f}, {pending} runs in flight)", flush=True)
                break
            for c in conds:
                futs.append(ex.submit(run_one, idx, c, prefix, out_path))
            while sum(1 for f in futs if not f.done()) >= a.parallel * 2:
                time.sleep(2)
        for f in futs:
            f.result()
    print("finished", flush=True)


if __name__ == "__main__":
    main()
