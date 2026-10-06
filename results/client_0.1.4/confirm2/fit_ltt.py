"""WS-U confirm-2: the Learn-then-Test acceptance rule (accept = act on a confident answer without verifying it),
calibrated on the confirm-1 fresh set. No model call.

Why confirm-1 and not dev: the guarantee needs an exchangeable sample of the population with every signal present.
- Dev is a case-control sample (every confident error, about 20% of the right answers), so the error rate among
  accepted answers cannot be counted there.
- Confirm-1 was fully enumerated, is spent (its confirmatory test is done), and confirm-2 uses new seeds.

Unit: one confident question per scenario (seed 61); questions of the same scenario share the state, so they are not
independent.
Levels: α = 0.02 (primary) and 0.01; δ = 0.05.

Nodes (hierarchical, after HG-CRC and LTT):
- a family with ≥ 3/α calibration units gets its own λ;
- every suite gets a λ from all its calibration units;
- a family uses its own λ if it was certified, else its suite's λ (rare families pool into the suite);
- a family never seen in calibration, or a suite with nothing certified, is always verified.

Also one pooled λ for every unit.
python3 fit_ltt.py  ->  adds "ltt" to params_confirm2.json; ltt_calibration.json (paths, in-sample numbers)"""
import collections
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import metrics2 as M  # noqa: E402

C1 = "/root/decis/mission/U/confirm"
DELTA = 0.05
SEED = 61


def main():
    rows, missing = M.scored_rows(f"{C1}/fresh_rows.jsonl", f"{C1}/extra.jsonl")
    assert missing == 0, missing
    units = M.one_per_scenario(rows, SEED)
    params = json.load(open(os.path.join(HERE, "params_confirm2.json")))
    params["ltt"] = {}
    report = {"rows": len(rows), "units": len(units), "unit_errors": sum(u["wrong"] for u in units),
              "units_per_suite": dict(collections.Counter(u["suite"] for u in units)), "levels": {}}
    fam_units = collections.defaultdict(list)
    for u in units:
        fam_units[f"{u['suite']}|{u['family']}"].append(u)
    for key, alpha in (("a02", 0.02), ("a01", 0.01)):
        need = math.ceil(3 / alpha)
        own = sorted(f for f, us in fam_units.items() if len(us) >= need)
        groups, paths = {}, {}
        members = {f: fam_units[f] for f in own}
        for s in M.PRIMARY:
            members[f"{s}|*suite*"] = [u for u in units if u["suite"] == s]
        for g, us in sorted(members.items()):
            lam, path = M.ltt_lambda([u["S"] for u in us], [u["wrong"] for u in us], alpha, DELTA)
            acc = [u for u in us if lam is not None and u["S"] < lam]
            groups[g] = {"lambda": lam, "units": len(us), "errors": sum(u["wrong"] for u in us),
                         "accepted_in_sample": len(acc), "errors_among_accepted_in_sample": sum(u["wrong"] for u in acc)}
            paths[g] = path[-3:]
        pooled, ppath = M.ltt_lambda([u["S"] for u in units], [u["wrong"] for u in units], alpha, DELTA)
        params["ltt"][key] = {"alpha": alpha, "delta": DELTA, "need_units": need, "groups": groups,
                              "seen_families": sorted(fam_units), "pooled_lambda": pooled, "calibration_unit_seed": SEED}
        n_acc = sum(M.ltt_accept(units, params, key))
        report["levels"][key] = {"alpha": alpha, "own_family_groups": len(own), "groups": len(groups),
                                 "groups_with_nothing_certified": sum(g["lambda"] is None for g in groups.values()),
                                 "accepted_share_in_sample": round(n_acc / len(units), 4),
                                 "pooled_lambda": pooled, "pooled_path_tail": ppath[-3:], "group_path_tails": paths}
    json.dump(params, open(os.path.join(HERE, "params_confirm2.json"), "w"), indent=1)
    json.dump(report, open(os.path.join(HERE, "ltt_calibration.json"), "w"), indent=1)
    print(json.dumps({k: (v if k != "levels" else {a: {x: y for x, y in d.items() if x != "group_path_tails"} for a, d in v.items()})
                      for k, v in report.items()}, indent=1))


if __name__ == "__main__":
    main()
