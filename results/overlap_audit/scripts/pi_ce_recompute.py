"""WS-PI: every number published on the 15,008 confident-error questions, recomputed on all items and with the items that
overlap the training rows of the model in question removed.

Overlap (pi_overlap_byfile.py, WS-F's rules): an item's floor (state + actions) identical to a training row's floor,
or a word 8-gram near duplicate (Jaccard >= 0.5) of one. Three subsets besides "all":
  same_item  removes items whose floor is identical to a training row that asks the same question (type, text, options);
  identical  removes every item whose floor is identical to a training row (any question);
  overlap    removes identical and near-duplicate items.
Which training rows count depends on the model: V42 = its file ftrain_mixG3 (it holds every earlier stage's file);
the release (w4a5) = ftrain_mixG3 + mined_wide + mined_chain (r4a's sets); each repair round = ftrain_mixG3 + its mined
sets. Paired comparisons use the union of both models' training rows.

Served predictions are re-scored with the paper's own scripts (analysis/confident_errors_analyze.py, _compare.py, run
unchanged on the filtered rows); the trainer readouts with the same definitions, here.
usage: python pi_ce_recompute.py   (in /root/decis/mission/PI; writes ce_recompute.json and prints the tables)"""
from __future__ import annotations

import bisect
import collections
import json
import os
import re
import statistics
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
FAC = "/dev/shm/conseq/fac"
CONF = 0.9
FILES = {
    "v42": ["ftrain_mixG3"], "v42base": ["ftrain_mixG3"], "eikos": [],
    "w4a5": ["ftrain_mixG3", "mined_wide", "mined_chain"],
    "v43ce": ["ftrain_mixG3"], "v43fl": ["ftrain_mixG3"], "v43ls": ["ftrain_mixG3"],
    "r2err": ["ftrain_mixG3", "mined_err"], "r2hard": ["ftrain_mixG3", "mined_hard"],
    "r2conf": ["ftrain_mixG3", "mined_conf"], "r2conffl": ["ftrain_mixG3", "mined_conf"],
    "r3h10": ["ftrain_mixG3", "mined_hard"], "r3h20": ["ftrain_mixG3", "mined_hard"],
    "r3w20": ["ftrain_mixG3", "mined_wide"],
    "r4a": ["ftrain_mixG3", "mined_wide", "mined_chain"], "r4b": ["ftrain_mixG3", "mined_wide", "mined_chain"],
    "r4c": ["ftrain_mixG3", "mined_chain"],
    "w4a7": ["ftrain_mixG3", "mined_wide", "mined_chain"], "w4b5": ["ftrain_mixG3", "mined_wide", "mined_chain"],
}
LEVELS = ("all", "same_item", "identical", "overlap")


def norm(t):
    t = t if isinstance(t, str) else json.dumps(t, ensure_ascii=False)  # as pi_overlap.text: a non-string floor is its JSON
    return re.sub(r"\s+", " ", t).strip().lower()


def qkey(qtype, q):
    if isinstance(q, dict):
        return (qtype, norm(q.get("instructions", "")), tuple(sorted(map(str, (q.get("criteria") or {}).keys()))))
    return (qtype, norm(str(q)), ())


def jl(p):
    return [json.loads(l) for l in open(p)]


items = jl(f"{FAC}/ce_items.jsonl")
by = json.load(open(os.path.join(HERE, "overlap_byfile.json")))["flags"]["ce_items"]
assert len(by) == len(items)

# same question in a training row with the identical floor, per training file
need = {hash(norm(r["floor"])) for r in items}
sameq = collections.defaultdict(set)  # file -> item indices whose identical-floor training row asks the same question
fq = collections.defaultdict(lambda: collections.defaultdict(set))  # floor hash -> file -> question keys
for name in sorted({f for v in FILES.values() for f in v}):
    for r in jl(f"{FAC}/{name}.jsonl"):
        h = hash(norm(r.get("floor", "")))
        if h in need:
            fq[h][name].add(qkey(r.get("qtype"), r.get("question")))
for i, r in enumerate(items):
    h = hash(norm(r["floor"]))
    for name, keys in fq.get(h, {}).items():
        if qkey(r.get("qtype"), r.get("question")) in keys:
            sameq[name].add(i)


def excluded(files, level):
    if level == "all" or not files:
        return set()
    out = set()
    for i, f in enumerate(by):
        if level == "same_item":
            if any(i in sameq[n] for n in files):
                out.add(i)
        elif level == "identical":
            if any(n in f["identical_in"] for n in files):
                out.add(i)
        elif level == "overlap":
            if any(n in f["identical_in"] or f["J"].get(n, 0) >= 0.5 for n in files):
                out.add(i)
    return out


def run_script(script, args):
    p = subprocess.run([sys.executable, os.path.join(HERE, "analysis", script)] + args, capture_output=True, text=True)
    if p.returncode:
        raise SystemExit(p.stderr[-2000:])
    return p.stdout


def write_rows(rows, d, name):
    path = os.path.join(d, name)
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return path


