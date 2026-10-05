"""PLAN_loop_ideas4.md: partial looks against the release model's default on the same chains (variables seen: a whole
look sees every variable; the number of variables comes from the paired chain, the same world).
argv: long_chain3.jsonl (with the default) long_chain3_ideas4.jsonl out.json"""
import json
import sys

key = lambda r: (r["fam"], r["len"], r["i"])
base = {key(r): r for r in (json.loads(l) for l in open(sys.argv[1])) if r["mode"] == "check0.9"}
new = [json.loads(l) for l in open(sys.argv[2])]
rep = {}


def agg(rows, nv):
    acts = sum(r["len"] for r in rows)
    seen = sum(r["observed_vars"] if "observed_vars" in r else r["looks"] * nv[key(r)] for r in rows)
    return {"chains": len(rows), "exact": sum(r["state_ok"] for r in rows), "wrong_per_100": 100 * sum(r["wrong_steps"] for r in rows) / acts,
            "looks_per_100": 100 * sum(r["looks"] for r in rows) / acts, "seen_per_100": 100 * seen / acts,
            "whole_looks_per_100": 100 * sum(r.get("full_looks", r["looks"]) for r in rows) / acts}


for mode in sorted({r["mode"] for r in new}):
    rows = [r for r in new if r["mode"] == mode and key(r) in base]
    nv = {key(r): r["n_vars"] for r in rows}
    a, d = agg(rows, nv), agg([base[key(r)] for r in rows], nv)
    rep[mode] = {"mode": a, "default_same_chains": d, "passes": a["seen_per_100"] < d["seen_per_100"] and a["wrong_per_100"] <= d["wrong_per_100"],
                 "per_world": {w: {"mode": agg([r for r in rows if r["fam"] == w], nv), "default": agg([base[key(r)] for r in rows if r["fam"] == w], nv)}
                               for w in ("jugs", "toggles", "machines") if any(r["fam"] == w for r in rows)}}
json.dump(rep, open(sys.argv[3], "w"), indent=1)
for mode, r in rep.items():
    a, d = r["mode"], r["default_same_chains"]
    print(f"{mode:<9} exact {a['exact']}/{a['chains']} (default {d['exact']})  wrong {a['wrong_per_100']:.2f} (default {d['wrong_per_100']:.2f})  "
          f"seen {a['seen_per_100']:.1f} (default {d['seen_per_100']:.1f})  looks {a['looks_per_100']:.1f}, whole {a['whole_looks_per_100']:.1f} "
          f"(default {d['looks_per_100']:.1f})  -> {'PASSES' if r['passes'] else 'no'}")
    for w, x in r["per_world"].items():
        print(f"    {w:<9} wrong {x['mode']['wrong_per_100']:.2f} vs {x['default']['wrong_per_100']:.2f}   seen {x['mode']['seen_per_100']:.1f} vs {x['default']['seen_per_100']:.1f}")
