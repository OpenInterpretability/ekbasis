"""Datasets of the world factory (worldgen.py). Out dir argv[1]:
- ftrain.jsonl: TRAIN families (a new world per example), trained question types, 1-3 actions, kind "floor"; plus
  "read" items (the ceiling prompt as input: reading a true outcome) and "replay" items from the Eikos training
  snapshot (soft teacher targets), so training does not narrow the model;
- fval.jsonl: VAL families, to choose checkpoints;
- ftest_in / ftest_newq (held question type) / ftest_long (5 actions) / ftest_family (TEST families, never seen).
argv: out N_per_cell [snapshot dir]"""
import collections, glob, hashlib, json, os, random, sys
from pathlib import Path
from worldgen import TEST, TRAIN, VAL, fbalanced

OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
N = int(sys.argv[2]) if len(sys.argv) > 2 else 800
SNAP = sys.argv[3] if len(sys.argv) > 3 else "/root/decis/jb/snap_final1"
h = lambda ex: hashlib.sha1(ex["floor"].encode()).hexdigest()


def dump(name, rows):
    with open(OUT / name, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print(f"{name}: {len(rows)}  {dict(collections.Counter(r.get('kind', 'floor') for r in rows))}", flush=True)


rng = random.Random(21)
trained_q = lambda F: [q for q in F.QTYPES if q != F.HELD_Q]
floor = [dict(ex, kind="floor") for F in TRAIN for q in trained_q(F) for s in (1, 2, 3) for ex in fbalanced(F, s, q, rng, N)]
read = [dict(ex, kind="read") for F in TRAIN for q in trained_q(F) for s in (1, 2, 3)
        for ex in fbalanced(F, s, q, rng, max(4, N // 6))]
replay = []
if os.path.isdir(SNAP):
    for f in sorted(glob.glob(f"{SNAP}/*.jsonl")):
        if "long_items" in f:
            continue
        for l in open(f):
            ex = json.loads(l)
            if not ex.get("teacher_probs") or len(ex.get("state") if isinstance(ex.get("state"), str) else json.dumps(ex.get("state", ""))) > 2500:
                continue
            replay.append({"kind": "replay", "world": "eikos", "qtype": ex.get("family", "?"), "steps": 0,
                           "floor": ex["state"], "question": ex["question"], "probs": ex["teacher_probs"],
                           "gold": ex.get("teacher_top")})
    random.Random(22).shuffle(replay)
    replay = replay[:int(0.18 / 0.70 * len(floor))]
train = floor + read + replay
random.Random(23).shuffle(train)
seen = {h(ex) for ex in floor + read}
dump("ftrain.jsonl", train)
rng = random.Random(24)
dump("fval.jsonl", [ex for F in VAL for q in F.QTYPES for s in (1, 2, 3) for ex in fbalanced(F, s, q, rng, 25)])
rng = random.Random(25)
splits = {
    "ftest_in.jsonl": [(F, q, s, 30) for F in TRAIN for q in trained_q(F) for s in (1, 2, 3)],
    "ftest_newq.jsonl": [(F, F.HELD_Q, s, 45) for F in TRAIN for s in (1, 2, 3)],
    "ftest_long.jsonl": [(F, q, 5, 30) for F in TRAIN for q in trained_q(F)],
    "ftest_family.jsonl": [(F, q, s, 40) for F in TEST for q in F.QTYPES for s in (1, 2, 3)],
}
for name, cells in splits.items():
    dump(name, [ex for F, q, s, n in cells for ex in fbalanced(F, s, q, rng, n) if h(ex) not in seen])
