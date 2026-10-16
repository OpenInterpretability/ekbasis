#!/usr/bin/env python3
"""D8, part 2: every published number of the Skopos documents (make_card.py's results/ files, the quantized cards'
gates, the addendum) recomputed without the evaluation items that overlap the lineage's training rows
(out/overlap.json), with the same metric code as the original analysis (ported line by line from the scripts named in
each section) and the same bootstrap (seed, resamples, percentiles).

Each section reports: "published" (the value in the results file), "all" (recomputed here on every item: it must
reproduce the published value, "reproduced": true), "primary" (without the items the audit's rule flags: identical or
near-duplicate, overlap.json "flagged") and "sensitivity" (also without the near-duplicates of the symmetric variant,
"flagged_sensitivity"), and whether each pre-registered conclusion holds.

usage: python3 recompute_without_overlap.py      (reads out/overlap.json, writes out/recomputed.json; ~2 min)"""
from __future__ import annotations

import collections
import json
import math
import os
import random
import statistics

HERE = os.path.dirname(os.path.abspath(__file__))
RS = os.path.dirname(HERE)
DM = os.path.dirname(os.path.dirname(os.path.dirname(RS)))
HF = os.path.join(HERE, "hf")
V = f"{HF}/rtx/v50p"  # ekbasis-v50-research@6bfd3c9dc7 rtx/v50p (per-item predictions, as run)
DATA = f"{V}/data"
RAW = f"{HF}/ekbasis-data/raw"
RES = f"{RS}/results"
OV = json.load(open(f"{HERE}/out/overlap.json"))
RULES = {"all": None, "primary": "flagged", "sensitivity": "flagged_sensitivity"}
L = lambda p: [json.loads(l) for l in open(p)]
n_ = lambda g: {True: "yes", False: "no"}[g] if isinstance(g, bool) else str(g)
FAC = {s: f"{DATA}/{s}.jsonl" for s in ("git3_test_known", "git3_test_held", "multi_test_testfam", "ftest_family",
                                        "guard_known", "fac_val", "git_long", "git_long_val", "fhorizon", "latent_test",
                                        "m3val", "fval_git3", "sess_val", "awb_neutral", "ftest_fresh")}
FAC.update({s: f"{RAW}/{s}.jsonl" for s in ("guard_held", "multi_test_trainfam", "gold0_ftest_family", "ce_items")})
ROWS = {}


def rows(s):
    if s not in ROWS:
        ROWS[s] = L(FAC[s])
    return ROWS[s]


def excl(rule, s):
    """indices of set s excluded under a rule (empty for 'all')."""
    return set() if RULES[rule] is None else set(OV["flags"][s][RULES[rule]])


def close(a, b, tol=1e-9):
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(close(x, y, tol) for x, y in zip(a, b))
    if a is None or b is None:
        return a is b
    return abs(float(a) - float(b)) <= tol


def run3(fn):
    return {r: fn(r) for r in RULES}


# ============================================================ A. release protocol (compare_release.py), each build
def ece(P, bins=10):
    b = collections.defaultdict(list)
    for p in P:
        b[min(bins - 1, int(p["conf"] * bins))].append(p)
    return sum(len(v) / len(P) * abs(sum(x["ok"] for x in v) / len(v) - sum(x["conf"] for x in v) / len(v)) for v in b.values())


def git_preds(d, rule):
    out = []
    for s in ("git3_test_known", "git3_test_held"):
        R, P, X = rows(s), L(f"{d}/preds_{s}.jsonl"), excl(rule, s)
        assert len(R) == len(P), s
        out += [{"ok": p["ok"] if "ok" in p else p["pred"] == p["gold"], "conf": p["conf"]} for i, p in enumerate(P) if i not in X]
    return out


def multi_changed(d, split, mode, rule):
    path = f"{d}/preds_{split}_{mode}.jsonl"
    if not os.path.exists(path):
        return None, 0
    R, P, X = rows(split), L(path), excl(rule, split)
    assert len(R) == len(P), split
    chg = []
    for i, (r, p) in enumerate(zip(R, P)):
        if i in X:
            continue
        for k, q in enumerate(r["questions"]):
            g0 = r["gold0s"][k]
            if r["known0s"][k] and g0 is not None and n_(g0) != n_(r["golds"][k]):
                chg.append(p["preds"][k] == n_(r["golds"][k]))
    return 100 * sum(chg) / len(chg), len(chg)


def ftest_changed(d, rule):
    R, g0, P, X = rows("ftest_family"), rows("gold0_ftest_family"), L(f"{d}/preds_ftest_family.jsonl"), excl(rule, "ftest_family")
    ch = [i for i, (r, g) in enumerate(zip(R, g0)) if g["known"] and n_(g["gold0"]) != n_(r["gold"]) and i not in X]
    return 100 * sum((P[i]["ok"] if "ok" in P[i] else P[i]["pred"] == n_(R[i]["gold"])) for i in ch) / len(ch), len(ch)


def guard(d, split, rule):
    R, P, X = rows(split), L(f"{d}/preds_{split}.jsonl"), excl(rule, split)
    lost = [(r, p) for i, (r, p) in enumerate(zip(R, P)) if r["qtype"] == "lost" and i not in X]
    pos = [p for r, p in lost if r["gold"]]
    neg = [p for r, p in lost if not r["gold"]]
    return [sum(p["p_yes"] >= 0.2 for p in pos), len(pos), sum(p["p_yes"] >= 0.2 for p in neg), len(neg)]


def release_read(rel, cand, rule):
    res = {}
    for name, d, gd in (("release", rel, f"{rel}/guard_larger_set"), ("candidate", cand, cand)):
        G = git_preds(d, rule)
        res[name] = {"git_v3_all": 100 * sum(p["ok"] for p in G) / len(G), "git_v3_n": len(G),
                     "ece_git_v3_10bins": ece(G, 10), "ece_git_v3_15bins": ece(G, 15),
                     "multi_testfam_single": multi_changed(d, "multi_test_testfam", "single", rule)[0],
                     "multi_testfam_read_once": multi_changed(d, "multi_test_testfam", "read_once", rule)[0],
                     "multi_trainfam_single": multi_changed(d, "multi_test_trainfam", "single", rule)[0],
                     "multi_trainfam_read_once": multi_changed(d, "multi_test_trainfam", "read_once", rule)[0],
                     "multi_trainfam_n_changed": multi_changed(d, "multi_test_trainfam", "single", rule)[1],
                     "ftest_changed": ftest_changed(d, rule)[0],
                     "guard_known": guard(gd, "guard_known", rule), "guard_held": guard(gd, "guard_held", rule)}
    r, c = res["release"], res["candidate"]
    ro = c["multi_testfam_read_once"] is not None
    chk = {"1 git v3": c["git_v3_all"] >= r["git_v3_all"] - 1,
           "2a multi single": c["multi_testfam_single"] >= r["multi_testfam_single"] - 1,
           "2b multi read-once": (c["multi_testfam_read_once"] >= r["multi_testfam_read_once"] - 1) if ro else None,
           "3 ftest changed": c["ftest_changed"] >= r["ftest_changed"] - 1,
           "4 ECE git v3": c["ece_git_v3_10bins"] <= r["ece_git_v3_10bins"] + 0.01 and
                           (c["ece_git_v3_15bins"] <= r["ece_git_v3_15bins"] + 0.01),
           "5a guard known flagged": c["guard_known"][0] >= r["guard_known"][0] - 0.01 * r["guard_known"][1],
           "5b guard known false alarms": c["guard_known"][2] <= r["guard_known"][2] + 0.01 * r["guard_known"][3],
           "6a guard held flagged": c["guard_held"][0] >= r["guard_held"][0] - 0.01 * r["guard_held"][1],
           "6b guard held false alarms": c["guard_held"][2] <= r["guard_held"][2] + 0.01 * r["guard_held"][3]}
    res["checks"] = chk
    res["pass"] = all(v for v in chk.values() if v is not None)
    return res


