"""PLAN_v43_round4_confirm.md: r4b against V42 on the same fresh chains (paired by world, length, seed and rule).
argv: long_chain3_confirm_v42.jsonl long_chain3_confirm_<name>.jsonl out.json [name, r4b by default]"""
import json
import sys

key = lambda r: (r["fam"], r["len"], r["i"], r["mode"])
v42 = {key(r): r for r in (json.loads(l) for l in open(sys.argv[1]))}
new = {key(r): r for r in (json.loads(l) for l in open(sys.argv[2]))}
pairs = [k for k in new if k in v42]
NAME = sys.argv[4] if len(sys.argv) > 4 else "r4b"
WORLDS = ("jugs", "toggles", "machines", "cards")


def pooled(src, mode, worlds=WORLDS):
    g = [src[k] for k in pairs if k[3] == mode and k[0] in worlds]
    acts = sum(r["len"] for r in g)
    return {"chains": len(g), "exact": sum(r["state_ok"] for r in g), "wrong_per_100": 100 * sum(r["wrong_steps"] for r in g) / acts,
            "looks_per_100": 100 * sum(r["looks"] for r in g) / acts} if g else None


rep = {"pairs": len(pairs), "pooled": {m: {"v42": pooled(v42, m), NAME: pooled(new, m)} for m in ("check0.9", "conf0.5")},
       "per_world": {f"{w}/{m}": {"v42": pooled(v42, m, (w,)), NAME: pooled(new, m, (w,))} for w in WORLDS for m in ("check0.9", "conf0.5")}}
a, b = rep["pooled"]["check0.9"][NAME], rep["pooled"]["check0.9"]["v42"]
rep["criteria"] = {"fewer_wrong": a["wrong_per_100"] < b["wrong_per_100"], "looks_within_10pct": a["looks_per_100"] <= 1.10 * b["looks_per_100"],
                   "exact_not_fewer": a["exact"] >= b["exact"]}
rep["criteria"]["confirmed"] = all(rep["criteria"].values())
json.dump(rep, open(sys.argv[3], "w"), indent=1)
print(f"{len(pairs)} paired chains")
for m, d in rep["pooled"].items():
    for who in ("v42", NAME):
        x = d[who]
        print(f"{m:<9}{who:<5} exact {x['exact']}/{x['chains']}  wrong {x['wrong_per_100']:.2f}/100  looks {x['looks_per_100']:.1f}/100")
for k, d in rep["per_world"].items():
    print(f"  {k:<18} v42 wrong {d['v42']['wrong_per_100']:.2f} looks {d['v42']['looks_per_100']:.1f} exact {d['v42']['exact']}/{d['v42']['chains']}"
          f"   {NAME} wrong {d[NAME]['wrong_per_100']:.2f} looks {d[NAME]['looks_per_100']:.1f} exact {d[NAME]['exact']}/{d[NAME]['chains']}")
print("criteria:", json.dumps(rep["criteria"]))
