"""CONFIRM_FTEST.md reading. python3 analyze_confirm_ftest.py /root/v50p"""
import json, random, sys, collections
D = sys.argv[1]
L = lambda p: [json.loads(l) for l in open(f"{D}/{p}")]
rows = L("data/ftest_fresh.jsonl"); rel = L("confirm_rel/preds_ftest_fresh_floor.jsonl"); r4 = L("confirm_r4/preds_ftest_fresh_floor.jsonl")
assert len(rows) == len(rel) == len(r4)
ch = [i for i, r in enumerate(rows) if r.get("known0") and r.get("gold0") is not None and str(r["gold0"]) != str(r["gold"])]
def boot(ix):
    d = [int(r4[i]["ok"]) - int(rel[i]["ok"]) for i in ix]
    rng = random.Random(20261015); v = sorted(sum(d[rng.randrange(len(d))] for _ in d) / len(d) for _ in range(2000))
    return round(100 * sum(d) / len(d), 2), [round(100 * v[50], 2), round(100 * v[1949], 2)]
acc = lambda P, ix: round(100 * sum(P[i]["ok"] for i in ix) / len(ix), 2)
allix = list(range(len(rows)))
out = {"changed": {"n": len(ch), "release": acc(rel, ch), "r4": acc(r4, ch), "r4_minus_release": boot(ch)},
       "all": {"n": len(rows), "release": acc(rel, allix), "r4": acc(r4, allix), "r4_minus_release": boot(allix)}}
for key in ("world", "steps"):
    out[f"changed_by_{key}"] = {}
    for v in sorted({rows[i][key] for i in ch}, key=str):
        ix = [i for i in ch if rows[i][key] == v]
        out[f"changed_by_{key}"][str(v)] = {"n": len(ix), "release": acc(rel, ix), "r4": acc(r4, ix), "diff": boot(ix)}
out["loss_confirmed"] = out["changed"]["r4_minus_release"][0] < -1.0
json.dump(out, open(f"{D}/confirm_r4/CONFIRM_FTEST.json", "w"), indent=1)
print(json.dumps(out, indent=1))