def section_release():
    out = {}
    for tag, cand in (("bf16", "release_r4"), ("int4", "release_r4_int4"), ("fp8", "release_r4_fp8"), ("mlx", "release_r4_mlx")):
        pub = json.load(open(f"{RES}/release_read_{tag}.json"))
        r3 = run3(lambda rule: release_read(f"{V}/release_ref", f"{V}/{cand}", rule))
        keys = ["git_v3_all", "ece_git_v3_10bins", "multi_testfam_single", "multi_testfam_read_once", "multi_trainfam_single",
                "multi_trainfam_read_once", "ftest_changed", "guard_known", "guard_held"]
        rep = all(close(r3["all"][m][k], pub[m][k]) for m in ("release", "candidate") for k in keys if k in pub[m])
        out[tag] = {"source": f"results/release_read_{tag}.json (compare_release.py on rtx/v50p/{cand} vs release_ref)",
                    "reproduced": rep, "published_checks": pub.get("checks"), **r3,
                    "conclusion_holds": {r: {k: (r3[r]["checks"][k] == r3["all"]["checks"][k]) for k in r3["all"]["checks"]}
                                         for r in ("primary", "sensitivity")}}
    return out


# ============================================================ B. the served report (release_eval.py)
def boot0(xs, n=2000, seed=0):
    rng = random.Random(seed)
    m = [sum(rng.choice(xs) for _ in xs) / len(xs) for _ in range(n)]
    m.sort()
    return [100 * m[int(0.025 * n)], 100 * m[int(0.975 * n)]]


def auroc(pos, neg):
    return sum((a > b) + 0.5 * (a == b) for a in pos for b in neg) / (len(pos) * len(neg))


def git_report(d, split, rule):
    R, P, X = rows(split), L(f"{d}/preds_{split}.jsonl"), excl(rule, split)
    keep = [(r, p) for i, (r, p) in enumerate(zip(R, P)) if i not in X]
    res = {}
    for k, sel in (("lost", lambda r: r["qtype"] == "lost"), ("fails", lambda r: r["qtype"] == "fails"),
                   ("in_progress", lambda r: r["qtype"] == "in_progress"),
                   ("changed state", lambda r: r["qtype"] not in ("lost", "fails", "in_progress") and r["known0"]
                    and n_(r["gold0"]) != n_(r["gold"])), ("all", lambda r: True)):
        ok = [p["pred"] == n_(r["gold"]) for r, p in keep if sel(r)]
        res[k] = {"n": len(ok), "acc": 100 * sum(ok) / len(ok), "ci95": boot0(ok)}
    lost = [(p["p_yes"], r["gold"]) for r, p in keep if r["qtype"] == "lost"]
    pos = [p for p, g in lost if g]
    neg = sorted((p for p, g in lost if not g), reverse=True)
    res["lost_auroc"] = auroc(pos, neg)
    res["lost_flagged_at_0.2"] = 100 * sum(a >= 0.2 for a in pos) / len(pos)
    res["false_alarm_at_0.2"] = 100 * sum(a >= 0.2 for a in neg) / len(neg)
    return res


def multi_report(d, split, mode, rule):
    R, P, X = rows(split), L(f"{d}/preds_{split}_{mode}.jsonl"), excl(rule, split)
    flat, chg = [], []
    for i, (r, p) in enumerate(zip(R, P)):
        if i in X:
            continue
        for k, q in enumerate(r["questions"]):
            ok = p["preds"][k] == n_(r["golds"][k])
            flat.append(ok)
            g0 = r["gold0s"][k]
            if r["known0s"][k] and g0 is not None and n_(g0) != n_(r["golds"][k]):
                chg.append(ok)
    return {"n_changed": len(chg), "acc_changed": 100 * sum(chg) / len(chg), "ci95_changed": boot0(chg),
            "acc_all": 100 * sum(flat) / len(flat)}


def section_report():
    pub = json.load(open(f"{RES}/release_read_bf16_report.json"))
    out = {}
    for model, d in (("skopos", f"{V}/release_r4"), ("ekbasis27b", f"{V}/release_ref")):
        r3 = run3(lambda rule: {**{s: git_report(d, s, rule) for s in ("git3_test_known", "git3_test_held")},
                                **{f"{s} ({'read-once' if m == 'read_once' else 'one prompt per question'})": multi_report(d, s, m, rule)
                                   for s in ("multi_test_trainfam", "multi_test_testfam") for m in ("single", "read_once")}})
        out[model] = r3
    rep = True
    for k, v in pub.items():
        mine = out["skopos"]["all"][k]
        for kk, vv in v.items():
            if kk in ("seconds", "lost_caught_at_10pct_false_alarm", "prompt_tokens_per_state"):
                continue
            a = mine[kk]
            rep &= close(a["acc"], vv["acc"]) and close(a["ci95"], vv["ci95"]) if isinstance(vv, dict) else close(a, vv)
    return {"source": "results/release_read_bf16_report.json (release_eval.py's report, recomputed from rtx/v50p/release_r4)",
            "reproduced": rep, **out}


# ============================================================ C. H2H trainer readout (analyze_r4.py / analyze_skopos.py)
def boot_paired(a, b):
    rng = random.Random(20261015)
    n = len(a)
    d = [x - y for x, y in zip(a, b)]
    v = sorted(sum(d[rng.randrange(n)] for _ in range(n)) / n for _ in range(2000))
    return round(sum(d) / n, 4), [round(v[50], 4), round(v[1949], 4)]


H2H_SUITES = ["fac_val", "git_long", "git_long_val", "fhorizon", "latent_test", "git3_test_known", "git3_test_held",
              "guard_known", "ftest_family", "m3val", "fval_git3", "sess_val"]


