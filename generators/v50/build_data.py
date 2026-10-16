"""V50 pilot data. (1) fhorizon: the horizon test exactly as conseq/gen_horizon.py builds it (seed 81, training
families, new worlds, 1/2/3/5/8/12/20 actions, change-balanced), excluding floors seen in ftrain_mixG3. (2) floorPL:
long sequences (4/5/6/8/10/12/16 actions) in the training families (factory 1) and factory 3, seed 4501, firewalled:
no floor equal to a fhorizon floor. (3) ftrain_v50p = ftrain_mixG3 + floorPL. Writes into data/."""
import collections, json, random, sys
sys.path.insert(0, "/Volumes/SSD Major/news/decision_model/conseq")
from worldgen import TRAIN, fbalanced
from worldgen3 import m3balanced

D = "/Volumes/SSD Major/news/decision_model/mission/V50P/data"
base = [json.loads(l) for l in open(f"{D}/ftrain_mixG3.jsonl")]
seen = {r["floor"] for r in base if isinstance(r.get("floor"), str)}
tq = lambda F: [q for q in F.QTYPES if q != F.HELD_Q]

rng = random.Random(81)
hz = [ex for k in (1, 2, 3, 5, 8, 12, 20) for F in TRAIN for q in tq(F)
      for ex in fbalanced(F, k, q, rng, 10, change_balance=True) if ex["floor"] not in seen]
with open(f"{D}/fhorizon.jsonl", "w") as f:
    for r in hz:
        f.write(json.dumps(r) + "\n")
test_floors = {r["floor"] for r in hz}
print("fhorizon", len(hz), dict(sorted(collections.Counter(r["steps"] for r in hz).items())))

rng = random.Random(4501)
pl, dropped = [], 0
for k in (4, 5, 6, 8, 10, 12, 16):
    cand = [ex for F in TRAIN for q in tq(F) for ex in fbalanced(F, k, q, rng, 25, change_balance=True)]
    cand += m3balanced(k, 120, rng, "exclude", change_balance=True)
    for ex in cand:
        if ex["floor"] in test_floors or ex["floor"] in seen:
            dropped += 1
            continue
        pl.append(dict(ex, kind="floorPL"))
random.Random(4502).shuffle(pl)
print("floorPL", len(pl), "dropped by firewall", dropped, dict(sorted(collections.Counter(int(r["steps"]) for r in pl).items())))
with open(f"{D}/ftrain_v50p.jsonl", "w") as f:
    for r in base + pl:
        f.write(json.dumps(r) + "\n")
print("ftrain_v50p", len(base) + len(pl))
