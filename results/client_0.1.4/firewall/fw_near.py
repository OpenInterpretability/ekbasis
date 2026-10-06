"""Diagnostic for fw_u.py (no change to its result): which evaluation evidences are closest to ftrain_all's floors
(best Jaccard >= 0.4, under the 0.5 rule), by set and suite, with two examples. PYTHONHASHSEED=0 python3 fw_near.py"""
import collections
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fw_u as F  # noqa: E402


def main():
    rows_by_ev, _ = F.build_eval(["dev", "c1", "c2"])
    F.E = np.unique(np.fromiter((g for s in F.EV_SH for g in s), dtype=np.int64))
    lay = F.layout_for("ftrain_all")
    by, ex, seen = collections.Counter(), [], set()
    for line in open(f"{F.FAC}/ftrain_all.jsonl"):
        r = json.loads(line)
        fl = F.text(r.get("floor", ""))
        if hash(fl) in seen:
            continue
        seen.add(hash(fl))
        s = F.shingles(fl) - lay
        if len(s) < 10:
            continue
        arr = np.fromiter(s, dtype=np.int64, count=len(s))
        idx = np.minimum(np.searchsorted(F.E, arr), len(F.E) - 1)
        if float((F.E[idx] == arr).mean()) < 0.5:
            continue
        cnt = collections.Counter()
        for g in s:
            p = F.POST.get(g)
            if p is not None and len(p) <= F.RANK_CAP:
                cnt.update(p)
        best, bk = 0.0, None
        for k, _ in cnt.most_common(50):
            inter = len(s & F.EV_SH[k])
            j = inter / (len(s) + F.EV_LEN[k] - inter)
            if j > best:
                best, bk = j, k
        if best >= 0.4:
            sets = sorted({(a, b) for a, b, _, _ in rows_by_ev[F.EV_TEXT[bk]]})
            for a, b in sets:
                by[f"{a}|{b}"] += 1
            if len(ex) < 2 or best > ex[-1][0]:
                ex.append((round(best, 3), r.get("world"), r.get("kind"), fl[:500], F.EV_TEXT[bk][:500], sets))
                ex = sorted(ex, key=lambda e: -e[0])[:2]
    print(json.dumps({"by_set_suite_of_best_match": dict(by), "examples": ex}, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
