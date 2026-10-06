"""WS-U confirm-2: per-row scores and the metrics of every policy, shared by the held-out check on confirm-1 data and
the confirm-2 analysis. The per-row score is computed exactly as confirm/confirm_analyze.py does:
  - the warm family rate starts from WS-P's dev history and is updated online over all kept fresh rows, in the order
    sha256("wsu-confirm-20261006|rid");
  - the perturbation and self-check come from the extra calls;
  - the score is confirm/policy.py Policy.score.

Policies, all thresholds fixed in params_confirm2.json (dev only):
  global     S ≥ τ (the policy confirmed on 06/10);
  domain     S ≥ τ_suite;
  conformal  S ≥ τ_group (Mondrian groups: a family with ≥ 10 dev errors, else its suite's rest);
  confidence the best possible use of confidence alone at the same verify share as `global` (curve point);
  abstain    the model's own "unsure" choice when told to abstain if unsure (confirm-2 only)."""
import collections
import hashlib
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
U = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(U, "confirm"))
sys.path.insert(0, U)
from common import auroc  # noqa: E402
from policy import FamilyRates, Policy, observable  # noqa: E402

PRIMARY = ["rules_stress", "sql_wild", "shell_wild", "git_wild", "accumulation"]
STREAM_SEED = "wsu-confirm-20261006"


def jl(p):
    return [json.loads(l) for l in open(p) if l.strip()]


def scored_rows(fresh_rows_path, extra_path, pol=None):
    """Primary confident rows with every signal; mirrors confirm_analyze.py lines for the stream and the score."""
    pol = pol or Policy()
    rows = [r for r in jl(fresh_rows_path) if r["exclude"] is None]
    extra = {e["rid"]: e for e in jl(extra_path) if "error" not in e}
    warm = FamilyRates.from_dev(tuple(pol.p["family_prior"]))
    for r in sorted(rows, key=lambda r: hashlib.sha256(f"{STREAM_SEED}|{r['rid']}".encode()).hexdigest()):
        k = (r["suite"], observable(r["suite"], r["family"]))
        r["famobs"] = warm.rate(k)
        warm.update(k, not r["correct"])
    out, missing = [], 0
    for r in rows:
        if r["suite"] not in PRIMARY or (r["conf"] or 0) < 0.9:
            continue
        e = extra.get(r["rid"])
        if e is None:
            missing += 1
            continue
        mp = 1 - min(e["reorder"]["p_original"], e["para"]["p_original"])
        vf = float((e["verify"]["probabilities"] or {}).get("no", 0.0))
        row = {"suite": r["suite"], "family": observable(r["suite"], r["family"]), "req": r["req"], "rid": r["rid"],
               "wrong": not r["correct"], "maxp": 1 - r["conf"], "S": pol.score(r["suite"], r["famobs"], mp, vf)}
        if "abstain" in e:
            pa = e["abstain"]["probabilities"] or {}
            row["p_unsure"] = float(pa.get("unsure", 0.0))
            row["abstained"] = bool(pa) and max(pa, key=pa.get) == "unsure"
        out.append(row)
    return out, missing


def group_of(row, params):
    g = f"{row['suite']}|{row['family']}"
    return g if g in set(params["conformal"]["own_groups"]) else f"{row['suite']}|*rest*"


def flags(rows, params, which):
    if which == "global":
        return [r["S"] >= params["tau_global"] for r in rows]
    if which == "domain":
        return [r["S"] >= params["domain"]["taus"][r["suite"]] for r in rows]
    if which == "conformal":
        return [r["S"] >= params["conformal"]["taus"][group_of(r, params)]["tau"] for r in rows]
    if which == "abstain":
        return [bool(r.get("abstained")) for r in rows]
    raise ValueError(which)


def suite_weights(rows, pop):
    cnt = collections.Counter(r["suite"] for r in rows)
    tot, tot_pop = sum(cnt[s] for s in PRIMARY), sum(pop[s] for s in PRIMARY)
    return {s: (pop[s] / tot_pop) / (cnt[s] / tot) for s in PRIMARY if cnt[s]}


def rec_share(flag, wrong, w):
    flag, wrong, w = np.asarray(flag, bool), np.asarray(wrong, bool), np.asarray(w, float)
    return float((w * wrong * flag).sum() / (w * wrong).sum()), float((w * flag).sum() / w.sum())


def recall_at_share(score, wrong, w, share):
    """Weighted recall when the top `share` of answers by `score` are verified (curve point)."""
    s, y, w = np.asarray(score, float), np.asarray(wrong, bool), np.asarray(w, float)
    order = np.argsort(-s, kind="mergesort")
    cw, ce = np.cumsum(w[order]) / w.sum(), np.cumsum((w * y)[order]) / (w * y).sum()
    i = int(np.searchsorted(cw, share - 1e-12))
    return float(ce[min(i, len(ce) - 1)])


