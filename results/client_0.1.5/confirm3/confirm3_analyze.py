"""WS-U confirm-3 analysis (SPEC_confirm3.md): the corrected Learn-then-Test rules (L1 strict, L2 difficulty) on fresh
units, their criteria and price; the per-domain rule's third test (secondary). No model call.
python3 confirm3_analyze.py  ->  ../results/confirm3/confirm3.json   (CONFIRM3_DIR / CONFIRM3_OUT: test harness only)"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
U = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(U, "confirm2"))
import ltt3 as L  # noqa: E402
import metrics2 as M  # noqa: E402

OUT = os.environ.get("CONFIRM3_OUT", os.path.join(U, "results", "confirm3"))
BASE = os.environ.get("CONFIRM3_DIR", HERE)
UNIT_SEED = 63


def main():
    P3 = json.load(open(os.path.join(HERE, "params_confirm3.json")))
    P2 = json.load(open(os.path.join(U, "confirm2", "params_confirm2.json")))
    rows, missing = M.scored_rows(os.path.join(BASE, "fresh_rows.jsonl"), os.path.join(BASE, "extra.jsonl"))
    units = M.one_per_scenario(rows, UNIT_SEED)
    res = {"n_rows": len(rows), "missing_extra": missing, "n_units": len(units),
           "n_unit_errors": sum(u["wrong"] for u in units), "ltt": {}}
    for key, alpha in (("a02", 0.02), ("a01", 0.01)):
        res["ltt"][key] = {rule: L.report(units, P3[key], rule, alpha) for rule in ("L1", "L2")}
    a = res["ltt"]["a02"]
    ev = M.evaluate(rows, P2)
    dom = ev["policies"]["domain"]
    res["per_domain_rule"] = {"overall": dom, "ci95_recall": ev["ci95"]["domain_recall"], "ci95_share": ev["ci95"]["domain_share"],
                              "per_suite": {s: v["domain"] for s, v in ev["per_suite"].items()},
                              "global": ev["policies"]["global"], "conformal": ev["policies"]["conformal"],
                              "auroc_weighted": ev["auroc_weighted"]}
    res["criteria"] = {
        "C1_L1_strict_a02": bool(a["L1"]["rate_ok"] and a["L1"]["no_node_significantly_above"]),
        "C2_L2_difficulty_a02": bool(a["L2"]["rate_ok"] and a["L2"]["no_node_significantly_above"]),
        "S1_per_domain_third_test": bool(dom["recall"] >= 0.80 and dom["share"] <= 0.30
                                         and all(v["domain"]["recall"] >= 0.75 for v in ev["per_suite"].values())),
    }
    os.makedirs(OUT, exist_ok=True)
    json.dump(res, open(os.path.join(OUT, "confirm3.json"), "w"), indent=1)
    print(json.dumps({"criteria": res["criteria"], "a02": {r: {k: v for k, v in a[r].items() if k not in ("nodes", "by_suite")}
                                                          for r in ("L1", "L2")}, "per_domain": dom}, indent=1))


if __name__ == "__main__":
    main()
