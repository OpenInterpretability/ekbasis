#!/usr/bin/env python3
"""Pass 3 (PREREG_v2.md): the revised data_loss question (toolguard.HARMS) against the first wording
(toolguard.DATA_LOSS_V1) on the holdout, one request each; and, exploratory, the revised question on the 36 pilot
scenarios. Writes raw_v2_holdout.jsonl, raw_v1_holdout.jsonl, raw_v2_pilot.jsonl.

    EKBASIS_URL=https://openinterp.org/api/v1 EKBASIS_API_KEY=... python3 run_v2.py
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from ekbasis import toolguard as T  # noqa: E402
from ekbasis.client import CannotJudge  # noqa: E402
from run_pilot import Metered  # noqa: E402

V2 = dict(T.HARMS)
V1 = {**T.HARMS, "data_loss": T.DATA_LOSS_V1}


def run(src, dst, harms):
    client = Metered(surface="toolguard-pilot", timeout=60)
    T.HARMS.clear()
    T.HARMS.update(harms)
    with open(os.path.join(HERE, dst), "w") as out:
        for l in open(os.path.join(HERE, src)):
            r = json.loads(l)
            rec = {"id": r["id"], "family": r["family"], "condition": r["condition"]}
            try:
                v = T.check(r["tool"], r["input"], r["events"], description=r["description"], client=client)
                rec.update(verdict=v.verdict, p=v.p, state_chars=len(v.state), state=v.state, **client.last)
            except CannotJudge as e:
                rec.update(verdict="cannot_foresee", error=str(e))
            out.write(json.dumps(rec) + "\n")
            print(f"{dst:22s} {r['id']:30s} {rec['verdict']}")


if __name__ == "__main__":
    run("holdout.jsonl", "raw_v2_holdout.jsonl", V2)
    run("holdout.jsonl", "raw_v1_holdout.jsonl", V1)
    run("scenarios.jsonl", "raw_v2_pilot.jsonl", V2)
