"""WS-U confirmatory test: the frozen policy on the fresh rows; primary criterion, secondary metrics, the accumulation
arm (SPEC_confirm.md). No model call.
python3 confirm_analyze.py  ->  ../results/confirm/confirm.json   (CONFIRM_DIR / CONFIRM_OUT: test harness only)"""
import collections
import hashlib
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
from common import auroc  # noqa: E402
from policy import FamilyRates, Policy, observable  # noqa: E402

OUT = os.environ.get("CONFIRM_OUT", os.path.join(os.path.dirname(HERE), "results", "confirm"))
BASE = os.environ.get("CONFIRM_DIR", HERE)
STREAM_SEED = "wsu-confirm-20261006"
N_BOOT = 2000
PRIMARY = ["rules_stress", "sql_wild", "shell_wild", "git_wild", "accumulation"]
TARGETS = (0.5, 0.8, 0.9, 0.95)


def jl(p):
    return [json.loads(l) for l in open(p) if l.strip()]


def at_tau(flag, wrong, w):
    flag, wrong, w = np.asarray(flag, bool), np.asarray(wrong, bool), np.asarray(w, float)
    we = (w * wrong).sum()
    return (float((w * wrong * flag).sum() / we) if we else float("nan")), float((w * flag).sum() / w.sum())


def share_needed(score, wrong, w, targets=TARGETS):
    """Post hoc: the weighted share of confident answers to verify, most suspicious first, to catch each target share of
    the weighted confident errors (ties: whole tie group)."""
    s, y, w = np.asarray(score, float), np.asarray(wrong, bool), np.asarray(w, float)
    order = np.argsort(-s, kind="mergesort")
    s, y, w = s[order], y[order], w[order]
    cw, ce = np.cumsum(w) / w.sum(), np.cumsum(w * y) / (w * y).sum()
    last = np.r_[s[1:] != s[:-1], True]  # end of each tie group
    out = {}
    for t in targets:
        i = int(np.flatnonzero(last & (ce >= t - 1e-12))[0])
        out[str(int(t * 100))] = round(float(cw[i]), 4)
    return out


def suite_weights(rows, pop):
    tot_pop = sum(pop[s] for s in PRIMARY)
    cnt = collections.Counter(r["suite"] for r in rows)
    tot = sum(cnt[s] for s in PRIMARY)
    return {s: (pop[s] / tot_pop) / (cnt[s] / tot) for s in PRIMARY if cnt[s]}


def boot(rows, pop, pol, rng):
    """Cluster bootstrap within suites (cluster = the scenario, row field 'req'): recall and share at τ, AUROC(S) −
    AUROC(maxp), weights recomputed per replicate."""
    clusters = collections.defaultdict(lambda: collections.defaultdict(list))
    for i, r in enumerate(rows):
        clusters[r["suite"]][r["req"]].append(i)
    keys = {s: list(c) for s, c in clusters.items()}
    S = np.array([r["S"] for r in rows])
    M = np.array([r["maxp"] for r in rows])
    Y = np.array([r["wrong"] for r in rows])
    F = S >= pol.tau
    suite = np.array([r["suite"] for r in rows])
    res = {"recall": [], "share": [], "auc_diff": []}
    for _ in range(N_BOOT):
        idx = []
        for s, ks in keys.items():
            pick = rng.integers(0, len(ks), len(ks))
            for j in pick:
                idx += clusters[s][ks[j]]
        idx = np.array(idx)
        sw = suite_weights([rows[i] for i in idx], pop)
        w = np.array([sw[suite[i]] for i in idx])
        rc, sh = at_tau(F[idx], Y[idx], w)
        res["recall"].append(rc)
        res["share"].append(sh)
        res["auc_diff"].append(auroc(S[idx], Y[idx], w) - auroc(M[idx], Y[idx], w))
    return {k: [round(float(np.percentile(v, 2.5)), 4), round(float(np.percentile(v, 97.5)), 4)] for k, v in res.items()}


