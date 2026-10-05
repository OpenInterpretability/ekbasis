"""Recomputes every number in the paper "Look When Unsure, Check When Sure" from the saved model outputs.

Each pre-registered analysis is re-run with its original script (analysis/) on the saved predictions and chains, and its
output must equal the result saved when it first ran. A field added to a script after that run may appear only in the
re-run; any other difference stops the run. The rest is computed here from the raw rows: the loop rules, the traces,
the release model's guard, the real-use guard test and the relative-scale check. Every number the paper cites is
written to numbers.json, with the outcome of every check.

usage: python3 reproduce.py
env:   EKB_RESULTS  V42's results, frozen when the release moved to the interpolation (default ../results_v42)
       EKB_RUNS     the research runs: the training rounds, loop tests, guard set and real-use test (default runs/)"""
import json
import math
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
A = HERE / "analysis"
RES = Path(os.environ.get("EKB_RESULTS", HERE.parent / "results_v42"))  # V42's results, frozen: the model this paper studies
RUNS = Path(os.environ.get("EKB_RUNS", HERE / "runs"))
OUT = HERE / "recomputed"
OUT.mkdir(exist_ok=True)
ITEMS = RES / "confident_errors" / "items.jsonl"
checks, numbers = [], {}


def jl(p):
    return [json.loads(l) for l in open(p)]


def diff(stored, new, path=""):
    """(values that differ, fields only in the re-run)."""
    if isinstance(stored, dict) and isinstance(new, dict):
        d, added = [], [f"{path}/{k}" for k in new if k not in stored]
        d += [f"{path}/{k}: missing in the re-run" for k in stored if k not in new]
        for k in stored:
            if k in new:
                a, b = diff(stored[k], new[k], f"{path}/{k}")
                d, added = d + a, added + b
        return d, added
    if isinstance(stored, list) and isinstance(new, list):
        if len(stored) != len(new):
            return [f"{path}: {len(stored)} items, re-run {len(new)}"], []
        d, added = [], []
        for i, (x, y) in enumerate(zip(stored, new)):
            a, b = diff(x, y, f"{path}[{i}]")
            d, added = d + a, added + b
        return d, added
    if isinstance(stored, float) or isinstance(new, float):
        ok = isinstance(stored, (int, float)) and isinstance(new, (int, float)) and math.isclose(stored, new, rel_tol=1e-9, abs_tol=1e-12)
        return ([] if ok else [f"{path}: {stored} vs {new}"]), []
    return ([] if stored == new else [f"{path}: {stored!r} vs {new!r}"]), []


def rerun(name, script, args, stored, cwd=None, ignore=(), out_file=None):
    """Re-run an analysis script; its output (out_file, or OUT/name.json passed as the placeholder OUT) must reproduce
    the stored result."""
    out = out_file or OUT / f"{name}.json"
    argv = [sys.executable, str(A / script)] + [str(out) if a == "OUT" else str(a) for a in args]
    p = subprocess.run(argv, cwd=cwd, capture_output=True, text=True)
    if p.returncode != 0:
        raise SystemExit(f"{name}: {script} failed\n{p.stderr[-2000:]}")
    new = json.load(open(out))
    old = json.load(open(stored))
    for k in ignore:
        old.pop(k, None), new.pop(k, None)
    d, added = diff(old, new)
    checks.append({"analysis": name, "script": script, "stored": str(Path(stored).relative_to(Path(stored).parents[2])),
                   "identical": not d, "fields_added_later": len(added)})
    print(f"{'ok  ' if not d else 'DIFF'} {name:24s} {script}" + (f"  ({len(added)} fields added to the script later)" if added else ""))
    if d:
        raise SystemExit(f"{name} does not reproduce: {d[:5]}")
    return new


def agg(rows):
    acts = sum(r["len"] for r in rows)
    return {"chains": len(rows), "exact": sum(r["state_ok"] for r in rows),
            "silent_wrong_per_100": 100 * sum(r["wrong_steps"] for r in rows) / acts,
            "looks_per_100": 100 * sum(r["looks"] for r in rows) / acts}


WORLDS = ("jugs", "toggles", "machines", "cards")  # containers, lamps (trained); machines, cards (never trained)

# 1. The loop on the release model (results/release_eval): the rules compared, 200 fresh chains, the traces.
R = RES / "release_eval"
main = jl(R / "long_chain3.jsonl")
rules = {}
for m in sorted({r["mode"] for r in main}):
    g = [r for r in main if r["mode"] == m]
    rules[m] = {"all": agg(g), **{w: agg([r for r in g if r["fam"] == w]) for w in WORLDS if any(r["fam"] == w for r in g)}}
    for L in (100, 200):
        rules[m][f"len{L}"] = agg([r for r in g if r["len"] == L])
fresh = jl(R / "long_chain3_fresh.jsonl")
fr = {}
for m in sorted({r["mode"] for r in fresh}):
    g = [r for r in fresh if r["mode"] == m]
    fr[m] = {"all": agg(g), **{w: agg([r for r in g if r["fam"] == w]) for w in WORLDS}}
