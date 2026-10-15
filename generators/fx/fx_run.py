"""Run one FX family over a seed range until a row cap, in parallel; gzip-compressed rows + stats with CPU time.
python3 fx_run.py <family> <part: train|val|eval> <cap_rows> <out.jsonl.gz> [workers] [max_seeds]
Each row gets fx_family, fx_split, fx_seed and an id prefixed with the family and part (twins too)."""
import gzip
import importlib
import json
import multiprocessing as mp
import os
import random
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fx_registry import CORE, SEEDS, split_of  # noqa: E402
from common import stable_seed  # noqa: E402

NEW = {}  # family -> (module, allowed) for FX-built families, filled by fx_new_registry if present
try:
    from fx_new_registry import NEW  # noqa: F401,E402
except Exception:  # noqa: BLE001
    pass


def spec(family):
    if family in CORE:
        return CORE[family]
    return NEW[family]


def branch_k(family):
    """Addendum 3: K alternative actions at the same state (core shell/git K=2, FX-built shell K=3)."""
    modname = spec(family)[0]
    if family in CORE and modname in ("shell", "gitfam"):
        return 2
    if modname == "fx_shell_new":
        return 3
    return 1


def work(args):
    family, seed = args
    modname, allowed = spec(family)
    mod = importlib.import_module(modname)
    K = branch_k(family)
    try:
        if K == 1:
            return seed, mod.make_items(seed, allowed)
        rng = random.Random(stable_seed("fx_branch", family, seed))
        order = list(allowed)
        rng.shuffle(order)
        rows_all, stats, k = [], {}, 0
        for name in order:
            if k >= K:
                break
            rows, st = mod.make_items(seed, [name])
            for kk, vv in st.items():
                stats[kk] = stats.get(kk, 0) + vv if isinstance(vv, (int, float)) else vv
            if not rows:
                continue
            for r in rows:
                r["id"] = f"b{k}-" + r["id"]
                if r.get("twin"):
                    r["twin"] = f"b{k}-" + r["twin"]
                r["fx_branch"], r["fx_branch_k"] = f"{family}-{seed}", k
            rows_all += rows
            k += 1
        stats["branches"] = k
        stats["states"] = 1 if k else 0
        return seed, (rows_all, stats)
    except Exception as e:  # noqa: BLE001
        return seed, ([], {"error": 1, "last_error": f"{type(e).__name__}: {e}"[:200]})


def free_gb(path):
    return shutil.disk_usage(path).free / 1e9


if __name__ == "__main__":
    family, part, cap, out = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
    workers = int(sys.argv[5]) if len(sys.argv) > 5 else 48
    max_seeds = int(sys.argv[6]) if len(sys.argv) > 6 else 200_000
    # FX writes its rows to the RAM disk (data -> /dev/shm/fx/data) so WS-F keeps the root disk; guard that disk instead
    if free_gb(os.path.dirname(os.path.realpath(out))) < 8 or free_gb("/dev/shm") < 8:
        print(json.dumps({"family": family, "stopped": "low disk", "out_free_gb": round(free_gb(os.path.dirname(os.path.realpath(out))), 1)}))
        sys.exit(2)
    split = split_of(family) if part != "val" else "val"
    if part in ("val", "trainplus") and split_of(family) != "train":
        sys.exit("val/trainplus are only for train families")
    s0 = SEEDS["trainplus" if part == "trainplus" else ("val" if part == "val" else ("eval" if split.startswith("eval") else "train"))]
    if family.startswith("se_") or family == "mm_side_effects":
        s0 += 4_000_000  # Addendum 5: side-effect families have their own seed ranges (24M train, 25M val, 26M eval)
    t0, c0 = time.time(), os.times()
    stats, n_rows, n_seeds = {}, 0, 0
    tmp = out + ".part"
    batch = max(64, workers * 8)
    with gzip.open(tmp, "wt") as f, mp.Pool(workers) as pool:
        nxt = s0
        while n_rows < cap and nxt < s0 + max_seeds:
            seeds = list(range(nxt, min(nxt + batch, s0 + max_seeds)))
            nxt += len(seeds)
            for seed, (rows, st) in sorted(pool.map(work, [(family, s) for s in seeds], chunksize=2), key=lambda x: x[0]):
                n_seeds += 1
                for k, v in st.items():
                    stats[k] = stats.get(k, 0) + v if isinstance(v, (int, float)) else v
                if n_rows >= cap:
                    continue
                for r in rows:
                    pre = f"fx-{family}-{part}-"
                    r["id"] = pre + r["id"]
                    if r.get("twin"):
                        r["twin"] = pre + r["twin"]
                    r["fx_family"], r["fx_split"], r["fx_seed"] = family, split, seed
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
                n_rows += len(rows)
    os.replace(tmp, out)
    c1 = os.times()
    cpu = (c1.children_user - c0.children_user) + (c1.children_system - c0.children_system) + (c1.user - c0.user) + \
          (c1.system - c0.system)
    stats.update({"family": family, "part": part, "split": split, "seed_base": s0, "seeds_used": n_seeds, "rows": n_rows,
                  "wall_s": round(time.time() - t0, 1), "cpu_s_parent_view": round(cpu, 1)})
    json.dump(stats, open(out.replace(".jsonl.gz", ".stats.json"), "w"), indent=1)
    print(json.dumps(stats))
