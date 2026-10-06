"""WS-PI: the same rules as pi_overlap.py (WS-F eval_masks rules), with the hit attributed to each training file:
for every evaluation row, whether its floor is identical to a row of file F, and the best Jaccard against a single row
of file F (top 20 candidates per file). Needed because different public claims rest on different training files:
V42's numbers on ftrain_mixG3; the release's (w4a5) on ftrain_mixG3 + mined_wide + mined_chain; the paper's repair
rounds on their own mined sets (mined_err, mined_conf, mined_hard, mined_wide).

usage: PYTHONHASHSEED=0 python pi_overlap_byfile.py OUT.json split [split ...]
env:   PI_TRAIN  comma-separated training files in /dev/shm/conseq/fac (default: the lineage and every mined set)"""
from __future__ import annotations

import collections
import json
import multiprocessing as mp
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pi_overlap import FAC, load, norm, shingles, text  # noqa: E402  (same rules)

TRAIN = os.environ.get("PI_TRAIN", "ftrain_mixG3,mined_wide,mined_chain,mined_err,mined_conf,mined_hard").split(",")


def shard_worker(args):
    name, lo, hi, want = args
    out = []
    with open(f"{FAC}/{name}.jsonl") as f:
        for i, line in enumerate(f):
            if i < lo:
                continue
            if i >= hi:
                break
            r = json.loads(line)
            full = shingles(text(r.get("floor", "")))
            hit = full & want
            if hit:
                out.append((name, i, len(full), list(hit)))
    return out


def main():
    out_path, splits = sys.argv[1], sys.argv[2:]
    long_h = collections.defaultdict(set)
    universe = set()
    sizes_by_file = {}
    for n in TRAIN:
        rows = load(n)
        sizes_by_file[n] = len(rows)
        for r in rows:
            long_h[hash(norm(text(r.get("floor", ""))))].add(n)
            if r.get("ceiling"):
                long_h[hash(norm(text(r["ceiling"])))].add(n)
            universe |= shingles(text(r.get("floor", "")))
        del rows
    print(sizes_by_file, "shingles", len(universe), flush=True)
    ev, cands = {}, {}
    for sp in splits:
        rows = load(sp)
        step = max(1, len(rows) // 1500)
        c = collections.Counter()
        for r in rows[::step]:
            c.update(shingles(text(r["floor"])))
        n_s = len(rows[::step])
        lay = {g for g, k in c.items() if k >= 0.2 * n_s}
        for r in rows:
            qs = r.get("questions") if "questions" in r else [r.get("question")]
            for q in qs or []:
                lay |= shingles(q.get("instructions", "") if isinstance(q, dict) else "")
        flags, cand = [], []
        for i, r in enumerate(rows):
            fl = text(r["floor"])
            f = {"i": i, "identical_in": sorted(long_h.get(hash(norm(fl)), set())), "J": {}}
            s = shingles(fl) - lay
            if len(s) >= 10 and sum(g in universe for g in s) / len(s) >= 0.5:
                cand.append((i, s))
            flags.append(f)
        ev[sp], cands[sp] = flags, cand
        print(sp, len(rows), "near candidates", len(cand), flush=True)
    want = set()
    for cand in cands.values():
        for _, s in cand:
            want |= s
    jobs = []
    for n, size_n in sizes_by_file.items():
        k = 32
        size = (size_n + k - 1) // k
        jobs += [(n, a, min(size_n, a + size), want) for a in range(0, size_n, size)]
    with mp.Pool(64) as pool:
        parts = pool.map(shard_worker, jobs, chunksize=1)
    index, sizes, files = collections.defaultdict(list), [], []
    for part in parts:
        for n, i, size, hit in part:
            k = len(sizes)
            sizes.append(size)
            files.append(n)
            for g in hit:
                index[g].append(k)
    for sp, cand in cands.items():
        for i, s in cand:
            cnt = collections.Counter(k for g in s for k in index.get(g, []))
            per = collections.defaultdict(list)
            for k, inter in cnt.most_common():
                if len(per[files[k]]) < 20:
                    per[files[k]].append((k, inter))
            ev[sp][i]["J"] = {fname: round(max(inter / (len(s) + sizes[k] - inter) for k, inter in lst), 4)
                              for fname, lst in per.items()}
        rep = {}
        for fname in TRAIN:
            ident = sum(fname in f["identical_in"] for f in ev[sp])
            near = sum((fname not in f["identical_in"]) and f["J"].get(fname, 0) >= 0.5 for f in ev[sp])
            rep[fname] = {"identical": ident, "near": near}
        print(sp, json.dumps(rep), flush=True)
    json.dump({"training": TRAIN, "flags": ev}, open(out_path, "w"))


if __name__ == "__main__":
    main()