def h2h(cand_default, src, rule, keep_fn=None, guard_dirs=None):
    out = {}
    for s in H2H_SUITES:
        cd, bd = src.get(s, (cand_default, "base_probs"))
        if not os.path.exists(f"{V}/{cd}/preds_{s}_floor.jsonl"):
            continue
        sk, c, b = L(f"{V}/skopos_eval/preds_{s}_floor.jsonl"), L(f"{V}/{cd}/preds_{s}_floor.jsonl"), L(f"{V}/{bd}/preds_{s}_floor.jsonl")
        assert len(sk) == len(c) == len(b), s
        X = excl(rule, s)
        idx = [i for i in range(len(sk)) if i not in X and (keep_fn is None or keep_fn(s, i))]
        ok = lambda P: [int(P[i]["ok"]) for i in idx]
        out[s] = {"n": len(idx), "skopos": round(sum(ok(sk)) / len(idx), 4), "r2": round(sum(ok(c)) / len(idx), 4),
                  "base": round(sum(ok(b)) / len(idx), 4), "r2_minus_skopos": boot_paired(ok(c), ok(sk)),
                  "skopos_minus_base": boot_paired(ok(sk), ok(b))}
    data, X = rows("guard_known"), excl(rule, "guard_known")
    g = {}
    for name, d in (("skopos", "skopos_eval"), ("r2", cand_default), ("base", "base_probs")):
        P = L(f"{V}/{d}/preds_guard_known_floor.jsonl")
        lost = [(x, p) for i, (x, p) in enumerate(zip(data, P)) if x["qtype"] == "lost" and i not in X]
        pos = [p for x, p in lost if p["gold"] == "yes"]
        neg = [p for x, p in lost if p["gold"] == "no"]
        g[name] = {"flagged_at_0.2": round(100 * sum(p["probs"][0] >= 0.2 for p in pos) / len(pos), 2),
                   "false_alarms_at_0.2": round(100 * sum(p["probs"][0] >= 0.2 for p in neg) / len(neg), 2)}
    out["guard_0.2"] = g
    worse = [s for s in out if isinstance(out[s], dict) and "r2_minus_skopos" in out[s]
             and out[s]["r2_minus_skopos"][0] < -0.01 and out[s]["r2_minus_skopos"][1][1] < 0]
    gain = [s for s in ("fac_val", "git_long", "git_long_val") if s in out and out[s]["r2_minus_skopos"][0] >= 0.01
            and out[s]["r2_minus_skopos"][1][0] > 0]
    gd = g["r2"]["flagged_at_0.2"] - g["skopos"]["flagged_at_0.2"]
    fa = g["r2"]["false_alarms_at_0.2"] - g["skopos"]["false_alarms_at_0.2"]
    out["verdict"] = {"suites_worse": worse, "gain_suites": gain, "guard_flagged_diff": round(gd, 2), "guard_fa_diff": round(fa, 2),
                      "replaces_skopos": bool(not worse and gd >= -1 and fa <= 1 and gain)}
    return out


def h2h_reproduced(pub, mine):
    ok = True
    for s, v in pub.items():
        if s in H2H_SUITES:
            ok &= all(close(mine[s][k], v[k], 1e-4) for k in ("skopos", "r2", "base")) and \
                close(mine[s]["r2_minus_skopos"][0], v["r2_minus_skopos"][0], 1e-4) and \
                close(mine[s]["r2_minus_skopos"][1], v["r2_minus_skopos"][1], 1e-4) and \
                close(mine[s]["skopos_minus_base"][1], v["skopos_minus_base"][1], 1e-4)
    ok &= mine["guard_0.2"] == pub["guard_0.2"]
    return ok


def section_h2h():
    out = {}
    R4 = {"fac_val": ("run_r4", "base_facval"), "git_long_val": ("run_r4", "diag_base"), "sess_val": ("run_r4", "base_sessval")}
    R2 = {"fac_val": ("run_r2", "base_facval"), "git_long_val": ("diag_r2", "diag_base"), "sess_val": ("r2_sessval", "base_sessval")}
    for name, cand, src, f in (("r4_vs_skopos_v49f", "run_r4", R4, "r4_vs_skopos_v49f.json"),
                               ("skopos_v49f_vs_r2", "run_r2", R2, "skopos_v49f_vs_r2.json")):
        pub = json.load(open(f"{RES}/{f}"))
        r3 = run3(lambda rule: h2h(cand, src, rule))
        out[name] = {"source": f"results/{f} (analyze_{'r4' if cand == 'run_r4' else 'skopos'}.py; 'r2' = the candidate)",
                     "reproduced": h2h_reproduced(pub, r3["all"]), **r3,
                     "verdict_holds": {r: r3[r]["verdict"]["replaces_skopos"] == r3["all"]["verdict"]["replaces_skopos"]
                                       for r in ("primary", "sensitivity")}}
    # descriptive: fac_val by family, and fac_val without its Python slice (the generator repeats prompts)
    fv = rows("fac_val")
    P = {m: L(f"{V}/{d}/preds_fac_val_floor.jsonl") for m, d in (("r4", "run_r4"), ("skopos", "skopos_eval"), ("base", "base_facval"))}
    fam = {}
    for rule in RULES:
        X = excl(rule, "fac_val")
        fam[rule] = {}
        for w in sorted({r["world"] for r in fv}):
            ix = [i for i, r in enumerate(fv) if r["world"] == w and i not in X]
            fam[rule][w] = {"n": len(ix), **{m: round(sum(P[m][i]["ok"] for i in ix) / len(ix), 4) if ix else None for m in P}}
    out["fac_val_by_family"] = fam
    # descriptive: fhorizon by number of actions (the card's "accuracy falls with the number of actions")
    fh = rows("fhorizon")
    P = {m: L(f"{V}/{d}/preds_fhorizon_floor.jsonl") for m, d in (("r4", "run_r4"), ("skopos", "skopos_eval"), ("base", "base_probs"))}
    out["fhorizon_by_steps"] = {}
    for rule in RULES:
        X = excl(rule, "fhorizon")
        out["fhorizon_by_steps"][rule] = {}
        for k in sorted({int(r["steps"]) for r in fh}):
            ix = [i for i, r in enumerate(fh) if int(r["steps"]) == k and i not in X]
            out["fhorizon_by_steps"][rule][str(k)] = {"n": len(ix), **{m: round(sum(P[m][i]["ok"] for i in ix) / len(ix), 4)
                                                                        if ix else None for m in P}}
    out["fac_val_without_python"] = run3(lambda rule: h2h("run_r4", R4, rule, keep_fn=lambda s, i: s != "fac_val" or fv[i]["world"] != "fac_python")["fac_val"])
    return out


