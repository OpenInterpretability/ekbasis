"""WS-U confirm-2, Part A (pre-registered in SPEC_confirm2.md; run after the freeze): the dev-fitted thresholds
(P-domain, P-conformal) on the confirm-1 fresh set, which was not used to fit them. No model call.
Not confirmatory: confirm-1's aggregate results were known when P-domain was designed. The Learn-then-Test rules are
calibrated on confirm-1, so they are not evaluated here; only their in-sample numbers are shown (ltt_calibration.json).
python3 heldout_confirm1.py  ->  ../results/confirm2/heldout_confirm1.json"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import metrics2 as M  # noqa: E402

C1 = "/root/decis/mission/U/confirm"
OUT = os.path.join(os.path.dirname(HERE), "results", "confirm2")


def main():
    params = json.load(open(os.path.join(HERE, "params_confirm2.json")))
    rows, missing = M.scored_rows(f"{C1}/fresh_rows.jsonl", f"{C1}/extra.jsonl")
    res = M.evaluate(rows, params)
    res["missing_extra"] = missing
    res["criteria_as_on_confirm2"] = {
        "domain": bool(res["policies"]["domain"]["recall"] >= 0.80 and res["policies"]["domain"]["share"] <= 0.30
                       and all(v["domain"]["recall"] >= 0.75 for v in res["per_suite"].values())),
        "conformal": bool(res["policies"]["conformal"]["recall"] >= 0.85
                          and all(v["conformal"]["recall"] >= 0.80 for v in res["per_suite"].values())),
        "global": bool(res["policies"]["global"]["recall"] >= 0.80 and res["policies"]["global"]["share"] <= 0.30)}
    os.makedirs(OUT, exist_ok=True)
    json.dump(res, open(os.path.join(OUT, "heldout_confirm1.json"), "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
