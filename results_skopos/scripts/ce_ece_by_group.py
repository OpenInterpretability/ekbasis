"""PREREG_ADDENDUM A2 asked, per group, for accuracy, wrong at >= 0.9 per 100 AND ECE, with and without the items the
overlap audit flags; ECE was not reported in ce_r4.json (found by the independent review, Part C). ECE = 10 equal-width
bins on the answer's confidence (as release_eval.py / quant_gate.py), paired bootstrap of the difference (2,000, seed
20261015) against Ekbasis-27B's published predictions on the same items.
    python3 ce_ece_by_group.py RS DM"""
import json, random, sys, collections
RS, DM = sys.argv[1], sys.argv[2]
S = [json.loads(l) for l in open(f"{RS}/addendum/ce/preds.jsonl")]
E = [json.loads(l) for l in open(f"{DM}/release_clean/code_eikos/ekbasis/results/confident_errors/preds.jsonl")]
flagged = set(json.load(open(f"{RS}/results/ce_r4_clean.json"))["clean"]["excluded_ids"]["ce_items"])  # item indices
def ece(P, I):
    b = collections.defaultdict(list)
    for i in I: b[min(9, int(P[i]["conf"] * 10))].append(i)
    return sum(len(v) / len(I) * abs(sum(P[i]["ok"] for i in v) / len(v) - sum(P[i]["conf"] for i in v) / len(v)) for v in b.values())
def boot(I):
    rng = random.Random(20261015); n = len(I); vals = []
    for _ in range(2000):
        smp = [I[rng.randrange(n)] for _ in range(n)]; vals.append(ece(S, smp) - ece(E, smp))
    vals.sort(); return [vals[50], vals[1949]]
out = {"method": __doc__.split("\n")[0], "groups": {}}
for g in "THU":
    for s in ("all", "changed"):
        for subset in ("all_items", "clean"):
            I = [i for i, p in enumerate(S) if p["group"] == g and (s == "all" or p["changed"]) and (subset == "all_items" or i not in flagged)]
            if not I: continue
            d = {"n": len(I), "ece_skopos": ece(S, I), "ece_ekbasis": ece(E, I), "diff_ci": boot(I)}
            d["diff"] = d["ece_skopos"] - d["ece_ekbasis"]
            out["groups"][f"{g}_{s}_{subset}"] = d
            print(f"{g} {s:7s} {subset:9s} n={d['n']:5d} ECE Skopos {d['ece_skopos']:.4f} Ekbasis {d['ece_ekbasis']:.4f} diff {d['diff']:+.4f} [{d['diff_ci'][0]:+.4f}, {d['diff_ci'][1]:+.4f}]", flush=True)
json.dump(out, open(f"{RS}/results/ce_r4_ece.json", "w"), indent=1)
