"""Shared metrics for WS-U: AUROC with ties, stratified paired bootstrap, weighted verification share."""
import numpy as np


def auroc(score, wrong, weight=None):
    """P(score of a wrong answer > score of a right one), ties counted half. Weighted (Mann-Whitney on weights)."""
    s = np.asarray(score, float)
    y = np.asarray(wrong, bool)
    w = np.ones(len(s)) if weight is None else np.asarray(weight, float)
    if y.sum() == 0 or (~y).sum() == 0:
        return float("nan")
    order = np.argsort(s, kind="mergesort")
    s, y, w = s[order], y[order], w[order]
    # walk tie groups: wrong-weight above right-weight below
    total_pos = w[y].sum()
    total_neg = w[~y].sum()
    auc = 0.0
    neg_below = 0.0
    i = 0
    n = len(s)
    while i < n:
        j = i
        while j < n and s[j] == s[i]:
            j += 1
        pos_here = w[i:j][y[i:j]].sum()
        neg_here = w[i:j][~y[i:j]].sum()
        auc += pos_here * (neg_below + 0.5 * neg_here)
        neg_below += neg_here
        i = j
    return float(auc / (total_pos * total_neg))


def boot_diff(sa, sb, wrong, strata, n=2000, seed=7):
    """Paired bootstrap of AUROC(sa) - AUROC(sb), resampling items within each stratum. Returns (diff, lo, hi)."""
    rng = np.random.default_rng(seed)
    sa, sb, y, st = map(np.asarray, (sa, sb, wrong, strata))
    groups = [np.flatnonzero(st == g) for g in np.unique(st)]
    base = auroc(sa, y) - auroc(sb, y)
    diffs = []
    for _ in range(n):
        idx = np.concatenate([rng.choice(g, len(g), replace=True) for g in groups])
        a, b = auroc(sa[idx], y[idx]), auroc(sb[idx], y[idx])
        if not (np.isnan(a) or np.isnan(b)):
            diffs.append(a - b)
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    return float(base), float(lo), float(hi)


def verify_share(score, wrong, weight=None, targets=(0.5, 0.8, 0.95), seed=11):
    """Share of (weighted) confident answers to verify, most suspicious first, to catch each target share of the
    (weighted) confident errors. Ties broken at random with a fixed seed."""
    s = np.asarray(score, float)
    y = np.asarray(wrong, bool)
    w = np.ones(len(s)) if weight is None else np.asarray(weight, float)
    rng = np.random.default_rng(seed)
    order = np.lexsort((rng.random(len(s)), -s))
    cw = np.cumsum(w[order]) / w.sum()
    ce = np.cumsum((w * y)[order]) / (w * y).sum()
    out = {}
    for t in targets:
        k = int(np.searchsorted(ce, t - 1e-12))
        out[f"{int(t * 100)}"] = round(float(cw[min(k, len(cw) - 1)]), 4)
    return out


def rank01(x):
    """Ranks scaled to [0, 1] (average ranks for ties)."""
    x = np.asarray(x, float)
    order = np.argsort(x, kind="mergesort")
    ranks = np.empty(len(x))
    i = 0
    while i < len(x):
        j = i
        while j < len(x) and x[order[j]] == x[order[i]]:
            j += 1
        ranks[order[i:j]] = (i + j - 1) / 2.0
        i = j
    return ranks / max(len(x) - 1, 1)
