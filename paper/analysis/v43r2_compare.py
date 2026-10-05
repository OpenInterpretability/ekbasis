"""V43 round 2 against V42 under the trainer's readout (conseq/PLAN_v43_round2.md).
argv: runs_dir ce_items.jsonl out.json   (runs_dir holds sw_v42base and the round-2 runs)"""
import bisect
import json
import sys
from pathlib import Path

R, ITEMS, OUT = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
items = [json.loads(l) for l in open(ITEMS)]
RUNS = ["sw_v42base"] + (sys.argv[4:] or ["sw_r2conf", "sw_r2err", "sw_r2hard", "sw_r2conffl"])  # argv[4:]: the runs to compare (round 3: sw_r3h10 ...)


def auroc(pos, neg):
    neg = sorted(neg)
    return sum(bisect.bisect_left(neg, a) + 0.5 * (bisect.bisect_right(neg, a) - bisect.bisect_left(neg, a)) for a in pos) / (len(pos) * len(neg))


def stats(rows):
    wrong = [r for r in rows if not r["ok"]]
    cw = [r for r in wrong if r["conf"] >= 0.9]
    right = [r for r in rows if r["ok"]]
    return {"n": len(rows), "acc": 100 * (1 - len(wrong) / len(rows)), "conf_errors_per_100": 100 * len(cw) / len(rows),
            "right_at_0.99": 100 * sum(r["conf"] >= 0.99 for r in right) / len(right) if right else None,
            "share_wrong_at_0.9": 100 * len(cw) / len(wrong) if wrong else 0.0,
            "auroc": auroc([r["conf"] for r in rows if r["ok"]], [r["conf"] for r in wrong]) if wrong else None}


rep = {}
for run in RUNS:
    d = R / run
    if not (d / "summary.json").exists():
        continue
    S = json.load(open(d / "summary.json"))
    P = [json.loads(l) for l in open(d / "preds_ce_items_floor.jsonl")]
    assert len(P) == len(items) and all(p["world"] == it["world"] and p["qtype"] == it["qtype"] for p, it in zip(P, items))
    for p, it in zip(P, items):
        p["group"] = it["group"]
    gk, gh = S["git3_test_known/floor"], S["git3_test_held/floor"]
    rep[run] = {"git3_pooled_acc": 100 * (gk["acc"] * gk["n"] + gh["acc"] * gh["n"]) / (gk["n"] + gh["n"]),
                "multi_testfam_changed_acc": 100 * S["multi_test_testfam/single"]["acc_changed"],
                "ftest_family_acc": 100 * S["ftest_family/floor"]["acc"],
                "all": stats(P), **{g: stats([p for p in P if p["group"] == g]) for g in ("T", "H", "U")}}

b = rep.get("sw_v42base")
verdict = {}
for run in RUNS[1:]:
    if not b or run not in rep:
        continue
    r = rep[run]
    conf_ok = (r["T"]["conf_errors_per_100"] <= 0.6 * b["T"]["conf_errors_per_100"] and r["U"]["conf_errors_per_100"] <= b["U"]["conf_errors_per_100"]
               and r["H"]["conf_errors_per_100"] <= b["H"]["conf_errors_per_100"])
    acc_ok = r["git3_pooled_acc"] >= b["git3_pooled_acc"] - 0.5 and r["multi_testfam_changed_acc"] >= b["multi_testfam_changed_acc"] - 0.5
    sep_ok = r["all"]["share_wrong_at_0.9"] <= b["all"]["share_wrong_at_0.9"] and r["all"]["auroc"] >= b["all"]["auroc"] - 0.005
    verdict[run] = {"succeeds": conf_ok and acc_ok and sep_ok, "confident_errors_down": conf_ok, "accuracy_holds": acc_ok,
                    "share_not_up_and_auroc_holds": sep_ok}
rep["verdict"] = verdict
qual = [r for r in verdict if verdict[r]["succeeds"]]
rep["chosen_for_loop"] = max(qual, key=lambda r: rep[r]["all"]["right_at_0.99"]) if qual else None
json.dump(rep, open(OUT, "w"), indent=1)
print(f"{'run':<12}{'git3':>7}{'multi chg':>10}{'ftest':>7}{'acc T':>7}{'acc H':>7}{'acc U':>7}{'conf err/100 T':>16}{'H':>6}{'U':>6}{'share>=.9':>10}{'AUROC':>7}")
for run in RUNS:
    if run in rep:
        r = rep[run]
        print(f"{run:<12}{r['git3_pooled_acc']:>7.1f}{r['multi_testfam_changed_acc']:>10.1f}{r['ftest_family_acc']:>7.1f}{r['T']['acc']:>7.1f}"
              f"{r['H']['acc']:>7.1f}{r['U']['acc']:>7.1f}{r['T']['conf_errors_per_100']:>16.2f}{r['H']['conf_errors_per_100']:>6.2f}"
              f"{r['U']['conf_errors_per_100']:>6.2f}{r['all']['share_wrong_at_0.9']:>10.1f}{r['all']['auroc']:>7.3f}")
print("right answers at >= 0.99 (sharpness):", {r: round(rep[r]["all"]["right_at_0.99"], 1) for r in RUNS if r in rep})
print("verdict:", json.dumps(verdict))
print("chosen for the loop test:", rep["chosen_for_loop"])
