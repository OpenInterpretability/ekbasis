"""V50P analysis (PREREG.md): paired bootstrap by item, 2,000 resamples, seed 20261014."""
import json, sys, collections
import numpy as np
R = sys.argv[1]   # dir with run/ and base/
rng = np.random.default_rng(20261014)
def load(which, split, mode="floor"):
    return [json.loads(l) for l in open(f"{R}/{which}/preds_{split}_{mode}.jsonl")]
def boot(a, b):
    a, b = np.array(a, float), np.array(b, float); n = len(a)
    d = [(a[i] - b[i]).mean() for i in (rng.integers(0, n, n) for _ in range(2000))]
    return float((a - b).mean()), [float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))]
def paired(split, mode="floor"):
    c, b = load("run", split, mode), load("base", split, mode)
    key = "gold" if "gold" in c[0] else "qtype"   # multi preds carry no gold: pair by order, check world/qtype
    assert len(c) == len(b) and all(x[key] == y[key] and x["world"] == y["world"] for x, y in zip(c, b)), split
    return c, b
out = {}
c, b = paired("fhorizon")
for k in (1, 2, 3, 5, 8, 12, 20):
    idx = [i for i, x in enumerate(c) if int(x["steps"]) == k]
    out[f"fhorizon_{k}"] = {"cand": np.mean([c[i]["ok"] for i in idx]), "base": np.mean([b[i]["ok"] for i in idx]), "n": len(idx)}
idx = [i for i, x in enumerate(c) if int(x["steps"]) in (8, 12, 20)]
d, ci = boot([c[i]["ok"] for i in idx], [b[i]["ok"] for i in idx])
out["M1_long_8_12_20"] = {"cand": float(np.mean([c[i]["ok"] for i in idx])), "base": float(np.mean([b[i]["ok"] for i in idx])), "diff": d, "ci": ci, "n": len(idx)}
c, b = paired("latent_test")
for g in ("trainworld", "heldout"):
    for k in (1, 3, 5, 10):
        idx = [i for i, x in enumerate(c) if x["world"].startswith(g) and int(x["steps"]) == k]
        d, ci = boot([c[i]["ok"] for i in idx], [b[i]["ok"] for i in idx])
        out[f"M2_{g}_k{k}"] = {"cand": float(np.mean([c[i]["ok"] for i in idx])), "base": float(np.mean([b[i]["ok"] for i in idx])), "diff": d, "ci": ci, "n": len(idx)}
regress = []
for s, mode in [("git3_test_known", "floor"), ("git3_test_held", "floor"), ("guard_known", "floor"), ("ftest_family", "floor"),
                ("m3val", "floor"), ("fval_git3", "floor"), ("multi_test_testfam", "multi"), ("multi_test_testfam", "single")]:
    c, b = paired(s, mode)
    d, ci = boot([x["ok"] for x in c], [x["ok"] for x in b])
    clear_drop = d < -0.01 and ci[1] < 0
    out[f"M3_{s}_{mode}"] = {"cand": float(np.mean([x["ok"] for x in c])), "base": float(np.mean([x["ok"] for x in b])), "diff": d, "ci": ci, "clear_drop_over_1pt": clear_drop, "n": len(c)}
    regress.append(clear_drop)
m1 = out["M1_long_8_12_20"]
out["verdict"] = {"a_long_gain_ge_3pts_ci_above_0": m1["diff"] >= 0.03 and m1["ci"][0] > 0, "b_no_clear_regression": not any(regress)}
out["verdict"]["promising"] = all(out["verdict"].values())
json.dump(out, open(f"{R}/V50P_RESULTS.json", "w"), indent=1)
for k, v in out.items():
    if k == "verdict": print("VERDICT", v); continue
    s = f"{k:32s} cand {v['cand']:.3f} base {v['base']:.3f}"
    if "diff" in v: s += f" diff {v['diff']:+.3f} CI [{v['ci'][0]:+.3f}, {v['ci'][1]:+.3f}]"
    print(s + f" n={v['n']}")
