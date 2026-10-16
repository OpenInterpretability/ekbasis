"""V50R1 training data: real git sequences of 4-16 commands (gitbox3 executes them for exact answers), kind
floorPLG, seeds 9000+, firewalled against the git_long test (seeds 7000+) and the git3/guard test floors."""
import json, multiprocessing as mp, random, sys, tempfile, collections
sys.path.insert(0, "/root/conseq")
import gitbox3 as gitbox
TEST = ["/root/v50p/data/git_long.jsonl", "/root/v50p/data/git3_test_known.jsonl", "/root/v50p/data/git3_test_held.jsonl",
        "/root/v50p/data/guard_known.jsonl"]
def work(args):
    seed, k, n = args
    return gitbox.to_rows(random.Random(seed), n, steps=(k,), root=tempfile.mkdtemp(prefix="gbx_tr_"))
if __name__ == "__main__":
    test_floors = {json.loads(l)["floor"] for p in TEST for l in open(p)}
    jobs = [(9000 + 1000 * k + i, k, 12) for k in (4, 5, 6, 8, 10, 12, 16) for i in range(36)]
    with mp.get_context("fork").Pool(28) as pool:
        rows = [r for part in pool.map(work, jobs) for r in part]
    kept = [dict(r, kind="floorPLG") for r in rows if r["floor"] not in test_floors]
    with open("/root/v50p/data/git_plan_train.jsonl", "w") as f:
        for r in kept: f.write(json.dumps(r) + "\n")
    print("git_plan_train", len(kept), "dropped", len(rows) - len(kept), dict(collections.Counter(r["steps"] for r in kept)))
