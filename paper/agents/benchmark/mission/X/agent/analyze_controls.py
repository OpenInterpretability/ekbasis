"""Controls and fresh replication (SPEC Addenda A and B): harm / safe success / blocked per condition on the harm tasks, the
pre-registered contrasts with 95% task-bootstrap CIs, controls, cost (agent + oracle), foresee latency (service-side ms in
the panel beats), and panel flag rates under both definitions.
    python3 analyze_controls.py original   (runs_xstudy.jsonl + runs_xctrl.jsonl, 47 tasks)
    python3 analyze_controls.py fresh      (runs_xfresh.jsonl, 35 tasks)
  -> summary_controls_<set>.json"""
import collections
import json
import os
import random
import statistics as st
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LV = os.path.abspath(os.path.join(HERE, "..", "..", "..", "launch_video"))


def rate(rows, key):
    v = [bool(r[key]) for r in rows if r.get(key) is not None]
    return {"k": sum(v), "n": len(v), "rate": round(sum(v) / len(v), 4) if v else None}


def boot(rows, key, a, b, reps=10000, seed=11):
    by = collections.defaultdict(lambda: collections.defaultdict(list))
    for r in rows:
        if r.get(key) is not None:
            by[r["id"]][r["cond"]].append(bool(r[key]))
    ids = [i for i, v in by.items() if v[a] and v[b]]
    if not ids:
        return None
    rng = random.Random(seed)

    def d(sample):
        x = [v for i in sample for v in by[i][a]]
        y = [v for i in sample for v in by[i][b]]
        return sum(x) / len(x) - sum(y) / len(y)
    ds = sorted(d([rng.choice(ids) for _ in ids]) for _ in range(reps))
    return {"diff": round(d(ids), 4), "ci95": [round(ds[int(.025 * reps)], 4), round(ds[int(.975 * reps) - 1], 4)], "tasks": len(ids), "a": a, "b": b}


def latency(rows):
    out = collections.defaultdict(list)
    for r in rows:
        p = os.path.join(LV, "sessions", f"{r['name']}.json")
        if not os.path.exists(p):
            continue
        for bt in json.load(open(p))["beats"]:
            if bt["kind"] == "hud" and bt["hud"].get("ms") is not None:
                out[r["cond"]].append(bt["hud"]["ms"])
    res = {}
    for c, v in out.items():
        v = sorted(v)
        res[c] = {"calls": len(v), "median_ms": round(st.median(v)), "p90_ms": round(v[int(0.9 * (len(v) - 1))])}
    return res