def section_vs_ekbasis():
    pub = json.load(open(f"{RES}/r4_vs_ekbasis27b_trainer.json"))
    SRC = {"fac_val": ("run_r4", "base_facval"), "git_long_val": ("run_r4", "diag_base"), "sess_val": ("run_r4", "base_sessval")}

    def one(rule):
        o = {}
        for s in pub["sets"]:
            cd, bd = SRC.get(s, ("run_r4", "base_probs"))
            c, b = L(f"{V}/{cd}/preds_{s}_floor.jsonl"), L(f"{V}/{bd}/preds_{s}_floor.jsonl")
            X = excl(rule, s)
            idx = [i for i in range(len(c)) if i not in X]
            ok = lambda P: [int(P[i]["ok"]) for i in idx]
            o[s] = {"n": len(idx), "r4": round(sum(ok(c)) / len(idx), 4), "ekbasis27b": round(sum(ok(b)) / len(idx), 4),
                    "r4_minus_ekbasis27b": list(boot_paired(ok(c), ok(b)))}
        return o
    r3 = run3(one)
    rep = all(close(r3["all"][s]["r4_minus_ekbasis27b"][1], v["r4_minus_ekbasis27b"][1], 1e-4) and close(r3["all"][s]["r4"], v["r4"], 1e-4)
              and close(r3["all"][s]["ekbasis27b"], v["ekbasis27b"], 1e-4) for s, v in pub["sets"].items())
    return {"source": "results/r4_vs_ekbasis27b_trainer.json (paired bootstrap as analyze_r4.py)", "reproduced": rep, **r3}


# ============================================================ D. fresh confirmation (analyze_confirm_ftest.py)
def section_confirm():
    R, rel, r4 = rows("ftest_fresh"), L(f"{V}/confirm_rel/preds_ftest_fresh_floor.jsonl"), L(f"{V}/confirm_r4/preds_ftest_fresh_floor.jsonl")

    def one(rule):
        X = excl(rule, "ftest_fresh")
        ch = [i for i, r in enumerate(R) if r.get("known0") and r.get("gold0") is not None and str(r["gold0"]) != str(r["gold"]) and i not in X]

        def boot(ix):
            d = [int(r4[i]["ok"]) - int(rel[i]["ok"]) for i in ix]
            rng = random.Random(20261015)
            v = sorted(sum(d[rng.randrange(len(d))] for _ in d) / len(d) for _ in range(2000))
            return round(100 * sum(d) / len(d), 2), [round(100 * v[50], 2), round(100 * v[1949], 2)]
        acc = lambda P, ix: round(100 * sum(P[i]["ok"] for i in ix) / len(ix), 2)
        allix = [i for i in range(len(R)) if i not in X]
        o = {"changed": {"n": len(ch), "release": acc(rel, ch), "r4": acc(r4, ch), "r4_minus_release": boot(ch)},
             "all": {"n": len(allix), "release": acc(rel, allix), "r4": acc(r4, allix), "r4_minus_release": boot(allix)}}
        o["loss_confirmed"] = o["changed"]["r4_minus_release"][0] < -1.0
        return o
    pub = json.load(open(f"{RES}/confirm_ftest_fresh.json"))
    r3 = run3(one)
    rep = all(close(r3["all"][k][kk], pub[k][kk]) for k in ("changed", "all") for kk in ("n", "release", "r4")) and \
        close(r3["all"]["changed"]["r4_minus_release"][1], pub["changed"]["r4_minus_release"][1])
    return {"source": "results/confirm_ftest_fresh.json", "reproduced": rep, "excluded": {r: len(excl(r, "ftest_fresh")) for r in RULES}, **r3}


# ============================================================ E. image check (PREREG_IMAGE.md)
def section_image():
    S, E = json.load(open(f"{V}/image_skopos_int4.json")), json.load(open(f"{V}/image_ekbasis_int4.json"))
    assert len(S) == len(E) == 400 and all((a["fam"], a["gold"], a["changed"]) == (b["fam"], b["gold"], b["changed"]) for a, b in zip(S, E))

    def one(rule):
        X = excl(rule, "image_fresh")
        o = {}
        for cond in ("text", "image", "read"):
            for sub in ("all", "changed"):
                ix = [i for i in range(400) if i not in X and (sub == "all" or S[i]["changed"])]
                d = [int(S[i][cond]) - int(E[i][cond]) for i in ix]
                rng = random.Random(20261015)
                v = sorted(sum(d[rng.randrange(len(d))] for _ in d) / len(d) for _ in range(2000))
                o[f"{cond}_{sub}"] = {"n": len(ix), "skopos": round(100 * sum(S[i][cond] for i in ix) / len(ix), 2),
                                      "ekbasis": round(100 * sum(E[i][cond] for i in ix) / len(ix), 2),
                                      "diff": round(100 * sum(d) / len(d), 2), "ci": [round(100 * v[50], 2), round(100 * v[1949], 2)]}
        o["preserved"] = o["image_all"]["diff"] >= -2.0 and o["read_all"]["diff"] >= -2.0
        return o
    pub = json.load(open(f"{RES}/image_compare.json"))
    r3 = run3(one)
    rep_pt = all(close(r3["all"][k][kk], pub[k][kk], 0.051) for k in pub if k != "preserved" for kk in ("n", "skopos", "ekbasis", "diff"))
    rep_ci = all(close(r3["all"][k]["ci"], pub[k]["ci"], 1e-6) for k in pub if k != "preserved")
    return {"source": "results/image_compare.json (per-item rtx/v50p/image_{skopos,ekbasis}_int4.json; the published "
                      "summary's script was not saved: paired bootstrap by item, 2,000, seed 20261015, as PREREG_IMAGE.md)",
            "reproduced_point_estimates": rep_pt, "reproduced_ci": rep_ci, **r3,
            "preserved_holds": {r: r3[r]["preserved"] == pub["preserved"] for r in ("primary", "sensitivity")}}


# ============================================================ F. calibration, INT4 (scripts_main/fit_T.py)
def scale(p, T):
    lp = {k: math.log(max(v, 1e-12)) / T for k, v in p.items()}
    m = max(lp.values())
    e = {k: math.exp(v - m) for k, v in lp.items()}
    z = sum(e.values())
    return {k: v / z for k, v in e.items()}


def nll(rs, T):
    return -sum(math.log(max(scale(r["probs"], T)[r["gold"]], 1e-12)) for r in rs) / len(rs)


def cstats(rs, T):
    bins = collections.defaultdict(list)
    ce = br = ok = 0
    for r in rs:
        q = scale(r["probs"], T)
        top = max(q, key=q.get)
        c = q[top]
        good = top == r["gold"]
        bins[min(9, int(c * 10))].append((good, c))
        ce += (not good) and c >= 0.9
        ok += good
        br += sum((q[k] - (1.0 if k == r["gold"] else 0.0)) ** 2 for k in q)
    e = sum(len(b) / len(rs) * abs(sum(g for g, _ in b) / len(b) - sum(c for _, c in b) / len(b)) for b in bins.values())
    return {"n": len(rs), "acc": round(ok / len(rs), 4), "ece": round(e, 4), "conf_err_per100": round(100 * ce / len(rs), 2),
            "brier": round(br / len(rs), 4)}


