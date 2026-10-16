"""Learnability check data: ftrain_m3only = only the change-balanced factory-3 items of ftrain_cb3b (floor + read);
m3val = 300 new change-balanced factory-3 items (no held pair) to choose its checkpoint. argv: data dir."""
import collections, json, random, sys
from pathlib import Path
from worldgen3 import m3balanced

D = Path(sys.argv[1])
rows = [r for r in (json.loads(l) for l in open(D / "ftrain_cb3b.jsonl")) if r.get("world") == "mech3"]
with open(D / "ftrain_m3only.jsonl", "w") as f:
    for r in rows:
        f.write(json.dumps(r) + "\n")
print("ftrain_m3only", len(rows), dict(collections.Counter(r["kind"] for r in rows)))
seen = {r["floor"] for r in rows} | {json.loads(l)["floor"] for t in ("m3test_held", "m3test_known") for l in open(D / f"{t}.jsonl")}
rng = random.Random(71)
val = [ex for s in (1, 2, 3) for ex in m3balanced(s, 100, rng, "exclude", change_balance=True) if ex["floor"] not in seen]
with open(D / "m3val.jsonl", "w") as f:
    for r in val:
        f.write(json.dumps(r) + "\n")
print("m3val", len(val))
