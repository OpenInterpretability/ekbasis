"""WS-U confirm-2 analysis (SPEC_confirm2.md): every pre-registered policy and baseline on the confirm-2 fresh rows,
the criteria, and the accumulation arm's replication. No model call.
python3 confirm2_analyze.py  ->  ../results/confirm2/confirm2.json   (CONFIRM2_DIR / CONFIRM2_OUT: test harness only)"""
import collections
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import metrics2 as M  # noqa: E402

OUT = os.environ.get("CONFIRM2_OUT", os.path.join(os.path.dirname(HERE), "results", "confirm2"))
BASE = os.environ.get("CONFIRM2_DIR", HERE)
UNIT_SEED = 62


def arm():
    """The simulate-vs-direct arm (confirm-1's C3), replicated: accumulation A/B on the confirm-2 items, at the frozen
    τ_acc read exactly from confirm/policy_params.json."""
    params_arm_tau = json.load(open(os.path.join(os.path.dirname(HERE), "confirm", "policy_params.json")))["arm"]["tau"]
    kept = {r["req"] for r in M.jl(os.path.join(BASE, "fresh_rows.jsonl"))
            if r["suite"] == "accumulation" and r["exclude"] is None}
    acc = collections.defaultdict(dict)
    for j in M.jl(os.path.join(BASE, "cap", "accumulation", "results.jsonl")):
        if not j.get("error"):
            acc[j["id"]][j["cond"]] = j
    ar = []
    for iid, d in acc.items():
        if iid in kept and "A" in d and "B" in d and d["A"]["confidence"] >= 0.9:
            pa, pb = d["A"]["probabilities"], d["B"]["probabilities"]
            la = max(pa, key=pa.get)
            ar.append((abs(pa.get(la, 0.0) - pb.get(la, 0.0)), not d["A"]["correct"]))
    if not ar:
        return None
    g, y = np.array([a for a, _ in ar]), np.array([b for _, b in ar])
    f = g >= params_arm_tau
    return {"n_confident": len(ar), "confident_errors": int(y.sum()), "recall": round(float((f & y).sum() / y.sum()), 4),
            "share": round(float(f.mean()), 4), "auroc_ab_gap": round(M.auroc(g, y), 4)}


def main():
    params = json.load(open(os.path.join(HERE, "params_confirm2.json")))
    rows, missing = M.scored_rows(os.path.join(BASE, "fresh_rows.jsonl"), os.path.join(BASE, "extra.jsonl"))
    res = M.evaluate(rows, params)
    res["missing_extra"] = missing
    p, ps = res["policies"], res["per_suite"]
    ci = res["ci95"]
    res["criteria"] = {
        "P1_domain": bool(p["domain"]["recall"] >= 0.80 and p["domain"]["share"] <= 0.30
                          and all(v["domain"]["recall"] >= 0.75 for v in ps.values())),
        "P2_conformal": bool(p["conformal"]["recall"] >= 0.85 and all(v["conformal"]["recall"] >= 0.80 for v in ps.values())),
        "S1_global_replication": bool(p["global"]["recall"] >= 0.80 and p["global"]["share"] <= 0.30),
        "S2_beats_confidence_auroc": bool(ci["auroc_S_minus_maxp"][0] > 0),
        "S3_beats_abstain_auroc": bool(ci.get("auroc_S_minus_unsure", [0])[0] > 0),
        "S3_beats_abstain_at_its_share": bool(p.get("S_at_abstain_share", {}).get("recall", 0) > p.get("abstain", {}).get("recall", 1)),
    }
    units = M.one_per_scenario(rows, UNIT_SEED)
    res["ltt"] = {}
    for key, alpha in (("a02", 0.02), ("a01", 0.01)):
        rep = M.ltt_report(units, params, key, alpha)
        h = rep["hierarchical"]
        rep["criteria"] = {
            "hierarchical_rate_ok": h["error_rate_among_accepted"] is not None and h["error_rate_among_accepted"] <= alpha,
            "no_node_significantly_above": not any(g["significant_bonferroni"] for g in h.get("groups", {}).values()),
            "pooled_rate_ok": rep["pooled"]["error_rate_among_accepted"] is not None
                              and rep["pooled"]["error_rate_among_accepted"] <= alpha}
        res["ltt"][key] = rep
    res["criteria"]["P3_ltt_a02"] = bool(res["ltt"]["a02"]["criteria"]["hierarchical_rate_ok"]
                                         and res["ltt"]["a02"]["criteria"]["no_node_significantly_above"])
    res["accumulation_arm_replication"] = arm()
    os.makedirs(OUT, exist_ok=True)
    json.dump(res, open(os.path.join(OUT, "confirm2.json"), "w"), indent=1)
    print(json.dumps({k: res[k] for k in ("n_confident", "confident_errors", "policies", "criteria")}, indent=1))


if __name__ == "__main__":
    main()
