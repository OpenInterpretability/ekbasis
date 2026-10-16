"""Certified-mode carry-over analysis (PREREG_CERTIFIED_CARRYOVER.md), WS-MAC T2's analyze_t2.py with only its paths,
the overlap exclusion, the MLX reference and the C2+ reading added. No model call. The served model's answers on the
subset, scored exactly as confirm-3 scores (confirm/policy.py Policy.score; family rate warm-started from WS-P's dev
history, as counts computed on the rig from the frozen dev dataset, sha256 426a2ed9...), then confirm-3's rules with
confirm-3's thresholds (params_confirm3.json, calibrated on Ekbasis-27B bf16, as the client ships them): L1 and L2 at
alpha 2% (and 1%), the per-domain rule. Paired references on the same scenarios: Ekbasis-27B bf16 (confirm-3's own
answers and extra calls) and the MLX build (T2's run, on the scenarios both completed).
    TAG=skopos-int4 python3 analyze_carryover.py            -> results/<TAG>_summary.json
    DRY_BF16=1 TAG=dry python3 analyze_carryover.py         (bf16's answers in place of the model's: the pipeline check)"""
import collections
import hashlib
import json
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
U = os.path.join(HERE, "confirm_code")
TAG = os.environ.get("TAG") or sys.exit("TAG is required")
EXCL = json.load(open(os.path.join(HERE, "data", "overlap_excluded.json"))) if os.path.exists(
    os.path.join(HERE, "data", "overlap_excluded.json")) else None
EXCLUDED = set(map(tuple, EXCL["scenarios"])) if EXCL else set()
sys.path[:0] = [os.path.join(U, "confirm"), os.path.join(U, "confirm2"), os.path.join(U, "confirm3"), U]
import policy  # noqa: E402

DEV = json.load(open(os.path.join(HERE, "data", "dev_family_counts.json")))
assert DEV["sha256"] == "426a2ed9061af04e725e7b2cba4d68b7c25c5357ad0e9d1e05cd5c9a72dce268"


def _from_dev(cls, prior=(1, 1)):
    fr = cls(prior)
    for k, (n, e) in DEV["counts"].items():
        s, f = k.split("\t", 1)
        fr.n[(s, f)] += n
        fr.e[(s, f)] += e
    return fr


policy.FamilyRates.from_dev = classmethod(_from_dev)
import ltt3 as L  # noqa: E402
import metrics2 as M  # noqa: E402

PRIMARY = M.PRIMARY
POP_UNITS = {"rules_stress": 8611, "sql_wild": 892, "shell_wild": 816, "git_wild": 1009, "accumulation": 1339}  # confirm-3
NO_SELF = {"git_wild", "shell_wild"}


def jl(p):
    return [json.loads(l) for l in open(p) if l.strip()] if os.path.exists(p) else []


def cp_upper(k, n, conf=0.95):
    """One-sided Clopper-Pearson upper bound for k of n."""
    if n == 0:
        return None
    if k >= n:
        return 1.0
    lo, hi = k / n, 1.0
    for _ in range(100):
        mid = (lo + hi) / 2
        if M.binom_cdf(k, n, mid) > 1 - conf:
            lo = mid
        else:
            hi = mid
    return round(hi, 5)


def famobs_stream(rows):
    """confirm-3's warm family rate: dev history, then online over the given rows in the hashed stream order."""
    pol = policy.Policy()
    warm = policy.FamilyRates.from_dev(tuple(pol.p["family_prior"]))
    out = {}
    for r in sorted(rows, key=lambda r: hashlib.sha256(f"{M.STREAM_SEED}|{r['rid']}".encode()).hexdigest()):
        k = (r["suite"], policy.observable(r["suite"], r["family"]))
        out[r["rid"]] = warm.rate(k)
        warm.update(k, not r["correct"])
    return out


def unit_rows(units_raw, rows_by_rid, fam, pol):
    out = []
    for u in units_raw:
        r = rows_by_rid[u["rid"]]
        vf = u.get("self_check_no", 0.0) if r["suite"] not in NO_SELF else 0.0
        out.append({"suite": r["suite"], "family": policy.observable(r["suite"], r["family"]), "req": r["req"], "rid": r["rid"],
                    "wrong": not r["correct"], "maxp": 1 - r["conf"], "S": pol.score(r["suite"], fam[r["rid"]], u["stability"], vf)})
    return out


