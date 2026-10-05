"""V43 round 1 against V42 under the trainer's readout (conseq/PLAN_v43_calibration.md).
argv: runs_dir ce_items.jsonl out.json   (runs_dir holds sw_v42base, sw_v43ce, sw_v43ls, sw_v43fl)"""
import bisect
import json
import sys
from pathlib import Path

R, ITEMS, OUT = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
items = [json.loads(l) for l in open(ITEMS)]
RUNS = ["sw_v42base", "sw_v43ce", "sw_v43ls", "sw_v43fl"]


def auroc(pos, neg):
    neg = sorted(neg)
    return sum(bisect.bisect_left(neg, a) + 0.5 * (bisect.bisect_right(neg, a) - bisect.bisect_left(neg, a)) for a in pos) / (len(pos) * len(neg))


def ece(rows, bins=15):
    out = 0.0
    for b in range(bins):
        sel = [r for r in rows if b / bins <= r["conf"] < (b + 1) / bins or (b == bins - 1 and r["conf"] == 1.0)]
        if sel:
            out += len(sel) / len(rows) * abs(sum(r["ok"] for r in sel) / len(sel) - sum(r["conf"] for r in sel) / len(sel))
    return out


def stats(rows):
    wrong = [r for r in rows if not r["ok"]]
    return {"n": len(rows), "error": 100 * len(wrong) / len(rows), "wrong_at_0.9": 100 * sum(r["conf"] >= 0.9 for r in wrong) / len(wrong),
            "auroc": auroc([r["conf"] for r in rows if r["ok"]], [r["conf"] for r in wrong]), "ece": ece(rows),
            "band_0.9_0.99": (lambda b: {"mean_conf": 100 * sum(r["conf"] for r in b) / len(b), "acc": 100 * sum(r["ok"] for r in b) / len(b),
                                         "share": 100 * len(b) / len(rows)} if b else None)([r for r in rows if 0.9 <= r["conf"] < 0.99])}


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
                "git3_known_acc": 100 * gk["acc"], "git3_held_acc": 100 * gh["acc"],
                "multi_testfam_changed_acc": 100 * S["multi_test_testfam/single"]["acc_changed"],
                "ftest_family_acc": 100 * S["ftest_family/floor"]["acc"],
                "ce_all": stats(P), **{f"ce_{g}": stats([p for p in P if p["group"] == g]) for g in ("T", "H", "U")}}

base = rep.get("sw_v42base")
verdict = {}
if base:
    for run in RUNS[1:]:
        if run not in rep:
            continue
        r = rep[run]
        acc_ok = r["git3_pooled_acc"] >= base["git3_pooled_acc"] - 0.5 and r["multi_testfam_changed_acc"] >= base["multi_testfam_changed_acc"] - 0.5
        unc_ok = (r["ce_T"]["wrong_at_0.9"] <= base["ce_T"]["wrong_at_0.9"] - 20) and (r["ce_U"]["wrong_at_0.9"] < base["ce_U"]["wrong_at_0.9"])
        sep_ok = r["ce_all"]["auroc"] >= base["ce_all"]["auroc"] - 0.005 and r["ce_all"]["ece"] < base["ce_all"]["ece"]
        verdict[run] = {"succeeds": acc_ok and unc_ok and sep_ok, "accuracy_holds": acc_ok, "errors_uncertain": unc_ok,
                        "separation_holds_and_ece_lower": sep_ok,
                        "auroc_change": r["ce_all"]["auroc"] - base["ce_all"]["auroc"]}
rep["verdict"] = verdict
json.dump(rep, open(OUT, "w"), indent=1)
print(f"{'run':<12}{'git3':>7}{'multi chg':>10}{'ftest':>7}{'err T':>7}{'err U':>7}{'wrong>=.9 T':>12}{'U':>6}{'AUROC':>7}{'ECE':>7}{'0.9-0.99 said/right':>21}")
for run in RUNS:
    if run in rep:
        r = rep[run]
        b = r["ce_all"]["band_0.9_0.99"]
        band = "{:.1f}/{:.1f}".format(b["mean_conf"], b["acc"]) if b else "-"
        print(f"{run:<12}{r['git3_pooled_acc']:>7.1f}{r['multi_testfam_changed_acc']:>10.1f}{r['ftest_family_acc']:>7.1f}{r['ce_T']['error']:>7.1f}"
              f"{r['ce_U']['error']:>7.1f}{r['ce_T']['wrong_at_0.9']:>12.1f}{r['ce_U']['wrong_at_0.9']:>6.1f}{r['ce_all']['auroc']:>7.3f}"
              f"{r['ce_all']['ece']:>7.3f}{band:>21}")
print("verdict:", json.dumps(verdict))
