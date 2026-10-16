"""PLAN_guard_set.md: a larger guard set from the git3 generator (gitbox3: real git in throwaway repositories), with seeds
no git generator has used, balanced like git3_test_known/held, only the guard's questions ("lost", "fails"), minus any
example whose state and commands appear in an existing training, validation or test file. argv: fac dir (read and written)"""
import collections
import json
import os
import random
import sys
from pathlib import Path

sys.path.insert(0, "/root/decis/conseq")
import gen_git3 as G  # noqa: E402  (gen(), balance(); the generator's scratch root)

FAC = Path(sys.argv[1])
seen, per_file = set(), {}
for f in sorted(FAC.glob("*.jsonl")):
    if f.name.startswith("guard_"):
        continue
    n = 0
    with open(f) as fh:
        for line in fh:
            if '"git' not in line and "floorG" not in line:
                continue
            r = json.loads(line)
            if r.get("world") == "git" or str(r.get("kind", "")).startswith("floorG"):
                seen.add(r["floor"])
                n += 1
    if n:
        per_file[f.name] = n
print(f"git items in existing files: {sum(per_file.values())} ({len(seen)} distinct states) in {len(per_file)} files", flush=True)

os.makedirs(G.ROOT, exist_ok=True)
os.chmod(G.ROOT, 0o755)
rng = random.Random(29)
for name, mode, seed0 in (("guard_known", "known", 2910000), ("guard_held", "held", 2960000)):
    rows = G.gen(mode, 20000, seed0, chunks=240)
    n0 = len(rows)
    rows = [r for r in rows if r["floor"] not in seen]
    n1 = len(rows)
    uniq, keep = set(), []
    for r in rows:
        k = (r["floor"], json.dumps(r["question"], sort_keys=True))
        if k not in uniq:
            uniq.add(k)
            keep.append(r)
    rows = [r for r in G.balance(keep, rng) if r["qtype"] in ("lost", "fails")]
    with open(FAC / f"{name}.jsonl", "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    c = collections.Counter((r["qtype"], r["gold"]) for r in rows)
    print(f"{name}: generated {n0} question rows; {n0 - n1} dropped (state seen in an existing file), {n1 - len(keep)} duplicates; "
          f"kept {len(rows)}: {dict(sorted(c.items(), key=str))}", flush=True)
