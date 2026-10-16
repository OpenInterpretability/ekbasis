"""NOT THE PUBLISHED MEASUREMENT. P12's preflight check is not runnable as published: its 141 plans are rebuilt by
mission/MAC/t3/plans.py with plan_line() from the snapshots taken before each command ran (/private/tmp/ekb_pc_94332945,
/private/tmp/ekb_pc2_94332945), and those folders are now empty (their directories remain, 0 files). This substitute,
reported apart from P12:
- the 423 requests client 0.1.6's model path sends for those 141 plans, recorded on 7 Oct on the snapshots with a
  stand-in client (MAC/t3/data/requests_016.jsonl; for shell plans check_plan(copy=False, why=False) sends one request
  with every step plus one per prefix whatever the answers are: preflight.py 0.1.6 lines 1688-1703), sent unchanged
  (the client's body: {"state", "questions"}) to the served model;
- preflight's arithmetic on the answers (preflight.py 0.1.6, _model_shell and check_plan lines 1762-1765): P(fail) per
  step = max(full prompt, prefix), steps decided by code (by_code, deterministic, from the bf16 record) = 1.0, P(any),
  first = the first step >= 0.5, else the most likely one when P(any) >= 0.5;
- the verdict (warn) also needs half_applied(plan, first), i.e. the plan's step effects, which are gone with the
  snapshots: it is set only where that step's verdict is already known (no failing step: allow; the step the bf16 or
  the MLX run flagged: that run's verdict), else "undetermined".
The fingerprint salts are the recording's (every check draws new ones; the bf16 run had its own).
  python3 replay_requests.py <api url> <out.jsonl>"""
import json
import math
import pathlib
import sys
import urllib.request

REF = pathlib.Path(__file__).resolve().parents[2] / "ref" / "preflight"
URL, OUT = sys.argv[1].rstrip("/"), sys.argv[2]
L = lambda p: [json.loads(x) for x in open(p)]


def ask(body):
    req = urllib.request.Request(f"{URL}/v1/systemone", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=900))["answers"]


known = {}   # (sid, tool_use_id) -> {first step: risky} from the bf16 and MLX runs
for r in L(REF / "shadow_confirm.jsonl"):
    if (r.get("model") or {}).get("risky") is not None:
        known.setdefault((r["sid"], r["tool_use_id"]), {})[r["model"]["first"]] = r["model"]["risky"]
for r in L(REF / "replay_dev_study1.jsonl"):
    if r.get("by") == "model":
        known.setdefault((r["sid"], r["tool_use_id"]), {})[r["first"]] = r["risky"]
by_code = {(r["sid"], r["tool_use_id"]): r["by_code"] for r in L(REF / "mlx_a.jsonl")}   # code facts: the same for any model
for r in L(REF / "mlx_a.jsonl"):
    known.setdefault((r["sid"], r["tool_use_id"]), {}).setdefault(r["first"], r["risky"])
with open(OUT, "w") as f:
    for rec in L(REF / "requests_016.jsonl"):
        k, n, reqs = (rec["sid"], rec["tool_use_id"]), len(rec["steps"]), rec["requests"]
        full = ask(reqs[0])
        p = [float(full[f"f{j}"]["probability"]) for j in range(1, n + 1)]
        walk = [0.0] + [float(ask(q)["f"]["probability"]) for q in reqs[1:n]]
        p = [max(x, y) for x, y in zip(p, walk)]
        for j in by_code[k]:
            p[j - 1] = 1.0
        p_any = 1 - math.prod(1 - x for x in p)
        first = next((j for j, x in enumerate(p, 1) if x >= 0.5), None)
        if first is None and p_any >= 0.5:
            first = max(range(1, n + 1), key=lambda j: p[j - 1])
        risky = False if first is None else known.get(k, {}).get(first, "undetermined")
        if len(reqs) > n:  # a sqlite3 call inside the chain (1 plan): its SQL requests are not replayed
            risky = "undetermined"
        f.write(json.dumps({"study": rec["study"], "sid": k[0], "tool_use_id": k[1], "p_fail": [round(x, 4) for x in p],
                            "p_lost": round(float(full["lost"]["probability"]), 4), "first": first, "risky": risky,
                            "extra_requests_not_replayed": len(reqs) - n}) + "\n")
print("done", OUT)