def fit_and_test(R, rule, T=None):
    """fit_T.py on the items a rule keeps; T given = keep that build's published temperature (no refit)."""
    keep = [r for r in R if r["i"] not in excl(rule, r["split"])]
    fit = [r for r in keep if r["set"] == "fit"]
    grid = [round(0.5 + 0.01 * k, 2) for k in range(251)]
    T = T if T is not None else min(grid, key=lambda t: nll(fit, t))
    test = [r for r in keep if r["set"] == "test"]
    out = {"T": T}
    for sp in ("fval_git3", "m3val", "git_long", "guard_known", "fac_val"):  # fit_T.py's layout and order
        rs = [r for r in keep if r["split"] == sp]
        out[sp] = {"T1": cstats(rs, 1.0), "Tfit": cstats(rs, T)}
    out["test_pooled"] = {"T1": cstats(test, 1.0), "Tfit": cstats(test, T)}
    out["map_binary"] = {str(p): round(1 / (1 + math.exp(-math.log(p / (1 - p)) / T)), 3) for p in (0.5, 0.7, 0.8, 0.9, 0.95, 0.99, 0.999)}
    return out


def section_calibration():
    files = {"skopos_int4": f"{V}/calib_scores_skopos_int4.jsonl", "ekbasis_int4": f"{HERE}/inputs/calib_scores_ekbasis_int4.jsonl",
             "skopos_bf16": f"{RS}/addendum/calib_scores_skopos_bf16.jsonl", "skopos_fp8": f"{RS}/addendum/calib_scores_skopos_fp8.jsonl",
             "skopos_mlx": f"{RS}/addendum/calib_scores_skopos_mlx.jsonl"}
    files = {k: v for k, v in files.items() if os.path.exists(v) and os.path.exists(f"{RES}/calib_fit_{k}.json")}
    out = {}
    for name, path in files.items():
        R = [r for r in L(path) if "probs" in r]
        pub = json.load(open(f"{RES}/calib_fit_{name}.json"))
        r3 = run3(lambda rule: fit_and_test(R, rule))
        r3["primary_published_T"] = fit_and_test(R, "primary", T=pub["T"])  # the twin: test splits only, T as published
        rep = all(r3["all"][k] == pub[k] for k in pub)
        out[name] = {"source": f"results/calib_fit_{name}.json", "scores": os.path.relpath(path, RS), "reproduced": rep, **r3}
    for r in RULES:  # the card's comparison: Skopos vs Ekbasis-27B on the same test items
        s, e = out["skopos_int4"][r]["test_pooled"], out["ekbasis_int4"][r]["test_pooled"]
        out.setdefault("comparison", {})[r] = {
            "acc": [s["T1"]["acc"], e["T1"]["acc"]], "conf_err_per100_T1": [s["T1"]["conf_err_per100"], e["T1"]["conf_err_per100"]],
            "conf_err_per100_Tfit": [s["Tfit"]["conf_err_per100"], e["Tfit"]["conf_err_per100"]],
            "ece_T1": [s["T1"]["ece"], e["T1"]["ece"]], "ece_Tfit": [s["Tfit"]["ece"], e["Tfit"]["ece"]],
            "skopos_better_on_all": s["T1"]["acc"] > e["T1"]["acc"] and s["T1"]["conf_err_per100"] < e["T1"]["conf_err_per100"]
                                    and s["Tfit"]["conf_err_per100"] < e["Tfit"]["conf_err_per100"]}
    out["note"] = ("the 2,500 test items are git_long 900 + guard_known 800 + fac_val 800, all three in-distribution sets "
                   "(their generators made training rows); the per-build fits (bf16, FP8, MLX) had no per-item scores here")
    return out


# ============================================================ G. confident errors (confident_errors_analyze.py + ce_rescore_and_compare.py)
CONF = 0.9


def ce_report(preds):
    fams = lambda g: sorted({p["world"] for p in preds if p["group"] == g})

    def share_conf(rs):
        wrong = [p for p in rs if not p["ok"]]
        return (sum(p["conf"] >= CONF for p in wrong) / len(wrong)) if wrong else float("nan"), len(wrong)

    def strata(g, sel=lambda p: True):
        return {f: [p for p in preds if p["group"] == g and p["world"] == f and sel(p)] for f in fams(g)}

    def boot_diff(sel=lambda p: True, n=2000, seed=0):
        rng = random.Random(seed)
        T, U = strata("T", sel), strata("U", sel)
        o = []
        for _ in range(n):
            rt = [rng.choice(v) for v in T.values() for _ in v]
            ru = [rng.choice(v) for v in U.values() for _ in v]
            o.append(share_conf(rt)[0] - share_conf(ru)[0])
        o.sort()
        return 100 * o[int(0.025 * n)], 100 * o[int(0.975 * n)]

    def describe(rs):
        sc, nw = share_conf(rs)
        return {"n": len(rs), "wrong": nw, "error_rate": 100 * nw / len(rs) if rs else float("nan"),
                "share_wrong_conf_ge_0.9": 100 * sc}
    rep = {"groups": {}, "families": {}}
    for g in ("T", "H", "U"):
        rs = [p for p in preds if p["group"] == g]
        rep["groups"][g] = {"all": describe(rs), "changed": describe([p for p in rs if p["changed"]])}
        for f in fams(g):
            rep["families"][f"{g}:{f}"] = describe([p for p in rs if p["world"] == f])
    sT, sU = rep["groups"]["T"]["all"]["share_wrong_conf_ge_0.9"], rep["groups"]["U"]["all"]["share_wrong_conf_ge_0.9"]
    lo, hi = boot_diff()
    fam_share = lambda g: [rep["families"][f"{g}:{f}"]["share_wrong_conf_ge_0.9"] for f in fams(g)
                           if rep["families"][f"{g}:{f}"]["wrong"] >= 10]
    med = lambda xs: statistics.median(xs) if xs else float("nan")
    mT, mU = med(fam_share("T")), med(fam_share("U"))
    diff = sT - sU
    verdict = "confirmed" if diff >= 15 and lo > 0 and mT > mU else "refuted" if lo <= 0 <= hi or diff < 0 else "inconclusive"
    rep["primary"] = {"share_T": sT, "share_U": sU, "difference_points": diff, "ci95": [lo, hi], "family_median_T": mT,
                      "family_median_U": mU, "families_counted_T": len(fam_share("T")),
                      "families_counted_U": len(fam_share("U")), "verdict": verdict}
    return rep


