"""PLAN_loop_ideas.md: each new loop mode of the release model against its default (check0.9) on the same chains.
argv: long_chain3.jsonl (with the default) long_chain3_ideas.jsonl out.json"""
import json
import sys

key = lambda r: (r["fam"], r["len"], r["i"])
base = {key(r): r for r in (json.loads(l) for l in open(sys.argv[1])) if r["mode"] == "check0.9"}
ideas = [json.loads(l) for l in open(sys.argv[2])]
rep = {}


def agg(rows):
    acts = sum(r["len"] for r in rows)
    miss = [r for r in rows if not r["state_ok"]]
    return {"chains": len(rows), "exact": len(rows) - len(miss), "wrong_per_100": 100 * sum(r["wrong_steps"] for r in rows) / acts,
            "looks_per_100": 100 * sum(r["looks"] for r in rows) / acts,
            "final_looks": sum(r.get("final_looks", 0) for r in rows), "incons_steps": sum(r.get("incons_steps", 0) for r in rows)}


for mode in sorted({r["mode"] for r in ideas}):
    rows = [r for r in ideas if r["mode"] == mode and key(r) in base]
    b = [base[key(r)] for r in rows]
    a, d = agg(rows), agg(b)
    better = (a["wrong_per_100"] < d["wrong_per_100"] and a["looks_per_100"] <= 1.10 * d["looks_per_100"]) or \
             (a["looks_per_100"] < d["looks_per_100"] and a["wrong_per_100"] <= d["wrong_per_100"])
    per_world = {}
    for w in ("jugs", "toggles", "machines", "cards"):
        rw = [r for r in rows if r["fam"] == w]
        if rw:
            per_world[w] = {"mode": agg(rw), "default": agg([base[key(r)] for r in rw])}
    rep[mode] = {"mode": a, "default_same_chains": d, "improves_loop": better, "per_world": per_world}
json.dump(rep, open(sys.argv[3], "w"), indent=1)
for mode, r in rep.items():
    a, d = r["mode"], r["default_same_chains"]
    print(f"{mode:<11} exact {a['exact']}/{a['chains']} (default {d['exact']})  wrong {a['wrong_per_100']:.2f} (default {d['wrong_per_100']:.2f})  "
          f"looks {a['looks_per_100']:.1f} (default {d['looks_per_100']:.1f})  final looks {a['final_looks']}  inconsistent steps {a['incons_steps']}"
          f"  -> {'IMPROVES' if r['improves_loop'] else 'no'}")
    for w, x in r["per_world"].items():
        print(f"    {w:<9} wrong {x['mode']['wrong_per_100']:.2f} vs {x['default']['wrong_per_100']:.2f}   looks {x['mode']['looks_per_100']:.1f} vs {x['default']['looks_per_100']:.1f}"
              f"   exact {x['mode']['exact']}/{x['mode']['chains']} vs {x['default']['exact']}")
