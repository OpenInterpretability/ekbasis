"""The analysis pre-registered in ekbasis/PREREG_confident_errors_eikos.md: the gap in confident errors (T minus U) for
Ekbasis and for Eikos-27B on the same items, and the difference between the gaps, by a paired bootstrap.
argv: ekbasis_preds.jsonl eikos_preds.jsonl out.json"""
import json
import random
import sys

E = [json.loads(l) for l in open(sys.argv[1])]
K = [json.loads(l) for l in open(sys.argv[2])]
assert len(E) == len(K) and all((a["world"], a["qtype"], a["steps"], a["gold"], a["group"]) ==
                                (b["world"], b["qtype"], b["steps"], b["gold"], b["group"]) for a, b in zip(E, K))
flags = lambda P: ([not p["ok"] for p in P], [(not p["ok"]) and p["conf"] >= 0.9 for p in P])
wE, cE = flags(E)
wK, cK = flags(K)
strata = {}
for i, p in enumerate(E):
    if p["group"] in ("T", "U"):
        strata.setdefault((p["group"], p["world"]), []).append(i)


def shares(idx_by_group, w, c):
    return {g: 100 * sum(c[i] for i in ix) / max(1, sum(w[i] for i in ix)) for g, ix in idx_by_group.items()}


full = {g: [i for (gg, _), ix in strata.items() if gg == g for i in ix] for g in ("T", "U")}
sE, sK = shares(full, wE, cE), shares(full, wK, cK)
gapE, gapK = sE["T"] - sE["U"], sK["T"] - sK["U"]
D = gapE - gapK
rng = random.Random(0)
boot = {"D": [], "gapK": [], "dT": [], "dU": []}
for _ in range(2000):
    res = {"T": [], "U": []}
    for (g, _), ix in strata.items():
        res[g].extend(rng.choice(ix) for _ in ix)
    bE, bK = shares(res, wE, cE), shares(res, wK, cK)
    boot["D"].append((bE["T"] - bE["U"]) - (bK["T"] - bK["U"]))
    boot["gapK"].append(bK["T"] - bK["U"])
    boot["dT"].append(bE["T"] - bK["T"])
    boot["dU"].append(bE["U"] - bK["U"])
ci = lambda xs: [sorted(xs)[int(0.025 * len(xs))], sorted(xs)[int(0.975 * len(xs))]]
cD = ci(boot["D"])
verdict = "training made it" if D >= 15 and cD[0] > 0 else ("the families explain it" if cD[0] <= 0 <= cD[1] else "both contribute")
err = lambda w, g: 100 * sum(w[i] for i in full[g]) / len(full[g])
out = {"ekbasis": {"share_T": sE["T"], "share_U": sE["U"], "gap": gapE, "error_T": err(wE, "T"), "error_U": err(wE, "U"),
                   "wrong_T": sum(wE[i] for i in full["T"]), "wrong_U": sum(wE[i] for i in full["U"])},
       "eikos27b": {"share_T": sK["T"], "share_U": sK["U"], "gap": gapK, "gap_ci95": ci(boot["gapK"]), "error_T": err(wK, "T"),
                    "error_U": err(wK, "U"), "wrong_T": sum(wK[i] for i in full["T"]), "wrong_U": sum(wK[i] for i in full["U"])},
       "D": D, "D_ci95": cD, "verdict": verdict,
       "training_change_T": {"points": sE["T"] - sK["T"], "ci95": ci(boot["dT"])},
       "training_change_U": {"points": sE["U"] - sK["U"], "ci95": ci(boot["dU"])}}
json.dump(out, open(sys.argv[3], "w"), indent=1)
e, k = out["ekbasis"], out["eikos27b"]
print(f"Ekbasis   : confident errors T {e['share_T']:.1f}% ({e['wrong_T']} wrong, {e['error_T']:.1f}% errors) vs U {e['share_U']:.1f}% "
      f"({e['wrong_U']} wrong, {e['error_U']:.1f}%)  gap {gapE:+.1f}")
print(f"Eikos-27B : confident errors T {k['share_T']:.1f}% ({k['wrong_T']} wrong, {k['error_T']:.1f}% errors) vs U {k['share_U']:.1f}% "
      f"({k['wrong_U']} wrong, {k['error_U']:.1f}%)  gap {gapK:+.1f}, CI [{k['gap_ci95'][0]:+.1f}, {k['gap_ci95'][1]:+.1f}]")
print(f"PRIMARY D = gap(Ekbasis) - gap(Eikos-27B) = {D:+.1f} points, 95% CI [{cD[0]:+.1f}, {cD[1]:+.1f}]  ->  {verdict.upper()}")
print(f"training changed the share of confident errors: T {out['training_change_T']['points']:+.1f} "
      f"[{out['training_change_T']['ci95'][0]:+.1f}, {out['training_change_T']['ci95'][1]:+.1f}], "
      f"U {out['training_change_U']['points']:+.1f} [{out['training_change_U']['ci95'][0]:+.1f}, {out['training_change_U']['ci95'][1]:+.1f}]")