def section_ce():
    S = L(f"{RS}/addendum/ce/preds.jsonl")
    E = L(f"{DM}/release_clean/code_eikos/ekbasis/results/confident_errors/preds.jsonl")
    assert len(S) == len(E) == 15008

    def boot(idx, f, B=2000, seed=20261015):
        rng = random.Random(seed)
        n = len(idx)
        vals = []
        for _ in range(B):
            smp = [idx[rng.randrange(n)] for _ in range(n)]
            vals.append(f(smp))
        vals.sort()
        return [vals[int(0.025 * B)], vals[int(0.975 * B) - 1]]
    import numpy as np  # the same sums as ce_rescore_and_compare.py's err/cw, vectorized (integer counts, so identical values)
    ERR = {id(P): np.array([int(not p["ok"]) for p in P]) for P in (S, E)}
    CW = {id(P): np.array([int((not p["ok"]) and p["conf"] >= 0.9) for p in P]) for P in (S, E)}
    err = lambda P, I: 100 * int(ERR[id(P)][np.asarray(I, dtype=np.int64)].sum()) / len(I)
    cw = lambda P, I: 100 * int(CW[id(P)][np.asarray(I, dtype=np.int64)].sum()) / len(I)

    def one(rule):
        X = excl(rule, "ce_items")
        keep = [i for i in range(len(S)) if i not in X]
        o = {"groups": {}}
        for g in "THU":
            for s in ("all", "changed"):
                I = [i for i in keep if S[i]["group"] == g and (s == "all" or S[i]["changed"])]
                o["groups"][f"{g}_{s}"] = {"n": len(I), "error_skopos": err(S, I), "error_ekbasis": err(E, I),
                                           "error_diff": err(S, I) - err(E, I), "error_diff_ci": boot(I, lambda J: err(S, J) - err(E, J)),
                                           "conf_wrong_per100_skopos": cw(S, I), "conf_wrong_per100_ekbasis": cw(E, I),
                                           "conf_wrong_diff": cw(S, I) - cw(E, I),
                                           "conf_wrong_diff_ci": boot(I, lambda J: cw(S, J) - cw(E, J))}
        o["primary_skopos"] = ce_report([S[i] for i in keep])["primary"]
        o["primary_ekbasis"] = ce_report([E[i] for i in keep])["primary"]
        o["prediction_within_1pt_every_group"] = all(abs(v["error_diff"]) <= 1 and abs(v["conf_wrong_diff"]) <= 1
                                                      for k, v in o["groups"].items() if k.endswith("_all"))
        return o
    pub = json.load(open(f"{RES}/ce_r4.json"))
    r3 = run3(one)
    rep = all(close(r3["all"]["groups"][k][kk], v[kk]) for k, v in pub["groups"].items() for kk in v if kk != "n") and \
        close(r3["all"]["primary_skopos"]["ci95"], pub["primary_skopos"]["ci95"]) and \
        r3["all"]["primary_skopos"]["verdict"] == pub["primary_skopos"]["verdict"]
    return {"source": "results/ce_r4.json + addendum/ce/report.json (RESULTS_ADDENDUM.md A2)", "reproduced": rep, **r3,
            "excluded": {r: len(excl(r, "ce_items")) for r in RULES},
            "excluded_by_group": {r: dict(collections.Counter(S[i]["group"] for i in excl(r, "ce_items"))) for r in RULES}}


# ============================================================ H. quantization gates (quant_gate.py), sensitivity only
def gate(B, Q, ro, rule):
    out, chk = {}, {}
    gb, gq = [], []
    for s in ("git3_test_known", "git3_test_held"):
        X = excl(rule, s)
        gb += [p for i, p in enumerate(L(f"{B}/preds_{s}.jsonl")) if i not in X]
        gq += [p for i, p in enumerate(L(f"{Q}/preds_{s}.jsonl")) if i not in X]
    acc = lambda P: 100 * sum(p["pred"] == p["gold"] for p in P) / len(P)

    def ece_(P):
        b = collections.defaultdict(list)
        for p in P:
            b[min(9, int(p["conf"] * 10))].append(p)
        return sum(len(v) / len(P) * abs(sum(x["pred"] == x["gold"] for x in v) / len(v) - sum(x["conf"] for x in v) / len(v)) for v in b.values())
    out["git3"] = (acc(gb), acc(gq))
    chk["1 git3"] = acc(gq) >= acc(gb) - 1
    out["ece_git3"] = (ece_(gb), ece_(gq))
    chk["2 ECE"] = ece_(gq) <= ece_(gb) + 0.01
    R = rows("multi_test_testfam")
    Xm = excl(rule, "multi_test_testfam")

    def multi(d, mode):
        P = L(f"{d}/preds_multi_test_testfam_{mode}.jsonl")
        ok, ans = [], []
        for i, (r, p) in enumerate(zip(R, P)):
            if i in Xm:
                continue
            for k, q in enumerate(r["questions"]):
                ans.append(p["preds"][k])
                g0 = r["gold0s"][k]
                if r["known0s"][k] and g0 is not None and n_(g0) != n_(r["golds"][k]):
                    ok.append(p["preds"][k] == n_(r["golds"][k]))
        return 100 * sum(ok) / len(ok), ans
    for mode in (("single", "read_once") if ro else ("single",)):
        (ab, _), (aq, _) = multi(B, mode), multi(Q, mode)
        out[f"multi_{mode}"] = (ab, aq)
        chk[f"1 multi {mode}"] = aq >= ab - 1
    fr, g0 = rows("ftest_family"), rows("gold0_ftest_family")
    Xf = excl(rule, "ftest_family")
    fb, fq = L(f"{B}/preds_ftest_family.jsonl"), L(f"{Q}/preds_ftest_family.jsonl")
    ch = [i for i, (r, g) in enumerate(zip(fr, g0)) if g["known"] and n_(g["gold0"]) != n_(r["gold"]) and i not in Xf]
    fa = lambda P: 100 * sum(P[i]["ok"] for i in ch) / len(ch)
    out["ftest_changed"] = (fa(fb), fa(fq))
    chk["1 ftest"] = fa(fq) >= fa(fb) - 1
    for s in ("guard_known", "guard_held"):
        gr, X = rows(s), excl(rule, s)
        pb, pq = L(f"{B}/preds_{s}.jsonl"), L(f"{Q}/preds_{s}.jsonl")

        def g(P):
            lost = [(r, p) for i, (r, p) in enumerate(zip(gr, P)) if r["qtype"] == "lost" and i not in X]
            pos = [p for r, p in lost if r["gold"]]
            neg = [p for r, p in lost if not r["gold"]]
            return 100 * sum(p["p_yes"] >= 0.2 for p in pos) / len(pos), 100 * sum(p["p_yes"] >= 0.2 for p in neg) / len(neg)
        (fb_, ab_), (fq_, aq_) = g(pb), g(pq)
        out[s] = {"flagged": (fb_, fq_), "false_alarms": (ab_, aq_)}
        chk[f"3 {s} flagged"] = fq_ >= fb_ - 1
        chk[f"3 {s} false alarms"] = aq_ <= ab_ + 1
    _, ansb = multi(B, "single")
    _, ansq = multi(Q, "single")
    fbk = [p for i, p in enumerate(fb) if i not in Xf]
    fqk = [p for i, p in enumerate(fq) if i not in Xf]
    same = [p["pred"] == q["pred"] for p, q in zip(gb, gq)] + [a == b for a, b in zip(ansb, ansq)] + \
           [p["pred"] == q["pred"] for p, q in zip(fbk, fqk)]
    conf = [p["pred"] == q["pred"] for p, q in zip(gb + fbk, gq + fqk) if p["conf"] >= 0.9]
    out["agreement"] = 100 * sum(same) / len(same)
    out["agreement_conf09"] = 100 * sum(conf) / len(conf)
    chk["4 agreement >= 97"] = out["agreement"] >= 97
    chk["4 agreement conf>=0.9 >= 99"] = out["agreement_conf09"] >= 99
    return {"values_bf16_build": out, "checks": chk, "pass": all(chk.values())}


