#!/usr/bin/env python3
"""Re-asks the requests of a raw file that failed (server error: recorded as cannot_foresee with `error`), with the
same questions, and writes them back in place; the failed attempt is kept in `failed_attempts`.

    python3 retry_failed.py raw_v1_holdout.jsonl holdout.jsonl v1
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from ekbasis import toolguard as T  # noqa: E402
from run_pilot import Metered  # noqa: E402
from run_v2 import V1, V2  # noqa: E402

raw, src, arm = sys.argv[1:4]
T.HARMS.clear()
T.HARMS.update(V1 if arm == "v1" else V2)
scen = {json.loads(l)["id"]: json.loads(l) for l in open(os.path.join(HERE, src))}
rows = [json.loads(l) for l in open(os.path.join(HERE, raw))]
client = Metered(surface="toolguard-pilot", timeout=60)
for i, rec in enumerate(rows):
    if "error" not in rec:
        continue
    r = scen[rec["id"]]
    v = T.check(r["tool"], r["input"], r["events"], description=r["description"], client=client)
    rows[i] = {"id": r["id"], "family": r["family"], "condition": r["condition"], "verdict": v.verdict, "p": v.p,
               "state_chars": len(v.state), "state": v.state, **client.last,
               "failed_attempts": rec.get("failed_attempts", []) + [rec["error"]]}
    print(rec["id"], v.verdict)
with open(os.path.join(HERE, raw), "w") as out:
    for rec in rows:
        out.write(json.dumps(rec) + "\n")
