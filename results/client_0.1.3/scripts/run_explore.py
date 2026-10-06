"""E2 (exploratory, see ../SPEC.md): Claude Haiku 4.5 on the 4 tempting tasks, H and C, 3 rounds, same harness.

usage: python3 run_explore.py      (sessions x<round>_<k>_<task>_<arm>; results in results/sessions_explore/)
"""
from __future__ import annotations

import concurrent.futures as cf
import json
import os
import random
import shutil
import traceback

from common import RESULTS, d, ledger_spent
import replay as RP
import run_session as RS
import run_study as RSY
import tasks as T

from common import BUDGET, HAIKU_CAP  # noqa: E402

MODEL, CAP, STOP_AT, SEED = "haiku", HAIKU_CAP, BUDGET, 77012611
TEMPTING = [t.id for t in T.TASKS if t.tempting]


def keep(sid):
    dst = os.path.join(RESULTS, "sessions_explore", sid)
    os.makedirs(dst, exist_ok=True)
    for f in ("session.json", "events.jsonl", "calls.jsonl", "stream.jsonl", "claude.err"):
        if os.path.exists(d("logs", sid, f)):
            shutil.copy(d("logs", sid, f), os.path.join(dst, f))


def pair(rnd, k, tid):
    sids = {arm: f"y{rnd}_{k:02d}_{tid}_{arm}" for arm in ("H", "C")}   # y: Haiku, 0.1.3 re-run
    RSY.log({"event": "e2_pair_start", "round": rnd, "task": tid, "sids": sids, "spent": ledger_spent()})
    outs = {}
    with cf.ThreadPoolExecutor(2) as ex:
        futs = {arm: ex.submit(RS.run_session, tid, arm, sids[arm], CAP, MODEL) for arm in sids}
        for arm, f in futs.items():
            try:
                outs[arm] = f.result()
            except Exception as e:  # noqa: BLE001
                outs[arm] = {"error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()[-1500:]}
    for arm, sid in sids.items():
        if "error" not in outs[arm]:
            try:
                RP.process(sid)
            except Exception as e:  # noqa: BLE001
                RSY.log({"event": "replay_error", "sid": sid, "error": f"{type(e).__name__}: {e}"})
            keep(sid)
    RSY.log({"event": "e2_pair_done", "round": rnd, "task": tid, "spent": ledger_spent(),
             "summary": {a: {x: o.get(x) for x in ("usd", "bash_calls", "asks", "error")} |
                         {"done": (o.get("check") or {}).get("done"), "preserved": (o.get("preserved") or {}).get("share")}
                         for a, o in outs.items()}})


def main():
    RS.install_bin()
    RS.agent_profile()
    plan = []
    for rnd in (1, 2, 3):
        ids = list(TEMPTING)
        random.Random(SEED + rnd).shuffle(ids)
        plan += [(rnd, k, tid) for k, tid in enumerate(ids, 1)]
    pending = set()
    with cf.ThreadPoolExecutor(2) as pool:
        for rnd, k, tid in plan:
            while len(pending) >= 2:
                fin, pending = cf.wait(pending, return_when=cf.FIRST_COMPLETED)
            if ledger_spent() + (len(pending) + 1) * 2 * CAP > STOP_AT:
                RSY.log({"event": "e2_stop", "why": "budget", "spent": ledger_spent()})
                break
            if not RSY.ensure_tunnel():
                RSY.log({"event": "e2_stop", "why": "tunnel down"})
                break
            pending.add(pool.submit(pair, rnd, k, tid))
        cf.wait(pending)
    RSY.log({"event": "e2_end", "spent": ledger_spent()})


if __name__ == "__main__":
    main()
