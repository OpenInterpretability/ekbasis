"""WS-U confirmatory test, step 1 (dev data only, no model call): fix every free parameter of the "check when sure"
policy before any fresh item exists, and write them to policy_params.json.

Population: WS-P's dev dataset (29,029 answered questions) restricted to the PRIMARY suites; confident = confidence ≥ 0.9.
Signals on WS-P's 6,000-question sample (population weights per (suite, correct), as in parts 2–4):
  famobs  = family error rate, observable family key, leave-one-out over the dev dataset, Beta(1, 1) prior
            (the dev stand-in for the fresh signal: dev history as a warm start + online updates);
  minpert = 1 − min(P_reordered(answer), P_prefixed(answer))  (WS-P's two perturbations);
  verify  = P(no) on the self-check question.
Transform: each signal → its weighted mid-ECDF among the dev confident answers of the primary suites.
Score: the mean of the transformed signals; variant A uses all three everywhere, variant B drops the self-check on
git_wild and shell_wild. Rules fixed here, before running:
  - variant choice: the one with the lower dev verification share at 80% recall (ties → A);
  - threshold τ: the dev cutoff maximising min(recall − 0.80, 0.30 − share) ("equal margins"), flag = score ≥ τ;
  - accumulation arm: signal ab_gap = |P_A(answer_A) − P_B(answer_A)| (A: all actions at once, B: released
    simulate, last step), τ_acc by the same equal-margins rule on the dev accumulation confident A answers.
python3 dev_calibrate.py  ->  policy_params.json, dev_reference.json"""
import bisect
import collections
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from common import auroc  # noqa: E402

P = "/root/decis/mission/P"
U = "/root/decis/mission/U"
ACC = "/root/decis/capability/accumulation/results.jsonl"
PRIMARY = ["rules_stress", "sql_wild", "shell_wild", "git_wild", "accumulation"]
NO_SELFCHECK = {"git_wild", "shell_wild"}


def observable(suite, family):
    """Addendum 2's observable family key (unchanged)."""
    parts = family.split("|")
    if suite in ("apps", "accumulation", "planning_probe"):
        return parts[0]
    if suite == "habit_vs_rule":
        return "|".join(parts[:2])
    if suite == "web":
        return parts[-1]
    return family


def mid_ecdf(values, weights):
    """Sorted support and cumulative weights: F(x) = W(< x) + 0.5 W(= x), normalised."""
    order = np.argsort(values, kind="mergesort")
    v, w = np.asarray(values, float)[order], np.asarray(weights, float)[order]
    sup, cum = [], []
    tot = w.sum()
    i, below = 0, 0.0
    while i < len(v):
        j = i
        while j < len(v) and v[j] == v[i]:
            j += 1
        here = w[i:j].sum()
        sup.append(float(v[i]))
        cum.append([below / tot, here / tot])
        below += here
        i = j
    return {"support": sup, "below_here": cum}


def apply_ecdf(t, x):
    k = bisect.bisect_left(t["support"], x)
    if k < len(t["support"]) and t["support"][k] == x:
        b, h = t["below_here"][k]
        return b + 0.5 * h
    if k == 0:
        return 0.0
    b, h = t["below_here"][k - 1]
    return b + h


def curve(score, wrong, w):
    """Every distinct cutoff: (τ, recall, share) with flag = score ≥ τ, weighted."""
    s, y, w = np.asarray(score, float), np.asarray(wrong, bool), np.asarray(w, float)
    order = np.argsort(-s, kind="mergesort")
    s, y, w = s[order], y[order], w[order]
    cw, ce = np.cumsum(w) / w.sum(), np.cumsum(w * y) / (w * y).sum()
    out = []
    for i in range(len(s)):
        if i + 1 < len(s) and s[i + 1] == s[i]:
            continue
        out.append((float(s[i]), float(ce[i]), float(cw[i])))
    return out


def equal_margins(cv):
    best = max(cv, key=lambda c: min(c[1] - 0.80, 0.30 - c[2]))
    return {"tau": best[0], "recall": round(best[1], 4), "share": round(best[2], 4),
            "margin": round(min(best[1] - 0.80, 0.30 - best[2]), 4)}


def share_at(cv, target):
    return round(next(c[2] for c in cv if c[1] >= target - 1e-12), 4)


