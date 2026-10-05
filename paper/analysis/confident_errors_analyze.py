"""The analysis pre-registered in ekbasis/PREREG_confident_errors.md, on results/confident_errors/preds.jsonl.
argv: preds.jsonl report.json"""
import json
import random
import statistics
import sys

preds = [json.loads(l) for l in open(sys.argv[1])]
CONF = 0.9
fams = lambda g: sorted({p["world"] for p in preds if p["group"] == g})


def share_conf(rows):
    wrong = [p for p in rows if not p["ok"]]
    return (sum(p["conf"] >= CONF for p in wrong) / len(wrong)) if wrong else float("nan"), len(wrong)


def strata(g, sel=lambda p: True):
    return {f: [p for p in preds if p["group"] == g and p["world"] == f and sel(p)] for f in fams(g)}


def boot_diff(sel=lambda p: True, n=2000, seed=0):
    rng = random.Random(seed)
    T, U = strata("T", sel), strata("U", sel)
    out = []
    for _ in range(n):
        rt = [rng.choice(v) for v in T.values() for _ in v]
        ru = [rng.choice(v) for v in U.values() for _ in v]
        out.append(share_conf(rt)[0] - share_conf(ru)[0])
    out.sort()
    return 100 * out[int(0.025 * n)], 100 * out[int(0.975 * n)]


def auroc(pos, neg):  # P(confidence of a right answer > that of a wrong one)
    if not pos or not neg:
        return float("nan")
    neg = sorted(neg)
    import bisect
    s = 0.0
    for a in pos:
        lo, hi = bisect.bisect_left(neg, a), bisect.bisect_right(neg, a)
        s += lo + 0.5 * (hi - lo)
    return s / (len(pos) * len(neg))


def caught_at(rows, budget=0.10):  # share of the errors among the least-confident `budget` of the answers
    wrong = sum(not p["ok"] for p in rows)
    if not wrong:
        return float("nan")
    k = max(1, round(budget * len(rows)))
    low = sorted(rows, key=lambda p: p["conf"])[:k]
    return sum(not p["ok"] for p in low) / wrong


def describe(rows):
    wrong = [p for p in rows if not p["ok"]]
    sc, nw = share_conf(rows)
    return {"n": len(rows), "wrong": nw, "error_rate": 100 * nw / len(rows) if rows else float("nan"),
            "share_wrong_conf_ge_0.9": 100 * sc, "share_wrong_below_0.7": 100 * sum(p["conf"] < 0.7 for p in wrong) / nw if nw else float("nan"),
            "median_conf_wrong": statistics.median(p["conf"] for p in wrong) if wrong else float("nan"),
            "auroc": auroc([p["conf"] for p in rows if p["ok"]], [p["conf"] for p in wrong]),
            "errors_caught_least_confident_10pct": 100 * caught_at(rows)}


rep = {"groups": {}, "families": {}}
for g in ("T", "H", "U"):
    rows = [p for p in preds if p["group"] == g]
    rep["groups"][g] = {"all": describe(rows), "changed": describe([p for p in rows if p["changed"]]), "families": fams(g)}
    for f in fams(g):
        fr = [p for p in rows if p["world"] == f]
        rep["families"][f"{g}:{f}"] = describe(fr)

# primary
sT, sU = rep["groups"]["T"]["all"]["share_wrong_conf_ge_0.9"], rep["groups"]["U"]["all"]["share_wrong_conf_ge_0.9"]
lo, hi = boot_diff()
fam_share = lambda g: [rep["families"][f"{g}:{f}"]["share_wrong_conf_ge_0.9"] for f in fams(g) if rep["families"][f"{g}:{f}"]["wrong"] >= 10]
med = lambda xs: statistics.median(xs) if xs else float("nan")  # no family with 10 wrong answers: the condition is not met
mT, mU = med(fam_share("T")), med(fam_share("U"))
diff = sT - sU
verdict = ("confirmed" if diff >= 15 and lo > 0 and mT > mU else "refuted" if lo <= 0 <= hi or diff < 0 else "inconclusive")
rep["primary"] = {"share_T": sT, "share_U": sU, "difference_points": diff, "ci95": [lo, hi],
                  "family_median_T": mT, "family_median_U": mU, "families_counted_T": len(fam_share("T")),
                  "families_counted_U": len(fam_share("U")), "verdict": verdict}
cT, cU = rep["groups"]["T"]["changed"]["share_wrong_conf_ge_0.9"], rep["groups"]["U"]["changed"]["share_wrong_conf_ge_0.9"]
clo, chi = boot_diff(lambda p: p["changed"])
rep["secondary_changed"] = {"share_T": cT, "share_U": cU, "difference_points": cT - cU, "ci95": [clo, chi]}
json.dump(rep, open(sys.argv[2], "w"), indent=1)

print(f"PRIMARY  wrong answers at confidence >= {CONF}: T {sT:.1f}% vs U {sU:.1f}%  difference {diff:+.1f} points, "
      f"95% CI [{lo:+.1f}, {hi:+.1f}]; family medians T {mT:.1f}% vs U {mU:.1f}%  ->  {verdict.upper()}")
print(f"changed answers only: T {cT:.1f}% vs U {cU:.1f}%  difference {cT - cU:+.1f}, CI [{clo:+.1f}, {chi:+.1f}]")
print(f"{'':16}{'n':>6}{'wrong':>7}{'err%':>7}{'conf>=.9':>10}{'<0.7':>7}{'med conf':>10}{'AUROC':>7}{'caught@10%':>12}")
for k, v in [(f"group {g}", rep["groups"][g]["all"]) for g in ("T", "H", "U")] + list(rep["families"].items()):
    print(f"{k:<16}{v['n']:>6}{v['wrong']:>7}{v['error_rate']:>7.1f}{v['share_wrong_conf_ge_0.9']:>10.1f}{v['share_wrong_below_0.7']:>7.1f}"
          f"{v['median_conf_wrong']:>10.3f}{v['auroc']:>7.3f}{v['errors_caught_least_confident_10pct']:>12.1f}")
