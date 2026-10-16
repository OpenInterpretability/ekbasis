"""P12 preflight SUBSTITUTE (see replay_requests.py: not the published measurement). Skopos against Ekbasis-27B on the
same 423 recorded requests, both served here (Ekbasis-27B re-run: the published bf16 verdicts used other salts), and
each against the recorded bf16 verdicts (shadow / replay_dev) and the truth of the 137 confirmation plans: first
flagged step and step-level P(fail) >= 0.5 agreement (computable for every plan); verdicts where determined.
  python3 compare.py --skopos <jsonl> --ekbasis <jsonl> --out <json>"""
import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "common"))
from paired import dump, paired, summary  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--skopos", required=True)
ap.add_argument("--ekbasis", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--note", action="append", default=[], help="run conditions to record (repeatable)")
a = ap.parse_args()
REF = HERE.parents[1] / "ref" / "preflight"
L = lambda p: [json.loads(x) for x in open(p)]
S = {(r["sid"], r["tool_use_id"]): r for r in L(a.skopos)}
E = {(r["sid"], r["tool_use_id"]): r for r in L(a.ekbasis)}
bf, truth = {}, {}
for r in L(REF / "shadow_confirm.jsonl"):
    if (r.get("model") or {}).get("risky") is not None:
        bf[(r["sid"], r["tool_use_id"])] = r["model"]
        truth[(r["sid"], r["tool_use_id"])] = r["truth"]
for r in L(REF / "replay_dev_study1.jsonl"):
    if r.get("by") == "model":
        bf[(r["sid"], r["tool_use_id"])] = {"risky": r["risky"], "first": r["first"]}
keys = sorted(bf)
assert set(S) == set(E) == set(keys) and len(keys) == 141
recs = [paired([S[k]["first"] == bf[k]["first"] for k in keys], [E[k]["first"] == bf[k]["first"] for k in keys],
               "same first flagged step as the recorded bf16 verdict (141)")]
steps_s = [(x >= 0.5) == (y >= 0.5) for k in keys if "p_fail" in bf[k] for x, y in zip(S[k]["p_fail"], bf[k]["p_fail"])]
steps_e = [(x >= 0.5) == (y >= 0.5) for k in keys if "p_fail" in bf[k] for x, y in zip(E[k]["p_fail"], bf[k]["p_fail"])]
recs.append(paired(steps_s, steps_e, f"steps with the recorded bf16 fails/not ({len(steps_s)})"))
det = [k for k in keys if S[k]["risky"] != "undetermined" and E[k]["risky"] != "undetermined"]
recs.append(paired([S[k]["risky"] == bf[k]["risky"] for k in det], [E[k]["risky"] == bf[k]["risky"] for k in det],
                   f"same verdict as the recorded bf16 one, where determined for both ({len(det)} of 141)"))
for m in recs:  # a substitute is reported only: never a blocker or a flag under the sealed rule
    m["rule"] = "SUBSTITUTE, not under the sealed rule: reported only (" + m["rule"] + " shown for information)"
    m["release_blocker"] = False
    m.pop("flag_worse_by_2", None)
half = [k for k in det if k in truth and truth[k]["half"]]
safe = [k for k in det if k in truth and not truth[k]["half"]]
dump(a.out, {"run_conditions": a.note, "item": "P12 preflight SUBSTITUTE (not the published measurement)",
             "status": ("P12 preflight: not run as published (plans' snapshots lost). This file is a substitute: report it "
                        "separately, never in the same table as published numbers."),
             "summary": summary(recs), "measures": recs,
             "undetermined": {"skopos": sum(S[k]["risky"] == "undetermined" for k in keys), "ekbasis27b": sum(E[k]["risky"] == "undetermined" for k in keys)},
             "against the truth (determined confirmation plans)": {
                 "half-applied warned": [sum(S[k]["risky"] is True for k in half), sum(E[k]["risky"] is True for k in half), len(half)],
                 "needless warnings": [sum(S[k]["risky"] is True for k in safe), sum(E[k]["risky"] is True for k in safe), len(safe)]},
             "first_step_skopos_vs_ekbasis_here_same": sum(S[k]["first"] == E[k]["first"] for k in keys)})