def main():
    full = {}
    fam_n, fam_e = collections.Counter(), collections.Counter()
    for l in open(f"{P}/data/dataset.jsonl"):
        r = json.loads(l)
        key = (r["suite"], observable(r["suite"], r["family"]))
        full[r["qid"]] = {"suite": r["suite"], "key": key, "conf": r["conf"], "correct": r["correct"]}
        fam_n[key] += 1
        fam_e[key] += not r["correct"]
    sample = [json.loads(l) for l in open(f"{P}/results/infer_raw.jsonl")]
    live = collections.defaultdict(dict)
    for j in map(json.loads, open(f"{U}/results/part2_live.jsonl")):
        if "error" not in j and j.get("probabilities"):
            live[j["qid"]][j["kind"]] = j
    pop = collections.Counter((r["suite"], r["correct"]) for r in full.values() if r["conf"] >= 0.9 and r["suite"] in PRIMARY)
    samp = collections.Counter((s["suite"], s["correct"]) for s in sample if s["conf"] >= 0.9 and s["suite"] in PRIMARY)
    rows = []
    for s in sample:
        if s["suite"] not in PRIMARY or s["conf"] < 0.9 or "verify" not in live.get(s["qid"], {}):
            continue
        f = full[s["qid"]]
        wrong = not s["correct"]
        rows.append({"suite": s["suite"], "wrong": wrong, "w": pop[(s["suite"], s["correct"])] / samp[(s["suite"], s["correct"])],
                     "maxp": 1 - s["conf"],
                     "famobs": (fam_e[f["key"]] - wrong + 1) / (fam_n[f["key"]] - 1 + 2),
                     "minpert": 1 - min(s["reorder"]["p_original"], s["para"]["p_original"]),
                     "verify": float(live[s["qid"]]["verify"]["probabilities"].get("no", 0.0))})
    W = [r["w"] for r in rows]
    Y = [r["wrong"] for r in rows]
    tf = {k: mid_ecdf([r[k] for r in rows], W) for k in ("famobs", "minpert", "verify")}
    for r in rows:
        for k in tf:
            r["F_" + k] = apply_ecdf(tf[k], r[k])
        r["S_A"] = (r["F_famobs"] + r["F_minpert"] + r["F_verify"]) / 3
        r["S_B"] = (r["F_famobs"] + r["F_minpert"]) / 2 if r["suite"] in NO_SELFCHECK else r["S_A"]
    ref = {"n_confident_sample": len(rows), "confident_errors_sample": int(sum(Y)),
           "population_confident": {s: sum(v for (su, c), v in pop.items() if su == s) for s in PRIMARY},
           "population_confident_errors": {s: pop[(s, False)] for s in PRIMARY}, "variants": {}}
    for var in ("S_A", "S_B"):
        cv = curve([r[var] for r in rows], Y, W)
        per = {}
        for su in PRIMARY:
            sub = [r for r in rows if r["suite"] == su]
            per[su] = {"auroc": round(auroc([r[var] for r in sub], [r["wrong"] for r in sub]), 4),
                       "auroc_maxp": round(auroc([r["maxp"] for r in sub], [r["wrong"] for r in sub]), 4)}
        ref["variants"][var] = {"auroc_weighted": round(auroc([r[var] for r in rows], Y, W), 4),
                                "auroc_maxp_weighted": round(auroc([r["maxp"] for r in rows], Y, W), 4),
                                "share_at": {t: share_at(cv, t / 100) for t in (50, 80, 90, 95)},
                                "equal_margins": equal_margins(cv), "per_suite": per}
    a, b = ref["variants"]["S_A"], ref["variants"]["S_B"]
    chosen = "S_B" if b["share_at"][80] < a["share_at"][80] else "S_A"
    em = ref["variants"][chosen]["equal_margins"]
    # per-suite recall/share at the chosen τ (dev), for the record
    ref["chosen"] = chosen
    ref["at_tau_per_suite"] = {}
    for su in PRIMARY:
        sub = [r for r in rows if r["suite"] == su]
        fl = [r[chosen] >= em["tau"] for r in sub]
        we = sum(r["w"] for r in sub if r["wrong"])
        ref["at_tau_per_suite"][su] = {
            "recall": round(sum(r["w"] for r, f in zip(sub, fl) if f and r["wrong"]) / we, 4) if we else None,
            "share": round(sum(r["w"] for r, f in zip(sub, fl) if f) / sum(r["w"] for r in sub), 4)}
    # accumulation arm
    acc = collections.defaultdict(dict)
    for j in map(json.loads, open(ACC)):
        acc[j["id"]][j["cond"]] = j
    ar = []
    for iid, d in acc.items():
        if "A" in d and "B" in d and d["A"].get("probabilities") and d["B"].get("probabilities") and d["A"]["confidence"] >= 0.9:
            pa, pb = d["A"]["probabilities"], d["B"]["probabilities"]
            la = max(pa, key=pa.get)
            ar.append({"wrong": not d["A"]["correct"], "maxp": 1 - d["A"]["confidence"],
                       "ab_gap": abs(pa.get(la, 0.0) - pb.get(la, 0.0))})
    cva = curve([r["ab_gap"] for r in ar], [r["wrong"] for r in ar], [1.0] * len(ar))
    arm = {"n_confident": len(ar), "confident_errors": int(sum(r["wrong"] for r in ar)),
           "auroc_ab_gap": round(auroc([r["ab_gap"] for r in ar], [r["wrong"] for r in ar]), 4),
           "auroc_maxp": round(auroc([r["maxp"] for r in ar], [r["wrong"] for r in ar]), 4),
           "share_at": {t: share_at(cva, t / 100) for t in (50, 80, 90, 95)}, "equal_margins": equal_margins(cva)}
    ref["accumulation_arm"] = arm
    params = {"primary_suites": PRIMARY, "secondary_suites": ["planning_probe"], "confident": 0.9,
              "variant": chosen, "no_selfcheck_suites": sorted(NO_SELFCHECK) if chosen == "S_B" else [],
              "signals": ["famobs", "minpert", "verify"], "transforms": tf, "tau": em["tau"],
              "dev_at_tau": {"recall": em["recall"], "share": em["share"]},
              "family_prior": [1, 1], "population_confident": ref["population_confident"],
              "arm": {"signal": "ab_gap", "tau": arm["equal_margins"]["tau"],
                      "dev_at_tau": {"recall": arm["equal_margins"]["recall"], "share": arm["equal_margins"]["share"]}}}
    json.dump(params, open(os.path.join(HERE, "policy_params.json"), "w"), indent=1)
    json.dump(ref, open(os.path.join(HERE, "dev_reference.json"), "w"), indent=1)
    print(json.dumps({k: v for k, v in ref.items()}, indent=1))
    print("tau", params["tau"], "arm tau", params["arm"]["tau"])


if __name__ == "__main__":
    main()
