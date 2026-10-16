"""Git v3 data (gitbox3.py: v2 plus the per-branch differences in the state, more command types), in parallel worker processes. Writes to <out>:
git_train.jsonl (kind floorG; no held command types; 'lost' and 'fails' balanced yes/no), git_test_known.jsonl (new
examples, no held command types), git_test_held.jsonl (every example uses a held command type: git clean -fd,
git stash drop, git reset --hard HEAD~1, git checkout -- .), and their gold0 sidecars. argv: out dir, n train examples."""
import collections, json, multiprocessing as mp, os, random, sys
from pathlib import Path
import gitbox3 as gitbox

OUT, N = (Path(sys.argv[1]), int(sys.argv[2])) if __name__ == "__main__" else (None, 0)
ROOT = "/dev/shm/gbx3"


def work(args):
    seed, n, mode = args
    rng = random.Random(seed)
    return gitbox.to_rows(rng, n, steps=(1, 2, 3), allow_held=mode == "held", require_held=mode == "held", root=ROOT)


def gen(mode, n, seed0, chunks=96):
    per = max(1, n // chunks)
    with mp.Pool(min(120, os.cpu_count() or 8)) as pool:
        parts = pool.map(work, [(seed0 + i, per, mode) for i in range(chunks)])
    return [r for p in parts for r in p]


def balance(rows, rng):
    """'lost' and 'fails': as many yes as no (all of the rarer answer kept); other question types unchanged."""
    out = [r for r in rows if r["qtype"] not in ("lost", "fails")]
    for qt in ("lost", "fails", "in_progress"):
        yes = [r for r in rows if r["qtype"] == qt and r["gold"]]
        no = [r for r in rows if r["qtype"] == qt and not r["gold"]]
        rng.shuffle(no)
        out += yes + no[:len(yes)]
    rng.shuffle(out)
    return out


def write(name, rows, kind=None):
    with open(OUT / f"{name}.jsonl", "w") as f, open(OUT / f"gold0_{name}.jsonl", "w") as g:
        for r in rows:
            f.write(json.dumps(dict(r, kind=kind) if kind else r) + "\n")
            g.write(json.dumps({"gold0": r["gold0"], "known": r["known0"]}) + "\n")
    c = collections.Counter(r["qtype"] for r in rows)
    pos = {qt: sum(1 for r in rows if r["qtype"] == qt and r["gold"] is True) for qt in ("lost", "fails")}
    print(f"{name}: {len(rows)} rows {dict(c)} yes: {pos}", flush=True)


if __name__ == "__main__":
    os.makedirs(ROOT, exist_ok=True)
    os.chmod(ROOT, 0o755)
    rng = random.Random(5)
    write("git3_test_known", balance(gen("known", 1000, 1910000, chunks=120), rng))
    write("git3_test_held", balance(gen("held", 1000, 1960000, chunks=120), rng))
    write("git3_val", balance(gen("known", 500, 1980000, chunks=120), rng))
    write("git3_train", balance(gen("train", N, 1003000, chunks=240), rng), kind="floorG3")