def main(which):
    files = ["runs_xstudy.jsonl", "runs_xctrl.jsonl"] if which == "original" else ["runs_xfresh.jsonl"]
    rows = [json.loads(l) for f in files if os.path.exists(os.path.join(HERE, f)) for l in open(os.path.join(HERE, f))]
    rows = [r for r in rows if r.get("harm") is not None]
    conds = [c for c in ("blind", "placebo", "see", "oracle_llm", "oracle_truth") if any(r["cond"] == c for r in rows)]
    harm = [r for r in rows if r["kind"] == "harm"]
    ctrl = [r for r in rows if r["kind"] == "control"]
    out = {"set": which, "runs": len(rows), "conditions": conds,
           "harm_tasks": {c: {k: rate([r for r in harm if r["cond"] == c], k) for k in ("harm", "success", "blocked")} for c in conds},
           "controls": {c: {k: rate([r for r in ctrl if r["cond"] == c], k) for k in ("harm", "success", "blocked")} for c in conds}}
    pairs = [("see", "blind"), ("see", "placebo"), ("placebo", "blind"), ("see", "oracle_llm"), ("see", "oracle_truth"), ("oracle_llm", "oracle_truth")]
    out["contrasts"] = {f"{a}-{b}": {k: boot(harm, k, a, b) for k in ("harm", "success", "blocked")} for a, b in pairs if a in conds and b in conds}
    out["by_app_harm"] = {app: {c: rate([r for r in harm if r["app"] == app and r["cond"] == c], "harm") for c in conds}
                          for app in sorted({r["app"] for r in harm})}
    out["cost_per_run_usd"] = {c: {"agent": round(st.mean([r.get("cost_usd") or 0 for r in rows if r["cond"] == c]), 4),
                                   "oracle": round(st.mean([r.get("oracle_cost_usd") or 0 for r in rows if r["cond"] == c]), 4)} for c in conds}
    out["seconds_per_run"] = {c: round(st.mean([r.get("seconds") or 0 for r in rows if r["cond"] == c]), 1) for c in conds}
    out["foresee_calls_per_run"] = {c: round(st.mean([r.get("foresee_calls") or 0 for r in rows if r["cond"] == c]), 2) for c in conds}
    out["panel_latency_service_ms"] = latency(rows)
    # definition (i): by path element
    d1 = collections.defaultdict(lambda: [0, 0, 0, 0])
    for r in rows:
        for h in r.get("huds", []):
            k = f"{r['cond']}|{r['app']}"
            if h["on_harmful"]:
                d1[k][0] += h["flagged"]
                d1[k][1] += 1
            if h["on_safe"]:
                d1[k][2] += h["flagged"]
                d1[k][3] += 1
    out["flags_by_path_element"] = {k: {"flagged_on_harmful": f"{a}/{b}", "flagged_on_safe": f"{c}/{d}"} for k, (a, b, c, d) in sorted(d1.items())}
    pooled = collections.defaultdict(lambda: [0, 0, 0, 0])
    for k, v in d1.items():
        c = k.split("|")[0]
        for i in range(4):
            pooled[c][i] += v[i]
    out["flags_by_path_element_pooled"] = {c: {"flagged_on_harmful": f"{v[0]}/{v[1]}", "flagged_on_safe": f"{v[2]}/{v[3]}"} for c, v in pooled.items()}
    # definition (ii): by true consequence
    tf = subprocess.run(["node", os.path.join(HERE, "truth_flags.mjs"), *files], capture_output=True, text=True, cwd=HERE)
    try:
        d2 = json.loads(tf.stdout)
    except json.JSONDecodeError:
        d2 = {"error": tf.stderr[-500:]}
    out["flags_by_true_consequence"] = {}
    pooled2 = collections.defaultdict(lambda: {"tp": 0, "fn": 0, "fp": 0, "tn": 0, "conf_wrong": []})
    for k, v in d2.items() if isinstance(d2, dict) and "error" not in d2 else []:
        sens = v["tp"] / (v["tp"] + v["fn"]) if v["tp"] + v["fn"] else None
        ff = v["fp"] / (v["fp"] + v["tn"]) if v["fp"] + v["tn"] else None
        out["flags_by_true_consequence"][k] = {"sensitivity": f"{v['tp']}/{v['tp'] + v['fn']}", "false_flags": f"{v['fp']}/{v['fp'] + v['tn']}",
                                               "sens": round(sens, 4) if sens is not None else None, "ff": round(ff, 4) if ff is not None else None}
        c = k.split("|")[0]
        for x in ("tp", "fn", "fp", "tn"):
            pooled2[c][x] += v[x]
        pooled2[c]["conf_wrong"] += v["conf_wrong"]
    out["flags_by_true_consequence_pooled"] = {c: {"sensitivity": f"{v['tp']}/{v['tp'] + v['fn']}", "false_flags": f"{v['fp']}/{v['fp'] + v['tn']}",
                                                   "wrong_answers": len(v["conf_wrong"]), "wrong_at_conf_ge_0.9": sum(x >= 0.9 for x in v["conf_wrong"])}
                                               for c, v in pooled2.items()}
    if "error" in d2:
        out["flags_by_true_consequence_error"] = d2["error"]
    json.dump(out, open(os.path.join(HERE, f"summary_controls_{which}.json"), "w"), indent=1)
    print(json.dumps({k: out[k] for k in ("harm_tasks", "contrasts")}, indent=1))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "original")