def section_gates():
    out = {}
    for tag, d, ro in (("int4", "release_r4_int4", True), ("fp8", "release_r4_fp8", True), ("mlx", "release_r4_mlx", False)):
        pub = json.load(open(f"{RES}/quant_gate_{tag}.json"))
        r3 = run3(lambda rule: gate(f"{V}/release_r4", f"{V}/{d}", ro, rule))
        rep = r3["all"]["pass"] == pub["pass"] and close(r3["all"]["values_bf16_build"]["agreement"], pub["values_bf16_build"]["agreement"])
        out[tag] = {"source": f"results/quant_gate_{tag}.json", "reproduced": rep, **r3,
                    "pass_holds": {r: r3[r]["pass"] == pub["pass"] for r in ("primary", "sensitivity")}}
    return out


# ============================================================ I. frontier subsets (analyze_frontier.py), descriptive
def section_frontier():
    pub = json.load(open(f"{RES}/frontier_agentworld.json"))

    def one(rule):
        o = {}
        for s in ("git_long", "guard_known", "fhorizon", "latent_test"):
            aw = L(f"{V}/frontier/aw_{s}.jsonl")
            base, r1 = L(f"{V}/base_probs/preds_{s}_floor.jsonl"), L(f"{V}/run_r1/preds_{s}_floor.jsonl")
            X = excl(rule, s)
            aw = [a for a in aw if a["i"] not in X]
            idx = [a["i"] for a in aw]
            awok = [int(a["ok"]) for a in aw]

            def boot(d):
                rng = random.Random(20261015)
                n = len(d)
                v = sorted(sum(d[rng.randrange(n)] for _ in range(n)) / n for _ in range(2000))
                return round(v[50], 3), round(v[1949], 3)
            o[s] = {"n": len(aw), "aw": round(sum(awok) / len(aw), 3), "base": round(sum(base[i]["ok"] for i in idx) / len(idx), 3),
                    "r1": round(sum(r1[i]["ok"] for i in idx) / len(idx), 3),
                    "base_minus_aw": (round(sum(int(base[i]["ok"]) - a for i, a in zip(idx, awok)) / len(idx), 3),
                                      boot([int(base[i]["ok"]) - a for i, a in zip(idx, awok)]))}
        return o
    r3 = run3(one)
    rep = all(close(r3["all"][s][k], pub[s][k], 1e-3) for s in pub for k in ("n", "aw", "base", "r1"))
    return {"source": "results/frontier_agentworld.json (AgentWorld vs Ekbasis-27B and R1, a sibling of R4; not in the card)",
            "reproduced": rep, **r3}


# ============================================================ J. are the overlapping items answered better? (descriptive)
def section_flagged_vs_clean():
    """Accuracy of Skopos (R4) and Ekbasis-27B on the flagged items and on the rest, primary rule: if the overlap
    inflated a number, the flagged items would be answered better than the others."""
    out = {}

    def pair(name, sk, ek, X, n):
        f = [i for i in range(n) if i in X]
        c = [i for i in range(n) if i not in X]
        acc = lambda P, I: round(100 * sum(P(i) for i in I) / len(I), 2) if I else None
        out[name] = {"flagged_n": len(f), "clean_n": len(c), "skopos_flagged": acc(sk, f), "skopos_clean": acc(sk, c),
                     "ekbasis27b_flagged": acc(ek, f), "ekbasis27b_clean": acc(ek, c)}
    for s, d_sk, d_ek in (("fac_val", "run_r4", "base_facval"), ("fhorizon", "run_r4", "base_probs")):
        a, b = L(f"{V}/{d_sk}/preds_{s}_floor.jsonl"), L(f"{V}/{d_ek}/preds_{s}_floor.jsonl")
        pair(s, lambda i: a[i]["ok"], lambda i: b[i]["ok"], excl("primary", s), len(a))
    R = rows("multi_test_trainfam")
    a, b = L(f"{V}/release_r4/preds_multi_test_trainfam_single.jsonl"), L(f"{V}/release_ref/preds_multi_test_trainfam_single.jsonl")
    st = lambda P, i: sum(p == g for p, g in zip(P[i]["preds"], P[i]["golds"])) / len(P[i]["golds"])
    pair("multi_test_trainfam (share of a state's questions right)", lambda i: st(a, i), lambda i: st(b, i),
         excl("primary", "multi_test_trainfam"), len(R))
    S, E = L(f"{RS}/addendum/ce/preds.jsonl"), L(f"{DM}/release_clean/code_eikos/ekbasis/results/confident_errors/preds.jsonl")
    X = excl("primary", "ce_items")
    for g in "TH":
        idx = [i for i in range(len(S)) if S[i]["group"] == g]
        sub = {k: i for k, i in enumerate(idx)}
        pair(f"ce_items group {g}", lambda k: S[sub[k]]["ok"], lambda k: E[sub[k]]["ok"], {k for k, i in sub.items() if i in X}, len(idx))
    IS, IE = json.load(open(f"{V}/image_skopos_int4.json")), json.load(open(f"{V}/image_ekbasis_int4.json"))
    pair("image (text prompt)", lambda i: IS[i]["text"], lambda i: IE[i]["text"], excl("primary", "image_fresh"), 400)
    return out


