"""The rule of PRELAUNCH_EVAL.md, Part A, for every compare.py: on a set of >= 100 items with per-item outputs for both
models, the paired 95% bootstrap (2,000 resamples, seed 20261015) of Skopos minus Ekbasis-27B; a difference whose
interval lies entirely on the worse side is a release blocker. Smaller sets are counts; Skopos worse by 2 or more is
flagged. Percentile interval as release_eval.py's boot(): the sorted resamples at int(0.025 B) and int(0.975 B)."""
import json
import random

B, SEED, MIN_N = 2000, 20261015, 100


def paired(sk, ek, name, higher_is_better=True, den=None, scale=100.0):
    """sk, ek: per-item values in the same item order (bools for right/wrong). den: per-item denominators for a ratio
    (e.g. actions per chain: 100 * sum(errors) / sum(actions)); otherwise the mean. Returns the comparison record."""
    n = len(sk)
    assert n == len(ek) and n > 0, (name, n, len(ek))
    d = den or [1] * n
    stat = lambda xs, idx: scale * sum(float(xs[i]) for i in idx) / sum(d[i] for i in idx)
    full = range(n)
    s, e = stat(sk, full), stat(ek, full)
    out = {"measure": name, "n": n, "skopos": s, "ekbasis27b": e, "difference": s - e,
           "higher_is_better": higher_is_better}
    if n >= MIN_N:
        rng = random.Random(SEED)
        diffs = []
        for _ in range(B):
            idx = [rng.randrange(n) for _ in range(n)]
            diffs.append(stat(sk, idx) - stat(ek, idx))
        diffs.sort()
        lo, hi = diffs[int(0.025 * B)], diffs[int(0.975 * B)]
        worse = hi < 0 if higher_is_better else lo > 0
        out.update({"ci95": [lo, hi], "rule": "paired bootstrap", "release_blocker": worse})
    else:
        ks, ke = sum(float(x) for x in sk), sum(float(x) for x in ek)
        out.update({"counts": [ks, ke], "rule": f"counts (n < {MIN_N})",
                    "flag_worse_by_2": (ke - ks >= 2) if higher_is_better else (ks - ke >= 2)})
    return out


def counts(name, sk, ek, n, higher_is_better=True):
    """Counts only (no per-item pairing possible, or a small cell)."""
    return {"measure": name, "n": n, "skopos": sk, "ekbasis27b": ek, "rule": "counts",
            "flag_worse_by_2": (ek - sk >= 2) if higher_is_better else (sk - ek >= 2)}


def summary(records):
    """The blockers and flags of a compare.py, for its JSON's top."""
    return {"release_blockers": [r["measure"] for r in records if r.get("release_blocker")],
            "flagged_worse_by_2": [r["measure"] for r in records if r.get("flag_worse_by_2")]}


def dump(path, obj):
    json.dump(obj, open(path, "w"), indent=1)
    print(json.dumps(obj.get("summary", {}), indent=1))
    print("wrote", path)