def auroc(pos, neg):
    if not pos or not neg:
        return float("nan")
    neg = sorted(neg)
    s = 0.0
    for a in pos:
        lo, hi = bisect.bisect_left(neg, a), bisect.bisect_right(neg, a)
        s += lo + 0.5 * (hi - lo)
    return s / (len(pos) * len(neg))


def readout_stats(preds, keep):
    """The trainer-readout numbers the paper cites: accuracy, per group the share of errors at >= 0.9, confident errors
    per 100 answers, AUROC; the share of right answers at >= 0.99; the 0.9-0.99 band (mean confidence, accuracy)."""
    rows = [(items[i], preds[i]) for i in keep]
    out = {"n": len(rows), "accuracy": 100 * sum(p["ok"] for _, p in rows) / len(rows)}
    right = [p for _, p in rows if p["ok"]]
    out["right_ge_0.99"] = 100 * sum(p["conf"] >= 0.99 for p in right) / len(right)
    band = [p for _, p in rows if 0.9 <= p["conf"] < 0.99]
    out["band_0.9_0.99"] = {"n": len(band), "mean_conf": 100 * statistics.mean(p["conf"] for p in band) if band else None,
                            "accuracy": 100 * sum(p["ok"] for p in band) / len(band) if band else None}
    out["auroc_all"] = auroc([p["conf"] for _, p in rows if p["ok"]], [p["conf"] for _, p in rows if not p["ok"]])
    for g in ("T", "H", "U"):
        gr = [p for it, p in rows if it["group"] == g]
        w = [p for p in gr if not p["ok"]]
        out[g] = {"n": len(gr), "wrong": len(w), "error_rate": 100 * len(w) / len(gr) if gr else None,
                  "share_wrong_conf_ge_0.9": 100 * sum(p["conf"] >= CONF for p in w) / len(w) if w else None,
                  "conf_errors_per_100": 100 * sum(p["conf"] >= CONF for p in w) / len(gr) if gr else None,
                  "auroc": auroc([p["conf"] for p in gr if p["ok"]], [p["conf"] for p in w])}
    return out


def served(path):
    return jl(path)


SERVED = {"v42": os.path.join(HERE, "served/v42/preds.jsonl"), "eikos": os.path.join(HERE, "served/eikos/preds.jsonl"),
          "w4a5": os.path.join(HERE, "served/w4a5/preds.jsonl")}
RUNS = {n: os.path.join(HERE, "runs", f"sw_{n}", "preds_ce_items_floor.jsonl")
        for n in ("v42base", "v43ce", "v43fl", "v43ls", "r2err", "r2hard", "r2conf", "r2conffl", "r3h10", "r3h20", "r3w20",
                  "r4a", "r4b", "r4c", "w4a5", "w4a7", "w4b5")}

res = {"counts": {}, "served": {}, "compare_v42_eikos": {}, "card_w4a5_vs_v42": {}, "readouts": {}}
for model, files in FILES.items():
    res["counts"][model] = {lv: {g: sum(1 for i in excluded(files, lv) if items[i]["group"] == g) for g in ("T", "H", "U")}
                            for lv in LEVELS if lv != "all"}
res["counts"]["sameq_by_file"] = {n: len(v) for n, v in sameq.items()}

with tempfile.TemporaryDirectory() as d:
    for lv in LEVELS:
        # V42 and its parent on V42's subset (the paper's Table ce, primary, secondary and the parent comparison)
        ex = excluded(FILES["v42"], lv)
        keep = [i for i in range(len(items)) if i not in ex]
        P = {m: served(SERVED[m]) for m in ("v42", "eikos")}
        rep = {}
        for m in ("v42", "eikos"):
            pf = write_rows([P[m][i] for i in keep], d, f"{m}_{lv}.jsonl")
            out = os.path.join(d, f"rep_{m}_{lv}.json")
            run_script("confident_errors_analyze.py", [pf, out])
            rep[m] = json.load(open(out))
            right = [P[m][i] for i in keep if P[m][i]["ok"]]
            rep[m]["right_ge_0.9"] = 100 * sum(p["conf"] >= 0.9 for p in right) / len(right)
            rep[m]["conf_errors_per_100"] = {g: 100 * sum((not P[m][i]["ok"]) and P[m][i]["conf"] >= CONF for i in keep
                                                          if items[i]["group"] == g) / max(1, sum(items[i]["group"] == g for i in keep))
                                             for g in ("T", "H", "U")}
        res["served"][lv] = rep
        cout = os.path.join(d, f"cmp_{lv}.json")
        run_script("confident_errors_compare.py", [os.path.join(d, f"v42_{lv}.jsonl"), os.path.join(d, f"eikos_{lv}.jsonl"), cout])
        res["compare_v42_eikos"][lv] = json.load(open(cout))
        # the card: the release against V42 on the same items (the union of their training rows)
        ex = excluded(FILES["w4a5"], lv)
        keep = [i for i in range(len(items)) if i not in ex]
        Pw = served(SERVED["w4a5"])
        card = {}
        for m, PP in (("w4a5", Pw), ("v42", P["v42"])):
            pf = write_rows([PP[i] for i in keep], d, f"card_{m}_{lv}.jsonl")
            out = os.path.join(d, f"card_rep_{m}_{lv}.json")
            run_script("confident_errors_analyze.py", [pf, out])
            r = json.load(open(out))
            card[m] = {g: {"n": r["groups"][g]["all"]["n"], "accuracy": 100 - r["groups"][g]["all"]["error_rate"],
                           "share_wrong_conf_ge_0.9": r["groups"][g]["all"]["share_wrong_conf_ge_0.9"],
                           "conf_errors_per_100": 100 * sum((not PP[i]["ok"]) and PP[i]["conf"] >= CONF for i in keep
                                                            if items[i]["group"] == g) / max(1, sum(items[i]["group"] == g for i in keep))}
                       for g in ("T", "H", "U")}
        res["card_w4a5_vs_v42"][lv] = card
    # trainer readouts: each run against V42's readout on the items neither model's training rows overlap
    base = jl(RUNS["v42base"])
    for run, path in RUNS.items():
        if not os.path.exists(path):
            continue
        P = jl(path)
        assert len(P) == len(items)
        res["readouts"][run] = {}
        for lv in LEVELS:
            ex = excluded(sorted(set(FILES[run]) | set(FILES["v42base"])), lv)
            keep = [i for i in range(len(items)) if i not in ex]
            res["readouts"][run][lv] = {"run": readout_stats(P, keep), "v42base": readout_stats(base, keep)}

