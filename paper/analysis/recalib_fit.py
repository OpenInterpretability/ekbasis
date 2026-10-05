"""The analysis pre-registered in ekbasis/PREREG_recalibration.md. argv: answers.jsonl out_dir
Methods fit on the fit set only: M1 global temperature, M2 temperature from features (decision_core.temp_for),
M3 Platt scaling of the chosen answer's confidence, M4 isotonic regression of it."""
import bisect
import json
import math
import sys
from pathlib import Path

import torch

rows = [json.loads(l) for l in open(sys.argv[1])]
OUT = Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)
for r in rows:
    labs = list(r["probs"])
    p = torch.tensor([max(float(r["probs"][l]), 1e-12) for l in labs], dtype=torch.float64)
    r["_logp"] = torch.log(p / p.sum())
    r["_gold"] = labs.index(r["gold"]) if r["gold"] in labs else None
    r["_labs"] = labs
    r["_f"] = [math.log(max(r["n_tok"], 1)) - 6.5, math.log(len(labs)) - 1.2, float(r["type"] in ("noul", "boolean")), 0.0]
rows = [r for r in rows if r["_gold"] is not None]
fit_all = [r for r in rows if r["set"].startswith("fit_")]
fit_known = [r for r in fit_all if r["group"] in ("T", "H", "git")]


def dist(r, T):  # the distribution at temperature T
    return torch.softmax(r["_logp"] / T, -1)


def temp_of(params, r):
    b, w = params
    return math.exp(b + sum(wi * fi for wi, fi in zip(w, r["_f"])))


def fit_temperature(fit, feats):
    b = torch.zeros(1, dtype=torch.float64, requires_grad=True)
    w = torch.zeros(4, dtype=torch.float64, requires_grad=True)
    L = torch.nn.utils.rnn.pad_sequence([r["_logp"] for r in fit], batch_first=True, padding_value=-1e9)
    g = torch.tensor([r["_gold"] for r in fit])
    F = torch.tensor([r["_f"] for r in fit], dtype=torch.float64)
    opt = torch.optim.LBFGS([b, w] if feats else [b], lr=0.5, max_iter=200)

    def closure():
        opt.zero_grad()
        T = torch.exp(b + (F @ w if feats else 0.0)).unsqueeze(1)
        loss = -torch.log_softmax(L / T, -1)[torch.arange(len(fit)), g].mean()
        loss.backward()
        return loss
    opt.step(closure)
    return float(b), [float(x) for x in w] if feats else [0.0] * 4


def top(r, T=1.0):
    p = dist(r, T)
    k = int(p.argmax())
    return k, float(p[k])


def fit_platt(fit):
    c = torch.tensor([min(max(top(r)[1], 1e-6), 1 - 1e-6) for r in fit], dtype=torch.float64)
    y = torch.tensor([float(top(r)[0] == r["_gold"]) for r in fit], dtype=torch.float64)
    x = torch.log(c / (1 - c))
    a, d = torch.ones(1, dtype=torch.float64, requires_grad=True), torch.zeros(1, dtype=torch.float64, requires_grad=True)
    opt = torch.optim.LBFGS([a, d], lr=0.5, max_iter=200)

    def closure():
        opt.zero_grad()
        loss = torch.nn.functional.binary_cross_entropy_with_logits(a * x + d, y)
        loss.backward()
        return loss
    opt.step(closure)
    return float(a), float(d)


def fit_isotonic(fit):  # pool adjacent violators on (confidence, right)
    pts = sorted((top(r)[1], float(top(r)[0] == r["_gold"])) for r in fit)
    blocks = []  # [sum_y, n, max_x]
    for x, y in pts:
        blocks.append([y, 1, x])
        while len(blocks) > 1 and blocks[-2][0] / blocks[-2][1] > blocks[-1][0] / blocks[-1][1]:
            y2, n2, x2 = blocks.pop()
            blocks[-1][0] += y2
            blocks[-1][1] += n2
            blocks[-1][2] = x2
    return [b[2] for b in blocks], [b[0] / b[1] for b in blocks]


def iso_map(model, c):
    xs, ys = model
    i = bisect.bisect_left(xs, c)
    return ys[min(i, len(ys) - 1)]


def calibrated(method, params, r):
    """(chosen index, its calibrated confidence, calibrated P(yes) for yes/no questions or None)."""
    if method in ("T=1", "M1", "M2"):
        T = 1.0 if method == "T=1" else temp_of(params, r)
        p = dist(r, T)
        k = int(p.argmax())
        pyes = float(p[r["_labs"].index("yes")]) if "yes" in r["_labs"] else None
        return k, float(p[k]), pyes
    k, c = top(r)
    if method == "M3":
        a, d = params
        cc = min(max(c, 1e-6), 1 - 1e-6)
        c2 = 1 / (1 + math.exp(-(a * math.log(cc / (1 - cc)) + d)))
    else:
        c2 = iso_map(params, c)
    pyes = None
    if "yes" in r["_labs"]:
        pyes = c2 if r["_labs"][k] == "yes" else 1 - c2
    return k, c2, pyes


