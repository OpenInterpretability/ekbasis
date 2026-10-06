"""WS-PI: the V41-vs-V42 selection rule's no-regression checks (select_release.py; results_v42/RELEASE_EVAL.md) on the
two splits that overlap the training rows, ftest_in and multi_test_trainfam, recomputed on the rows / states that do
not overlap (overlap_public.json, the lineage's flags: a superset of V41's and V42's own files' flags). V41's trainer
readout comes from the private research-runs repository (served/sw_v41/), V42's from /dev/shm/conseq/sw_v42.
usage: python pi_select.py   (in /root/decis/mission/PI; writes select.json)"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
FAC = "/dev/shm/conseq/fac"
RUNS = {"v41": os.path.join(HERE, "served", "sw_v41"), "v42": "/dev/shm/conseq/sw_v42"}
FL = json.load(open(os.path.join(HERE, "overlap_public.json")))["flags"]


def jl(p):
    return [json.loads(l) for l in open(p)]


def flagged(split):
    return {f["i"] for f in FL[split] if f["identical"] or f["near"]}


res = {}
ex = flagged("ftest_in")
for m, d in RUNS.items():
    P = jl(os.path.join(d, "preds_ftest_in_floor.jsonl"))
    assert len(P) == len(FL["ftest_in"])
    keep = [i for i in range(len(P)) if i not in ex]
    res.setdefault("ftest_in", {})[m] = {"all": [len(P), 100 * sum(p["ok"] for p in P) / len(P)],
                                         "clean": [len(keep), 100 * sum(P[i]["ok"] for i in keep) / len(keep)]}
states = jl(f"{FAC}/multi_test_trainfam.jsonl")
ex = flagged("multi_test_trainfam")
for mode in ("single", "multi"):
    for m, d in RUNS.items():
        P = jl(os.path.join(d, f"preds_multi_test_trainfam_{mode}.jsonl"))
        assert len(P) == sum(len(s["questions"]) for s in states)
        k, a = 0, {"all": [], "clean": []}
        for i, s in enumerate(states):
            for _ in s["questions"]:
                if P[k]["changed"]:
                    a["all"].append(P[k]["ok"])
                    if i not in ex:
                        a["clean"].append(P[k]["ok"])
                k += 1
        res.setdefault(f"multi_test_trainfam ({mode}, changed)", {})[m] = {lv: [len(v), 100 * sum(v) / len(v)] for lv, v in a.items()}
for k, v in res.items():
    for lv in ("all", "clean"):
        v[f"diff_{lv}"] = v["v42"][lv][1] - v["v41"][lv][1]
    print(f"{k:42s} all: V41 {v['v41']['all'][1]:.1f} V42 {v['v42']['all'][1]:.1f} diff {v['diff_all']:+.1f} (n {v['v42']['all'][0]})"
          f" | clean: V41 {v['v41']['clean'][1]:.1f} V42 {v['v42']['clean'][1]:.1f} diff {v['diff_clean']:+.1f} (n {v['v42']['clean'][0]})")
json.dump(res, open(os.path.join(HERE, "select.json"), "w"), indent=1)
