"""WS-RA2 study runner (copy of RA's run_study_ra.py with RA2's tasks, stage, modes and paths). For each run a fresh world is
seeded through the app's API (tasks/ra2_tasks.py), the agent works through run_agent_ra2.sh (Claude Code, web tools only),
the run is judged at once from the app's own state and appended to results/runs_<prefix>.jsonl (resumable). Runs go in a
fixed shuffled order, a few in parallel; at most one Nextcloud run at a time across RA AND RA2 (RA's lock file). Stops
scheduling at the spend cap (RA2/spend.jsonl), on an agent API error (HTTP 429 usage limit: the run is not recorded), or
when a condition that needs Ekbasis finds the RA2 bridge down.
    python3 run_study_ra2.py --agent haiku0 --conds blind ask_ekbasis --seeds 1 2 --prefix h --parallel 3 --cap 25"""
import argparse
import concurrent.futures as cf
import json
import os
import random
import subprocess
import sys
import threading
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
R2 = os.path.abspath(os.path.join(HERE, ".."))
RA = os.path.abspath(os.path.join(R2, "..", "RA"))
sys.path.insert(0, os.path.join(R2, "tasks"))
import ra2_tasks  # noqa: E402

LOCK = threading.Lock()
AGENTS = {
    "haiku0": {"model": "haiku", "env": {"MAX_THINKING_TOKENS": "0"}},
    "sonnet": {"model": "sonnet", "env": {}},
}
NEEDS_EKBASIS = {"guard", "guard_goal", "guard_alt", "ask_ekbasis"}
SPEND = os.path.join(R2, "spend.jsonl")
CTX_DIR = os.path.join(R2, "logs", "run_ctx")
SESS = os.path.join(R2, "results", "sessions")
NC_LOCK = os.path.join(RA, "logs", "locks", "nextcloud.lock")  # shared with RA on purpose (same Nextcloud, SQLite)
LIMIT = [False]


def api_error(path):
    """The agent's own API failure (HTTP 429 usage limit, overload...), read from its result event; None if it really ran."""
    res = None
    if os.path.exists(path):
        for line in open(path):
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if e.get("type") == "result":
                res = e
    if res is None:
        return "no result event"
    txt = (res.get("result") or "").lower()
    if res.get("api_error_status") or "session limit" in txt or "rate limit" in txt or "usage limit" in txt:
        return f"{res.get('api_error_status')} {(res.get('result') or '')[:80]}"
    return None


def transcript_stats(path):
    cost = turns = model = None
    calls = []
    if os.path.exists(path):
        for line in open(path):
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if e.get("type") == "system" and e.get("subtype") == "init":
                model = e.get("model")
            if e.get("type") == "result":
                cost, turns = e.get("total_cost_usd"), e.get("num_turns")
            if e.get("type") == "assistant":
                for c in e.get("message", {}).get("content", []):
                    if c.get("type") == "tool_use":
                        calls.append(c["name"].split("__")[-1])
    return cost, turns, model, calls


def session_summary(path):
    if not os.path.exists(path):
        return {}
    d = json.load(open(path))
    beats = d.get("beats", [])
    checks = []
    for c in d.get("foresee_calls", []):
        sp = c.get("spec") or {}
        checks.append({"label": sp.get("label"), "action_type": sp.get("action_type"), "mode": c.get("mode"), "silent": bool(c.get("silent")),
                       "kind": c.get("kind"), "flagged": c.get("flagged"), "safe": c.get("safe"), "user": c.get("user"), "ms": c.get("ms")})
    uq = d.get("user_questions", [])
    acts = [{"kind": b["kind"], "name": (b.get("name") or b.get("text") or b.get("url") or "")[:80]} for b in beats if b["kind"] in ("click", "type", "select", "press", "goto")]
    return {"checks": checks, "n_checks": len(checks), "n_pauses": len(d.get("pauses", [])), "n_user_q": len(uq),
            "n_user_needless": sum(1 for q in uq if not q.get("concern")), "n_suggest": sum(1 for c in checks if c.get("kind") == "suggest"),
            "user_q": [{"label": q.get("label"), "concern": q.get("concern"), "answer": q.get("answer")[:120]} for q in uq],
            "actions": acts, "n_actions": len(acts),
            "foresee_errors": sum(1 for b in beats if b["kind"] == "foresee_error"),
            "done": next((b.get("text") for b in beats if b["kind"] == "done"), None)}


class AppLock:
    def __init__(self, app):
        self.app, self.f = app, None

    def __enter__(self):
        if self.app == "nextcloud":
            import fcntl
            os.makedirs(os.path.dirname(NC_LOCK), exist_ok=True)
            self.f = open(NC_LOCK, "w")
            fcntl.flock(self.f, fcntl.LOCK_EX)
        return self

    def __exit__(self, *a):
        if self.f:
            import fcntl
            fcntl.flock(self.f, fcntl.LOCK_UN)
            self.f.close()


def one(task, cond, seed, agent, prefix, out_path, spent):
    with AppLock(task["app"]):
        return _one(task, cond, seed, agent, prefix, out_path, spent)


