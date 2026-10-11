#!/usr/bin/env python3
"""Runs the tool-guard pilot (PREREG.md) and writes raw_pass<N>.jsonl; analyze.py turns them into RESULTS.md.

    EKBASIS_URL=https://openinterp.org/api/v1 EKBASIS_API_KEY=... python3 run_pilot.py 1
    python3 run_pilot.py --offline     # H4 and H5 only (no model calls)

Nothing is executed: the scenarios are text, and the model is only asked what the call would do.
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from ekbasis import toolguard as T  # noqa: E402
from ekbasis.client import CannotJudge, Ekbasis  # noqa: E402


class Metered(Ekbasis):
    """Keeps the usage and the wall-clock time of the last request."""

    def _call(self, path, body=None):
        t0 = time.monotonic()
        out = super()._call(path, body)
        self.last = {"usage": out.get("usage"), "latency_s": time.monotonic() - t0, "server_latency_s": out.get("latency_s")}
        return out


def scenarios():
    return [json.loads(l) for l in open(os.path.join(HERE, "scenarios.jsonl")) if l.strip()]


def offline():
    rows = []
    for r in scenarios():
        st = T.build_state(r["tool"], r["input"], r["events"], r["description"])
        rows.append({"id": r["id"], "condition": r["condition"], "state_chars": len(st),
                     "raw_chars": sum(len(json.dumps(e)) for e in r["events"]),
                     "fact_in_state": (r["fact"] in st) if r["fact"] else None})
    names = json.load(open(os.path.join(HERE, "readonly_names.json")))["items"]
    ro = [{"name": it[0], "input": it[2] if len(it) > 2 else {}, "label_read_only": it[1],
           "classed_read_only": bool(T.read_only(it[0], it[2] if len(it) > 2 else {}))} for it in names]
    return rows, ro


def run(n: int):
    client = Metered(surface="toolguard-pilot", timeout=60)
    out = open(os.path.join(HERE, f"raw_pass{n}.jsonl"), "w")
    for r in scenarios():
        rec = {"id": r["id"], "family": r["family"], "condition": r["condition"]}
        try:
            v = T.check(r["tool"], r["input"], r["events"], description=r["description"], client=client)
            rec.update(verdict=v.verdict, p=v.p, reasons=v.reasons, state_chars=len(v.state), state=v.state,
                       **client.last)
        except CannotJudge as e:
            rec.update(verdict="cannot_foresee", error=str(e))
        out.write(json.dumps(rec) + "\n")
        out.flush()
        print(f"{r['id']:34s} {rec['verdict']:15s} " + " ".join(f"{k}={v:.2f}" for k, v in rec.get("p", {}).items()))


if __name__ == "__main__":
    if sys.argv[1:] == ["--offline"]:
        rows, ro = offline()
        json.dump({"states": rows, "read_only": ro}, open(os.path.join(HERE, "offline.json"), "w"), indent=1)
        print(sum(r["fact_in_state"] is True for r in rows), "facts quoted;", max(r["state_chars"] for r in rows), "max chars")
    else:
        run(int(sys.argv[1]))
