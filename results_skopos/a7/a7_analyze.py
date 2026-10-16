"""PREREG_ADDENDUM A7 (appended 2026-10-16 02:39 UTC): confident errors with full probabilities, raw and at each build's
own calibrated temperature, Skopos INT4 against Ekbasis-27B INT4, on the 15,008 items of A2.

Inputs: the two files scripts_main/ce_probs.py writes (one record per item: k, world, qtype, group, changed, gold,
probs = every option's probability), and the temperatures of results/calib_fit_skopos_int4.json (1.67) and
results/calib_fit_ekbasis_int4.json (1.55, the hosted one).
- Answer = the most probable option; confidence = its probability. Calibrated = serve.py's / the hosted API's
  `calibrated` field: every option's probability raised to 1/T and renormalized (repos/patch_calibrated.py, calibrate()).
  A monotone transform, so the answer, and therefore accuracy, is the same raw and calibrated; only confidence moves.
- Per group (T trained families, H held-out question types, U never-trained families) x (all answers, answers the
  actions change) x (all items, clean = without the items the overlap audit flags: results/ce_r4_clean.json):
  accuracy; wrong at confidence >= 0.9 per 100 answers; ECE (10 equal-width bins on the confidence, as
  ce_ece_by_group.py); the share of wrong answers at >= 0.9 (A2's primary quantity), raw and calibrated.
- Paired bootstrap (2,000, seed 20261015; percentile interval at sorted[50] and sorted[1949], as A2's
  ce_rescore_and_compare.py and ce_ece_by_group.py) of: Skopos INT4 - Ekbasis-27B INT4, raw and calibrated (each at
  its own temperature); calibrated - raw within each build; and the prediction's comparison, Skopos INT4 calibrated -
  Ekbasis-27B INT4 raw.
- The prediction (A7: "the calibrated temperature lowers confidently wrong answers in U for every build, so Skopos
  calibrated is at or below Ekbasis-27B raw there; the INT4 builds repeat A2's pattern: fewer errors in T/H, more
  confident errors in U") is checked and reported as held / not held, each piece on its paired interval: "lowers" and
  "fewer"/"more" = the interval entirely on that side of 0; "at or below" = the interval's lower end <= 0 (not
  significantly above). These readings are ws-eval's (A7 fixes no criterion): A7 decides only what the card and the
  scorecard may say.
Self-test (2026-10-16): with A2's top-confidence predictions as input (both models), the raw numbers reproduce
results/ce_r4.json (error and wrong at >= 0.9 per 100, every group) and results/ce_r4_ece.json (ECE) exactly.
Runtime about 7 minutes (the ECE bootstraps).
- Not run: A7 on Skopos bf16 (NOT_RUN_BF16 below: the phase A bf16 attempt was stopped while sharing the GPU; the INT4
  builds ran first after the battery; the machine was then retired by the owner's decision), so the pre-registered
  consistency check (bf16 here = A2 on >= 99%) cannot run. Reported instead, for information: how often each INT4 build gives the answer
  its bf16 gave in A2 (Skopos: addendum/ce/preds.jsonl; Ekbasis-27B: its published preds).
Fails loudly on a missing or errored item, or on items that differ between the files.
  python3 a7_analyze.py --skopos ce_a7_skopos_int4.jsonl --ekbasis ce_a7_ekbasis_int4.jsonl --out results/ce_a7.json
                        [--rs <release_skopos>] [--dm <decision_model>]"""