def _one(task, cond, seed, agent, prefix, out_path, spent):
    rid = f"r{prefix}{os.urandom(3).hex()}"
    t0 = time.time()
    row = {"id": task["id"], "app": task["app"], "kind": task["kind"], "family": task["family"], "new_family": task.get("new_family", False),
           "conflict": task.get("conflict", False), "cond": cond, "seed": seed, "agent": agent, "rid": rid}
    ctx = None
    try:
        ctx = task["seed"](rid, CTX_DIR)
        ctx.update({"task": task["task"], "task_id": task["id"], "intent": task["intent"]})
        cpath = os.path.join(CTX_DIR, f"run_{rid}.json")
        json.dump(ctx, open(cpath, "w"))
        out = os.path.join(SESS, prefix, f"{task['id']}_{cond}_s{seed}_{rid}")
        a = AGENTS[agent]
        p = subprocess.run(["bash", os.path.join(HERE, "run_agent_ra2.sh"), cpath, out, cond, a["model"]], capture_output=True, text=True,
                           env=dict(os.environ, MAXT=os.environ.get("MAXT", "40"), **a["env"]), timeout=1800)
        row["agent_exit"] = p.stdout.strip().splitlines()[:1]
        api_err = api_error(out + ".agent.jsonl")
        if api_err:  # the agent never acted (e.g. the plan's usage limit): not a result, run it again later
            LIMIT[0] = True
            raise RuntimeError(f"agent API error, not a run: {api_err}")
        time.sleep(2)
        row.update(ra2_tasks.score(task, ctx))
        cost, turns, model, calls = transcript_stats(out + ".agent.jsonl")
        row.update({"cost_usd": cost, "turns": turns, "model_id": model, "tool_calls": len(calls)})
        row.update(session_summary(out + ".session.json"))
    except Exception as e:  # noqa: BLE001
        row.update({"harm": None, "success": None, "blocked": None, "error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()[-600:]})
    finally:
        if ctx:
            try:  # the run's own objects go away once judged, so later runs never see them
                ra2_tasks.cleanup_run(ctx)
            except Exception as e:  # noqa: BLE001
                row["cleanup_error"] = str(e)[:200]
    row["seconds"] = round(time.time() - t0, 1)
    with LOCK:
        with open(out_path, "a") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        c = row.get("cost_usd") or 0
        spent[0] += c
        with open(SPEND, "a") as f:
            f.write(json.dumps({"time": time.time(), "prefix": prefix, "rid": rid, "id": task["id"], "cond": cond, "agent": agent, "total_usd": round(c, 5)}) + "\n")
    print(f"{task['id']:16s} {cond:11s} s{seed} {agent:6s} harm={row.get('harm')} success={row.get('success')} userQ={row.get('n_user_q')} "
          f"pauses={row.get('n_pauses')} ${row.get('cost_usd')} {row['seconds']:.0f}s {('ERR ' + row['error'][:120]) if row.get('error') else ''} (spent ${spent[0]:.2f})", flush=True)
    return row


def ekbasis_up():
    import urllib.request
    try:
        return bool(json.load(urllib.request.urlopen("http://127.0.0.1:8791/health", timeout=20)).get("ok"))
    except Exception:  # noqa: BLE001
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", required=True, choices=list(AGENTS))
    ap.add_argument("--conds", nargs="+", required=True)
    ap.add_argument("--seeds", type=int, nargs="+", default=[1])
    ap.add_argument("--parallel", type=int, default=3)
    ap.add_argument("--cap", type=float, default=25.0, help="stop scheduling when the TOTAL RA2 spend (spend.jsonl) reaches this")
    ap.add_argument("--only", default="")
    ap.add_argument("--prefix", required=True)
    ap.add_argument("--tasks", default="frozen", help="'frozen' = tasks/frozen_tasks.json (the verified set), or 'all'")
    a = ap.parse_args()
    tasks = ra2_tasks.TASKS
    if a.tasks == "frozen":
        keep = set(json.load(open(os.path.join(R2, "tasks", "frozen_tasks.json")))["ids"])
        tasks = [t for t in tasks if t["id"] in keep]
    if a.only:
        sel = set(a.only.split(","))
        tasks = [t for t in tasks if t["id"] in sel]
    os.makedirs(CTX_DIR, exist_ok=True)
    os.makedirs(os.path.join(SESS, a.prefix), exist_ok=True)
    out_path = os.path.join(R2, "results", f"runs_{a.prefix}.jsonl")
    done = set()
    if os.path.exists(out_path):
        for l in open(out_path):
            r = json.loads(l)
            if r.get("harm") is not None and not r.get("foresee_errors"):
                done.add((r["id"], r["cond"], r["seed"], r["agent"]))
    spent = [0.0]
    if os.path.exists(SPEND):
        for l in open(SPEND):
            spent[0] += json.loads(l).get("total_usd") or 0
    jobs = [(t, c, s) for t in tasks for c in a.conds for s in a.seeds if (t["id"], c, s, a.agent) not in done]
    random.Random(20261007).shuffle(jobs)
    print(f"{len(jobs)} runs to do ({a.agent}, {a.conds}, seeds {a.seeds}), {len(done)} already done, RA2 spend so far ${spent[0]:.2f}, cap ${a.cap}", flush=True)
    with cf.ThreadPoolExecutor(a.parallel) as ex:
        futs = []
        for t, c, s in jobs:
            while len([f for f in futs if not f.done()]) >= a.parallel:
                time.sleep(1)
            if spent[0] >= a.cap:
                print(f"cap reached (${spent[0]:.2f}); not scheduling more runs", flush=True)
                break
            if LIMIT[0]:
                print("agent usage limit hit (HTTP 429): pausing here (resumable)", flush=True)
                break
            if c in NEEDS_EKBASIS and not ekbasis_up():
                print("Ekbasis bridge is down: pausing here (resumable)", flush=True)
                break
            futs.append(ex.submit(one, t, c, s, a.agent, a.prefix, out_path, spent))
        for f in futs:
            f.result()
    print(f"finished; RA2 spend ${spent[0]:.2f}", flush=True)


if __name__ == "__main__":
    main()
