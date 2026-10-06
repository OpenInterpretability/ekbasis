"""WS-RA study runner (port of mission/X/agent/run_study.py): every task x condition x seed for one agent. For each run a
fresh world is seeded through the app's API (tasks/ra_tasks.py), the agent works through run_agent_ra.sh (Claude Code,
web tools only) or run_agent_ra_qwen.sh (opencode + Qwen 3.5 9B), and the run is judged at once from the app's own state
and appended to results/runs_<prefix>.jsonl, so the study can stop and resume. Runs go in a fixed shuffled order, a few
in parallel. Stops scheduling once the logged Claude spend (agent + oracle) reaches the cap; every run's spend also goes
to RA/spend.jsonl.
    python3 run_study_ra.py --agent haiku0 --conds blind see --prefix h --parallel 3 --cap 6 [--only id1,id2] [--seeds 1]"""
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
RA = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(RA, "tasks"))
import ra_tasks  # noqa: E402
sys.path.insert(0, os.path.join(RA, "apps"))
import cleanup  # noqa: E402

LOCK = threading.Lock()
AGENTS = {
    "haiku0": {"runner": "claude", "model": "haiku", "env": {"MAX_THINKING_TOKENS": "0"}},
    "sonnet": {"runner": "claude", "model": "sonnet", "env": {}},
    "qwen9b": {"runner": "qwen", "model": "qwen35-9b", "env": {"QWEN_BASEURL": "http://127.0.0.1:18595/v1", "QWEN_MODEL": "qwen35-9b", "QWEN_NAME": "Qwen3.5-9B"}},
    "qwen4b": {"runner": "qwen", "model": "qwen35-4b", "env": {"QWEN_BASEURL": "http://127.0.0.1:18596/v1", "QWEN_MODEL": "qwen35-4b", "QWEN_NAME": "Qwen3.5-4B"}},
}
SPEND = os.path.join(RA, "spend.jsonl")
CTX_DIR = os.path.join(RA, "logs", "run_ctx")
SESS = os.path.join(RA, "results", "sessions")

DEFECT_NOQ = "iterable argument is empty"  # known adapter defect (addendum H): a file described as an empty folder -> a spec with no questions


def infra_foresee_errors(row, ra_dir=None):
    """Ekbasis failures in a run's session that come from an outage, i.e. not from the known no-questions defect."""
    import glob as _g
    n = row.get("foresee_errors") or 0
    if not n:
        return 0
    f = _g.glob(os.path.join(ra_dir or RA, "results", "sessions", row.get("prefix") or "*", f"*_{row['rid']}.session.json"))
    if not f:
        return n
    beats = json.load(open(f[0])).get("beats", [])
    return sum(1 for b in beats if b.get("kind") == "foresee_error" and DEFECT_NOQ not in (b.get("error") or ""))


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
        return None
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
    huds = []
    for c in d.get("foresee_calls", []):
        sp = c.get("spec") or {}
        ans = c.get("answers") or {}
        lines = []
        for q in sp.get("questions", []):
            a = ans.get(q["key"])
            if a:
                lines.append([q["key"], str(a["value"]), round(a["confidence"], 4), str(a["value"]) == str(q.get("bad"))])
        huds.append({"el": c.get("el"), "name": (c.get("name") or "")[:80], "action_type": sp.get("action_type"), "label": sp.get("label"),
                     "mode": c.get("mode"), "lines": lines, "ms": c.get("ms"), "model_ms": c.get("model_ms"), "none": not sp})
    acts = [{"kind": b["kind"], "name": (b.get("name") or b.get("text") or b.get("url") or "")[:80]} for b in beats if b["kind"] in ("click", "type", "select", "press", "goto")]
    oracle = round(sum((c.get("cost_usd") or 0) for c in d.get("foresee_calls", [])), 5)
    return {"huds": huds, "actions": acts, "n_actions": len(acts), "oracle_cost_usd": oracle,
            "foresee_errors": sum(1 for b in beats if b["kind"] == "foresee_error"),
            "defect_noquestions": sum(1 for b in beats if b["kind"] == "foresee_error" and DEFECT_NOQ in (b.get("error") or "")),
            "done": next((b.get("text") for b in beats if b["kind"] == "done"), None)}


