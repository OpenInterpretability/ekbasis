"""Validation twin of git_long (for diagnosis and design, so the test is never used to pick a recipe): real git
sequences of 5/8/12 commands executed by gitbox3, seeds 40000+, firewalled against git_long, git_plan_train and the
git3/guard floors."""
import json, multiprocessing as mp, random, sys, tempfile, collections
sys.path.insert(0, "/root/conseq")
import gitbox3 as gitbox
OTHER = ["git_long", "git_plan_train", "git3_test_known", "git3_test_held", "guard_known", "fval_git3"]
def work(args):
    seed, k, n = args
    return gitbox.to_rows(random.Random(seed), n, steps=(k,), root=tempfile.mkdtemp(prefix="gbx_val_"))
if __name__ == "__main__":
    other = {json.loads(l)["floor"] for p in OTHER for l in open(f"/root/v50p/data/{p}.jsonl")}
    jobs = [(40000 + 1000 * k + i, k, 12) for k in (5, 8, 12) for i in range(25)]
    with mp.get_context("fork").Pool(12) as pool:
        rows = [r for part in pool.map(work, jobs) for r in part]
    kept = [r for r in rows if r["floor"] not in other]
    with open("/root/v50p/data/git_long_val.jsonl", "w") as f:
        for r in kept: f.write(json.dumps(r) + "\n")
    print("git_long_val", len(kept), "dropped", len(rows) - len(kept), dict(collections.Counter(r["steps"] for r in kept)),
          dict(collections.Counter(r["qtype"] for r in kept)))
