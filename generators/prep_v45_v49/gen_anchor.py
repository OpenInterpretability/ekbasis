"""V46 anchor (PLAN_v45 Addendum 4, item 2): fresh rows from the guard sets' own generator (gen_git3 / gitbox3, real git in
throwaway repositories), mode "known" (no held command type: rebase, restore_old), seeds 4610000-4610239 (unused by every
git generator), 10,000 examples requested, only "lost" and "fails", balanced yes/no with gen_git3.balance (rng 46), minus
every example whose floor appears in any file of /dev/shm/conseq/fac (guard_known and guard_held included).
/usr/bin/python3 gen_anchor.py <out.jsonl>   (rows keep the generator's fields; kind floorGA)"""
import collections
import json
import os
import random
import sys
from pathlib import Path

sys.path.insert(0, "/root/decis/conseq")
import gen_git3 as G  # noqa: E402

OUT = sys.argv[1]
FAC = Path("/dev/shm/conseq/fac")
seen, per_file = set(), {}
for f in sorted(FAC.glob("*.jsonl")):
    n = 0
    with open(f) as fh:
        for line in fh:
            if '"floor"' not in line:
                continue
            r = json.loads(line)
            if isinstance(r.get("floor"), str):  # (a few files keep a structured floor: not a git state)
                seen.add(r["floor"])
                n += 1
    per_file[f.name] = n
print(f"floors in the data folder: {len(seen)} distinct, from {sum(per_file.values())} rows in {len(per_file)} files", flush=True)
os.makedirs(G.ROOT, exist_ok=True)
os.chmod(G.ROOT, 0o755)
rows = G.gen("known", 10000, 4610000, chunks=240)
n0 = len(rows)
held = sum(1 for r in rows if set(r.get("kinds") or []) & {"rebase", "restore_old"})
rows = [r for r in rows if r["floor"] not in seen]
n1 = len(rows)
uniq, keep = set(), []
for r in rows:
    k = (r["floor"], json.dumps(r["question"], sort_keys=True))
    if k not in uniq:
        uniq.add(k)
        keep.append(r)
rows = [dict(r, kind="floorGA") for r in G.balance(keep, random.Random(46)) if r["qtype"] in ("lost", "fails")]
with open(OUT, "w") as fh:
    for r in rows:
        fh.write(json.dumps(r) + "\n")
c = collections.Counter((r["qtype"], r["gold"]) for r in rows)
kinds = collections.Counter(k for r in rows for k in set(r.get("kinds") or []))
print(json.dumps({"generated_question_rows": n0, "with_held_kind": held, "dropped_floor_seen": n0 - n1,
                  "duplicates": n1 - len(keep), "kept": len(rows), "by_qtype_gold": {f"{a}:{b}": v for (a, b), v in sorted(c.items(), key=str)},
                  "families": len(kinds), "reset_merge": kinds.get("reset_merge", 0), "stash_drop": kinds.get("stash_drop", 0)}), flush=True)
