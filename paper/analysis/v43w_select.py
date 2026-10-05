"""PLAN_v43_wise.md + addendum, selection of the interpolations on the trainer's readout against V42's: the guard on the
larger set (guard_big.json: per split, 1 point each way), git3 pooled and multi changed within 0.5 points, ftest within
1, confident errors in group T not higher. argv: compare.json (v43r2_compare.py) guard_big.json out.json run..."""
import json
import sys

cmp_, big, out, runs = json.load(open(sys.argv[1])), json.load(open(sys.argv[2])), sys.argv[3], sys.argv[4:]
b = cmp_["sw_v42base"]
rep = {}
for r in runs:
    c, g = cmp_[r], big[r.replace("sw_", "")]
    crit = dict(g["gate"])
    crit["git3 pooled within 0.5"] = c["git3_pooled_acc"] >= b["git3_pooled_acc"] - 0.5
    crit["multi changed within 0.5"] = c["multi_testfam_changed_acc"] >= b["multi_testfam_changed_acc"] - 0.5
    crit["ftest within 1"] = c["ftest_family_acc"] >= b["ftest_family_acc"] - 1.0
    crit["confident errors T not higher"] = c["T"]["conf_errors_per_100"] <= b["T"]["conf_errors_per_100"]
    rep[r] = {"qualifies": all(crit.values()), "criteria": crit}
order = [r for r in runs if rep[r]["qualifies"]]
json.dump({"runs": rep, "loop_order": order}, open(out, "w"), indent=1)
for r in runs:
    print(f"{r}: {'QUALIFIES' if rep[r]['qualifies'] else 'does not qualify: ' + ', '.join(k for k, v in rep[r]['criteria'].items() if not v)}")
print("loop order:", " ".join(order) if order else "none")
