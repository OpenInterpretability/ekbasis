"""V50R2 analysis (PREREG_R2.md). Paired bootstrap by item (2,000, seed 20261014).
Rule: R2 preferred over R1 if fac_val pooled R2 − R1 ≥ +0.02 with CI > 0, git_long R2 − R1 CI not entirely below 0,
and no M3 suite R2 − base < −0.01 with CI entirely below 0. Also: R2 vs base everywhere, refit (T on fval_git3+m3val),
confident errors and ECE, fac_val by family.
    python3 analyze_r2.py /root/v50p"""
import json, sys, collections
import numpy as np
D = sys.argv[1]
rng = np.random.default_rng(20261014)
L = lambda d, s: [json.loads(l) for l in open(f"{D}/{d}/preds_{s}_floor.jsonl")]


def gi(p):
    pr = np.array(p["probs"], float); k = int(pr.argmax())
    if p["ok"]:
        return k
    d = np.abs(pr - p["p_gold"]); d[k] = np.inf
    return int(d.argmin())


def temp(P, T):
    out = []
    for p in P:
        lp = np.log(np.clip(np.array(p["probs"]), 1e-12, 1)) / T; q = np.exp(lp - lp.max()); q /= q.sum()
        k = int(q.argmax()); out.append({"ok": k == gi(p), "conf": float(q[k]), "pg": float(q[gi(p)])})
    return out


def fitT(P):
    return float(min(np.arange(0.5, 3.01, 0.05), key=lambda T: -np.mean([np.log(max(x["pg"], 1e-12)) for x in temp(P, T)])))


def ece(P):
    bins = collections.defaultdict(list)
    for p in P:
        bins[min(9, int(p["conf"] * 10))].append(p)
    return float(sum(len(b) / len(P) * abs(np.mean([x["ok"] for x in b]) - np.mean([x["conf"] for x in b])) for b in bins.values()))


def boot(a, b):
    a, b = np.array(a, float), np.array(b, float); n = len(a)
    d = [(a[i] - b[i]).mean() for i in (rng.integers(0, n, n) for _ in range(2000))]
    return round(float((a - b).mean()), 4), [round(float(np.percentile(d, 2.5)), 4), round(float(np.percentile(d, 97.5)), 4)]


ce = lambda P: round(100 * float(np.mean([(not x["ok"]) and x["conf"] >= 0.9 for x in P])), 2)
T2 = fitT(L("run_r2", "fval_git3") + L("run_r2", "m3val"))
T1 = fitT(L("run_r1", "fval_git3") + L("run_r1", "m3val"))
TB = fitT(L("base_probs", "fval_git3") + L("base_probs", "m3val"))
out = {"T": {"r2": T2, "r1": T1, "base": TB}}
src = {"fac_val": ("base_facval", "r1_facval")}
for s in ["fac_val", "git_long", "fhorizon", "latent_test", "git3_test_known", "git3_test_held", "guard_known", "ftest_family", "m3val", "fval_git3"]:
    bdir, r1dir = src.get(s, ("base_probs", "run_r1"))
    r2, r1, b = L("run_r2", s), L(r1dir, s), L(bdir, s)
    assert len(r2) == len(r1) == len(b), s
    ok = lambda P: [x["ok"] for x in P]
    res = {"r2": round(float(np.mean(ok(r2))), 4), "r1": round(float(np.mean(ok(r1))), 4), "base": round(float(np.mean(ok(b))), 4)}
    res["r2_minus_r1"] = boot(ok(r2), ok(r1)); res["r2_minus_base"] = boot(ok(r2), ok(b))
    r2t, r1t, bt = temp(r2, T2), temp(r1, T1), temp(b, TB)
    res["conf_err_refit"] = {"r2": ce(r2t), "r1": ce(r1t), "base": ce(bt)}
    res["ece_refit"] = {"r2": round(ece(r2t), 4), "r1": round(ece(r1t), 4), "base": round(ece(bt), 4)}
    if s == "fac_val":
        res["by_family"] = {}
        for w in sorted({x["world"] for x in r2}):
            ix = [i for i, x in enumerate(r2) if x["world"] == w]
            res["by_family"][w] = {"n": len(ix), "r2": round(float(np.mean([r2[i]["ok"] for i in ix])), 3),
                                   "r1": round(float(np.mean([r1[i]["ok"] for i in ix])), 3),
                                   "base": round(float(np.mean([b[i]["ok"] for i in ix])), 3)}
    out[s] = res
f = out["fac_val"]["r2_minus_r1"]; g = out["git_long"]["r2_minus_r1"]
guards = {s: not (out[s]["r2_minus_base"][0] < -0.01 and out[s]["r2_minus_base"][1][1] < 0)
          for s in ["git3_test_known", "git3_test_held", "guard_known", "ftest_family", "m3val", "fval_git3"]}
out["verdict"] = {"fac_val_gain": bool(f[0] >= 0.02 and f[1][0] > 0), "git_long_not_below_r1": bool(g[1][1] >= 0),
                  "m3_guards": guards, "r2_preferred": bool(f[0] >= 0.02 and f[1][0] > 0 and g[1][1] >= 0 and all(guards.values()))}
json.dump(out, open(f"{D}/run_r2/R2_RESULTS.json", "w"), indent=1)
print(json.dumps(out, indent=1))
