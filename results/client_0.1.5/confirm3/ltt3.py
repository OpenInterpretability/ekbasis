"""WS-U confirm-3: the corrected Learn-then-Test acceptance rules (accept = act on a confident answer without verifying).
Confirm-2's P3 failed because rare rules families fell back to their suite's λ and reached 3.4% errors among accepted
(the HG-CRC warning). Two fixes, both calibrated on confirm-1 + confirm-2 only:

  L1 strict (primary):  a family with >= 3/α calibration units and a certified λ uses it; every other family (rare,
                        uncertified or never seen) is ALWAYS verified. No fallback.
  L2 difficulty:        a family with its own certified λ uses it; any other family seen in calibration falls back to
                        a (suite, difficulty) node instead of the suite. Difficulty is the family's calibration error
                        rate among its confident units, Beta(1, 1): [0, 1%), [1%, 3%), [3%, 10%), [10%, 100%]. In
                        deployment this is the family tracker's rate. Each node is calibrated on the units of the
                        families that will use it. Unseen families, and nodes with nothing certified, are always
                        verified.

λ per node is from metrics2.ltt_lambda (fixed-sequence LTT, binomial p-values, δ = 0.05), as in confirm-2."""
import collections
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "confirm2"))
import metrics2 as M  # noqa: E402

BUCKETS = (0.01, 0.03, 0.10)


def bucket(rate):
    return sum(rate >= b for b in BUCKETS)  # 0: < 1%, 1: 1-3%, 2: 3-10%, 3: >= 10%


def fit(units, alpha, delta=0.05):
    """Both rules' nodes from calibration units (one confident question per scenario)."""
    need = math.ceil(3 / alpha)
    fam = collections.defaultdict(list)
    for u in units:
        fam[f"{u['suite']}|{u['family']}"].append(u)
    own = {}
    for f, us in sorted(fam.items()):
        if len(us) >= need:
            lam, _ = M.ltt_lambda([u["S"] for u in us], [u["wrong"] for u in us], alpha, delta)
            own[f] = {"lambda": lam, "units": len(us), "errors": sum(u["wrong"] for u in us)}
    certified = {f for f, v in own.items() if v["lambda"] is not None}
    rate = {f: (sum(u["wrong"] for u in us) + 1) / (len(us) + 2) for f, us in fam.items()}
    diff_members = collections.defaultdict(list)
    for f, us in fam.items():
        if f not in certified:
            diff_members[f"{f.split('|', 1)[0]}|d{bucket(rate[f])}"] += us
    diff = {}
    for node, us in sorted(diff_members.items()):
        lam, _ = M.ltt_lambda([u["S"] for u in us], [u["wrong"] for u in us], alpha, delta)
        diff[node] = {"lambda": lam, "units": len(us), "errors": sum(u["wrong"] for u in us)}
    return {"alpha": alpha, "delta": delta, "need_units": need, "family_nodes": own,
            "difficulty_nodes": diff, "family_rate": rate, "buckets": list(BUCKETS)}


def node_of(row, P, rule):
    """The node a confident answer uses under rule "L1" or "L2", or None (always verify)."""
    f = f"{row['suite']}|{row['family']}"
    fn = P["family_nodes"].get(f)
    if fn and fn["lambda"] is not None:
        return ("family", f)
    if rule == "L2" and f in P["family_rate"]:
        d = f"{row['suite']}|d{bucket(P['family_rate'][f])}"
        dn = P["difficulty_nodes"].get(d)
        if dn and dn["lambda"] is not None:
            return ("difficulty", d)
    return None


def accept(rows, P, rule):
    out = []
    for r in rows:
        n = node_of(r, P, rule)
        if n is None:
            out.append(False)
            continue
        lam = P["family_nodes" if n[0] == "family" else "difficulty_nodes"][n[1]]["lambda"]
        out.append(r["S"] < lam)
    return out


def report(units, P, rule, alpha):
    acc = accept(units, P, rule)
    n = sum(acc)
    k = sum(a and u["wrong"] for a, u in zip(acc, units))
    errs = sum(u["wrong"] for u in units)
    nodes = collections.defaultdict(lambda: [0, 0])
    for a, u in zip(acc, units):
        if a:
            g = nodes[node_of(u, P, rule)[1]]
            g[0] += 1
            g[1] += u["wrong"]
    G = max(len(nodes), 1)
    per = {}
    for g, (ng, kg) in sorted(nodes.items()):
        p_exceed = 1 - M.binom_cdf(kg - 1, ng, alpha) if kg else 1.0
        per[g] = {"accepted": ng, "errors": kg, "rate": round(kg / ng, 5), "p_above_alpha": round(p_exceed, 5),
                  "significant_bonferroni": p_exceed < 0.05 / G}
    by_suite = {}
    for s in M.PRIMARY:
        idx = [i for i, u in enumerate(units) if u["suite"] == s]
        if idx:
            by_suite[s] = {"units": len(idx), "verified_share": round(1 - sum(acc[i] for i in idx) / len(idx), 4)}
    return {"units": len(units), "accepted": n, "verified_share": round(1 - n / len(units), 4),
            "errors_among_accepted": k, "error_rate_among_accepted": round(k / n, 5) if n else None,
            "errors_caught_share": round(1 - k / max(errs, 1), 4), "nodes": per, "by_suite": by_suite,
            "rate_ok": n > 0 and k / n <= alpha, "no_node_significantly_above": not any(v["significant_bonferroni"] for v in per.values())}
