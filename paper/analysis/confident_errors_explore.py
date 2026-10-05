"""Exploratory checks (not pre-registered) of the confident-errors test: answer format, the difficulty of each cell,
leaving one family out, and a logistic regression with a family-cluster bootstrap. argv: items.jsonl preds.jsonl out.json"""
import collections
import json
import math
import random
import sys

items = [json.loads(l) for l in open(sys.argv[1])]
preds = [json.loads(l) for l in open(sys.argv[2])]
assert len(items) == len(preds) and all(i["world"] == p["world"] and i["qtype"] == p["qtype"] and i["gold"] == p["gold"]
                                        for i, p in zip(items, preds))
for i, p in zip(items, preds):
    p["fmt"] = "yes/no" if i["question"]["type"] in ("noul", "boolean") else "choice"
share = lambda w: 100 * sum(p["conf"] >= 0.9 for p in w) / len(w) if w else float("nan")
wrong = lambda g, f=lambda p: True: [p for p in preds if p["group"] == g and not p["ok"] and f(p)]
out = {"format": {}, "difficulty": {}, "leave_one_family_out": {}}
for fmt in ("yes/no", "choice"):
    out["format"][fmt] = {g: {"share": share(wrong(g, lambda p: p["fmt"] == fmt)), "wrong": len(wrong(g, lambda p: p["fmt"] == fmt))}
                          for g in ("T", "H", "U")}
cell = collections.defaultdict(list)
for p in preds:
    cell[(p["world"], p["qtype"], p["steps"])].append(p)
rate = {k: sum(not p["ok"] for p in v) / len(v) for k, v in cell.items()}
for lo, hi, name in ((0, 0.05, "under 5%"), (0.05, 0.15, "5-15%"), (0.15, 1.01, "15% or more")):
    sel = lambda p: lo <= rate[(p["world"], p["qtype"], p["steps"])] < hi
    out["difficulty"][name] = {g: {"share": share(wrong(g, sel)), "wrong": len(wrong(g, sel))} for g in ("T", "U")}
diffs = {}
for f in sorted({p["world"] for p in preds if p["group"] in ("T", "U")}):
    keep = lambda p: p["world"] != f
    diffs[f] = share(wrong("T", keep)) - share(wrong("U", keep))
out["leave_one_family_out"] = {"min": min(diffs.values()), "max": max(diffs.values()), "per_family_left_out": diffs}

rows = [p for p in preds if p["group"] in ("T", "U") and not p["ok"]]


def x_of(p):
    r = min(max(rate[(p["world"], p["qtype"], p["steps"])], 0.005), 0.995)
    return [1.0, 1.0 if p["group"] == "T" else 0.0, math.log(r / (1 - r)), 1.0 if p["fmt"] == "yes/no" else 0.0]


def fit(X, y, iters=40):  # logistic regression by Newton-Raphson
    k, b = len(X[0]), [0.0] * len(X[0])
    for _ in range(iters):
        g, H = [0.0] * k, [[0.0] * k for _ in range(k)]
        for x, t in zip(X, y):
            q = 1 / (1 + math.exp(-sum(bi * xi for bi, xi in zip(b, x))))
            for i in range(k):
                g[i] += (t - q) * x[i]
                for j in range(k):
                    H[i][j] += q * (1 - q) * x[i] * x[j]
        A = [row[:] + [gi] for row, gi in zip(H, g)]
        for c in range(k):
            piv = max(range(c, k), key=lambda r: abs(A[r][c]))
            A[c], A[piv] = A[piv], A[c]
            for r in range(k):
                if r != c:
                    fct = A[r][c] / A[c][c]
                    A[r] = [a - fct * bc for a, bc in zip(A[r], A[c])]
        b = [bi + A[i][k] / A[i][i] for i, bi in enumerate(b)]
    return b


X, y = [x_of(p) for p in rows], [1.0 if p["conf"] >= 0.9 else 0.0 for p in rows]
b = fit(X, y)
fams = sorted({p["world"] for p in rows})
byf = {f: [i for i, p in enumerate(rows) if p["world"] == f] for f in fams}
rng, coefs = random.Random(0), []
while len(coefs) < 300:
    pick = [rng.choice(fams) for _ in fams]
    idx = [i for f in pick for i in byf[f]]
    if len({rows[i]["group"] for i in idx}) < 2:
        continue
    try:
        coefs.append(fit([X[i] for i in idx], [y[i] for i in idx], iters=25)[1])
    except (ZeroDivisionError, OverflowError):
        continue
coefs.sort()
out["logistic"] = {"n_wrong": len(rows), "familiar": b[1], "odds_ratio": math.exp(b[1]), "logit_cell_error_rate": b[2],
                   "yes_no": b[3], "familiar_family_cluster_ci95": [coefs[7], coefs[292]], "resamples": len(coefs)}
json.dump(out, open(sys.argv[3], "w"), indent=1)
print(json.dumps({k: out[k] for k in ("format", "difficulty")}, indent=None))
print("leave one family out:", {k: round(v, 1) for k, v in diffs.items()})
print("logistic:", {k: (round(v, 2) if isinstance(v, float) else v) for k, v in out["logistic"].items()})
