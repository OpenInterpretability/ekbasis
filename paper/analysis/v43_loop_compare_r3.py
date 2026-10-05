"""conseq/PLAN_v43_round3.md, loop test: the chosen round-3 run against V42 on the same 240 chains (paired by world,
length, seed and mode). argv: dir (long_chain3.jsonl, long_chain3_v42more.jsonl, the V42 traces, long_chain3_<name>.jsonl)
name out.json"""
import json
import sys
from pathlib import Path

R, NAME, OUT = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
key = lambda r: (r["fam"], r["len"], r["i"], r["mode"])
new = {key(r): r for r in (json.loads(l) for l in open(R / f"long_chain3_{NAME}.jsonl"))}
v42 = {}
for f in ("long_chain3.jsonl", "long_chain3_v42more.jsonl"):
    for l in open(R / f):
        r = json.loads(l)
        v42.setdefault(key(r), r)
pairs = [k for k in new if k in v42]
WORLDS = ("jugs", "toggles", "machines", "cards")


def pooled(src, mode, worlds=WORLDS):
    g = [src[k] for k in pairs if k[3] == mode and k[0] in worlds]
    acts = sum(r["len"] for r in g)
    last_only = sum(1 for r in g if not r["state_ok"] and r["wrong_steps"] <= 1)
    return {"chains": len(g), "exact": sum(r["state_ok"] for r in g), "missed_at_most_last_action": last_only,
            "wrong_per_100": 100 * sum(r["wrong_steps"] for r in g) / acts, "looks_per_100": 100 * sum(r["looks"] for r in g) / acts}


rep = {"pairs": len(pairs), "pooled": {m: {"v42": pooled(v42, m), NAME: pooled(new, m)} for m in ("text", "conf0.5", "check0.9")},
       "per_world": {f"{w}/{m}": {"v42": pooled(v42, m, (w,)), NAME: pooled(new, m, (w,))} for w in WORLDS for m in ("conf0.5", "check0.9")}}
trace = lambda src, worlds: [s for k in pairs if k[3] == "text" and k[0] in worlds for s in src[k].get("trace", [])]
for who, src in (("v42", v42), (NAME, new)):
    st = trace(src, ("jugs", "toggles"))
    wrong = [p for p, ok in st if not ok]
    rep.setdefault("trained_traces", {})[who] = {"steps": len(st), "wrong": len(wrong), "wrong_at_0.9": sum(p >= 0.9 for p in wrong)}
d42, dn = rep["pooled"]["check0.9"]["v42"], rep["pooled"]["check0.9"][NAME]
c_default = dn["wrong_per_100"] <= d42["wrong_per_100"] and dn["looks_per_100"] <= 1.10 * d42["looks_per_100"]
best = min((rep["pooled"][m][NAME] for m in ("conf0.5", "check0.9")), key=lambda x: (x["looks_per_100"], x["wrong_per_100"]))
c_matched = any(rep["pooled"][m][NAME]["wrong_per_100"] < d42["wrong_per_100"] and rep["pooled"][m][NAME]["looks_per_100"] < d42["looks_per_100"]
                for m in ("conf0.5", "check0.9"))
rep["criteria"] = {"default_not_worse": c_default, "matched_cost_better": c_matched, "loop_better": c_default or c_matched}
json.dump(rep, open(OUT, "w"), indent=1)
print(f"{len(pairs)} paired chains")
for m, d in rep["pooled"].items():
    for who in ("v42", NAME):
        x = d[who]
        print(f"{m:<9}{who:<8} exact {x['exact']}/{x['chains']} (misses at the last action only: {x['missed_at_most_last_action']})  "
              f"wrong {x['wrong_per_100']:.2f}/100  looks {x['looks_per_100']:.1f}/100")
print("trained-world traces:", rep["trained_traces"])
print("criteria:", json.dumps(rep["criteria"]))
