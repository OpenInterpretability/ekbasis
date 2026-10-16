"""Adds to pool_items.jsonl the release evaluation's "changed state" flag of each git v3 row (release_eval.py: a question
other than lost / fails / in_progress whose answer before the commands is known and differs from the answer after)."""
import json, os
from pathlib import Path

HERE = Path(__file__).parent
RAW = Path(os.environ.get("RS", ".")) / "audit/hf/ekbasis-data/raw"
norm = lambda g: {True: "yes", False: "no"}[g] if isinstance(g, bool) else str(g)
raw = {s: [json.loads(l) for l in open(RAW / f"{s}.jsonl")] for s in ("git3_test_known", "git3_test_held")}
rows = [json.loads(l) for l in open(HERE / "pool_items.jsonl")]
for p in rows:
    if p["src"] in raw:
        r = raw[p["src"]][p["row"]]
        p["changed_state"] = bool(r["qtype"] not in ("lost", "fails", "in_progress") and r["known0"] and norm(r["gold0"]) != norm(r["gold"]))
with open(HERE / "pool_items.jsonl", "w") as f:
    for p in rows:
        f.write(json.dumps(p) + "\n")
print(sum(p.get("changed_state", False) for p in rows), "changed-state rows")
