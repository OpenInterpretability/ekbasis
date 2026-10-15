"""PREREG_ADDENDUM.md A2, as run on 2026-10-15 (the two inline steps saved verbatim as one script).
1) Re-score `ok` with the yes/no answer normalized as in the code repository's results/confident_errors/items.jsonl
   (ekbasis-data raw/ce_items.jsonl stores it as a boolean; items otherwise identical, checked); predictions unchanged.
2) conseq/confident_errors_analyze.py on the re-scored predictions (run separately: analyze PREDS report.json).
3) Paired bootstrap (2,000, seed 20261015) against Ekbasis-27B's published predictions -> results/ce_r4.json.
    python3 ce_rescore_and_compare.py RS DM   (RS = release_skopos, DM = decision_model)"""
import json, random, sys
from huggingface_hub import hf_hub_download
RS, DM = sys.argv[1], sys.argv[2]
REF = f"{DM}/release_clean/code_eikos/ekbasis/results/confident_errors"
norm = lambda g: {True: "yes", False: "no"}[g] if isinstance(g, bool) else str(g)
code = [json.loads(l) for l in open(f"{REF}/items.jsonl")]
data = [json.loads(l) for l in open(hf_hub_download("caiovicentino1/ekbasis-data", "raw/ce_items.jsonl", repo_type="dataset"))]
assert len(code) == len(data)
assert not [i for i, (a, b) in enumerate(zip(code, data)) if {**a, "gold": norm(a["gold"])} != {**b, "gold": norm(b["gold"])}]
preds = [json.loads(l) for l in open(f"{RS}/addendum/ce/preds_raw_scoring.jsonl")]
with open(f"{RS}/addendum/ce/preds.jsonl", "w") as f:
    for p in preds:
        g = norm(p["gold"]); f.write(json.dumps({**p, "gold": g, "ok": p["pred"] == g}) + "\n")
S = [json.loads(l) for l in open(f"{RS}/addendum/ce/preds.jsonl")]
E = [json.loads(l) for l in open(f"{REF}/preds.jsonl")]
assert len(S) == len(E) and all(s["world"] == e["world"] and s["qtype"] == e["qtype"] and s["gold"] == e["gold"] for s, e in zip(S, E))


def boot(idx, f, B=2000, seed=20261015):
    rng = random.Random(seed); n = len(idx); vals = []
    for _ in range(B):
        smp = [idx[rng.randrange(n)] for _ in range(n)]; vals.append(f(smp))
    vals.sort(); return [vals[int(0.025 * B)], vals[int(0.975 * B) - 1]]


err = lambda P, I: 100 * sum(not P[i]["ok"] for i in I) / len(I)
cw = lambda P, I: 100 * sum((not P[i]["ok"]) and P[i]["conf"] >= 0.9 for i in I) / len(I)
out = {"n": len(S), "deviation": "the published raw/ce_items.jsonl stores yes/no gold as booleans while confident_errors.py compares strings; ok re-scored with the gold normalized to yes/no exactly as in the code repository's results/confident_errors/items.jsonl (items otherwise identical, checked); predictions unchanged", "groups": {}}
for g in "THU":
    for s in ("all", "changed"):
        I = [i for i, p in enumerate(S) if p["group"] == g and (s == "all" or p["changed"])]
        out["groups"][f"{g}_{s}"] = {"n": len(I), "error_skopos": err(S, I), "error_ekbasis": err(E, I), "error_diff": err(S, I) - err(E, I),
                                     "error_diff_ci": boot(I, lambda J: err(S, J) - err(E, J)),
                                     "conf_wrong_per100_skopos": cw(S, I), "conf_wrong_per100_ekbasis": cw(E, I), "conf_wrong_diff": cw(S, I) - cw(E, I),
                                     "conf_wrong_diff_ci": boot(I, lambda J: cw(S, J) - cw(E, J))}
rep = json.load(open(f"{RS}/addendum/ce/report.json")); ref = json.load(open(f"{REF}/report.json"))
out["primary_skopos"], out["primary_ekbasis"] = rep["primary"], ref["primary"]
json.dump(out, open(f"{RS}/results/ce_r4.json", "w"), indent=1)