def weighted(units, acc):
    """Population-weighted error among accepted and verified share (each suite weighted to its confirm-3 units)."""
    by = collections.defaultdict(lambda: [0, 0, 0])
    for a, u in zip(acc, units):
        g = by[u["suite"]]
        g[0] += 1
        g[1] += a
        g[2] += a and u["wrong"]
    w = {s: POP_UNITS[s] / v[0] for s, v in by.items() if v[0]}
    acc_w = sum(w[s] * v[1] for s, v in by.items())
    err_w = sum(w[s] * v[2] for s, v in by.items())
    tot_w = sum(w[s] * v[0] for s, v in by.items())
    return {"error_rate_among_accepted_weighted": round(err_w / acc_w, 5) if acc_w else None,
            "verified_share_weighted": round(1 - acc_w / tot_w, 4) if tot_w else None,
            "per_suite": {s: {"units": v[0], "accepted": v[1], "errors_among_accepted": v[2],
                              "error_rate": round(v[2] / v[1], 5) if v[1] else None, "cp95_upper": cp_upper(v[2], v[1]),
                              "verified_share": round(1 - v[1] / v[0], 4)} for s, v in sorted(by.items())}}


def rule_block(units, params, alpha):
    out = {}
    for rule in ("L1", "L2"):
        rep = L.report(units, params, rule, alpha)
        acc = L.accept(units, params, rule)
        rep["cp95_upper_overall"] = cp_upper(rep["errors_among_accepted"], rep["accepted"])
        rep.update(weighted(units, acc))
        out[rule] = rep
    return out


def dedupe(raw):
    """One record per (i, part): a successful one when a resumed run retried a failed scenario."""
    best = {}
    for r in raw:
        k = (r["i"], r["part"])
        if k not in best or ("error" in best[k] and "error" not in r):
            best[k] = r
    return list(best.values())


def model_units(raw, meta, pol, keep):
    """Rows and units of a model's raw records, restricted to the scenarios in `keep`."""
    done = [r for r in raw if "error" not in r and (r["suite"], r["req"]) in keep]
    mrows, units_raw = [], []
    for rec in done:
        for x in rec["rows"]:
            m = meta[x["rid"]]
            mrows.append({"suite": m["suite"], "family": m["family"], "req": m["req"], "rid": x["rid"], "answer": x["answer"],
                          "conf": x["conf"], "correct": x["correct"], "truth": m["truth"]})
        if rec.get("unit"):
            units_raw.append(rec["unit"])
    by_rid = {r["rid"]: r for r in mrows}
    fam = famobs_stream(mrows)
    return mrows, unit_rows(units_raw, by_rid, fam, pol), {(r["suite"], r["req"]) for r in done}


def bf16_units(bf_all, bf_extra, meta, scen, pol, fam_bf_full):
    bf_rows = {r["rid"]: r for r in bf_all if r["rid"] in meta and (r["suite"], r["req"]) in scen}
    raw = []
    for key in sorted(scen):
        cand = sorted([r for r in bf_rows.values() if (r["suite"], r["req"]) == key and (r["conf"] or 0) >= 0.9], key=lambda r: r["rid"])
        if not cand:
            continue
        u = random.Random(f"63|{key[0]}|{key[1]}").choice(cand)
        e = bf_extra.get(u["rid"])
        if e is None:
            continue
        raw.append({"rid": u["rid"], "stability": 1 - min(e["reorder"]["p_original"], e["para"]["p_original"]),
                    "self_check_no": float((e["verify"]["probabilities"] or {}).get("no", 0.0))})
    return bf_rows, unit_rows(raw, bf_rows, fam_bf_full, pol)


def brief(block):
    return {r: {x: block[r][x] for x in ("units", "accepted", "verified_share", "errors_among_accepted", "error_rate_among_accepted",
                                         "cp95_upper_overall", "errors_caught_share", "error_rate_among_accepted_weighted",
                                         "verified_share_weighted", "no_node_significantly_above")} for r in ("L1", "L2")}


