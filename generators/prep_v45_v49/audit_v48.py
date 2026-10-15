"""Firewall of V48's fresh guard-like files (PLAN_v48) against every evaluation file: audit_overlap.py's rules and
evaluation side (Addendum 7/8: identical long string or read prompt, word 8-gram near-duplicate with Jaccard >= 0.5
against one evaluation item, equal sequence of 2+ commands), run on the new files only. Flagged rows are dropped.
  PYTHONHASHSEED=0 /opt/sglang/bin/python audit_v48.py <name> [<name> ...]   (files /dev/shm/conseq/fac/<name>.jsonl)
  -> v48/data/<name>.clean.jsonl (rows kept) and v48/audit_v48.json (counts, flagged ids and why)"""
import collections
import json
import multiprocessing as mp
import os
import re
import sys

import numpy as np

sys.path.insert(0, "/root/decis/mission/F/v47")
import audit_overlap as A  # noqa: E402

# V48's own training files are never evaluation files
A.NOT_EVAL = re.compile(A.NOT_EVAL.pattern.replace("^(", "^(v48_|v49_|", 1))  # V48's and V49's training files
OUT = os.environ.get("AUDIT_OUT", "/root/decis/mission/F/v48")


def main(names):
    ev = A.eval_files()
    assert not any(os.path.basename(p).startswith(("v48_", "v49_")) for p in ev)
    with mp.Pool(48) as pool:
        parts = pool.map(A.eval_worker, ev, chunksize=1)
    A.E = np.unique(np.concatenate([p[2] for p in parts if len(p[2])]))
    for p in parts:
        t = A.tag_of(p[0])
        for h in p[3]:
            A.LONGS.setdefault(h, set()).add(t)
        for h in p[4]:
            A.ACTS.setdefault(h, set()).add(t)
    print(json.dumps({"eval_files": len(ev), "eval_items": sum(p[1] for p in parts)}), flush=True)
    A.LAYOUT = A.layout_for(names)
    with mp.Pool(min(48, len(names) * 8)) as pool:
        results = pool.map(A.train_worker, [(n, k, 8) for n in names for k in range(8)], chunksize=1)
    flagged = [(r["file"], fid, set(s)) for r in results for fid, s in r["flagged"]]
    near = collections.defaultdict(dict)
    if flagged:
        want = set().union(*[s for _, _, s in flagged])
        index, item_sh = collections.defaultdict(list), []
        for path in ev:
            for it in A.eval_items(path):
                full = A.shingles(" ".join(A.strings(it, [])))
                s = full & want
                if s:
                    k = len(item_sh)
                    item_sh.append((A.tag_of(path), len(full)))
                    for g in s:
                        index[g].append(k)
        for fname, fid, s in flagged:
            cand = collections.Counter(k for g in s for k in index.get(g, []))
            best, bt = 0.0, None
            for k, inter in cand.most_common(20):
                j = inter / (len(s) + item_sh[k][1] - inter)
                if j > best:
                    best, bt = j, item_sh[k][0]
            if best >= 0.5:
                near[fname][fid] = (round(best, 3), bt)
    rep = {}
    for name in names:
        rs = [r for r in results if r["file"] == name]
        bad = {}
        for r in rs:
            for fid in r["ids"].get("identical", []):
                bad[fid] = "identical"
            for fid in r["ids"].get("action_seq", []):
                bad.setdefault(fid, "action_seq")
        for fid, (j, t) in near.get(name, {}).items():
            bad.setdefault(fid, f"near_dup {j} {t}")
        rows = [json.loads(line) for line in open(f"{A.FAC}/{name}.jsonl")]
        keep = [r for i, r in enumerate(rows) if (r.get("id") or f"{name}:{i}") not in bad]
        with open(f"{OUT}/data/{name}.clean.jsonl", "w") as f:
            for r in keep:
                f.write(json.dumps(r) + "\n")
        rep[name] = {"rows": len(rows), "flagged": len(bad), "kept": len(keep),
                     "by_rule": dict(collections.Counter(v.split()[0] for v in bad.values())),
                     "near_candidates": sum(r["near_candidates"] for r in rs), "flagged_ids": dict(list(bad.items())[:200])}
        print(name, json.dumps({k: v for k, v in rep[name].items() if k != "flagged_ids"}), flush=True)
    json.dump(rep, open(f"{OUT}/" + os.environ.get("AUDIT_REPORT", "audit_v48.json"), "w"), indent=1)


if __name__ == "__main__":
    assert os.environ.get("PYTHONHASHSEED") == "0", "run with PYTHONHASHSEED=0"
    main(sys.argv[1:])