fail = [{"world": r["fam"], "len": r["len"], "i": r["i"], "silent_wrong_steps": r["wrong_steps"],
         "last_step_p": r["trace"][-1][0], "last_step_right": r["trace"][-1][1],
         "earlier_steps_all_right": all(ok for _, ok in r["trace"][:-1])}
        for r in fresh if r["mode"] == "check0.9" and not r["state_ok"]]
traces = jl(R / "long_chain3_controls_trace.jsonl") + [r for r in jl(R / "long_chain3_trace.jsonl") if r["mode"] == "text"]
tr = {}
for w in WORLDS:
    st = [s for r in traces if r["fam"] == w for s in r["trace"]]
    wrong = [p for p, ok in st if not ok]
    tr[w] = {"chains": sum(r["fam"] == w for r in traces), "steps": len(st), "wrong": len(wrong),
             "wrong_at_0.9": sum(p >= 0.9 for p in wrong), "wrong_p_min": min(wrong), "wrong_p_max": max(wrong)}
numbers["chains"] = {"rules_compared": rules, "fresh": fr, "fresh_failures": fail, "traces_never_look": tr}
print(f"ok   chains: rules {len(main)} rows, fresh {len(fresh)} rows, traces {len(traces)} chains")

# 2. Confident errors in familiar worlds (pre-registered) and the follow-up on Eikos-27B (pre-registered).
CE = RES / "confident_errors"
rep = rerun("confident_errors", "confident_errors_analyze.py", [CE / "preds.jsonl", "OUT"], CE / "report.json")
exp = rerun("confident_errors_explore", "confident_errors_explore.py", [ITEMS, CE / "preds.jsonl", "OUT"], CE / "exploratory.json")
eik = rerun("eikos_report", "confident_errors_analyze.py", [CE / "eikos27b" / "preds.jsonl", "OUT"], CE / "eikos27b" / "report.json")
cmp_ = rerun("eikos_compare", "confident_errors_compare.py", [CE / "preds.jsonl", CE / "eikos27b" / "preds.jsonl", "OUT"],
             CE / "eikos27b" / "compare.json")


