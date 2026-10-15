"""M5 data: REAL git sequences of 5, 8 and 12 commands (gitbox3 executes them on a scratch repository for the exact
answers: lost work, failing commands, ...), no held command types, 2 questions per example ('lost'/'fails' favoured).
The lineage trained git on 1-3 commands only."""
import json, multiprocessing as mp, random, sys, tempfile, collections
sys.path.insert(0, "/Volumes/SSD Major/news/decision_model/conseq")
import gitbox3 as gitbox

OUT = "/Volumes/SSD Major/news/decision_model/mission/V50P/data/git_long.jsonl"

def work(args):
    seed, k, n = args
    root = tempfile.mkdtemp(prefix="gbx_long_")
    return gitbox.to_rows(random.Random(seed), n, steps=(k,), root=root)

if __name__ == "__main__":
    jobs = [(7000 + 100 * k + i, k, 15) for k in (5, 8, 12) for i in range(10)]
    with mp.get_context("fork").Pool(8) as pool:
        rows = [r for part in pool.map(work, jobs) for r in part]
    with open(OUT, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    c = collections.Counter((r["steps"], r["qtype"], str(r["gold"])) for r in rows)
    print("git_long", len(rows), dict(collections.Counter(r["steps"] for r in rows)))
    print({k: v for k, v in sorted(c.items()) if k[1] in ("lost", "fails")})
