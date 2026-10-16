"""Pack the factory rows for training: shuffle choice options (no gold-first bias), cap each yes/no question type at
70/30 (dropping majority rows of scenarios without a twin first), keep the quarantined GUI family out.
python3 pack.py <data_dir> -> <data_dir>/train_<family>.jsonl, train_rx.jsonl, pack.json"""
import collections
import hashlib
import json
import os
import random
import sys

data_dir = sys.argv[1]
FAMS = ["shell", "sql", "python", "git"]
CAP = 0.70
report = {}
allrows = []
for fam in FAMS:
    rows = [json.loads(l) for l in open(os.path.join(data_dir, f"{fam}.jsonl"))]
    rows = [r for r in rows if not r.get("quarantined")]
    for r in rows:  # deterministic option order per row
        q = r["question"]
        if q["type"] == "choice":
            items = list(q["criteria"].items())
            random.Random(int(hashlib.md5(r["id"].encode()).hexdigest()[:8], 16)).shuffle(items)
            q["criteria"] = dict(items)
    keep, dropped = [], 0
    by_q = collections.defaultdict(list)
    for r in rows:
        by_q[r["qtype"]].append(r)
    for qt, rs in by_q.items():
        if rs[0]["question"]["type"] != "noul":
            keep += rs
            continue
        yes = [r for r in rs if r["gold"] is True]
        no = [r for r in rs if r["gold"] is False]
        maj, mino = (yes, no) if len(yes) > len(no) else (no, yes)
        limit = int(len(mino) * CAP / (1 - CAP))
        if len(maj) > limit:
            maj = sorted(maj, key=lambda r: (r.get("twin") is not None, hashlib.md5(r["id"].encode()).hexdigest()))
            dropped += len(maj) - limit
            maj = maj[len(maj) - limit:]
        keep += maj + mino
    keep.sort(key=lambda r: r["id"])
    with open(os.path.join(data_dir, f"train_{fam}.jsonl"), "w") as f:
        for r in keep:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    first = sum(1 for r in keep if r["question"]["type"] == "choice" and list(r["question"]["criteria"])[0] == r["gold"])
    nch = sum(1 for r in keep if r["question"]["type"] == "choice")
    report[fam] = {"rows_in": len(rows), "rows_out": len(keep), "dropped_for_balance": dropped,
                   "choice_gold_first_after_shuffle": round(first / max(1, nch), 3),
                   "yes_share_after": {qt: round(sum(1 for r in keep if r["qtype"] == qt and r["gold"] is True) /
                                                  max(1, sum(1 for r in keep if r["qtype"] == qt)), 3)
                                       for qt in by_q if by_q[qt][0]["question"]["type"] == "noul"}}
    allrows += keep
with open(os.path.join(data_dir, "train_rx.jsonl"), "w") as f:
    for r in allrows:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
report["total_rows"] = len(allrows)
json.dump(report, open(os.path.join(data_dir, "pack.json"), "w"), indent=1)
print(json.dumps(report, indent=1))
