import json, random, sys
sys.path.insert(0, "/root/decis/serve_v13/eikos")
import decision_core as dc
out = []
def add(split, kind, n=None):
    rows = [json.loads(l) for l in open(f"/root/v50p/data/{split}.jsonl")]
    idx = list(range(len(rows)))
    if n and len(idx) > n:
        idx = sorted(random.Random(20261015).sample(idx, n))
    for i in idx:
        r = rows[i]; q = r["question"]
        lab = ("yes" if r["gold"] in (True, "True", "true") else "no") if q["type"] in ("noul", "boolean") else str(r["gold"])
        if lab not in [v for v, _ in dc.options_of(q)]:
            continue
        out.append({"set": kind, "split": split, "i": i, "state": r["floor"], "question": q, "gold": lab})
add("fval_git3", "fit"); add("m3val", "fit")
add("git_long", "test"); add("guard_known", "test", 800); add("fac_val", "test", 800)
json.dump(out, open("/root/v50p/calib_items.json", "w"))
import collections; print(len(out), collections.Counter((o["set"], o["split"]) for o in out))
