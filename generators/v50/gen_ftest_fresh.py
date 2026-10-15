"""CONFIRM_FTEST: fresh never-trained-family items (Cards, Timers, Machines), exactly ftest_family's recipe
(gen_factory.py: every question type, 1/2/3 actions, fbalanced without change_balance) at 5x the size (200 per cell),
seed string 'ftest-fresh-20261015' (never used), firewalled against every file in /root/v50p/data.
    python3 gen_ftest_fresh.py OUT.jsonl"""
import glob, hashlib, json, random, sys
sys.path.insert(0, "/root/v50p/worldgen")
from worldgen import TEST, fbalanced
seen = set()
for p in glob.glob("/root/v50p/data/*.jsonl"):
    for l in open(p):
        try:
            seen.add(hashlib.sha1(json.loads(l)["floor"].encode()).hexdigest())
        except Exception:
            pass
rng = random.Random("ftest-fresh-20261015")
rows = [ex for F in TEST for q in F.QTYPES for s in (1, 2, 3) for ex in fbalanced(F, s, q, rng, 200)]
kept = [r for r in rows if hashlib.sha1(r["floor"].encode()).hexdigest() not in seen]
with open(sys.argv[1], "w") as f:
    for r in kept:
        f.write(json.dumps(r) + "\n")
ch = sum(1 for r in kept if r.get("known0") and r.get("gold0") is not None and str(r["gold0"]) != str(r["gold"]))
print("ftest_fresh", len(kept), "dropped", len(rows) - len(kept), "changed", ch)