LOCKS = os.path.join(RA, "logs", "locks")


class AppLock:
    """Nextcloud runs on SQLite: two runs writing at once (seeding, the agent's own actions) can hit a locked database.
    So at most one Nextcloud run at a time, across every runner process (addendum D). Other apps run in parallel."""
    def __init__(self, app):
        self.app = app
        self.f = None

    def __enter__(self):
        if self.app == "nextcloud":
            import fcntl
            os.makedirs(LOCKS, exist_ok=True)
            self.f = open(os.path.join(LOCKS, "nextcloud.lock"), "w")
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
    rid = f"{prefix}{os.urandom(3).hex()}"
    t0 = time.time()
    row = {"id": task["id"], "app": task["app"], "kind": task["kind"], "family": task["family"], "cond": cond, "seed": seed, "agent": agent, "rid": rid}
    try:
        ctx = task["seed"](rid, CTX_DIR)
        ctx["task"] = task["task"]
        ctx["task_id"] = task["id"]
        cpath = os.path.join(CTX_DIR, f"run_{rid}.json")
        json.dump(ctx, open(cpath, "w"))
        out = os.path.join(SESS, prefix, f"{task['id']}_{cond}_s{seed}_{rid}")
        a = AGENTS[agent]
        if a["runner"] == "claude":
            cmd = ["bash", os.path.join(HERE, "run_agent_ra.sh"), cpath, out, cond, a["model"]]
        else:
            cmd = ["bash", os.path.join(HERE, "run_agent_ra_qwen.sh"), cpath, out, cond]
        p = subprocess.run(cmd, capture_output=True, text=True, env=dict(os.environ, MAXT=os.environ.get("MAXT", "40"), **a["env"]), timeout=1800)
        row["agent_exit"] = p.stdout.strip().splitlines()[:1]
        time.sleep(2)
        row.update(ra_tasks.score(task, ctx))
        cost, turns, model, calls = transcript_stats(out + ".agent.jsonl")
        api_err = api_error(out + ".agent.jsonl")
        if api_err:  # the agent never acted (e.g. the plan's usage limit): not a result, run it again later
            LIMIT[0] = True
            raise RuntimeError(f"agent API error, not a run: {api_err}")
        row.update({"cost_usd": cost, "turns": turns, "model_id": model, "tool_calls": len(calls), "foresee_calls": calls.count("foresee")})
        row.update(session_summary(out + ".session.json"))
        if a["runner"] == "qwen":
            row["foresee_calls"] = sum(1 for h in row.get("huds", []))
        try:  # the run's own objects go away once judged, so later runs never see them (addendum C)
            cleanup.run(ctx)
        except Exception as e:  # noqa: BLE001
            row["cleanup_error"] = str(e)[:200]
    except Exception as e:  # noqa: BLE001
        row.update({"harm": None, "success": None, "blocked": None, "error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()[-600:]})
    row["seconds"] = round(time.time() - t0, 1)
    with LOCK:
        with open(out_path, "a") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        c = (row.get("cost_usd") or 0) + (row.get("oracle_cost_usd") or 0)
        spent[0] += c
        with open(SPEND, "a") as f:
            f.write(json.dumps({"time": time.time(), "prefix": prefix, "rid": rid, "id": task["id"], "cond": cond, "agent": agent,
                                "agent_usd": row.get("cost_usd"), "oracle_usd": row.get("oracle_cost_usd"), "total_usd": round(c, 5)}) + "\n")
    print(f"{task['id']:16s} {cond:10s} s{seed} {agent:6s} harm={row.get('harm')} success={row.get('success')} foresee={row.get('foresee_calls')} "
          f"${row.get('cost_usd')} {row['seconds']:.0f}s {('ERR ' + row['error'][:120]) if row.get('error') else ''} (spent ${spent[0]:.2f})", flush=True)
    return row


def ekbasis_up():
    import urllib.request
    try:
        return bool(json.load(urllib.request.urlopen("http://127.0.0.1:8781/health", timeout=20)).get("ok"))
    except Exception:  # noqa: BLE001
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", required=True, choices=list(AGENTS))
    ap.add_argument("--conds", nargs="+", default=["blind", "see"])
    ap.add_argument("--seeds", type=int, nargs="+", default=[1])
    ap.add_argument("--parallel", type=int, default=3)
    ap.add_argument("--cap", type=float, default=40.0, help="stop scheduling when the TOTAL RA spend (spend.jsonl, all prefixes) reaches this (safety stop, addendum E)")
    ap.add_argument("--only", default="")
    ap.add_argument("--prefix", required=True)
    ap.add_argument("--tasks", default="frozen", help="'frozen' = tasks/frozen_tasks.json (verified set), 'harm' = its 24 harm tasks, or 'all'")
    a = ap.parse_args()
    tasks = ra_tasks.TASKS
    if a.tasks in ("frozen", "harm"):
        fz = json.load(open(os.path.join(RA, "tasks", "frozen_tasks.json")))
        keep = set(fz["ids"] if a.tasks == "frozen" else fz["harm"])
        tasks = [t for t in tasks if t["id"] in keep]
    if a.only:
        sel = set(a.only.split(","))
        tasks = [t for t in tasks if t["id"] in sel]
    os.makedirs(CTX_DIR, exist_ok=True)
    os.makedirs(os.path.join(SESS, a.prefix), exist_ok=True)
    out_path = os.path.join(RA, "results", f"runs_{a.prefix}.jsonl")
    done = set()
    ab = os.path.join(RA, "results", "infra_aborted.json")
    aborted = set(json.load(open(ab))["rids"]) if os.path.exists(ab) else set()
    if os.path.exists(out_path):
        for l in open(out_path):
            r = json.loads(l)
            # a run cut by an outage (Ekbasis failure logged, or listed as infra-aborted) is not done: it is run again
            r.setdefault("prefix", a.prefix)
            if r.get("harm") is not None and not infra_foresee_errors(r) and r["rid"] not in aborted:
                done.add((r["id"], r["cond"], r["seed"]))
    spent = [0.0]
    if os.path.exists(SPEND):
        for l in open(SPEND):
            spent[0] += json.loads(l).get("total_usd") or 0
    jobs = [(t, c, s) for t in tasks for c in a.conds for s in a.seeds if (t["id"], c, s) not in done]
    random.Random(20261006).shuffle(jobs)
    needs_ekbasis = [c for c in a.conds if c in ("see", "guard", "guard_goal")]
    print(f"{len(jobs)} runs to do ({a.agent}, {a.conds}, seeds {a.seeds}), {len(done)} already done, RA spend so far ${spent[0]:.2f}, cap ${a.cap}", flush=True)
    with cf.ThreadPoolExecutor(a.parallel) as ex:
        futs = []
        for t, c, s in jobs:
            while len([f for f in futs if not f.done()]) >= a.parallel:
                time.sleep(1)
            if spent[0] >= a.cap:
                print(f"cap reached (${spent[0]:.2f}); not scheduling more runs", flush=True)
                break
            if LIMIT[0]:
                print("agent usage limit hit (HTTP 429): pausing here (resumable; nothing else scheduled in this step)", flush=True)
                break
            if c not in needs_ekbasis and os.path.exists(os.path.join(RA, "logs", "pause_nonekbasis")):
                print("paused: the Ekbasis window is open and its runs go first (logs/pause_nonekbasis); resumable", flush=True)
                break
            if c in needs_ekbasis and not ekbasis_up():
                print("Ekbasis replica is down: pausing here (resumable; nothing else scheduled in this step)", flush=True)
                break
            futs.append(ex.submit(one, t, c, s, a.agent, a.prefix, out_path, spent))
        for f in futs:
            f.result()
    print(f"finished; RA spend ${spent[0]:.2f}", flush=True)


if __name__ == "__main__":
    main()
