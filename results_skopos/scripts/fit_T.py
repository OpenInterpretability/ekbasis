"""Fit one global temperature on the production INT4 probabilities (fit set = fval_git3 + m3val, NLL of the gold
option, grid 0.5..3.0 by 0.01) and report ECE / confident errors (wrong at >= 0.9) / Brier on the test splits."""
import json, math, sys, collections
R = [json.loads(l) for l in open(sys.argv[1]) if "probs" in json.loads(l)]
def scale(p, T):
    lp = {k: math.log(max(v, 1e-12)) / T for k, v in p.items()}; m = max(lp.values())
    e = {k: math.exp(v - m) for k, v in lp.items()}; z = sum(e.values())
    return {k: v / z for k, v in e.items()}
def nll(rows, T):
    return -sum(math.log(max(scale(r["probs"], T)[r["gold"]], 1e-12)) for r in rows) / len(rows)
def stats(rows, T):
    bins = collections.defaultdict(list); ce = 0; br = 0; ok = 0
    for r in rows:
        q = scale(r["probs"], T); top = max(q, key=q.get); c = q[top]; good = top == r["gold"]
        bins[min(9, int(c * 10))].append((good, c)); ce += (not good) and c >= 0.9; ok += good
        br += sum((q[k] - (1.0 if k == r["gold"] else 0.0)) ** 2 for k in q)
    ece = sum(len(b) / len(rows) * abs(sum(g for g, _ in b) / len(b) - sum(c for _, c in b) / len(b)) for b in bins.values())
    return {"n": len(rows), "acc": round(ok / len(rows), 4), "ece": round(ece, 4), "conf_err_per100": round(100 * ce / len(rows), 2),
            "brier": round(br / len(rows), 4)}
fit = [r for r in R if r["set"] == "fit"]
grid = [round(0.5 + 0.01 * k, 2) for k in range(251)]
T = min(grid, key=lambda t: nll(fit, t))
print("fit n", len(fit), "T*", T, "NLL T1", round(nll(fit, 1.0), 4), "NLL T*", round(nll(fit, T), 4))
out = {"T": T}
for sp in ["fval_git3", "m3val", "git_long", "guard_known", "fac_val"]:
    rows = [r for r in R if r["split"] == sp]
    a, b = stats(rows, 1.0), stats(rows, T)
    out[sp] = {"T1": a, "Tfit": b}
    print(f"{sp:12s} n {a['n']:4d} acc {a['acc']:.3f} | ECE {a['ece']:.3f} -> {b['ece']:.3f} | conf.err/100 {a['conf_err_per100']:.2f} -> {b['conf_err_per100']:.2f} | Brier {a['brier']:.4f} -> {b['brier']:.4f}")
test = [r for r in R if r["set"] == "test"]
a, b = stats(test, 1.0), stats(test, T)
print(f"{'TEST pooled':12s} n {a['n']:4d} acc {a['acc']:.3f} | ECE {a['ece']:.3f} -> {b['ece']:.3f} | conf.err/100 {a['conf_err_per100']:.2f} -> {b['conf_err_per100']:.2f} | Brier {a['brier']:.4f} -> {b['brier']:.4f}")
out["test_pooled"] = {"T1": a, "Tfit": b}
# what a raw yes-probability becomes, for client thresholds
out["map_binary"] = {str(p): round(1 / (1 + math.exp(-math.log(p / (1 - p)) / T)), 3) for p in (0.5, 0.7, 0.8, 0.9, 0.95, 0.99, 0.999)}
print("binary raw -> calibrated:", out["map_binary"])
json.dump(out, open(sys.argv[2], "w"), indent=1)