def measures(method, params, sel):
    out = [(calibrated(method, params, r), r) for r in sel]
    conf = [c for (k, c, _), r in out]
    ok = [float(k == r["_gold"]) for (k, c, _), r in out]
    n = len(out)
    ece = 0.0
    for b in range(15):
        lo, hi = b / 15, (b + 1) / 15
        idx = [i for i in range(n) if lo <= conf[i] < hi or (b == 14 and conf[i] == 1.0)]
        if idx:
            ece += len(idx) / n * abs(sum(ok[i] for i in idx) / len(idx) - sum(conf[i] for i in idx) / len(idx))
    bands = {}
    for name, lo, hi in (("0.7-0.9", 0.7, 0.9), ("0.9-0.99", 0.9, 0.99), ("0.99-1", 0.99, 1.01)):
        idx = [i for i in range(n) if lo <= conf[i] < hi]
        bands[name] = {"share": 100 * len(idx) / n, "mean_conf": 100 * sum(conf[i] for i in idx) / len(idx) if idx else None,
                       "acc": 100 * sum(ok[i] for i in idx) / len(idx) if idx else None}
    wrong = [i for i in range(n) if not ok[i]]
    pos, neg = [conf[i] for i in range(n) if ok[i]], sorted(conf[i] for i in wrong)
    auroc = sum(bisect.bisect_left(neg, a) + 0.5 * (bisect.bisect_right(neg, a) - bisect.bisect_left(neg, a)) for a in pos) / (len(pos) * len(neg)) if pos and neg else None
    return {"n": n, "acc": 100 * sum(ok) / n, "ece": ece, "brier": sum((conf[i] - ok[i]) ** 2 for i in range(n)) / n, "bands": bands,
            "wrong_at_0.9": 100 * sum(conf[i] >= 0.9 for i in wrong) / len(wrong) if wrong else None, "auroc": auroc}


def guard(method, params, sel):
    lost = [(calibrated(method, params, r)[2], r["gold"] == "yes") for r in sel if r["qtype"] == "lost"]
    pos, neg = [p for p, g in lost if g], [p for p, g in lost if not g]
    return {"flagged_at_0.2": 100 * sum(p >= 0.2 for p in pos) / len(pos), "false_alarms_at_0.2": 100 * sum(p >= 0.2 for p in neg) / len(neg),
            "n_lost": len(pos), "n_not_lost": len(neg)}


report = {"methods": {}}
for fitname, fit in (("all", fit_all), ("known_only", fit_known)):
    params = {"T=1": None, "M1": fit_temperature(fit, False), "M2": fit_temperature(fit, True), "M3": fit_platt(fit), "M4": fit_isotonic(fit)}
    for m, pr in params.items():
        key = f"{m}@{fitname}"
        tw = [r for r in rows if r["set"] == "test_world"]
        res = {"params": (pr if m != "M4" else {"knots": len(pr[0])}),
               "test_world": measures(m, pr, tw),
               "test_world_T": measures(m, pr, [r for r in tw if r["group"] == "T"]),
               "test_world_H": measures(m, pr, [r for r in tw if r["group"] == "H"]),
               "test_world_U": measures(m, pr, [r for r in tw if r["group"] == "U"]),
               "test_git_known": measures(m, pr, [r for r in rows if r["set"] == "test_git_known"]),
               "test_git_held": measures(m, pr, [r for r in rows if r["set"] == "test_git_held"]),
               "guard_git_held": guard(m, pr, [r for r in rows if r["set"] == "test_git_held"])}
        report["methods"][key] = res

base = report["methods"]["T=1@all"]
verdicts = {}
for key, res in report["methods"].items():
    if key.startswith("T=1") or not key.endswith("@all"):
        continue
    band_ok = all(res[g]["bands"]["0.9-0.99"]["acc"] is not None and abs(res[g]["bands"]["0.9-0.99"]["acc"] - res[g]["bands"]["0.9-0.99"]["mean_conf"]) <= 3
                  for g in ("test_world_T", "test_world_U"))
    ece_ok = res["test_world"]["ece"] <= base["test_world"]["ece"] / 2
    g0, g1 = base["guard_git_held"], res["guard_git_held"]
    guard_ok = g1["flagged_at_0.2"] >= g0["flagged_at_0.2"] - 1 and g1["false_alarms_at_0.2"] <= g0["false_alarms_at_0.2"] + 1
    verdicts[key] = {"fixes_it": band_ok and ece_ok and guard_ok, "ece_half": ece_ok, "band_within_3_T_and_U": band_ok, "guard_within_1": guard_ok}
report["verdicts"] = verdicts
json.dump(report, open(OUT / "report.json", "w"), indent=1, default=float)


def fmt_band(b):
    return f"{b['mean_conf']:.1f}/{b['acc']:.1f} ({b['share']:.0f}%)" if b["acc"] is not None else "-"


print(f"{'method':<16}{'ECE':>7}{'Brier':>8}{'0.9-0.99 T: said/right':>26}{'U':>20}{'wrong>=0.9 T':>14}{'U':>7}{'AUROC':>7}{'guard flag/FA':>16}")
for key, res in report["methods"].items():
    T_, U_ = res["test_world_T"], res["test_world_U"]
    print(f"{key:<16}{res['test_world']['ece']:>7.3f}{res['test_world']['brier']:>8.4f}{fmt_band(T_['bands']['0.9-0.99']):>26}"
          f"{fmt_band(U_['bands']['0.9-0.99']):>20}{T_['wrong_at_0.9']:>14.1f}{U_['wrong_at_0.9']:>7.1f}{res['test_world']['auroc']:>7.3f}"
          f"{res['guard_git_held']['flagged_at_0.2']:>9.1f}/{res['guard_git_held']['false_alarms_at_0.2']:.1f}")
print("verdicts:", json.dumps(verdicts, indent=None))