def evaluate(rows, params, n_boot=1000, seed=20261006):
    pop = params["population_confident"]
    sw = suite_weights(rows, pop)
    W = [sw[r["suite"]] for r in rows]
    Y = [r["wrong"] for r in rows]
    have_abstain = all("p_unsure" in r for r in rows)
    pols = ["global", "domain", "conformal"] + (["abstain"] if have_abstain else [])
    F = {p: flags(rows, params, p) for p in pols}
    res = {"n_confident": len(rows), "confident_errors": int(sum(Y)), "policies": {}, "per_suite": {}}
    for p in pols:
        rc, sh = rec_share(F[p], Y, W)
        res["policies"][p] = {"recall": round(rc, 4), "share": round(sh, 4)}
    res["policies"]["confidence_at_global_share"] = {
        "recall": round(recall_at_share([r["maxp"] for r in rows], Y, W, res["policies"]["global"]["share"]), 4),
        "share": res["policies"]["global"]["share"]}
    res["auroc_weighted"] = {"S": round(auroc([r["S"] for r in rows], Y, W), 4),
                             "maxp": round(auroc([r["maxp"] for r in rows], Y, W), 4)}
    if have_abstain:
        res["auroc_weighted"]["p_unsure"] = round(auroc([r["p_unsure"] for r in rows], Y, W), 4)
        res["policies"]["S_at_abstain_share"] = {
            "recall": round(recall_at_share([r["S"] for r in rows], Y, W, res["policies"]["abstain"]["share"]), 4),
            "share": res["policies"]["abstain"]["share"]}
    for s in PRIMARY:
        idx = [i for i, r in enumerate(rows) if r["suite"] == s]
        if not idx:
            continue
        ys = [Y[i] for i in idx]
        res["per_suite"][s] = {"n_confident": len(idx), "confident_errors": int(sum(ys))}
        for p in pols:
            rc, sh = rec_share([F[p][i] for i in idx], ys, [1.0] * len(idx))
            res["per_suite"][s][p] = {"recall": round(rc, 4), "share": round(sh, 4)}
    # conformal: realized recall per group against the 1 − α target
    grp = collections.defaultdict(lambda: [0, 0])
    for r, f in zip(rows, F["conformal"]):
        if r["wrong"]:
            g = grp[group_of(r, params)]
            g[0] += 1
            g[1] += f
    target = 1 - params["conformal"]["alpha"]
    res["conformal_groups"] = {g: {"errors": n, "caught": c, "recall": round(c / n, 4), "below_target": c / n < target}
                               for g, (n, c) in sorted(grp.items())}
    # cluster bootstrap within suites (cluster = scenario), suite weights recomputed per replicate
    rng = np.random.default_rng(seed)
    clusters = collections.defaultdict(lambda: collections.defaultdict(list))
    for i, r in enumerate(rows):
        clusters[r["suite"]][r["req"]].append(i)
    keys = {s: list(c) for s, c in clusters.items()}
    Fa = {p: np.array(F[p]) for p in pols}
    Ya = np.array(Y)
    Sa, Ma = np.array([r["S"] for r in rows]), np.array([r["maxp"] for r in rows])
    Pa = np.array([r.get("p_unsure", 0.0) for r in rows])
    boots = collections.defaultdict(list)
    for _ in range(n_boot):
        idx = np.array([j for s, ks in keys.items() for k in rng.integers(0, len(ks), len(ks)) for j in clusters[s][ks[k]]])
        sw_b = suite_weights([rows[i] for i in idx], pop)
        w = np.array([sw_b[rows[i]["suite"]] for i in idx])
        for p in pols:
            rc, sh = rec_share(Fa[p][idx], Ya[idx], w)
            boots[f"{p}_recall"].append(rc)
            boots[f"{p}_share"].append(sh)
        boots["auroc_S_minus_maxp"].append(auroc(Sa[idx], Ya[idx], w) - auroc(Ma[idx], Ya[idx], w))
        if have_abstain:
            boots["auroc_S_minus_unsure"].append(auroc(Sa[idx], Ya[idx], w) - auroc(Pa[idx], Ya[idx], w))
    res["ci95"] = {k: [round(float(np.percentile(v, 2.5)), 4), round(float(np.percentile(v, 97.5)), 4)] for k, v in boots.items()}
    return res


# ---- Learn-then-Test acceptance rule (accept = act without verifying), certified per group --------------------------
LTT_FRACS = [round(0.30 + 0.005 * j, 3) for j in range(140)]  # acceptance fractions 0.300 ... 0.995, tested in this order


def binom_cdf(k, n, p):
    """P(Binomial(n, p) <= k), summed in log space (k is small next to n here)."""
    import math
    if n == 0:
        return 1.0
    lp, lq = math.log(p), math.log1p(-p)
    tot = 0.0
    for i in range(0, k + 1):
        tot += math.exp(math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1) + i * lp + (n - i) * lq)
    return min(1.0, tot)


