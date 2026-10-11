#!/usr/bin/env python3
"""Addendum 2: sends calls_pub.jsonl (to answers_pub.jsonl), two questions per request (p, p_as_asked). Otherwise run_calls.py of the main study.

Sends calls.jsonl to the hosted API, one request at a time (PREREG.md), and appends one row per call to
answers.jsonl: call, item, set, stratum, label, format, attack, p (P(yes) = follows a third party), input tokens,
Server-Timing (queue, model), wall seconds, error. Resumable (calls already written are skipped); one retry after
10 s on an error; stops at the token cap.
    EKBASIS_URL=https://openinterp.org/api/v1 EKBASIS_API_KEY=... python3 run_calls.py
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
from ekbasis.client import CannotJudge, Ekbasis  # noqa: E402

TOKEN_CAP = 1_600_000
OUT = os.path.join(HERE, "answers_pub.jsonl")


def main():
    calls = [json.loads(l) for l in open(os.path.join(HERE, "calls_pub.jsonl"))]
    done, tokens = set(), 0
    if os.path.exists(OUT):
        for l in open(OUT):
            r = json.loads(l)
            done.add(r["call"])
            tokens += r.get("input_tokens") or 0
    client = Ekbasis(timeout=180, surface="intent-check-study")
    print(f"{len(calls)} calls, {len(done)} done, {tokens} tokens so far", flush=True)
    with open(OUT, "a") as f:
        for c in calls:
            if c["call"] in done:
                continue
            if tokens >= TOKEN_CAP:
                print("token cap reached", flush=True)
                break
            row = {k: c[k] for k in ("call", "item", "set", "stratum", "label", "format", "attack", "cluster", "variant")}
            for attempt in range(2):
                t0 = time.time()
                try:
                    raw = client._call("/v1/systemone", {"state": c["state"], "questions": c["questions"]})
                    a = raw["answers"]["third_party"]
                    row.update(p=float(a["probability"]), p_as_asked=float(raw["answers"]["as_asked"]["probability"]), input_tokens=(raw.get("usage") or {}).get("input_tokens"),
                               timing=client.last_timing if hasattr(client, "last_timing") else {}, error=None)
                    break
                except (CannotJudge, KeyError, TypeError, ValueError) as e:
                    row.update(p=None, error=f"{type(e).__name__}: {str(e)[:200]}")
                    if attempt == 0:
                        time.sleep(10)
            row["seconds"] = round(time.time() - t0, 3)
            row["attempts"] = attempt + 1
            f.write(json.dumps(row) + "\n")
            f.flush()
            tokens += row.get("input_tokens") or 0
            if row["error"] or c["call"] % 50 == 0:
                print(c["call"], tokens, row.get("error") or "", flush=True)
    print(f"finished, tokens={tokens}", flush=True)


if __name__ == "__main__":
    main()
