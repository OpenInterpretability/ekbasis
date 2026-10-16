"""The git v3 test sets per question type, Skopos (release read, served bf16) against Ekbasis-27B (its release
evaluation) on the same items: accuracy of each and the paired 95% bootstrap of the difference (2,000 resamples of
items, seed 20261015; percentile interval at int(0.025 B) and int(0.975 B), as in the pre-launch evaluation's rule).
Written for publication; it reads only the per-item predictions (each carries its gold and question type). Added after
the independent review (Part C) asked for the Ekbasis-27B column; the pre-launch evaluation (P2) computed the same.
    python3 git3_by_type_paired.py <results_skopos/runs/release_r4> <results/release_eval> <out.json>"""
import collections
import json
import random
import sys

SK, EK, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
B, SEED = 2000, 20261015


def paired(a, b):
    n = len(a)
    s, e = 100 * sum(a) / n, 100 * sum(b) / n
    rng = random.Random(SEED)
    d = sorted(100 * sum(a[i] - b[i] for i in idx) / n
               for idx in ([rng.randrange(n) for _ in range(n)] for _ in range(B)))
    return {"n": n, "skopos": s, "ekbasis": e, "diff": s - e, "ci": [d[int(0.025 * B)], d[int(0.975 * B)]]}


out = {"method": __doc__.split("\n")[0] + " " + __doc__.split("\n")[1], "sets": {}}
for split in ("git3_test_known", "git3_test_held"):
    S = [json.loads(l) for l in open(f"{SK}/preds_{split}.jsonl")]
    E = [json.loads(l) for l in open(f"{EK}/preds_{split}.jsonl")]
    assert len(S) == len(E) and all(x["gold"] == y["gold"] and x["qtype"] == y["qtype"] for x, y in zip(S, E)), split
    ok = lambda P, I: [int(P[i]["pred"] == P[i]["gold"]) for i in I]
    by = collections.defaultdict(list)
    for i, p in enumerate(S):
        by[p["qtype"]].append(i)
    for key, idx in [("all", list(range(len(S))))] + sorted(by.items()):
        out["sets"][f"{split}:{key}"] = paired(ok(S, idx), ok(E, idx))
json.dump(out, open(OUT, "w"), indent=1)
for k, d in out["sets"].items():
    print(f"{k:30s} n={d['n']:5d} Skopos {d['skopos']:6.2f} Ekbasis-27B {d['ekbasis']:6.2f} "
          f"diff {d['diff']:+.2f} [{d['ci'][0]:+.2f}, {d['ci'][1]:+.2f}]")
