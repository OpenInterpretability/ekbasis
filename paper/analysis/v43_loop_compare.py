"""conseq/PLAN_v43_loop_test.md: the round-2 winner's chains against the release model's saved chains (same seeds).
argv: results_dir (holds long_chain3.jsonl, long_chain3_trace.jsonl, long_chain3_controls_trace.jsonl of the release
model, and long_chain3_r2err.jsonl) out.json"""
import json
import sys
from pathlib import Path

R, OUT = Path(sys.argv[1]), sys.argv[2]
v42 = [json.loads(l) for l in open(R / "long_chain3.jsonl")]
NAME = sys.argv[3] if len(sys.argv) > 3 else "r2err"
new = [json.loads(l) for l in open(R / f"long_chain3_{NAME}.jsonl")]
WORLDS = ("jugs", "toggles", "machines", "cards")


def pooled(rows, mode, worlds=WORLDS):
    g = [r for r in rows if r["mode"] == mode and r["fam"] in worlds]
    acts = sum(r["len"] for r in g)
    return {"chains": len(g), "exact": sum(r["state_ok"] for r in g), "wrong_per_100": 100 * sum(r["wrong_steps"] for r in g) / acts,
            "looks_per_100": 100 * sum(r["looks"] for r in g) / acts} if g else None


rep = {"pooled": {}, "per_world": {}}
for m in ("text", "conf0.5", "conf0.9", "check0.9"):
    rep["pooled"][m] = {"v42": pooled(v42, m), "r2err": pooled(new, m)}
    for w in WORLDS:
        rep["per_world"][f"{w}/{m}"] = {"v42": pooled(v42, m, (w,)), "r2err": pooled(new, m, (w,))}

# never-looking traces: wrong steps and the share given a probability of 0.9 or more
tv42 = {}
for f in ("long_chain3_trace.jsonl", "long_chain3_controls_trace.jsonl"):
    for l in open(R / f):
        r = json.loads(l)
        if r["mode"] == "text":
            tv42.setdefault(r["fam"], []).extend(r["trace"])
tnew = {}
for r in new:
    if r["mode"] == "text" and r.get("trace"):
        tnew.setdefault(r["fam"], []).extend(r["trace"])


def trace_stats(steps):
    wrong = [p for p, ok in steps if not ok]
    return {"steps": len(steps), "wrong_per_100": 100 * len(wrong) / len(steps) if steps else None,
            "wrong_at_0.9": sum(p >= 0.9 for p in wrong), "wrong": len(wrong)}


rep["traces"] = {w: {"v42": trace_stats(tv42.get(w, [])), "r2err": trace_stats(tnew.get(w, []))} for w in WORLDS}
trained = ("jugs", "toggles")
share = lambda d, who: (sum(d[w][who]["wrong_at_0.9"] for w in trained) / max(1, sum(d[w][who]["wrong"] for w in trained)))
c1 = rep["pooled"]["conf0.9"]["r2err"]["wrong_per_100"] < rep["pooled"]["conf0.9"]["v42"]["wrong_per_100"]
a, b = rep["pooled"]["check0.9"]["r2err"], rep["pooled"]["check0.9"]["v42"]
c2 = a["exact"] == a["chains"] and a["wrong_per_100"] <= b["wrong_per_100"] and a["looks_per_100"] <= 1.10 * b["looks_per_100"]
c3 = share(rep["traces"], "r2err") < share(rep["traces"], "v42")
rep["criteria"] = {"chain_rule_fewer_wrong_steps": c1, "default_exact_not_more_wrong_looks_within_10pct": c2,
                   "trained_world_traces_fewer_confident_errors": c3, "loop_better": c1 and c2 and c3,
                   "share_confident_wrong_trained": {"v42": share(rep["traces"], "v42"), "r2err": share(rep["traces"], "r2err")}}
json.dump(rep, open(OUT, "w"), indent=1)
print(f"{'rule':<10}{'model':<7}{'exact':>8}{'wrong/100':>11}{'looks/100':>11}")
for m, d in rep["pooled"].items():
    for who in ("v42", "r2err"):
        x = d[who]
        if x:
            print(f"{m:<10}{who:<7}{x['exact']:>4}/{x['chains']:<3}{x['wrong_per_100']:>11.2f}{x['looks_per_100']:>11.1f}")
print("traces (never looking):")
for w, d in rep["traces"].items():
    print(f"  {w:<9} v42 {d['v42']['wrong']}/{d['v42']['steps']} wrong ({d['v42']['wrong_at_0.9']} at >=0.9)   "
          f"r2err {d['r2err']['wrong']}/{d['r2err']['steps']} wrong ({d['r2err']['wrong_at_0.9']} at >=0.9)")
print("criteria:", json.dumps(rep["criteria"]))
