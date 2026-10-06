"""WS-PI: the round-5 runs' trainer readouts on the 15,008 questions (the paper's Table of runs: "r5a-c ... 89.8-91.0,
1.92-3.03 (T)"), on all items and without the items that overlap the release lineage's training rows (ftrain_mixG3,
mined_wide, mined_chain: a superset of each round-5 run's own files), against V42's readout on the same items.
usage: python pi_r5.py   (in /root/decis/mission/PI; writes r5.json)"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
items = [json.loads(l) for l in open(os.path.join(HERE, "served", "items_local.jsonl"))]
fl = json.load(open(os.path.join(HERE, "overlap_public.json")))["flags"]["ce_items"]
ex = {f["i"] for f in fl if f["identical"] or f["near"]}


def readout(run):
    P = [json.loads(l) for l in open(os.path.join(HERE, "runs", f"sw_{run}", "preds_ce_items_floor.jsonl"))]
    assert len(P) == len(items)
    out = {}
    for lv, keep in (("all", range(len(items))), ("clean", [i for i in range(len(items)) if i not in ex])):
        keep = list(keep)
        t = [i for i in keep if items[i]["group"] == "T"]
        out[lv] = {"n": len(keep), "accuracy": 100 * sum(bool(P[i]["ok"]) for i in keep) / len(keep),
                   "conf_errors_per_100_T": 100 * sum((not P[i]["ok"]) and float(P[i]["conf"]) >= 0.9 for i in t) / len(t)}
    return out


res = {r: readout(r) for r in ("v42base", "r5a", "r5b", "r5c")}
json.dump(res, open(os.path.join(HERE, "r5.json"), "w"), indent=1)
for r, v in res.items():
    print(r, {lv: {k: round(x, 2) for k, x in d.items()} for lv, d in v.items()})