def main():
    out = {"rules": {"primary": OV["rules"]["flagged"], "sensitivity": OV["rules"]["flagged_sensitivity"]},
           "excluded": {s: {r: len(excl(r, s)) for r in ("primary", "sensitivity")} for s in OV["flags"]}}
    import sys
    only = set(sys.argv[1:])
    for name, fn in (("release_protocol", section_release), ("served_report_bf16", section_report), ("h2h", section_h2h),
                     ("vs_ekbasis27b_trainer", section_vs_ekbasis),
                     ("fresh_confirmation", section_confirm), ("image", section_image), ("calibration_int4", section_calibration),
                     ("confident_errors", section_ce), ("quantization_gates", section_gates), ("frontier", section_frontier),
                     ("flagged_vs_clean", section_flagged_vs_clean)):
        if only and name not in only:
            continue
        out[name] = fn()
        print(name, "done", flush=True)
    out["unchanged_by_construction"] = {
        "neutral.json (awb_neutral)": "0 items flagged under either rule: every number unchanged",
        "ftest_fresh_int4.json / ftest_fresh_fp8.json": "ftest_fresh: 0 items flagged under either rule: unchanged",
        "t3c_r4.json": "real-repository scenarios (pallets/itsdangerous), not dataset items: outside the audit",
        "mlx_mac_test / served equivalence": "agreement between builds, not accuracy on a set: not affected by overlap"}
    json.dump(out, open(f"{HERE}/out/recomputed.json" if not only else f"{HERE}/out/recomputed_partial.json", "w"), indent=1)
    if not only:  # a pointer per flagged set in overlap.json (the card generator reads it): where its numbers were redone
        rel = lambda r: out["release_protocol"]["bf16"][r]
        h = lambda r, s: out["h2h"]["r4_vs_skopos_v49f"][r][s]
        ce = out["confident_errors"]
        OV["recomputed"] = {
            "file": "audit/out/recomputed.json",
            "multi_test_trainfam": {"section": "release_protocol", "reported_only": True,
                                    **{r: {"skopos": rel(r)["candidate"]["multi_trainfam_single"],
                                           "ekbasis27b": rel(r)["release"]["multi_trainfam_single"],
                                           "n_changed": rel(r)["candidate"]["multi_trainfam_n_changed"]} for r in RULES}},
            "fac_val": {"section": "h2h, calibration_int4", **{r: h(r, "fac_val") for r in RULES},
                        "verdict_holds": out["h2h"]["r4_vs_skopos_v49f"]["verdict_holds"]},
            "fhorizon": {"section": "h2h", **{r: h(r, "fhorizon") for r in RULES}},
            "image": {"section": "image", **{r: {k: out["image"][r][k] for k in ("image_all", "read_all", "text_all", "preserved")}
                                             for r in RULES}, "preserved_holds": out["image"]["preserved_holds"]},
            "ce_items": {"section": "confident_errors", **{r: {"groups": ce[r]["groups"], "primary_skopos": ce[r]["primary_skopos"]}
                                                           for r in RULES}},
            "pre_registered_conclusions_hold": {
                "release protocol (each build)": all(all(v["conclusion_holds"][r].values()) for v in out["release_protocol"].values()
                                                     for r in ("primary", "sensitivity")),
                "R4 replaces the first Skopos (PREREG_R4)": all(out["h2h"]["r4_vs_skopos_v49f"]["verdict_holds"].values()),
                "fresh confirmation (CONFIRM_FTEST)": all(out["fresh_confirmation"][r]["loss_confirmed"] ==
                                                          out["fresh_confirmation"]["all"]["loss_confirmed"] for r in ("primary", "sensitivity")),
                "image preserved (PREREG_IMAGE)": all(out["image"]["preserved_holds"].values()),
                "quantization gates (PREREG_quantized)": all(all(v["pass_holds"].values()) for v in out["quantization_gates"].values()),
                "confident errors, confirmatory T vs U (PREREG_confident_errors)": all(
                    ce[r]["primary_skopos"]["verdict"] == ce["all"]["primary_skopos"]["verdict"] for r in ("primary", "sensitivity")),
                "confident errors, A2 prediction (+-1 point in every group)": {r: ce[r]["prediction_within_1pt_every_group"] for r in RULES}}}
        json.dump(OV, open(f"{HERE}/out/overlap.json", "w"))
        write_clean_twins(out)
    print("written", "out/recomputed.json" if not only else "out/recomputed_partial.json")


def clean_field(ids, extra=None):
    o = {"audit": "audit/out/overlap.json", "rule": OV["rules"]["flagged"], "excluded_n": {k: len(v) for k, v in ids.items()},
         "excluded_ids": ids}
    if extra:
        o["note"] = extra
    return o


def write_clean_twins(out):
    """out/clean/<results file>_clean.json: each results file whose sets hold flagged items (primary rule), in the
    original file's schema, recomputed without them (the card generator reads `_clean` twins from results/)."""
    d = f"{HERE}/out/clean"
    os.makedirs(d, exist_ok=True)
    ids = lambda sets: {x: sorted(excl("primary", x)) for x in sets if excl("primary", x)}
    w = lambda f, v: json.dump(v, open(f"{d}/{f}", "w"), indent=1)
    h = out["h2h"]["r4_vs_skopos_v49f"]["primary"]
    pub = json.load(open(f"{RES}/r4_vs_skopos_v49f.json"))
    twin = {k: h[k] for k in pub if k in h}
    twin["neutral_auroc"] = pub["neutral_auroc"]
    twin["verdict"] = {**{k: h["verdict"][k] for k in ("suites_worse", "gain_suites", "guard_flagged_diff", "guard_fa_diff")},
                       "r4_replaces_skopos": h["verdict"]["replaces_skopos"]}
    w("r4_vs_skopos_v49f_clean.json", {**twin, "clean": clean_field(ids(H2H_SUITES))})
    pub = json.load(open(f"{RES}/r4_vs_ekbasis27b_trainer.json"))
    w("r4_vs_ekbasis27b_trainer_clean.json", {"method": pub["method"], "sets": out["vs_ekbasis27b_trainer"]["primary"],
                                              "clean": clean_field(ids(pub["sets"]))})
    w("image_compare_clean.json", {**out["image"]["primary"], "clean": clean_field(ids(["image_fresh"]))})
    for k, v in out["calibration_int4"].items():
        if isinstance(v, dict) and "primary_published_T" in v:
            ex = {sp: sorted(excl("primary", sp)) for sp in ("fval_git3", "m3val", "git_long", "guard_known", "fac_val")}
            R = [r for r in L(f"{RS}/{v['scores']}") if "probs" in r]
            ex_items = {sp: sorted(r["i"] for r in R if r["split"] == sp and r["i"] in set(ids)) for sp, ids in ex.items()}
            w(f"calib_fit_{k}_clean.json", {**v["primary_published_T"],
                                            "clean": clean_field({sp: ids for sp, ids in ex_items.items() if ids},
                                                                 "T kept as published (fit sets have no flagged item); test splits recomputed")})
    pub = json.load(open(f"{RES}/ce_r4.json"))
    ce = out["confident_errors"]["primary"]
    w("ce_r4_clean.json", {"n": sum(v["n"] for k, v in ce["groups"].items() if k.endswith("_all")), "deviation": pub["deviation"],
                           "groups": ce["groups"], "primary_skopos": ce["primary_skopos"], "primary_ekbasis": ce["primary_ekbasis"],
                           "clean": clean_field(ids(["ce_items"]))})
    for tag, v in out["release_protocol"].items():
        r = v["primary"]
        w(f"release_read_{tag}_clean.json", {"release": r["release"], "candidate": r["candidate"], "checks": r["checks"],
                                             "pass": r["pass"], "clean": clean_field(ids(["git3_test_known", "git3_test_held",
                                             "multi_test_testfam", "multi_test_trainfam", "ftest_family", "guard_known", "guard_held"]))})
    print("clean twins written to out/clean/", sorted(os.listdir(d)))


if __name__ == "__main__":
    main()
