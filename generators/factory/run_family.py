"""Run one family over a seed range in parallel; write rows (jsonl) and stats (json, with CPU time).
python3 run_family.py <family> <seed_start> <n_seeds> <out.jsonl> [workers]"""
import importlib
import json
import multiprocessing as mp
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def work(args):
    fam, seed = args
    mod = importlib.import_module(fam)
    try:
        return mod.make_items(seed)
    except Exception as e:  # noqa: BLE001
        return [], {"error": 1, "last_error": f"{type(e).__name__}: {e}"[:200]}


if __name__ == "__main__":
    fam, s0, n, out = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
    workers = int(sys.argv[5]) if len(sys.argv) > 5 else 32
    t0, c0 = time.time(), os.times()
    stats, n_rows = {}, 0
    with open(out, "w") as f, mp.Pool(workers) as pool:
        for rows, st in pool.imap_unordered(work, [(fam, s) for s in range(s0, s0 + n)], chunksize=4):
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
            n_rows += len(rows)
            for k, v in st.items():
                if isinstance(v, (int, float)):
                    stats[k] = stats.get(k, 0) + v
                else:
                    stats[k] = v
    c1 = os.times()
    cpu = (c1.children_user - c0.children_user) + (c1.children_system - c0.children_system) + \
          (c1.user - c0.user) + (c1.system - c0.system)
    stats.update({"family": fam, "seeds": [s0, s0 + n], "rows": n_rows, "wall_s": round(time.time() - t0, 1),
                  "cpu_s": round(cpu, 1), "rows_per_cpu_hour": round(n_rows / max(cpu, 1e-9) * 3600)})
    json.dump(stats, open(out.replace(".jsonl", ".stats.json"), "w"), indent=1)
    print(json.dumps(stats))
