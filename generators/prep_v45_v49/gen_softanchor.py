"""V48's fresh guard-like git items (PLAN_v48): the anchor's generator (gen_git3 / gitbox3, real git in throwaway
repositories), mode "known" (the held command types rebase and restore_old stay held out), only "lost" and "fails",
balanced yes/no with gen_git3.balance, minus every row whose floor appears in any file of /dev/shm/conseq/fac (gen_anchor's
rule; the Addendum 8 firewall against every evaluation file follows in audit_v48.py).
  /usr/bin/python3 gen_softanchor.py soft <out.jsonl>   seeds 4810000-4810239, 6,000 requested (v48k / v48r: w4a5's targets)
  /usr/bin/python3 gen_softanchor.py cal  <out.jsonl>   seeds 4820000-4820239, 3,000 requested (v48c: the calibration slice)
  /usr/bin/python3 gen_softanchor.py cal2 <out.jsonl>   seeds 4820240-4820479, 6,000 requested (Addendum B: more "lost" rows)"""
import collections
import json
import os
import random
import sys
from pathlib import Path

sys.path.insert(0, "/root/decis/conseq")
import gen_git3 as G  # noqa: E402

WHICH, OUT = sys.argv[1], sys.argv[2]
SEED0, N, RNG, KIND = {"soft": (4810000, 6000, 48, "v48soft"), "cal": (4820000, 3000, 49, "v48cal"),
                       "cal2": (4820240, 6000, 50, "v48cal")}[WHICH]  # cal2: PLAN_v48 Addendum B
FAC = Path("/dev/shm/conseq/fac")
seen = set()
for f in sorted(FAC.glob("*.jsonl")):
    with open(f) as fh:
        for line in fh:
            if '"floor"' not in line:
                continue
            r = json.loads(line)
            if isinstance(r.get("floor"), str):
                seen.add(r["floor"])
print(f"floors in the data folder: {len(seen)} distinct", flush=True)
os.makedirs(G.ROOT, exist_ok=True)
os.chmod(G.ROOT, 0o755)
rows = G.gen("known", N, SEED0, chunks=240)
n0 = len(rows)
held = sum(1 for r in rows if set(r.get("kinds") or []) & {"rebase", "restore_old"})
rows = [r for r in rows if r["floor"] not in seen and not set(r.get("kinds") or []) & {"rebase", "restore_old"}]
n1 = len(rows)
uniq, keep = set(), []
for r in rows:
    k = (r["floor"], json.dumps(r["question"], sort_keys=True))
    if k not in uniq:
        uniq.add(k)
        keep.append(r)
rows = [dict(r, kind=KIND) for r in G.balance(keep, random.Random(RNG)) if r["qtype"] in ("lost", "fails")]
with open(OUT, "w") as fh:
    for r in rows:
        fh.write(json.dumps(r) + "\n")
c = collections.Counter((r["qtype"], r["gold"]) for r in rows)
print(json.dumps({"which": WHICH, "seeds": [SEED0, SEED0 + 239], "generated_question_rows": n0, "with_held_kind": held,
                  "dropped_floor_seen_or_held": n0 - n1, "duplicates": n1 - len(keep), "kept": len(rows),
                  "by_qtype_gold": {f"{a}:{b}": v for (a, b), v in sorted(c.items(), key=str)}}), flush=True)