def ltt_lambda(scores, wrong, alpha, delta, fracs=LTT_FRACS):
    """Fixed-sequence Learn-then-Test: for acceptance fractions in increasing order, λ = the score at that rank (accept
    iff S < λ); H0: P(wrong | accepted) > alpha, p = P(Bin(n_acc, alpha) <= errors among accepted). The sequence starts
    at the first fraction whose accepted count could be certified at all (n >= ln(delta)/ln(1 - alpha), the "rule of
    three"; this depends on the group size only, not on the labels), then walks up while p <= delta. Returns the last
    certified λ (None: nothing certified). With probability >= 1 - delta over the calibration draw, the error rate among
    accepted answers of this group is <= alpha (exchangeable units)."""
    import math
    s = np.sort(np.asarray(scores, float))
    sc, y = np.asarray(scores, float), np.asarray(wrong, bool)
    n_min = math.ceil(math.log(delta) / math.log(1 - alpha))
    lam, path = None, []
    for f in fracs:
        if int(f * len(s)) < n_min:
            continue
        cut = float(s[min(int(f * len(s)), len(s) - 1)])
        acc = sc < cut
        n, k = int(acc.sum()), int((acc & y).sum())
        p = binom_cdf(k, n, alpha) if n else 1.0
        path.append((f, cut, n, k, p))
        if p <= delta:
            lam = cut
        else:
            break
    return lam, path


def one_per_scenario(rows, seed):
    """The unit for the guarantee: one confident question per scenario, chosen with a fixed seed (rows of the same
    scenario share the state and are not independent)."""
    import random
    by = collections.defaultdict(list)
    for r in rows:
        by[(r["suite"], r["req"])].append(r)
    rng = random.Random(seed)
    return [rng.choice(sorted(v, key=lambda r: r["rid"])) for _, v in sorted(by.items())]


def ltt_group(row, params, alpha_key):
    """Hierarchical lookup (after HG-CRC): the family's own node if it has a certified λ; else its suite's node (all
    the suite's calibration units) if the family was seen in calibration; else None: a family never seen in calibration,
    or a suite with nothing certified, is always verified."""
    L = params["ltt"][alpha_key]
    fam = f"{row['suite']}|{row['family']}"
    if fam in L["groups"] and L["groups"][fam]["lambda"] is not None:
        return fam
    suite = f"{row['suite']}|*suite*"
    if fam in set(L["seen_families"]) and suite in L["groups"] and L["groups"][suite]["lambda"] is not None:
        return suite
    return None


def ltt_accept(rows, params, alpha_key, pooled=False):
    """True = accept (act without verifying). Hierarchical (ltt_group): the family's certified λ, else its suite's;
    a family never seen in calibration, or a suite with nothing certified, is always verified. pooled: one λ for all."""
    out = []
    for r in rows:
        if pooled:
            lam = params["ltt"][alpha_key]["pooled_lambda"]
        else:
            g = ltt_group(r, params, alpha_key)
            lam = params["ltt"][alpha_key]["groups"][g]["lambda"] if g else None
        out.append(lam is not None and r["S"] < lam)
    return out


def ltt_report(units, params, alpha_key, alpha):
    """Error rate among accepted units, overall and per group, with a one-sided binomial test of 'risk <= alpha' per
    group (Bonferroni over the certified groups)."""
    res = {}
    for name, pooled in (("hierarchical", False), ("pooled", True)):
        acc = ltt_accept(units, params, alpha_key, pooled)
        n = sum(acc)
        k = sum(a and u["wrong"] for a, u in zip(acc, units))
        d = {"units": len(units), "accepted": n, "verified_share": round(1 - n / len(units), 4),
             "errors_among_accepted": k, "error_rate_among_accepted": round(k / n, 5) if n else None,
             "errors_caught_share": round(1 - k / max(sum(u["wrong"] for u in units), 1), 4)}
        if not pooled:
            groups = collections.defaultdict(lambda: [0, 0])
            for a, u in zip(acc, units):
                if a:
                    g = groups[ltt_group(u, params, alpha_key)]
                    g[0] += 1
                    g[1] += u["wrong"]
            G = max(len(groups), 1)
            d["groups"] = {}
            for g, (ng, kg) in sorted(groups.items()):
                p_exceed = 1 - binom_cdf(kg - 1, ng, alpha) if kg else 1.0  # P(X >= kg | risk = alpha)
                d["groups"][g] = {"accepted": ng, "errors": kg, "rate": round(kg / ng, 5),
                                  "p_above_alpha": round(p_exceed, 5), "significant_bonferroni": p_exceed < 0.05 / G}
        res[name] = d
    return res
