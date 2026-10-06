"""Run the 0.1.3 re-run (see ../SPEC_ADDENDUM_013.md; ../SPEC.md, "Arms, order and budget"): rounds of the 12 tasks as
H/C pairs started together,
two pairs at a time, under the budget rule; after each pair, the truth/replay/shadow pass of its two sessions.

usage: python3 run_study.py [max_rounds]      (resumes: pairs already done are skipped)
"""
from __future__ import annotations

import concurrent.futures as cf
import json
import os
import random
import shutil
import subprocess
import sys
import threading
import time
import traceback
import urllib.request

from common import (BUDGET, ORDER_SEED, RESULTS, SESSION_CAP, TUNNEL_URL, W, d, ledger_spent, read_jsonl)
import replay as RP
import run_session as RS
import tasks as T

PAIRS_AT_ONCE = 2
LOG = os.path.join(RESULTS, "study_log.jsonl")
_lock = threading.Lock()


def log(rec):
    with _lock, open(LOG, "a") as fh:
        fh.write(json.dumps({"t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **rec}) + "\n")


def order(rnd):
    ids = [t.id for t in T.TASKS]
    random.Random(ORDER_SEED + rnd).shuffle(ids)
    return ids


def tunnel_ok() -> bool:
    try:
        with urllib.request.urlopen(TUNNEL_URL + "/health", timeout=10) as r:
            return json.loads(r.read()).get("ok") is True
    except (OSError, ValueError):
        return False


def ensure_tunnel() -> bool:
    if tunnel_ok():
        return True
    p = subprocess.Popen(["ssh", "-N", "-o", "ConnectTimeout=20", "-o", "ServerAliveInterval=30", "-o",
                          "ExitOnForwardFailure=yes", "-L", os.environ.get("EKB_RT_TUNNEL_FORWARD", "18642:127.0.0.1:8542"),
                          *os.environ.get("EKB_RT_TUNNEL_SSH", "-p 22 user@ekbasis-host").split()], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
    with open(d("tunnel.pid"), "w") as fh:
        fh.write(str(p.pid))
    for _ in range(30):
        time.sleep(1)
        if tunnel_ok():
            log({"event": "tunnel_restarted", "pid": p.pid})
            return True
    return False


def keep_results(sid):
    dst = os.path.join(RESULTS, "sessions", sid)
    os.makedirs(dst, exist_ok=True)
    for f in ("session.json", "events.jsonl", "calls.jsonl", "stream.jsonl", "claude.err"):
        src = d("logs", sid, f)
        if os.path.exists(src):
            shutil.copy(src, os.path.join(dst, f))


def run_pair(rnd, k, tid):
    sids = {arm: f"s{rnd}_{k:02d}_{tid}_{arm}" for arm in ("H", "C")}   # s: Sonnet, 0.1.3 re-run
    log({"event": "pair_start", "round": rnd, "k": k, "task": tid, "sids": sids, "spent": ledger_spent()})
    outs = {}
    with cf.ThreadPoolExecutor(2) as ex:
        futs = {arm: ex.submit(RS.run_session, tid, arm, sids[arm], SESSION_CAP) for arm in ("H", "C")}
        for arm, f in futs.items():
            try:
                outs[arm] = f.result()
            except Exception as e:  # noqa: BLE001
                outs[arm] = {"error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()[-2000:]}
    for arm in ("H", "C"):
        if "error" not in outs[arm]:
            try:
                RP.process(sids[arm])
            except Exception as e:  # noqa: BLE001
                log({"event": "replay_error", "sid": sids[arm], "error": f"{type(e).__name__}: {e}",
                     "trace": traceback.format_exc()[-2000:]})
            keep_results(sids[arm])
    log({"event": "pair_done", "round": rnd, "k": k, "task": tid, "spent": ledger_spent(),
         "summary": {arm: ({x: outs[arm].get(x) for x in ("usd", "wall", "bash_calls", "asks", "cost_from_result")}
                           | {"done": (outs[arm].get("check") or {}).get("done")}) if "error" not in outs[arm]
                     else outs[arm] for arm in outs}})
    return outs


def main():
    max_rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    RS.install_bin()
    RS.agent_profile()
    done = {(r["round"], r["task"]) for r in read_jsonl(LOG) if r.get("event") == "pair_done"}
    plan = [(rnd, k, tid) for rnd in range(1, max_rounds + 1) for k, tid in enumerate(order(rnd), 1)
            if (rnd, tid) not in done]
    log({"event": "study_start", "pairs_planned": len(plan), "spent": ledger_spent()})
    no_result = [0]
    pending = {}
    with cf.ThreadPoolExecutor(PAIRS_AT_ONCE) as pool:
        for rnd, k, tid in plan:
            while len(pending) >= PAIRS_AT_ONCE:
                fin, _ = cf.wait(pending, return_when=cf.FIRST_COMPLETED)
                for f in fin:
                    outs = f.result()
                    for o in outs.values():
                        no_result[0] = 0 if o.get("cost_from_result") else no_result[0] + 1
                    del pending[f]
            if no_result[0] >= 2:
                log({"event": "study_stop", "why": "two sessions in a row ended with no result event"})
                break
            spent = ledger_spent()
            if spent + len(pending) * 2 * SESSION_CAP + 2 * SESSION_CAP > BUDGET:
                log({"event": "study_stop", "why": "budget", "spent": spent, "next": [rnd, k, tid]})
                break
            if not ensure_tunnel():
                log({"event": "study_stop", "why": "tunnel to the eval server is down"})
                break
            pending[pool.submit(run_pair, rnd, k, tid)] = (rnd, k, tid)
        cf.wait(pending)
    log({"event": "study_end", "spent": ledger_spent()})


if __name__ == "__main__":
    main()
