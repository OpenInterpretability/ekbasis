"""Horizon test: how many actions ahead can the model predict? Factory-1 training families (new worlds), trained
question types, 1/2/3/5/8/12/20 actions, change-balanced where the initial answer is defined (half the answers change).
Writes fac/fhorizon.jsonl and its gold0 sidecar. argv: data dir."""
import collections, json, random, sys
from pathlib import Path
from worldgen import TRAIN, fbalanced

D = Path(sys.argv[1])
seen = {r["floor"] for t in ("ftrain", "ftrain_cb") for r in map(json.loads, open(D / f"{t}.jsonl")) if isinstance(r["floor"], str)}
rng = random.Random(81)
tq = lambda F: [q for q in F.QTYPES if q != F.HELD_Q]
rows = [ex for k in (1, 2, 3, 5, 8, 12, 20) for F in TRAIN for q in tq(F)
        for ex in fbalanced(F, k, q, rng, 10, change_balance=True) if ex["floor"] not in seen]
with open(D / "fhorizon.jsonl", "w") as f, open(D / "gold0_fhorizon.jsonl", "w") as g:
    for r in rows:
        f.write(json.dumps(r) + "\n")
        g.write(json.dumps({"gold0": r["gold0"], "known": r["known0"]}) + "\n")
c = collections.Counter(r["steps"] for r in rows)
ch = collections.Counter(r["steps"] for r in rows if r["known0"] and r["gold0"] != r["gold"])
print("fhorizon", len(rows), {k: f"{c[k]} ({ch[k]} changed)" for k in sorted(c)})