def main():
    P3 = json.load(open(os.path.join(U, "confirm3", "params_confirm3.json")))
    P2 = json.load(open(os.path.join(U, "confirm2", "params_confirm2.json")))
    pol = policy.Policy()
    reqs = jl(os.path.join(HERE, "data", "subset_requests.jsonl"))
    meta = {}
    for it in reqs:
        for row in it["rows"]:
            meta[row["rid"]] = {**row, "suite": it["suite"], "req": it["req"]}
    all_scen = {(it["suite"], it["req"]) for it in reqs}
    keep = all_scen - EXCLUDED
    bf_all = [r for r in jl(os.path.join(HERE, "data", "fresh_rows_bf16.jsonl")) if r["exclude"] is None]
    bf_extra = {e["rid"]: e for e in jl(os.path.join(HERE, "data", "extra_bf16.jsonl")) if "error" not in e}
    if os.environ.get("DRY_BF16"):  # the pipeline check: bf16's own answers and extra calls posing as a run
        raw = []
        for it in reqs:
            rows = [{"rid": row["rid"], "qk": row["qk"], "answer": row["bf16"]["answer"], "probs": row["bf16"]["probs"],
                     "conf": row["bf16"]["conf"], "correct": row["bf16"]["correct"]} for row in it["rows"] if row.get("bf16")]
            rec = {"i": it["i"], "part": it["part"], "suite": it["suite"], "req": it["req"], "rows": rows}
            conf = [r for r in rows if r["conf"] >= 0.9]
            if conf:
                u = random.Random(f"63|{it['suite']}|{it['req']}").choice(sorted(conf, key=lambda r: r["rid"]))
                e = bf_extra.get(u["rid"])
                if e:
                    rec["unit"] = {"rid": u["rid"], "stability": 1 - min(e["reorder"]["p_original"], e["para"]["p_original"]),
                                   "self_check_no": float((e["verify"]["probabilities"] or {}).get("no", 0.0))}
            raw.append(rec)
    else:
        raw = dedupe(jl(os.path.join(HERE, "results", f"{TAG}_raw.jsonl")))
    mrows, units, scen_done = model_units(raw, meta, pol, keep)
    fam_bf_full = famobs_stream(bf_all)
    bf_rows, bf_units = bf16_units(bf_all, bf_extra, meta, scen_done, pol, fam_bf_full)
    mlx_raw = dedupe(jl(os.path.join(HERE, "data", "mlx_raw_t2.jsonl")))
    mlx_done = {(r["suite"], r["req"]) for r in mlx_raw if "error" not in r}
    common = scen_done & mlx_done
    _, mlx_units, _ = model_units(mlx_raw, meta, pol, common)
    _, units_common, _ = model_units(raw, meta, pol, common)
    res = {"tag": TAG, "dry_bf16": bool(os.environ.get("DRY_BF16")),
           "scenarios_requested": len(all_scen), "scenarios_excluded_overlap": len(all_scen & EXCLUDED),
           "excluded_source": (EXCL or {}).get("source"), "scenarios_done": len(scen_done),
           "requests_failed": sum("error" in r for r in raw), "rows": len(mrows), "units": len(units),
           "unit_errors": sum(u["wrong"] for u in units),
           "per_suite_scenarios": dict(collections.Counter(s for s, _ in scen_done)),
           "model": {"a02": rule_block(units, P3["a02"], 0.02), "a01": rule_block(units, P3["a01"], 0.01)},
           "ekbasis27b_bf16_same_scenarios": {"units": len(bf_units), "unit_errors": sum(u["wrong"] for u in bf_units),
                                              "a02": rule_block(bf_units, P3["a02"], 0.02)},
           "mlx_t2_common_scenarios": {"scenarios": len(common), "model_a02": rule_block(units_common, P3["a02"], 0.02) if units_common else None,
                                       "mlx_a02": rule_block(mlx_units, P3["a02"], 0.02) if mlx_units else None}}
    if units:
        ev = M.evaluate(units, P2, n_boot=200)
        res["per_domain_rule_units"] = {"overall": ev["policies"]["domain"], "per_suite": {s: v["domain"] for s, v in ev["per_suite"].items()}}
    pair = collections.defaultdict(lambda: collections.Counter())
    for r in mrows:
        b = bf_rows.get(r["rid"])
        if not b:
            continue
        c = pair[r["suite"]]
        c["rows"] += 1
        c["agree"] += r["answer"] == b["answer"]
        c["model_correct"] += r["correct"]
        c["bf16_correct"] += b["correct"]
        c["model_confident"] += r["conf"] >= 0.9
        c["model_confident_wrong"] += r["conf"] >= 0.9 and not r["correct"]
        c["bf16_confident_wrong"] += (b["conf"] or 0) >= 0.9 and not b["correct"]
    tot = collections.Counter()
    for c in pair.values():
        tot.update(c)
    res["paired_rows_vs_ekbasis27b"] = {"all": dict(tot), **{s: dict(c) for s, c in sorted(pair.items())}}
    a2 = res["model"]["a02"]

    def ok(rule):
        w = a2[rule]["error_rate_among_accepted_weighted"]
        return bool(w is not None and w <= 0.02 and a2[rule]["no_node_significantly_above"])
    res["criteria"] = {"C2_certified_mode_L2_a02": ok("L2"), "C1_L1_a02": ok("L1"),
                       "C2plus_L2_cp95_upper_le_2pct": bool(ok("L2") and a2["L2"]["cp95_upper_overall"] is not None
                                                             and a2["L2"]["cp95_upper_overall"] <= 0.02)}
    json.dump(res, open(os.path.join(HERE, "results", f"{TAG}_summary.json"), "w"), indent=1)
    out = {k: v for k, v in res.items() if k not in ("model", "ekbasis27b_bf16_same_scenarios", "mlx_t2_common_scenarios")}
    out["model"] = brief(res["model"]["a02"])
    out["ekbasis27b_bf16_same_scenarios"] = brief(res["ekbasis27b_bf16_same_scenarios"]["a02"])
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