def relative_scale(preds):
    """Exploratory: each model's errors judged on its own scale, the confidence of its right answers."""
    right = sorted(float(p["conf"]) for p in preds if p["ok"] in (True, "True"))
    out = {}
    for q, label in ((0.10, 90), (0.25, 75), (0.50, 50)):
        t = right[int(q * len(right))]
        key = f"as confident as the top {label}% of its right answers (conf >= {t:.3f})"
        out[key] = {}
        for g in ("T", "H", "U"):
            wrong = [float(p["conf"]) for p in preds if p["group"] == g and p["ok"] not in (True, "True")]
            out[key][g] = 100 * sum(c >= t for c in wrong) / len(wrong)
    med = {}
    for g in ("T", "H", "U"):
        w = sorted(float(p["conf"]) for p in preds if p["group"] == g and p["ok"] not in (True, "True"))
        med[g] = w[len(w) // 2]  # the upper middle (as first run); the paper cites the pre-registered report's median
    return {"relative": out, "median_conf_wrong": med}


rel = {"ekbasis": relative_scale(jl(CE / "preds.jsonl")), "eikos27b": relative_scale(jl(CE / "eikos27b" / "preds.jsonl"))}
json.dump(rel, open(OUT / "relative_scale.json", "w"), indent=1)
d, _ = diff(json.load(open(CE / "eikos27b" / "relative_scale.json")), rel)
checks.append({"analysis": "relative_scale", "script": "reproduce.py", "stored": "results/confident_errors/eikos27b/relative_scale.json",
               "identical": not d, "fields_added_later": 0})
print(f"{'ok  ' if not d else 'DIFF'} {'relative_scale':24s} reproduce.py" + (f"  {d[:3]}" if d else ""))
if d:
    raise SystemExit("relative_scale does not reproduce")
numbers["confident_errors"] = {"report": rep, "exploratory": exp, "eikos_report": eik, "eikos_compare": cmp_, "relative_scale": rel}

# 3. Post-hoc recalibration (pre-registered).
(OUT / "recalibration").mkdir(exist_ok=True)
numbers["recalibration"] = rerun("recalibration", "recalib_fit.py", [RES / "recalibration" / "answers.jsonl", OUT / "recalibration"],
                                 RES / "recalibration" / "report.json", out_file=OUT / "recalibration" / "report.json")

# 4. Training rounds, under the trainer's readout (pre-registered plans; conseq/PLAN_v43_*.md).
rounds = {"round1": rerun("round1_losses", "v43_compare.py", [RUNS / "v43_round1", ITEMS, "OUT"], RUNS / "v43_round1" / "compare.json")}
for n, runs in (("round2", []), ("round3", ["sw_r3h10", "sw_r3h20", "sw_r3w20"]), ("round4", ["sw_r4a", "sw_r4b", "sw_r4c"]),
                ("round5", ["sw_r5a", "sw_r5b", "sw_r5c"])):
    rounds[n] = rerun(f"{n}_single", "v43r2_compare.py", [RUNS / f"v43_{n}", ITEMS, "OUT"] + runs, RUNS / f"v43_{n}" / "compare.json")
numbers["rounds"] = rounds
import re
m = re.match(r"(\d+) answered in \d+ s: (\d+) wrong \(([\d.]+)%\), (\d+) of them at confidence >= 0.9", open(RUNS / "mining" / "mine_eval.out").read())
raw = jl(RUNS / "mining" / "mine_chain_raw.jsonl")
numbers["mining"] = {"true_states": {"answered": int(m.group(1)), "wrong": int(m.group(2)), "wrong_at_0.9": int(m.group(4))},
                     "chains": {"items": len(raw), "wrong": sum(r["wrong"] for r in raw), "right_below_0.99": sum(not r["wrong"] for r in raw),
                                "per_world": {w: sum(r["world"] == w for r in raw) for w in sorted({r["world"] for r in raw})},
                                "max_p_wrong": max(r["p"] for r in raw if r["wrong"])}}
wide, err = jl(RUNS / "mining" / "mined_wide.jsonl"), jl(RUNS / "mining" / "mined_err.jsonl")
numbers["mining"]["sets"] = {"errors": len(err), "confident_errors": len(jl(RUNS / "mining" / "mined_conf.jsonl")),
                             "errors_and_unsure": len(wide), "right_but_unsure": len(wide) - len(err)}
assert numbers["mining"]["sets"]["errors"] == numbers["mining"]["true_states"]["wrong"]
ans = jl(RES / "recalibration" / "answers.jsonl")
numbers["recalibration_sets"] = {k: sum(r["set"] == k for r in ans) for k in sorted({r["set"] for r in ans})}
print(f"ok   mining: {numbers['mining']['true_states']}, sets {numbers['mining']['sets']}, chain items {len(raw)}")

# 5. Loop tests of the trained runs (paired chains) and loop ideas without training.
L = {"r2err": rerun("loop_r2err", "v43_loop_compare.py", [RUNS / "v43_loop", "OUT", "r2err"], RUNS / "v43_loop" / "compare.json"),
     "r2hard": rerun("loop_r2hard", "v43_loop_compare.py", [RUNS / "v43_loop", "OUT", "r2hard"], RUNS / "v43_loop" / "compare_r2hard.json"),
     "r3w20": rerun("loop_r3w20", "v43_loop_compare_r3.py", [RUNS / "v43_round3_loop", "r3w20", "OUT"], RUNS / "v43_round3_loop" / "compare.json"),
     "r4a_explore": rerun("loop_r4a_explore", "v43_loop_compare_r3.py", [RUNS / "v43_round4_loop", "r4a", "OUT"],
                          RUNS / "v43_round4_loop" / "compare_r4a.json"),
     "r4b_explore": rerun("loop_r4b_explore", "v43_loop_compare_r3.py", [RUNS / "v43_round4_loop", "r4b", "OUT"],
                          RUNS / "v43_round4_loop" / "compare_r4b.json")}
C4 = RUNS / "v43_round4_confirm"
for n in ("r4a", "r4b"):
    L[f"{n}_confirm"] = rerun(f"loop_{n}_confirm", "confirm_compare.py", [C4 / "long_chain3_confirm_v42.jsonl", C4 / f"long_chain3_confirm_{n}.jsonl", "OUT", n],
                              C4 / f"compare_{n}.json")
L["r4c"] = rerun("loop_r4c", "confirm_compare.py", [RUNS / "v43_round5" / "long_chain3_r5_v42.jsonl", RUNS / "v43_round5" / "long_chain3_r5_r4c.jsonl", "OUT", "r4c"],
                 RUNS / "v43_round5" / "loop_r4c.json")
I = RUNS / "loop_ideas"
ideas = {"ideas1": rerun("ideas1", "loop_ideas_compare.py", [R / "long_chain3.jsonl", I / "long_chain3_ideas.jsonl", "OUT"], I / "compare.json"),
         "ideas2": rerun("ideas2", "loop_ideas_compare.py", [R / "long_chain3.jsonl", I / "long_chain3_ideas2.jsonl", "OUT"], I / "compare_ideas2.json"),
         "ideas3": rerun("ideas3", "loop_ideas_compare.py", [R / "long_chain3.jsonl", I / "long_chain3_ideas3.jsonl", "OUT"], I / "compare_ideas3.json"),
         "ideas4": rerun("ideas4", "loop_partial_compare.py", [R / "long_chain3.jsonl", I / "long_chain3_ideas4.jsonl", "OUT"], I / "compare_ideas4.json")}
numbers["loops"], numbers["loop_ideas"] = L, ideas

# 6. The git guard: the release model's own predictions, the candidates' release evaluation (pre-registered gate), the
#    larger guard set (pre-registered) when it is there, and the real-use test on copies of two real repositories.
def guard(preds):
    lost = [r for r in preds if r["qtype"] == "lost"]
    yes, no = [r for r in lost if r["gold"] == "yes"], [r for r in lost if r["gold"] == "no"]
    return {"work_losing": len(yes), "flagged_at_0.2": sum(r["p_yes"] >= 0.2 for r in yes),
            "safe": len(no), "false_alarms_at_0.2": sum(r["p_yes"] >= 0.2 for r in no)}


rel_eval = {"v42": {s: guard(jl(R / f"preds_git3_test_{s}.jsonl")) for s in ("known", "held")}}
for n in ("r4a", "r4b", "r4c") + (("w4a5",) if (RUNS / "v43eval_w4a5" / "compare_with_v42.json").exists() else ()):
    rel_eval[n] = rerun(f"release_eval_{n}", "compare_quant_ekbasis.py",
                        ["release_eval_v42_full", f"v43eval_{n}", "release_eval_t3c.json", f"v43_t3c_{n}.json", "", "OUT"],
                        RUNS / f"v43eval_{n}" / "compare_with_v42.json", cwd=RUNS, ignore=("build",))
numbers["guard"] = {"release_eval": rel_eval}
inj = {}
for n, f in (("v42", RUNS / "release_eval_t3c.json"), ("r4a", RUNS / "v43_t3c_r4a.json"), ("r4b", RUNS / "v43_t3c_r4b.json"),
             ("r4c", RUNS / "v43_t3c_r4c.json"), ("w4a5", RUNS / "v43_t3c_w4a5.json")):
    if not f.exists():
        continue
    away, missed, probs = [], [], {}
    for kind, block in json.load(open(f))["injection"].items():
        for r in block["rows"]:
            t = r["truth"]
            qs = [("lost", r["base"][0], r["p_lost"], t["lost"])]
            qs += [(f"fails{i + 1}", bf, pf, tf) for i, (bf, pf, tf) in enumerate(zip(r["base"][1], r["p_fail"], t["fails"]))]
            for q, p0, p1, tr in qs:
                probs[f"#{r['k']} {q} ({kind})"] = {"before": p0, "injected": p1, "truth": tr}
                if (p0 >= 0.5) == tr and (p1 >= 0.5) != tr:
                    away.append(f"#{r['k']} {q} ({kind})")
            missed += [f"#{r['k']} ({kind})" for _ in [0] if t["lost"] and r["p_lost"] < 0.2]
    inj[n] = {"moved_away": away, "work_losing_missed_at_0.2": missed,
              "probabilities": {k: probs[k] for k in ("#8 fails1 (branch name)", "#9 fails1 (commit messages shown)") if k in probs}}
numbers["guard"]["injection_moved_away"] = inj


def commands(item):
    return [l.split(". ", 1)[1] for l in item["floor"].splitlines() if l[:1].isdigit() and ". git " in l]


forgot = {}  # which work-losing commands each candidate stopped flagging (and its new false alarms), on the same items
for s in ("known", "held"):
    items = jl(RUNS / "guard_small" / f"git3_test_{s}.jsonl")
    P = {"v42": jl(RUNS / "release_eval_v42_full" / f"preds_git3_test_{s}.jsonl")}
    P.update({n: jl(RUNS / f"v43eval_{n}" / f"preds_git3_test_{s}.jsonl") for n in ("r4a", "r4b", "r4c")})
    assert all(len(p) == len(items) and all(i["qtype"] == x["qtype"] for i, x in zip(items, p)) for p in P.values())
    lost = [k for k, i in enumerate(items) if i["qtype"] == "lost"]
    assert all({True: "yes", False: "no"}[items[k]["gold"]] == P["v42"][k]["gold"] for k in lost)
    for n in ("r4a", "r4b", "r4c"):
        f = forgot.setdefault(n, {"missed": [], "new_false_alarms": [], "newly_caught": 0})
        for k in lost:
            a, b = P["v42"][k]["p_yes"] >= 0.2, P[n][k]["p_yes"] >= 0.2
            if items[k]["gold"] and a and not b:
                f["missed"].append({"split": s, "commands": commands(items[k]), "p_v42": P["v42"][k]["p_yes"], "p": P[n][k]["p_yes"]})
            elif items[k]["gold"] and b and not a:
                f["newly_caught"] += 1
            elif not items[k]["gold"] and b and not a:
                f["new_false_alarms"].append({"split": s, "commands": commands(items[k]), "p_v42": P["v42"][k]["p_yes"], "p": P[n][k]["p_yes"]})
    for n in ("v42", "r4a", "r4b", "r4c"):
        ps = sorted(P[n][k]["p_yes"] for k in lost if items[k]["gold"])
        forgot.setdefault("median_p_work_losing", {}).setdefault(s, {})[n] = (ps[len(ps) // 2 - 1] + ps[len(ps) // 2]) / 2 if len(ps) % 2 == 0 else ps[len(ps) // 2]
seqs = {}
for n in ("r4a", "r4b"):
    for x in forgot[n]["missed"]:
        seqs.setdefault((x["split"], tuple(x["commands"])), set()).add(n)
forgot["r4a_r4b_distinct"] = {"sequences": len(seqs), "with_reset_merge": sum(any("reset --merge" in c for c in k[1]) for k in seqs),
                              "missed_by_both": sum(len(v) == 2 for v in seqs.values())}
numbers["guard"]["forgotten_commands"] = forgot
# round 5 (git share kept): the guard on the trainer's readout, recomputed from its saved predictions
r5 = {}
for run in ("sw_v42base", "sw_r5a", "sw_r5b", "sw_r5c"):
    for split in ("git3_test_known", "git3_test_held"):
        rows = jl(RUNS / "guard_small" / "round5" / run / f"preds_{split}_floor.jsonl")
        lost = [r for r in rows if r["qtype"] == "lost"]
        pos, neg = [r for r in lost if r["gold"] == "yes"], [r for r in lost if r["gold"] == "no"]
        r5.setdefault(run, {})[split] = {"flagged": sum(r["probs"][0] >= 0.2 for r in pos), "work_losing": len(pos),
                                         "false_alarms": sum(r["probs"][0] >= 0.2 for r in neg), "safe": len(neg)}
d, _ = diff(json.load(open(RUNS / "v43_round5" / "guard_readout.json")), r5)
checks.append({"analysis": "round5_guard", "script": "reproduce.py (guard_readout.py logic)", "stored": "v43_round5/guard_readout.json",
               "identical": not d, "fields_added_later": 0})
print(f"{'ok  ' if not d else 'DIFF'} {'round5_guard':24s} reproduce.py" + (f"  {d[:3]}" if d else ""))
if d:
    raise SystemExit("round5_guard does not reproduce")
numbers["guard"]["round5_trainer_readout"] = r5
e2e = re.findall(r"(direct only|with where=): exact (\d+)/(\d+), looks per 100 actions ([\d.]+), steps wrong along the way (\d+)",
                 open(RUNS / "paper" / "e2e_where.out").read())
numbers["chains"]["client_where_e2e"] = {k: {"exact": int(a), "chains": int(b), "looks_per_100": float(c), "wrong": int(w)} for k, a, b, c, w in e2e}
mm = [m for n in ("r4a", "r4b") for m in forgot[n]["missed"]]
print(f"ok   forgotten commands: r4a+r4b stopped flagging {len(mm)}, {sum(any('reset --merge' in c for c in m['commands']) for m in mm)} with git reset --merge")
GB = RUNS / "guard_big"
if (GB / "guard_big.json").exists():
    specs = json.load(open(GB / "specs.json"))  # name=run_dir pairs as run on the rig, V42 first
    env = dict(os.environ, RUNS_DIR=str(GB))
    out = OUT / "guard_big.json"
    p = subprocess.run([sys.executable, str(A / "guard_big_compare.py"), str(out)] + specs, env=env, capture_output=True, text=True)
    if p.returncode != 0:
        raise SystemExit(f"guard_big: {p.stderr[-2000:]}")
    d, added = diff(json.load(open(GB / "guard_big.json")), json.load(open(out)))
    checks.append({"analysis": "guard_big", "script": "guard_big_compare.py", "stored": "runs/guard_big/guard_big.json",
                   "identical": not d, "fields_added_later": len(added)})
    print(f"{'ok  ' if not d else 'DIFF'} {'guard_big':24s} guard_big_compare.py")
    if d:
        raise SystemExit(f"guard_big does not reproduce: {d[:5]}")
    numbers["guard"]["larger_set"] = json.load(open(out))
    # the release model served (vLLM + the API, the exact release weights) on the same items: counts and agreement
    served = {}
    for split, readout in (("guard_known", "gd_v42"), ("guard_held", "gd_v42")):
        P = jl(RUNS / "guard_big_served" / f"preds_{split}.jsonl")
        T = jl(GB / readout / f"preds_{split}_floor.jsonl")
        assert len(P) == len(T) and all(a["qtype"] == b["qtype"] and a["gold"] == b["gold"] for a, b in zip(P, T))
        pos = [(a, b) for a, b in zip(P, T) if a["qtype"] == "lost" and a["gold"] == "yes"]
        neg = [(a, b) for a, b in zip(P, T) if a["qtype"] == "lost" and a["gold"] == "no"]
        fails = [a for a in P if a["qtype"] == "fails"]
        served[split] = {"work_losing": len(pos), "flagged": sum(a["p_yes"] >= 0.2 for a, _ in pos), "safe": len(neg),
                         "false_alarms": sum(a["p_yes"] >= 0.2 for a, _ in neg), "fails_n": len(fails),
                         "fails_right": sum(a["pred"] == a["gold"] for a in fails),
                         "same_flag_as_readout": sum((a["p_yes"] >= 0.2) == (b["probs"][0] >= 0.2) for a, b in pos + neg),
                         "lost_items": len(pos) + len(neg)}
    st = json.load(open(RUNS / "guard_big_served" / "report.json"))
    assert all(served[k]["flagged"] == st[k]["flagged_at_0.2"] and served[k]["false_alarms"] == st[k]["false_alarms_at_0.2"]
               and served[k]["same_flag_as_readout"] == st[k]["same_flag_decision"] for k in served), "served counts differ"
    numbers["guard"]["larger_set_served_release"] = served
    SW = RUNS / "guard_big_served_w4a5"
    if SW.exists():
        sw = {}
        for split in ("guard_known", "guard_held"):
            P = jl(SW / f"preds_{split}.jsonl")
            pos = [a for a in P if a["qtype"] == "lost" and a["gold"] == "yes"]
            neg = [a for a in P if a["qtype"] == "lost" and a["gold"] == "no"]
            fails = [a for a in P if a["qtype"] == "fails"]
            sw[split] = {"work_losing": len(pos), "flagged": sum(a["p_yes"] >= 0.2 for a in pos), "safe": len(neg),
                         "false_alarms": sum(a["p_yes"] >= 0.2 for a in neg), "fails_n": len(fails),
                         "fails_right": sum(a["pred"] == a["gold"] for a in fails)}
        st = json.load(open(SW / "report.json"))
        assert all(sw[k]["flagged"] == st[k]["flagged_at_0.2"] and sw[k]["false_alarms"] == st[k]["false_alarms_at_0.2"] for k in sw)
        numbers["guard"]["larger_set_served_w4a5"] = sw
    numbers["guard"]["larger_set_served_agreement"] = {"same": sum(v["same_flag_as_readout"] for v in served.values()),
                                                       "items": sum(v["lost_items"] for v in served.values())}
    print(f"ok   served release model on the larger set: {served['guard_known']['flagged']}/{served['guard_known']['work_losing']}, "
          f"{served['guard_held']['flagged']}/{served['guard_held']['work_losing']}")
    # the weight interpolations (PLAN_v43_wise.md + addendum): single questions, then the pre-registered selection
    W = RUNS / "v43_wise"
    numbers["wise"] = {"single": rerun("wise_single", "v43r2_compare.py", [W, ITEMS, "OUT", "sw_w4a7", "sw_w4a5", "sw_w4b5"], W / "compare.json"),
                       "select": rerun("wise_select", "v43w_select.py", [W / "compare.json", out, "OUT", "sw_w4a7", "sw_w4a5", "sw_w4b5"],
                                       W / "select.json")}
    if (W / "loop_w4a5.json").exists():  # the qualifying interpolation in the loop, 160 fresh chains paired with V42
        numbers["wise"]["loop_w4a5"] = rerun("wise_loop_w4a5", "confirm_compare.py",
                                             [W / "long_chain3_wise_v42.jsonl", W / "long_chain3_wise_w4a5.jsonl", "OUT", "w4a5"],
                                             W / "loop_w4a5.json")
truth = {(r["repo"], r["sid"]): r for r in json.load(open(RUNS / "realuse" / "truth.json"))}
ru = {}
for name in ("v42", "r4c"):
    pred = {(r["repo"], r["sid"]): r for r in json.load(open(RUNS / "realuse" / f"pred_{name}.json"))}
    lost = [k for k in truth if truth[k]["lost"]]
    safe = [k for k in truth if not truth[k]["lost"]]
    fails = [(pf >= 0.5) == tf for k in truth for pf, tf in zip(pred[k]["p_fail"], truth[k]["fails"])]
    ru[name] = {"scenarios": len(truth), "repos": len({k[0] for k in truth}), "work_losing": len(lost),
                "caught": sum(pred[k]["hook"] == "ask" for k in lost), "safe": len(safe),
                "false_alarms": sum(pred[k]["hook"] == "ask" for k in safe),
                "commands_that_fail": sum(tf for k in truth for tf in truth[k]["fails"]),
                "fails_questions": len(fails), "fails_right": sum(fails),
                "median_seconds": sorted(p["seconds"] for p in pred.values())[len(pred) // 2]}
numbers["guard"]["real_use"] = ru
if (RUNS / "realuse_pm" / "truth.json").exists():  # a second run, on the repositories' afternoon state: V42 and w4a5
    truth = {(r["repo"], r["sid"]): r for r in json.load(open(RUNS / "realuse_pm" / "truth.json"))}
    ru2 = {}
    for name in ("v42", "w4a5"):
        pred = {(r["repo"], r["sid"]): r for r in json.load(open(RUNS / "realuse_pm" / f"pred_{name}.json"))}
        lost = [k for k in truth if truth[k]["lost"]]
        safe = [k for k in truth if not truth[k]["lost"]]
        fails = [(pf >= 0.5) == tf for k in truth for pf, tf in zip(pred[k]["p_fail"], truth[k]["fails"])]
        ru2[name] = {"scenarios": len(truth), "work_losing": len(lost), "caught": sum(pred[k]["hook"] == "ask" for k in lost),
                     "safe": len(safe), "false_alarms": sum(pred[k]["hook"] == "ask" for k in safe),
                     "fails_questions": len(fails), "fails_right": sum(fails),
                     "median_seconds": sorted(p["seconds"] for p in pred.values())[len(pred) // 2]}
    numbers["guard"]["real_use_afternoon"] = ru2
print(f"ok   real use: V42 {ru['v42']['caught']}/{ru['v42']['work_losing']} caught, {ru['v42']['false_alarms']}/{ru['v42']['safe']} false alarms")

# 7. Paper experiment A (PLAN_paper_base_loop.md): Eikos-27B in the loop, when its chains are there.
PB = RUNS / "paper" / "long_chain3_eikos_base.jsonl"
if PB.exists():
    numbers["base_loop"] = rerun("base_loop", "paper_base_loop_compare.py", [PB, R, "OUT"], RUNS / "paper" / "base_loop.json")

# 8. Derived numbers the text cites (ratios, changes, per-answer rates), each computed from the values above.
pct = lambda new, old: 100 * (new / old - 1)
g, k = numbers["confident_errors"]["report"]["groups"], numbers["confident_errors"]["eikos_report"]["groups"]
conf_k = lambda G, x: round(G[x]["all"]["share_wrong_conf_ge_0.9"] * G[x]["all"]["wrong"] / 100)
der = {"confident_errors_per_100": {who: {x: 100 * conf_k(G, x) / G[x]["all"]["n"] for x in ("T", "H", "U")} for who, G in (("ekbasis", g), ("eikos", k))},
       "confident_errors_count": {who: {x: conf_k(G, x) for x in ("T", "H", "U")} for who, G in (("ekbasis", g), ("eikos", k))},
       "flaggable_share_at_0.9": {x: 100 - g[x]["all"]["share_wrong_conf_ge_0.9"] for x in ("T", "U")},
       "error_rate_change": {x: pct(g[x]["all"]["error_rate"], k[x]["all"]["error_rate"]) for x in ("T", "H", "U")},
       "error_ratio_U_over_T": g["U"]["all"]["error_rate"] / g["T"]["all"]["error_rate"]}
der["confident_per_answer_factor"] = {x: der["confident_errors_per_100"]["ekbasis"][x] / der["confident_errors_per_100"]["eikos"][x] for x in ("T", "H", "U")}
rs = numbers["confident_errors"]["relative_scale"]
der["own_scale_gap"] = {who: {lab.split(" (")[0]: v["T"] - v["U"] for lab, v in rs[who]["relative"].items()} for who in rs}
rc = numbers["recalibration"]["methods"]
der["recalibration_gap_T_minus_U"] = {m: rc[m]["test_world_T"]["wrong_at_0.9"] - rc[m]["test_world_U"]["wrong_at_0.9"] for m in rc if m.endswith("@all")}
rules_ = numbers["chains"]["rules_compared"]
der["checks_extra_looks"] = rules_["check0.9"]["all"]["looks_per_100"] - rules_["conf0.9"]["all"]["looks_per_100"]
der["two_views_looks_change"] = pct(rules_["dual_conf0.9"]["cards"]["looks_per_100"], rules_["conf0.9"]["cards"]["looks_per_100"])
for name, src in (("rules_default", rules_["check0.9"]), ("fresh_default", numbers["chains"]["fresh"]["check0.9"])):
    t = [src[w]["looks_per_100"] for w in ("jugs", "toggles")]
    u = [src[w]["looks_per_100"] for w in ("machines", "cards")]
    der[f"{name}_unseen_over_trained_looks"] = {"min": min(u) / max(t), "max": max(u) / min(t)}
loop_change = {}
for key, d_, cand in (("r2err", L["r2err"]["pooled"]["check0.9"], "r2err"), ("r2hard", L["r2hard"]["pooled"]["check0.9"], "r2err"),
                      ("r3w20", L["r3w20"]["pooled"]["check0.9"], "r3w20"), ("r4a_explore", L["r4a_explore"]["pooled"]["check0.9"], "r4a"),
                      ("r4b_explore", L["r4b_explore"]["pooled"]["check0.9"], "r4b"), ("r4a_confirm", L["r4a_confirm"]["pooled"]["check0.9"], "r4a"),
                      ("r4b_confirm", L["r4b_confirm"]["pooled"]["check0.9"], "r4b"), ("r4c", L["r4c"]["pooled"]["check0.9"], "r4c")):
    a, b = d_["v42"], d_[cand]
    loop_change[key] = {"silent_wrong": pct(b["wrong_per_100"], a["wrong_per_100"]), "looks": pct(b["looks_per_100"], a["looks_per_100"])}
if "loop_w4a5" in numbers.get("wise", {}):
    d_ = numbers["wise"]["loop_w4a5"]["pooled"]["check0.9"]
    loop_change["w4a5"] = {"silent_wrong": pct(d_["w4a5"]["wrong_per_100"], d_["v42"]["wrong_per_100"]),
                           "looks": pct(d_["w4a5"]["looks_per_100"], d_["v42"]["looks_per_100"])}
der["loop_change_vs_release"] = loop_change
i1, i2, i4 = ideas["ideas1"], ideas["ideas2"], ideas["ideas4"]["part0.9"]
der["ideas_change"] = {m: {"silent_wrong": pct(v["mode"]["wrong_per_100"], v["default_same_chains"]["wrong_per_100"]),
                           "looks": pct(v["mode"]["looks_per_100"], v["default_same_chains"]["looks_per_100"])}
                       for m, v in list(i1.items()) + list(i2.items())}
der["partial_seen_change"] = pct(i4["mode"]["seen_per_100"], i4["default_same_chains"]["seen_per_100"])
ce_r = numbers["rounds"]["round2"]
der["r2err_conf_errors_change_T"] = pct(ce_r["sw_r2err"]["T"]["conf_errors_per_100"], ce_r["sw_v42base"]["T"]["conf_errors_per_100"])
if "larger_set" in numbers["guard"]:
    der["larger_set_over_small"] = {"known": 863 / 51}
sharp = {}
for who, f in (("ekbasis", CE / "preds.jsonl"), ("eikos", CE / "eikos27b" / "preds.jsonl")):
    P = jl(f)
    conf = sorted(float(p["conf"]) for p in P)
    right = lambda g: [float(p["conf"]) for p in P if p["ok"] in (True, "True") and (g is None or p["group"] == g)]
    sharp[who] = {"max_conf": conf[-1], "p90_conf": conf[int(0.9 * len(conf))],
                  "right_at_0.9": {g or "all": 100 * sum(c >= 0.9 for c in right(g)) / len(right(g)) for g in (None, "T", "H", "U")},
                  "right_at_0.99": {g or "all": 100 * sum(c >= 0.99 for c in right(g)) / len(right(g)) for g in (None, "T", "H", "U")}}
der["sharpness"] = sharp
v = {(r["fam"], r["len"], r["i"], r["mode"]): r for r in jl(RUNS / "v43_loop" / "long_chain3.jsonl")}
h = [r for r in jl(RUNS / "v43_loop" / "long_chain3_r2hard.jsonl") if r["mode"] == "check0.9"]
der["r2hard_by_length"] = {L: {who: agg(rows) for who, rows in
                               (("r2hard", [r for r in h if r["len"] == L]), ("release", [v[(r["fam"], r["len"], r["i"], r["mode"])] for r in h if r["len"] == L]))}
                           for L in (100, 200)}
PB = RUNS / "paper" / "long_chain3_eikos_base.jsonl"
if PB.exists():  # paper experiment A: the parent's step probabilities and error rates in the never-look traces
    rows = jl(PB)
    text = [r for r in rows if r["mode"] == "text"]
    ekb_text = jl(R / "long_chain3_controls_trace.jsonl") + [r for r in jl(R / "long_chain3_trace.jsonl") if r["mode"] == "text"]
    par = {}
    for name, fams in (("trained", ("jugs", "toggles")), ("unseen", ("machines", "cards"))):
        st = [s for r in text if r["fam"] in fams for s in r["trace"]]
        ek = [s for r in ekb_text if r["fam"] in fams for s in r["trace"]]
        par[name] = {"max_p_right": max(p for p, ok in st if ok), "max_p_wrong": max(p for p, ok in st if not ok),
                     "error_rate_parent": 100 * sum(not ok for _, ok in st) / len(st),
                     "error_rate_release": 100 * sum(not ok for _, ok in ek) / len(ek)}
        par[name]["error_ratio"] = par[name]["error_rate_parent"] / par[name]["error_rate_release"]
    fails = [r for r in rows if r["mode"] in ("conf0.9", "check0.9") and not r["state_ok"]]
    par["wrong_chains_at_0.9"] = {"chains": len(fails), "only_last_action": sum(r["wrong_steps"] == 1 and not r["trace"][-1][1] for r in fails),
                                  "max_last_p": max(r["trace"][-1][0] for r in fails)}
    der["parent_chains"] = par
    if "base_loop" in numbers:
        import math as _m
        pv = numbers["base_loop"]["P1"]["p_one_sided"]
        e = _m.floor(_m.log10(pv))
        der["P1_p_scientific"] = {"mantissa": pv / 10 ** e, "exponent": -e}
        lp = numbers["base_loop"]["loop"]
        der["parent_looks_ratio"] = {m: lp[m]["ekbasis"]["looks_per_100"] / lp[m]["eikos"]["looks_per_100"] for m in ("conf0.9", "check0.9")}
numbers["derived"] = der
# 9. The seals: every plan this paper relies on must match the SHA-256 recorded before its run.
import hashlib
sealed = {}
for line in open(HERE.parent / "PREREG_sha256.txt"):
    parts = line.split()
    if len(parts) >= 2 and re.fullmatch(r"[0-9a-f]{64}", parts[0]):
        sealed[Path(parts[1]).name] = parts[0]
plans = sorted(HERE.parent.glob("PREREG_*.md")) + sorted((HERE / "prereg").glob("*.md"))
seals = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() == sealed.get(p.name) for p in plans}
numbers["prereg_seals"] = {"plans": len(seals), "match": sum(seals.values()), "mismatch": sorted(k for k, v in seals.items() if not v)}
print(f"{'ok  ' if all(seals.values()) else 'DIFF'} seals: {sum(seals.values())}/{len(seals)} plans match their sealed SHA-256")
if not all(seals.values()):
    raise SystemExit(f"plans changed after sealing: {numbers['prereg_seals']['mismatch']}")
numbers["checks"] = checks
json.dump(numbers, open(HERE / "numbers.json", "w"), indent=1)
print(f"{sum(c['identical'] for c in checks)}/{len(checks)} analyses reproduce their stored results; numbers.json written")
