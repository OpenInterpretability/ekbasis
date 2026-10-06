"""WS-PI, part 3: the release card's "first opinion" (short checks) and Portuguese numbers.
Both item sets are rebuilt exactly as their scripts build them (short_eval_release.py: robust_eval 'orig' and 'para',
seed 77; pt_eval_api.py: pt_eval.py's items, same seed) and checked against the release lineage's training rows by the
same rules (identical prompt; word 8-gram near duplicate, Jaccard >= 0.5 against a single training row, the set's own
layout removed). The short checks' saved answers (Ekbasis' and Qwen3.8-27B's) are re-scored on the items that do not
overlap. The Portuguese test kept no per-item answers, so only the overlap is reported there.
usage: python pi_short_pt.py   (in /root/decis/mission/PI; writes short_pt.json)"""
from __future__ import annotations

import collections
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from pi_overlap import FAC, norm, shingles, text  # noqa: E402

sys.path.insert(0, "/root/decis/conseq")
sys.argv = [sys.argv[0], "60"]
import robust_eval as R  # noqa: E402
from worldgen import Jugs, Machines, Toggles  # noqa: E402

TRAIN = ["ftrain_mixG3", "mined_wide", "mined_chain"]
WORLDS = {"machines", "toggles", "jugs"}

R.BIG = False
rng = random.Random(77)
short = [(fam, gold, name, txt, q) for F in (Machines, Toggles, Jugs) for fam, gold, v in R.items(F, rng, 40)
         for name, (txt, q) in v.items() if name in ("orig", "para")]
saved = json.load(open("/dev/shm/conseq/short_eval.json"))
assert [tuple(x) for x in saved["items"]] == [it[:3] for it in short], "short items differ"
src = open("/root/decis/conseq/pt_eval.py").read()
src = src[:src.index("res = {}")]
ns = {"__name__": "pt_items"}
exec(compile(src, "pt_eval.py", "exec"), ns)
pt_items = ns["items"]

train = []
for n in TRAIN:
    for line in open(f"{FAC}/{n}.jsonl"):
        r = json.loads(line)
        if r.get("world") in WORLDS:
            train.append(text(r.get("floor", "")))
print("training rows in these worlds:", len(train), flush=True)
exact = {hash(norm(t)) for t in train}
tsh = [shingles(t) for t in train]
index = collections.defaultdict(list)
for k, s in enumerate(tsh):
    for g in s:
        index[g].append(k)


def flags(texts, questions):
    c = collections.Counter()
    for t in texts:
        c.update(shingles(t))
    lay = {g for g, k in c.items() if k >= 0.2 * len(texts)}
    for q in questions:
        lay |= shingles(q.get("instructions", "") if isinstance(q, dict) else "")
    out = []
    for t in texts:
        if hash(norm(t)) in exact:
            out.append({"identical": True, "J": 1.0})
            continue
        s = shingles(t) - lay
        best = 0.0
        if len(s) >= 10:
            cnt = collections.Counter(k for g in s for k in index.get(g, []))
            for k, inter in cnt.most_common(20):
                best = max(best, inter / (len(s) + len(tsh[k]) - inter))
        out.append({"identical": False, "J": round(best, 4)})
    return out


res = {}
fs = flags([it[3] for it in short], [it[4] for it in short])
bad = {i for i, f in enumerate(fs) if f["identical"] or f["J"] >= 0.5}
res["short_overlap"] = {f"{fam}/{name}": f"{sum(1 for i, it in enumerate(short) if it[0] == fam and it[2] == name and i in bad)}"
                        f"/{sum(1 for it in short if it[0] == fam and it[2] == name)}"
                        for fam in ("machines", "toggles", "jugs") for name in ("orig", "para")}
rep = json.load(open("/root/decis/mission/PI/served/short_eval_release.json"))
P = rep["predictions"]
assert len(P) == len(short)
think = saved["res"]["think"]
keep_sets = {"all": range(len(short)), "clean": [i for i in range(len(short)) if i not in bad]}
res["short"] = {}
for lv, keep in keep_sets.items():
    keep = list(keep)
    acc = {name: 100 * sum(P[i]["ok"] for i in keep if short[i][2] == name) / max(1, sum(short[i][2] == name for i in keep))
           for name in ("orig", "para")}
    routing = []
    for cut in (None, 0.5, 0.9, 0.95, 0.99):
        to = [i for i in keep if cut is not None and P[i]["conf"] < cut]
        ok = [think[i]["ok"] if i in set(to) else P[i]["ok"] for i in keep]
        routing.append({"confidence_cut": cut, "to_llm_pct": 100 * len(to) / len(keep), "accuracy": 100 * sum(ok) / len(keep)})
    bands = []  # RELEASE_EVAL's calibration bins on these checks
    for lo, hi in ((0.5, 0.9), (0.9, 0.99), (0.99, 1.01)):
        b = [i for i in keep if lo <= P[i]["conf"] < hi]
        bands.append({"conf": f"[{lo}, {hi})", "n": len(b), "mean_conf": 100 * sum(P[i]["conf"] for i in b) / max(1, len(b)),
                      "acc": 100 * sum(P[i]["ok"] for i in b) / max(1, len(b))})
    res["short"][lv] = {"n": len(keep), "accuracy": acc, "routing": routing, "calibration": bands}

fe = flags([it["en"] for it in pt_items], [it["q"] for it in pt_items])
fp = flags([it["pt"] for it in pt_items], [it["qpt"] for it in pt_items])
chg = [i for i, it in enumerate(pt_items) if it["changed"]]
res["pt_overlap_changed_portuguese"] = {fam: sum(1 for i in chg if pt_items[i]["fam"] == fam and (fp[i]["identical"] or fp[i]["J"] >= 0.5))
                                        for fam in ("machines", "toggles", "jugs")}
res["pt_overlap_changed_english"] = {fam: f"{sum(1 for i in chg if pt_items[i]['fam'] == fam and (fe[i]['identical'] or fe[i]['J'] >= 0.5))}"
                                          f"/{sum(1 for i in chg if pt_items[i]['fam'] == fam)}" for fam in ("machines", "toggles", "jugs")}
json.dump(res, open(os.path.join(HERE, "short_pt.json"), "w"), indent=1)
print(json.dumps(res, indent=1))