json.dump(res, open(os.path.join(HERE, "ce_recompute.json"), "w"), indent=1)


def f1(x):
    return "—" if x is None or x != x else f"{x:.1f}"


print("Excluded items per model and level (T/H/U):")
for m, c in res["counts"].items():
    print(" ", m, c)
print("\nTable ce (served), V42 and the parent, V42's subsets:")
for lv in LEVELS:
    rep = res["served"][lv]
    for m in ("v42", "eikos"):
        for g in ("T", "H", "U"):
            a = rep[m]["groups"][g]["all"]
            print(f"  {lv:9} {m:5} {g} n={a['n']:5} wrong%={f1(a['error_rate']):>5} conf>=.9%={f1(a['share_wrong_conf_ge_0.9']):>5} "
                  f"per100={rep[m]['conf_errors_per_100'][g]:.2f} medconf={a['median_conf_wrong']:.3f} auroc={a['auroc']:.3f}")
    p, s = rep["v42"]["primary"], rep["v42"]["secondary_changed"]
    print(f"  {lv:9} PRIMARY T-U {p['difference_points']:+.1f} CI [{p['ci95'][0]:+.1f}, {p['ci95'][1]:+.1f}] fam medians "
          f"{f1(p['family_median_T'])} vs {f1(p['family_median_U'])} -> {p['verdict']}; changed {s['difference_points']:+.1f} "
          f"[{s['ci95'][0]:+.1f}, {s['ci95'][1]:+.1f}] ({f1(s['share_T'])} vs {f1(s['share_U'])})")
    c = res["compare_v42_eikos"][lv]
    print(f"  {lv:9} PARENT gap {c['eikos27b']['gap']:+.1f} {c['eikos27b']['gap_ci95']}  D {c['D']:+.1f} {c['D_ci95']} -> {c['verdict']}; "
          f"change T {c['training_change_T']['points']:+.1f} {c['training_change_T']['ci95']} U {c['training_change_U']['points']:+.1f} "
          f"{c['training_change_U']['ci95']}")
print("\nCard (served): release vs V42 on the release's subsets:")
for lv in LEVELS:
    c = res["card_w4a5_vs_v42"][lv]
    print("  ", lv, {m: {g: (round(c[m][g]["accuracy"], 1), f1(c[m][g]["share_wrong_conf_ge_0.9"]), round(c[m][g]["conf_errors_per_100"], 2), c[m][g]["n"])
                         for g in ("T", "U")} for m in c})
print("\nTrainer readouts (run vs V42 readout, same items):")
for run, d_ in res["readouts"].items():
    for lv in ("all", "overlap"):
        a, b = d_[lv]["run"], d_[lv]["v42base"]
        print(f"  {run:8} {lv:8} n={a['n']:5} acc {a['accuracy']:.1f} vs {b['accuracy']:.1f} | per100 T {a['T']['conf_errors_per_100']:.2f} vs "
              f"{b['T']['conf_errors_per_100']:.2f}, H {a['H']['conf_errors_per_100']:.2f} vs {b['H']['conf_errors_per_100']:.2f}, "
              f"U {a['U']['conf_errors_per_100']:.2f} vs {b['U']['conf_errors_per_100']:.2f} | share T {f1(a['T']['share_wrong_conf_ge_0.9'])} "
              f"U {f1(a['U']['share_wrong_conf_ge_0.9'])} | auroc {a['auroc_all']:.3f} vs {b['auroc_all']:.3f} | right>=.99 {a['right_ge_0.99']:.1f} vs "
              f"{b['right_ge_0.99']:.1f}")
