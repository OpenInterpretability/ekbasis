"""V50R1 analysis (PREREG_R1.md). Paired bootstrap by item (2,000, seed 20261014); one global temperature per model
fitted on validation (fval_git3 + m3val) by gold NLL, applied to every test suite; ECE and confident errors."""
import json, sys, collections
import numpy as np
C, B = sys.argv[1], sys.argv[2]            # candidate dir, base dir (preds_<split>_floor.jsonl with probs)
rng = np.random.default_rng(20261014)
L = lambda d, s: [json.loads(l) for l in open(f"{d}/preds_{s}_floor.jsonl")]
gi = lambda p: ord(p["gold"][0]) - 65 if len(p["gold"]) == 1 else None
def temp(P, T):
    out = []
    for p in P:
        lp = np.log(np.clip(np.array(p["probs"]), 1e-12, 1)) / T; q = np.exp(lp - lp.max()); q /= q.sum()
        k = int(q.argmax()); out.append({"ok": k == gi(p), "conf": float(q[k]), "pg": float(q[gi(p)])})
    return out
def fitT(P):
    P = [p for p in P if gi(p) is not None and "probs" in p]
    best = min(np.arange(0.5, 3.01, 0.05), key=lambda T: -np.mean([np.log(max(x["pg"], 1e-12)) for x in temp(P, T)]))
    return float(best)
def ece(P):
    bins = collections.defaultdict(list)
    for p in P: bins[min(9, int(p["conf"] * 10))].append(p)
    return sum(len(b) / len(P) * abs(np.mean([x["ok"] for x in b]) - np.mean([x["conf"] for x in b])) for b in bins.values())
def boot(a, b):
    a, b = np.array(a, float), np.array(b, float); n = len(a)
    d = [(a[i] - b[i]).mean() for i in (rng.integers(0, n, n) for _ in range(2000))]
    return float((a - b).mean()), [float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))]
out = {}
TC = fitT(L(C, "fval_git3") + L(C, "m3val")); TB = fitT(L(B, "fval_git3") + L(B, "m3val"))
out["T"] = {"cand": TC, "base": TB}
for s in ["git_long", "fhorizon", "latent_test", "git3_test_known", "git3_test_held", "guard_known", "ftest_family", "m3val", "fval_git3"]:
    c, b = L(C, s), L(B, s)
    assert len(c) == len(b) and all(x["gold"] == y["gold"] for x, y in zip(c, b)), s
    d, ci = boot([x["ok"] for x in c], [x["ok"] for x in b])
    cr, br = temp(c, TC), temp(b, TB)
    ce = lambda P: 100 * np.mean([(not x["ok"]) and x["conf"] >= 0.9 for x in P])
    out[s] = {"cand": float(np.mean([x["ok"] for x in c])), "base": float(np.mean([x["ok"] for x in b])), "diff": d, "ci": ci,
              "conf_err_raw": [ce(c), ce(b)], "conf_err_refit": [ce(cr), ce(br)], "ece_raw": [ece(c), ece(b)], "ece_refit": [ece(cr), ece(br)]}
    if s == "git_long":
        for k in (5, 8, 12):
            idx = [i for i, x in enumerate(c) if int(x["steps"]) == k]
            out[f"git_long_{k}"] = {"cand": float(np.mean([c[i]["ok"] for i in idx])), "base": float(np.mean([b[i]["ok"] for i in idx]))}
    if s == "fhorizon":
        idx = [i for i, x in enumerate(c) if int(x["steps"]) in (8, 12, 20)]
        out["fhorizon_long"] = dict(zip(("diff", "ci"), boot([c[i]["ok"] for i in idx], [b[i]["ok"] for i in idx])))
g = out["git_long"]
acc_pass = g["diff"] >= 0.03 and g["ci"][0] > 0
ce_pass = g["conf_err_refit"][0] <= 0.7 * g["conf_err_refit"][1] and g["diff"] >= 0
guards = all(not (out[s]["diff"] < -0.01 and out[s]["ci"][1] < 0) for s in ["git3_test_known", "git3_test_held", "guard_known", "ftest_family", "m3val", "fval_git3"])
fh = out["fhorizon_long"]["ci"][1] >= 0
out["verdict"] = {"primary_acc": acc_pass, "primary_conf_err": ce_pass, "guards_m3": guards, "guard_synthetic_long": fh,
                  "pass": (acc_pass or ce_pass) and guards and fh}
json.dump(out, open(f"{C}/R1_RESULTS.json", "w"), indent=1)
print("T", out["T"])
for k, v in out.items():
    if isinstance(v, dict) and "cand" in v:
        s = f"{k:18s} cand {v['cand']:.3f} base {v['base']:.3f}"
        if "diff" in v: s += f" diff {v['diff']:+.3f} [{v['ci'][0]:+.3f},{v['ci'][1]:+.3f}]"
        if "conf_err_refit" in v: s += f" | conf.err/100 raw {v['conf_err_raw'][0]:.2f}/{v['conf_err_raw'][1]:.2f} refit {v['conf_err_refit'][0]:.2f}/{v['conf_err_refit'][1]:.2f} | ECE refit {v['ece_refit'][0]:.3f}/{v['ece_refit'][1]:.3f}"
        print(s)
print("fhorizon_long", out["fhorizon_long"]); print("VERDICT", out["verdict"])