def main():
    pol = Policy()
    params = pol.p
    pop = params["population_confident"]
    os.makedirs(OUT, exist_ok=True)
    allrows = jl(os.path.join(BASE, "fresh_rows.jsonl"))
    rows = [r for r in allrows if r["exclude"] is None]
    extra = {e["rid"]: e for e in jl(os.path.join(BASE, "extra.jsonl")) if "error" not in e} \
        if os.path.exists(os.path.join(BASE, "extra.jsonl")) else {}
    # online family rates over every kept fresh row (all suites, confident or not), a fixed pseudo-random order
    warm, cold = FamilyRates.from_dev(tuple(params["family_prior"])), FamilyRates(tuple(params["family_prior"]))
    for r in sorted(rows, key=lambda r: hashlib.sha256(f"{STREAM_SEED}|{r['rid']}".encode()).hexdigest()):
        k = (r["suite"], observable(r["suite"], r["family"]))
        r["famobs"], r["famobs_cold"] = warm.rate(k), cold.rate(k)
        warm.update(k, not r["correct"])
        cold.update(k, not r["correct"])
    conf, missing = [], collections.Counter()
    for r in rows:
        if (r["conf"] or 0) < 0.9:
            continue
        e = extra.get(r["rid"])
        if e is None:
            missing[r["suite"]] += 1
            continue
        mp = 1 - min(e["reorder"]["p_original"], e["para"]["p_original"])
        vf = float((e["verify"]["probabilities"] or {}).get("no", 0.0))
        conf.append({"suite": r["suite"], "req": r["req"], "rid": r["rid"], "wrong": not r["correct"], "maxp": 1 - r["conf"],
                     "famobs": r["famobs"], "famobs_cold": r["famobs_cold"], "minpert": mp, "verify": vf,
                     "S": pol.score(r["suite"], r["famobs"], mp, vf),
                     "S_cold": pol.score(r["suite"], r["famobs_cold"], mp, vf),
                     "S_all3": pol.score_all3(r["famobs"], mp, vf)})
    res = {"policy": {"variant": params["variant"], "tau": params["tau"], "no_selfcheck": params["no_selfcheck_suites"],
                      "dev_at_tau": params["dev_at_tau"]},
           "rows": {"built": len(allrows), "excluded_dev_overlap": sum(r["exclude"] == "dev_overlap" for r in allrows),
                    "excluded_fresh_duplicate": sum(r["exclude"] == "fresh_duplicate" for r in allrows), "kept": len(rows),
                    "confident_without_extra_calls": dict(missing)}}
    prim = [r for r in conf if r["suite"] in PRIMARY]
    sw = suite_weights(prim, pop)
    W = [sw[r["suite"]] for r in prim]
    Y = [r["wrong"] for r in prim]
    rc, sh = at_tau([r["S"] >= pol.tau for r in prim], Y, W)
    rng = np.random.default_rng(20261006)
    ci = boot(prim, pop, pol, rng)
    res["primary"] = {"n_confident": len(prim), "confident_errors": int(sum(Y)), "suite_weights": {k: round(v, 4) for k, v in sw.items()},
                      "recall_at_tau": round(rc, 4), "share_at_tau": round(sh, 4),
                      "recall_ci95": ci["recall"], "share_ci95": ci["share"],
                      "PASS": bool(rc >= 0.80 and sh <= 0.30)}
    sigs = ["S", "maxp", "famobs", "minpert", "verify", "S_cold", "S_all3"]
    res["secondary"] = {
        "auroc_weighted": {s: round(auroc([r[s] for r in prim], Y, W), 4) for s in sigs},
        "auroc_S_minus_maxp_ci95": ci["auc_diff"],
        "share_needed_weighted": {s: share_needed([r[s] for r in prim], Y, W) for s in sigs},
        "unweighted_at_tau": dict(zip(("recall", "share"), (round(x, 4) for x in at_tau([r["S"] >= pol.tau for r in prim], Y, [1.0] * len(prim))))),
        "cold_start_at_tau": dict(zip(("recall", "share"), (round(x, 4) for x in at_tau([r["S_cold"] >= pol.tau for r in prim], Y, W)))),
        "all3_at_tau": dict(zip(("recall", "share"), (round(x, 4) for x in at_tau([r["S_all3"] >= pol.tau for r in prim], Y, W)))),
    }
    per = {}
    for su in PRIMARY + ["planning_probe"]:
        sub = [r for r in conf if r["suite"] == su]
        if not sub:
            continue
        ys = [r["wrong"] for r in sub]
        rcs, shs = at_tau([r["S"] >= pol.tau for r in sub], ys, [1.0] * len(sub))
        per[su] = {"n_confident": len(sub), "confident_errors": int(sum(ys)), "recall_at_tau": round(rcs, 4),
                   "share_at_tau": round(shs, 4),
                   **{f"auroc_{s}": round(auroc([r[s] for r in sub], ys), 4) for s in ("S", "maxp", "S_all3", "verify", "minpert", "famobs")}}
        if su in ("git_wild", "shell_wild"):
            rca, sha = at_tau([r["S_all3"] >= pol.tau for r in sub], ys, [1.0] * len(sub))
            per[su]["exploratory_selfcheck_kept_at_tau"] = {"recall": round(rca, 4), "share": round(sha, 4)}
    res["per_suite"] = per
    if "planning_probe" in per:
        res["planning_secondary"] = per["planning_probe"]
    # accumulation arm: simulate (B) vs direct (A) on the same fresh items
    kept_acc = {r["req"] for r in rows if r["suite"] == "accumulation"}
    acc = collections.defaultdict(dict)
    for j in jl(os.path.join(BASE, "cap", "accumulation", "results.jsonl")):
        if not j.get("error"):
            acc[j["id"]][j["cond"]] = j
    ar = []
    for iid, d in acc.items():
        if iid in kept_acc and "A" in d and "B" in d and d["A"]["confidence"] >= 0.9:
            pa, pb = d["A"]["probabilities"], d["B"]["probabilities"]
            la = max(pa, key=pa.get)
            ar.append({"wrong": not d["A"]["correct"], "maxp": 1 - d["A"]["confidence"],
                       "ab_gap": abs(pa.get(la, 0.0) - pb.get(la, 0.0)), "requests_B": d["B"].get("requests")})
    if ar:
        ya = [r["wrong"] for r in ar]
        tau_a = params["arm"]["tau"]
        rca, sha = at_tau([r["ab_gap"] >= tau_a for r in ar], ya, [1.0] * len(ar))
        brc, bsh, bd = [], [], []
        g = np.array([r["ab_gap"] for r in ar])
        m = np.array([r["maxp"] for r in ar])
        yy = np.array(ya)
        for _ in range(N_BOOT):
            i = rng.integers(0, len(ar), len(ar))
            a1, a2 = at_tau(g[i] >= tau_a, yy[i], np.ones(len(i)))
            brc.append(a1)
            bsh.append(a2)
            bd.append(auroc(g[i], yy[i]) - auroc(m[i], yy[i]))
        pc = lambda v: [round(float(np.percentile(v, 2.5)), 4), round(float(np.percentile(v, 97.5)), 4)]  # noqa: E731
        res["accumulation_arm"] = {"n_confident": len(ar), "confident_errors": int(sum(ya)), "tau": tau_a,
                                   "dev_at_tau": params["arm"]["dev_at_tau"],
                                   "recall_at_tau": round(rca, 4), "share_at_tau": round(sha, 4),
                                   "recall_ci95": pc(brc), "share_ci95": pc(bsh), "PASS": bool(rca >= 0.80 and sha <= 0.30),
                                   "auroc_ab_gap": round(auroc(g, yy), 4), "auroc_maxp": round(auroc(m, yy), 4),
                                   "auroc_diff_ci95": pc(bd),
                                   "share_needed": {s: share_needed([r[s] for r in ar], ya, [1.0] * len(ar)) for s in ("ab_gap", "maxp")},
                                   "mean_requests_B": round(float(np.mean([r["requests_B"] for r in ar if r["requests_B"]])), 2)}
    json.dump(res, open(os.path.join(OUT, "confirm.json"), "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
