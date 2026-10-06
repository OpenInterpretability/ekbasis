"""WS-U confirm-3: calibrate L1 (strict) and L2 (difficulty) on confirm-1 + confirm-2 ONLY (both fully enumerated
fresh sets, now spent), at α = 0.02 (primary) and 0.01; δ = 0.05. Units: one confident question per scenario, with
confirm-2's seeds (61 for confirm-1, 62 for confirm-2). The score is the frozen one, unchanged
(confirm2/metrics2.scored_rows: dev warm start, online within each set). No model call.
python3 fit_ltt3.py  ->  params_confirm3.json, ltt3_calibration.json (in-sample numbers: the expected price)"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
U = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(U, "confirm2"))
import ltt3 as L  # noqa: E402
import metrics2 as M  # noqa: E402


def main():
    units = []
    for d, seed in (("confirm", 61), ("confirm2", 62)):
        rows, missing = M.scored_rows(os.path.join(U, d, "fresh_rows.jsonl"), os.path.join(U, d, "extra.jsonl"))
        assert missing == 0, (d, missing)
        us = M.one_per_scenario(rows, seed)
        for u in us:
            u["set"] = d
        units += us
    params, cal = {"calibration": "confirm-1 + confirm-2 units", "n_units": len(units),
                   "n_unit_errors": sum(u["wrong"] for u in units)}, {}
    for key, alpha in (("a02", 0.02), ("a01", 0.01)):
        P = L.fit(units, alpha)
        params[key] = P
        cal[key] = {}
        for rule in ("L1", "L2"):
            rep = L.report(units, P, rule, alpha)
            cal[key][rule] = {k: v for k, v in rep.items() if k != "nodes"}
            cal[key][rule]["n_nodes_used"] = len(rep["nodes"])
        cal[key]["family_nodes"] = len(P["family_nodes"])
        cal[key]["family_nodes_certified"] = sum(v["lambda"] is not None for v in P["family_nodes"].values())
        cal[key]["difficulty_nodes_certified"] = {k: (round(v["lambda"], 4) if v["lambda"] else None, v["units"], v["errors"])
                                                 for k, v in P["difficulty_nodes"].items()}
    json.dump(params, open(os.path.join(HERE, "params_confirm3.json"), "w"), indent=1)
    json.dump(cal, open(os.path.join(HERE, "ltt3_calibration.json"), "w"), indent=1)
    print(json.dumps({"n_units": params["n_units"], "n_unit_errors": params["n_unit_errors"], **cal}, indent=1))


if __name__ == "__main__":
    main()
