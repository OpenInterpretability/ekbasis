"""WS-U confirm-2, fitting on DEV ONLY (no fresh data, no confirm-1 data, no model call): two new ways to set the
threshold of the frozen policy score S (confirm/policy.py, variant B, unchanged).

P-domain (per-suite thresholds, equal recall under a budget):
  - for a common recall target r, each primary suite gets τ_s(r) = the highest dev cutoff whose weighted recall in that
    suite is ≥ r;
  - r* = the largest r (grid step 0.0025) whose overall dev share of confident answers verified is ≤ 0.25. Overall
    means each suite is weighted by its dev confident population (and its errors by its dev confident errors).
P-conformal (Mondrian, group-conditional split conformal on the miss rate, α = 0.15):
  - partition: a family with ≥ 10 dev confident errors is its own group; every other family falls into its suite's
    "rest" group;
  - τ_g = the k-th smallest dev score among the group's confident errors, k = floor(α (n_g + 1)); k = 0 → τ_g = 0
    (check everything in the group);
  - under exchangeability of a group's errors this gives P(score ≥ τ_g | confident error in g) ≥ 1 − α = 0.85
    (conformal risk control with the 0/1 miss loss).
python3 fit_dev.py  ->  params_confirm2.json, dev_reference_confirm2.json"""
import collections
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
U = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(U, "confirm"))
sys.path.insert(0, U)
from common import auroc  # noqa: E402
from dev_calibrate import curve  # noqa: E402
from policy import Policy, observable  # noqa: E402

P = "/root/decis/mission/P"
PRIMARY = ["rules_stress", "sql_wild", "shell_wild", "git_wild", "accumulation"]
BUDGET = 0.25
ALPHA = 0.15
N_MIN = 10


def dev_rows(pol):
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
        famobs = (fam_e[f["key"]] - wrong + 1) / (fam_n[f["key"]] - 1 + 2)
        mp = 1 - min(s["reorder"]["p_original"], s["para"]["p_original"])
        vf = float(live[s["qid"]]["verify"]["probabilities"].get("no", 0.0))
        rows.append({"suite": s["suite"], "family": f["key"][1], "wrong": wrong,
                     "w": pop[(s["suite"], s["correct"])] / samp[(s["suite"], s["correct"])],
                     "maxp": 1 - s["conf"], "S": pol.score(s["suite"], famobs, mp, vf)})
    return rows, pop


def at(rows, flag):
    w = np.array([r["w"] for r in rows])
    y = np.array([r["wrong"] for r in rows])
    f = np.array(flag, bool)
    return float((w * y * f).sum() / (w * y).sum()), float((w * f).sum() / w.sum())


def main():
    pol = Policy()
    rows, pop = dev_rows(pol)
    conf_pop = {s: pop[(s, True)] + pop[(s, False)] for s in PRIMARY}
    err_pop = {s: pop[(s, False)] for s in PRIMARY}
    by = {s: [r for r in rows if r["suite"] == s] for s in PRIMARY}
    curves = {s: curve([r["S"] for r in by[s]], [r["wrong"] for r in by[s]], [r["w"] for r in by[s]]) for s in PRIMARY}

    def tau_for(s, r):  # the highest cutoff reaching recall >= r in suite s
        return next(c[0] for c in curves[s] if c[1] >= r - 1e-12)

    best = None
    for r in np.arange(0.70, 0.9975, 0.0025):
        taus = {s: tau_for(s, r) for s in PRIMARY}
        per = {s: at(by[s], [x["S"] >= taus[s] for x in by[s]]) for s in PRIMARY}
        share = sum(conf_pop[s] * per[s][1] for s in PRIMARY) / sum(conf_pop.values())
        recall = sum(err_pop[s] * per[s][0] for s in PRIMARY) / sum(err_pop.values())
        if share <= BUDGET:
            best = {"r": round(float(r), 4), "taus": taus, "dev_overall": {"recall": round(recall, 4), "share": round(share, 4)},
                    "dev_per_suite": {s: {"recall": round(per[s][0], 4), "share": round(per[s][1], 4)} for s in PRIMARY}}
    # Mondrian conformal partition and thresholds
    errs = [r for r in rows if r["wrong"]]
    n_fam = collections.Counter((r["suite"], r["family"]) for r in errs)
    own = sorted(k for k, n in n_fam.items() if n >= N_MIN)
    group = lambda r: f"{r['suite']}|{r['family']}" if (r["suite"], r["family"]) in set(own) else f"{r['suite']}|*rest*"  # noqa: E731
    by_g = collections.defaultdict(list)
    for r in errs:
        by_g[group(r)].append(r["S"])
    taus_g = {}
    for g, sc in sorted(by_g.items()):
        sc = sorted(sc)
        k = math.floor(ALPHA * (len(sc) + 1))
        taus_g[g] = {"n_errors": len(sc), "k": k, "tau": float(sc[k - 1]) if k >= 1 else 0.0}
    for s in PRIMARY:  # a suite whose rest group has no dev error: check everything there (no calibration)
        taus_g.setdefault(f"{s}|*rest*", {"n_errors": 0, "k": 0, "tau": 0.0})
    flag_c = [r["S"] >= taus_g[group(r)]["tau"] for r in rows]
    conf_per = {s: at([r for r in rows if r["suite"] == s], [f for r, f in zip(rows, flag_c) if r["suite"] == s]) for s in PRIMARY}
    conf_overall = (sum(err_pop[s] * conf_per[s][0] for s in PRIMARY) / sum(err_pop.values()),
                    sum(conf_pop[s] * conf_per[s][1] for s in PRIMARY) / sum(conf_pop.values()))
    gl = at(rows, [r["S"] >= pol.tau for r in rows])
    params = {"score": "confirm/policy.py Policy.score (variant B, unchanged)", "tau_global": pol.tau,
              "domain": {"budget": BUDGET, "r_star": best["r"], "taus": best["taus"]},
              "conformal": {"alpha": ALPHA, "n_min": N_MIN, "own_groups": [f"{s}|{f}" for s, f in own], "taus": taus_g},
              "population_confident": conf_pop, "population_confident_errors": err_pop}
    ref = {"dev_global_at_tau": {"recall": round(gl[0], 4), "share": round(gl[1], 4)}, "domain": best,
           "conformal_in_sample": {"overall": {"recall": round(conf_overall[0], 4), "share": round(conf_overall[1], 4)},
                                   "per_suite": {s: {"recall": round(v[0], 4), "share": round(v[1], 4)} for s, v in conf_per.items()},
                                   "groups": len(taus_g), "own_family_groups": len(own)},
           "note": "dev numbers are in-sample (the thresholds were fitted on these rows)"}
    json.dump(params, open(os.path.join(HERE, "params_confirm2.json"), "w"), indent=1)
    json.dump(ref, open(os.path.join(HERE, "dev_reference_confirm2.json"), "w"), indent=1)
    print(json.dumps(ref, indent=1))
    print(json.dumps({k: v for k, v in taus_g.items()}, indent=0)[:3000])


if __name__ == "__main__":
    main()
