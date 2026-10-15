"""The release read's failed criterion in detail: ftest_family, answers the actions change, each build against
Ekbasis-27B item by item (paired bootstrap, 2,000 resamples, seed 20261015; items lost and gained; per world), from the
per-item predictions. Written for publication (the same numbers RESULTS of the release read quoted).
    python3 ftest_paired.py <dir with the dataset's raw/ files>   -> ../release_read_ftest_paired.json"""
import collections
import json
import random
import sys
from pathlib import Path

RAW = Path(sys.argv[1])
RES = Path(__file__).resolve().parent.parent
L = lambda p: [json.loads(l) for l in open(p)]
n = lambda g: {True: "yes", False: "no"}[g] if isinstance(g, bool) else str(g)
rows, g0 = L(RAW / "ftest_family.jsonl"), L(RAW / "gold0_ftest_family.jsonl")
ch = [i for i, (r, g) in enumerate(zip(rows, g0)) if g["known"] and n(g["gold0"]) != n(r["gold"])]  # as compare_release.py


def ok(P):
    return [int(P[i]["ok"] if "ok" in P[i] else P[i]["pred"] == n(rows[i]["gold"])) for i in ch]


ref = ok(L(RES.parent / "results" / "release_eval" / "preds_ftest_family.jsonl"))
out = {"items_changed": len(ch)}
for build, d in (("bf16", "release_r4"), ("int4", "release_r4_int4"), ("fp8", "release_r4_fp8"), ("mlx", "release_r4_mlx")):
    a = ok(L(RES / "runs" / d / "preds_ftest_family.jsonl"))
    diff = [x - y for x, y in zip(a, ref)]
    rng = random.Random(20261015)
    v = sorted(sum(diff[rng.randrange(len(diff))] for _ in diff) / len(diff) for _ in range(2000))
    world = collections.defaultdict(lambda: [0, 0, 0])
    for i, x, y in zip(ch, a, ref):
        w = world[rows[i]["world"]]
        w[0] += 1; w[1] += x; w[2] += y
    out[build] = {"skopos": 100 * sum(a) / len(a), "ekbasis27b": 100 * sum(ref) / len(ref), "diff": 100 * sum(diff) / len(diff),
                  "ci95": [100 * v[50], 100 * v[1949]], "lost": sum(x < y for x, y in zip(a, ref)),
                  "gained": sum(x > y for x, y in zip(a, ref)),
                  "by_world": {k: {"n": w[0], "skopos": w[1], "ekbasis27b": w[2]} for k, w in sorted(world.items())}}
json.dump(out, open(RES / "release_read_ftest_paired.json", "w"), indent=1)
print(json.dumps({b: {k: out[b][k] for k in ("diff", "ci95", "lost", "gained")} for b in ("bf16", "int4", "fp8", "mlx")}))