import argparse
import collections
import json
import math
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
ap.add_argument("--skopos", required=True)
ap.add_argument("--ekbasis", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--rs", default=os.path.normpath(os.path.join(HERE, "..", "..")))
ap.add_argument("--dm", default=os.path.normpath(os.path.join(HERE, "..", "..", "..", "..", "..")))
ap.add_argument("--note", action="append", default=[], help="run conditions to record (repeatable)")
a = ap.parse_args()
L = lambda p: [json.loads(x) for x in open(p)]
B, SEED = 2000, 20261015
T_SK = json.load(open(f"{a.rs}/results/calib_fit_skopos_int4.json"))["T"]
T_EK = json.load(open(f"{a.rs}/results/calib_fit_ekbasis_int4.json"))["T"]
flagged = set(json.load(open(f"{a.rs}/results/ce_r4_clean.json"))["clean"]["excluded_ids"]["ce_items"])


def calibrate(probs, T):  # repos/patch_calibrated.py, calibrate(): the hosted API's `calibrated` field
    lp = {k: math.log(max(v, 1e-12)) / T for k, v in probs.items()}
    m = max(lp.values())
    e = {k: math.exp(v - m) for k, v in lp.items()}
    z = sum(e.values())
    return {k: v / z for k, v in e.items()}


def score(path, T):
    rows = sorted(L(path), key=lambda r: r["k"])
    bad = [r["k"] for r in rows if "error" in r]
    if bad or [r["k"] for r in rows] != list(range(len(rows))):
        raise SystemExit(f"{path}: {len(bad)} errored items, {len(rows)} rows: not complete, not analysed")
    out = []
    for r in rows:
        top = max(r["probs"], key=r["probs"].get)
        cq = calibrate(r["probs"], T)
        out.append({"group": r["group"], "changed": r["changed"], "gold": r["gold"], "world": r["world"], "qtype": r["qtype"],
                    "pred": top, "ok": top == r["gold"], "conf": r["probs"][top], "conf_cal": cq[top]})
    return out


S, E = score(a.skopos, T_SK), score(a.ekbasis, T_EK)
assert len(S) == len(E) == 15008, (len(S), len(E))
assert all((s["world"], s["qtype"], s["gold"], s["group"], s["changed"]) == (e["world"], e["qtype"], e["gold"], e["group"], e["changed"]) for s, e in zip(S, E)), "items differ"

acc = lambda P, I, c="conf": 100 * sum(P[i]["ok"] for i in I) / len(I)
cw = lambda P, I, c="conf": 100 * sum((not P[i]["ok"]) and P[i][c] >= 0.9 for i in I) / len(I)


def ece(P, I, c="conf"):
    b = collections.defaultdict(list)
    for i in I:
        b[min(9, int(P[i][c] * 10))].append(i)
    return sum(len(v) / len(I) * abs(sum(P[i]["ok"] for i in v) / len(v) - sum(P[i][c] for i in v) / len(v)) for v in b.values())


def share(P, I, c="conf"):
    w = [i for i in I if not P[i]["ok"]]
    return 100 * sum(P[i][c] >= 0.9 for i in w) / len(w) if w else None


def boot(I, f):
    rng = random.Random(SEED)
    n = len(I)
    vals = sorted(f([I[rng.randrange(n)] for _ in range(n)]) for _ in range(B))
    return [vals[int(0.025 * B)], vals[int(0.975 * B) - 1]]


def diff(name, f, g):  # f, g: functions of an index list
    return lambda I: {"measure": name, "value": f(I) - g(I), "ci95": boot(I, lambda J: f(J) - g(J))}


groups = {}
for g in "THU":
    for s in ("all", "changed"):
        for subset in ("all_items", "clean"):
            I = [i for i, p in enumerate(S) if p["group"] == g and (s == "all" or p["changed"]) and (subset == "all_items" or i not in flagged)]
            d = {"n": len(I)}
            for name, P in (("skopos_int4", S), ("ekbasis27b_int4", E)):
                d[name] = {"accuracy": acc(P, I), "conf_wrong_per100_raw": cw(P, I), "conf_wrong_per100_calibrated": cw(P, I, "conf_cal"),
                           "ece_raw": ece(P, I), "ece_calibrated": ece(P, I, "conf_cal"),
                           "share_of_wrong_at_ge_0.9_raw": share(P, I), "share_of_wrong_at_ge_0.9_calibrated": share(P, I, "conf_cal")}
            d["comparisons"] = [f(I) for f in (
                diff("accuracy: Skopos INT4 - Ekbasis-27B INT4", lambda J: acc(S, J), lambda J: acc(E, J)),
                diff("wrong at >= 0.9 per 100, raw: Skopos - Ekbasis-27B", lambda J: cw(S, J), lambda J: cw(E, J)),
                diff("wrong at >= 0.9 per 100, calibrated (own T): Skopos - Ekbasis-27B", lambda J: cw(S, J, "conf_cal"), lambda J: cw(E, J, "conf_cal")),
                diff("ECE, raw: Skopos - Ekbasis-27B", lambda J: ece(S, J), lambda J: ece(E, J)),
                diff("ECE, calibrated (own T): Skopos - Ekbasis-27B", lambda J: ece(S, J, "conf_cal"), lambda J: ece(E, J, "conf_cal")),
                diff("wrong at >= 0.9 per 100: Skopos calibrated - raw", lambda J: cw(S, J, "conf_cal"), lambda J: cw(S, J)),
                diff("wrong at >= 0.9 per 100: Ekbasis-27B calibrated - raw", lambda J: cw(E, J, "conf_cal"), lambda J: cw(E, J)),
                diff("ECE: Skopos calibrated - raw", lambda J: ece(S, J, "conf_cal"), lambda J: ece(S, J)),
                diff("ECE: Ekbasis-27B calibrated - raw", lambda J: ece(E, J, "conf_cal"), lambda J: ece(E, J)),
                diff("wrong at >= 0.9 per 100: Skopos calibrated - Ekbasis-27B raw (the prediction)", lambda J: cw(S, J, "conf_cal"), lambda J: cw(E, J)))]
            groups[f"{g}_{s}_{subset}"] = d
            print(f"{g} {s:7s} {subset:9s} n={len(I):5d} acc {d['skopos_int4']['accuracy']:.2f}/{d['ekbasis27b_int4']['accuracy']:.2f} "
                  f"cw raw {d['skopos_int4']['conf_wrong_per100_raw']:.2f}/{d['ekbasis27b_int4']['conf_wrong_per100_raw']:.2f} "
                  f"cal {d['skopos_int4']['conf_wrong_per100_calibrated']:.2f}/{d['ekbasis27b_int4']['conf_wrong_per100_calibrated']:.2f} "
                  f"ECE raw {d['skopos_int4']['ece_raw']:.4f}/{d['ekbasis27b_int4']['ece_raw']:.4f} cal {d['skopos_int4']['ece_calibrated']:.4f}/{d['ekbasis27b_int4']['ece_calibrated']:.4f}", flush=True)


def held(key, k):  # a pre-registered prediction's piece, judged on the interval of the named comparison
    c = next(x for x in groups[key]["comparisons"] if x["measure"].startswith(k))
    return c


pred = {}
for subset in ("all_items", "clean"):
    U = f"U_all_{subset}"
    p = {}
    for build in ("Skopos", "Ekbasis-27B"):
        c = held(U, f"wrong at >= 0.9 per 100: {build} calibrated - raw")
        p[f"calibrated lowers confident errors in U, {build}"] = {"value": c["value"], "ci95": c["ci95"], "held": c["ci95"][1] < 0}
    c = held(U, "wrong at >= 0.9 per 100: Skopos calibrated - Ekbasis-27B raw")
    p["Skopos calibrated at or below Ekbasis-27B raw in U"] = {"value": c["value"], "ci95": c["ci95"], "held": c["ci95"][0] <= 0}
    for g in "TH":
        c = held(f"{g}_all_{subset}", "accuracy: Skopos INT4 - Ekbasis-27B INT4")
        p[f"fewer errors in {g} (Skopos INT4 vs Ekbasis-27B INT4)"] = {"accuracy_diff": c["value"], "ci95": c["ci95"], "held": c["ci95"][0] > 0}
    c = held(U, "wrong at >= 0.9 per 100, raw: Skopos - Ekbasis-27B")
    p["more confident errors in U (raw)"] = {"value": c["value"], "ci95": c["ci95"], "held": c["ci95"][0] > 0}
    pred[subset] = p

info = {}
for name, P, ref in (("skopos_int4 vs Skopos bf16 in A2", S, f"{a.rs}/addendum/ce/preds.jsonl"),
                     ("ekbasis27b_int4 vs Ekbasis-27B bf16 published", E, f"{a.dm}/release_clean/code_eikos/ekbasis/results/confident_errors/preds.jsonl")):
    if os.path.exists(ref):
        R = L(ref)
        info[name] = {"same_answer": sum(p["pred"] == r["pred"] for p, r in zip(P, R)), "n": len(R)}
pct = {k: f"{100 * v['same_answer'] / v['n']:.1f}" for k, v in info.items()}
NOT_RUN_BF16 = ("A7 on Skopos bf16 was not run. A bf16 run during the phase A battery was stopped because it shared the GPU (124 "
                "items in 12 min; DEVIATIONS_RUN.md). After the battery, the two INT4 builds ran first (they back the hosted API's "
                "scorecard and the switch made on 2026-10-16), and the evaluation machine was then retired by the owner's decision "
                "before a bf16 run. The pre-registered bf16 = A2 consistency check therefore did not run; for information, each INT4 "
                f"build gives its own bf16's A2 answer on {pct.get('skopos_int4 vs Skopos bf16 in A2', '?')}% (Skopos) and "
                f"{pct.get('ekbasis27b_int4 vs Ekbasis-27B bf16 published', '?')}% (Ekbasis-27B) of items.")
json.dump({"item": "PREREG_ADDENDUM A7", "temperatures": {"skopos_int4": T_SK, "ekbasis27b_int4": T_EK},
           "groups": groups, "prediction": pred,
           "not_run": [{"part": "A7 on Skopos bf16, and with it the pre-registered consistency check (bf16 here = A2 on >= 99%)",
                        "reason": NOT_RUN_BF16}],
           "information_int4_vs_bf16_answers": info, "run_conditions": a.note, "method": __doc__.split("\n")[0]},
          open(a.out, "w"), indent=1)
print(json.dumps(pred, indent=1))
print("wrote", a.out)
