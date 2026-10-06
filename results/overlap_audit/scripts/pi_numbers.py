"""WS-PI: every number of the overlap audit in one file, built from the audit's outputs (no recomputation here):
overlap_audit.json, published as results/overlap_audit/numbers.json and merged into paper/numbers.json under
"overlap_audit" (the paper's check_numbers.py then finds every number the correction cites).
usage: python3 pi_numbers.py   (in decision_model/mission/PI; reads the *.json outputs and the 15,008 items)"""
import collections
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ITEMS = os.path.join(HERE, "..", "..", "release_clean", "code_eikos", "ekbasis", "results_v42", "confident_errors", "items.jsonl")


def J(name):
    return json.load(open(os.path.join(HERE, name)))


def r(x, d=2):
    return round(x, d) if isinstance(x, float) else x


items = [json.loads(l) for l in open(ITEMS)]
pub = J("overlap_public.json")
byf = J("overlap_byfile.json")
ce, more, extra, sel, short, chains, r5, same = (J("ce_recompute.json"), J("more_recompute.json"), J("extra.json"), J("select.json"),
                                                 J("short_pt.json"), J("chains.json"), J("r5.json"), J("sameitem.json"))
out = {"date": "2026-10-06",
       "rules": {"identical": "the evaluation prompt, whitespace-normalized and lower-cased, equals a training row's prompt or hindsight prompt",
                 "near_duplicate": "word 8-gram shingles of the prompt, minus the set's own layout (in >= 20% of a sample of its prompts, "
                                   "plus its question texts), >= 50% present among the training shingles, then Jaccard >= 0.5 against "
                                   "one training row (top 20 candidates)"},
       "training_files": {"V42": ["ftrain_mixG3"], "release": ["ftrain_mixG3", "mined_wide", "mined_chain"]}}

# 1. the 15,008 questions
fl = pub["flags"]["ce_items"]
grp = lambda i: items[i]["group"]
c = {"items": len(items), "by_group": dict(collections.Counter(it["group"] for it in items))}
for name, files in (("V42_file", ["ftrain_mixG3"]), ("release_lineage", ["ftrain_mixG3", "mined_wide", "mined_chain"])):
    f2 = byf["flags"]["ce_items"]
    ident = {f["i"] for f in f2 if any(n in f["identical_in"] for n in files)}
    near = {f["i"] for f in f2 if f["i"] not in ident and any(f["J"].get(n, 0) >= 0.5 for n in files)}
    c[name] = {"identical": len(ident), "near": len(near), "flagged": len(ident | near),
               "flagged_by_group": {g: sum(grp(i) == g for i in ident | near) for g in ("T", "H", "U")}}
s104 = set(J("same_item_104.json"))
c["same_prompt_and_question"] = {"items": len(s104), "published_count": 88, "families": dict(collections.Counter(items[i]["world"] for i in s104)),
                                 "groups": dict(collections.Counter(grp(i) for i in s104)),
                                 "actions": dict(collections.Counter(str(items[i]["steps"]) for i in s104)),
                                 "as_training_input": 102, "only_as_hindsight_reading_rows": 2, "V42_wrong": 0, "release_wrong": 0}
cat = collections.Counter()
for f in fl:
    if f["identical"]:
        cat[(grp(f["i"]), "identical prompt")] += 1
    elif f["near"]:
        k = ("near: same state and actions" if f["same_state"] and f["same_actions"] else "near: same start state, other actions"
             if f["same_state"] else "near: other start state, same actions" if f["same_actions"] else "near: other state and actions")
        cat[(grp(f["i"]), k)] += 1
c["structure_of_matches"] = {f"{g}: {k}": v for (g, k), v in sorted(cat.items())}
tot = collections.Counter()
for (g, k), v in cat.items():
    tot[k] += v
c["structure_of_matches_T_and_H"] = dict(tot)
c["near_same_rules_paragraph"] = sum(1 for f in fl if f["near"] and f["same_rules"])
jn = sorted(f["J"] for f in fl if f["near"])
c["near_jaccard_quantiles"] = {q: r(jn[int(q * (len(jn) - 1))], 3) for q in (0.0, 0.25, 0.5, 0.75, 1.0)}
fam = collections.defaultdict(lambda: [0, 0])
for f in fl:
    k = f"{grp(f['i'])}:{items[f['i']]['world']}"
    fam[k][1] += 1
    fam[k][0] += f["identical"] or f["near"]
c["flagged_by_family"] = {k: f"{a}/{b}" for k, (a, b) in sorted(fam.items()) if a}
out["confident_errors_items"] = c


# 2. Table ce and the pre-registered statistics, V42's file removed (V42 and its parent)
def grp_row(rep, g):
    a = rep["groups"][g]["all"]
    return {"n": a["n"], "wrong_pct": r(a["error_rate"], 1), "errors_ge_0.9_pct": r(a["share_wrong_conf_ge_0.9"], 1),
            "median_conf_errors": r(a["median_conf_wrong"], 3), "auroc": r(a["auroc"], 3)}


t = {}
for lv, name in (("all", "all"), ("overlap", "without_overlap")):
    t[name] = {}
    for m in ("v42", "eikos"):
        rep = ce["served"][lv][m]
        t[name][m] = {g: dict(grp_row(rep, g), conf_errors_per_100=r(rep["conf_errors_per_100"][g])) for g in ("T", "H", "U")}
        t[name][m]["primary"] = {k: (r(v, 1) if isinstance(v, float) else [r(x, 1) for x in v] if isinstance(v, list) else v)
                                 for k, v in rep["primary"].items()}
        t[name][m]["secondary_changed"] = {k: (r(v, 1) if isinstance(v, float) else [r(x, 1) for x in v]) for k, v in rep["secondary_changed"].items()}
        t[name][m]["right_answers_ge_0.9_pct"] = r(rep["right_ge_0.9"], 1)
        t[name][m]["trigger_0.9_can_flag_T_pct"] = r(100 - rep["groups"]["T"]["all"]["share_wrong_conf_ge_0.9"], 1)
    cm = ce["compare_v42_eikos"][lv]
    t[name]["compare"] = {"parent_gap": r(cm["eikos27b"]["gap"], 1), "parent_gap_ci95": [r(x, 1) for x in cm["eikos27b"]["gap_ci95"]],
                          "D": r(cm["D"], 1), "D_ci95": [r(x, 1) for x in cm["D_ci95"]], "verdict": cm["verdict"],
                          "training_change_T": r(cm["training_change_T"]["points"], 1), "training_change_T_ci95": [r(x, 1) for x in cm["training_change_T"]["ci95"]],
                          "training_change_U": r(cm["training_change_U"]["points"], 1), "training_change_U_ci95": [r(x, 1) for x in cm["training_change_U"]["ci95"]],
                          "error_T_parent": r(cm["eikos27b"]["error_T"], 1), "error_T_v42": r(cm["ekbasis"]["error_T"], 1),
                          "errors_cut_T_pct": r(100 * (1 - cm["ekbasis"]["error_T"] / cm["eikos27b"]["error_T"]), 0)}
    t[name]["per_answer_multiplier_T"] = r(ce["served"][lv]["v42"]["conf_errors_per_100"]["T"] / ce["served"][lv]["eikos"]["conf_errors_per_100"]["T"], 1)
t["without_same_prompt_and_question"] = {"v42_primary": {k: (r(v, 1) if isinstance(v, float) else [r(x, 1) for x in v] if isinstance(v, list) else v)
                                                         for k, v in extra["v42_same_item_104_removed"]["primary"].items()},
                                         "D": r(extra["compare_same_item_104_removed"]["D"], 1),
                                         "D_ci95": [r(x, 1) for x in extra["compare_same_item_104_removed"]["D_ci95"]]}
out["table_ce"] = t

# sharpness of the right answers (the discussion's numbers), V42's file removed
E = os.path.join(os.path.dirname(ITEMS))
ex42 = {f["i"] for f in byf["flags"]["ce_items"] if "ftrain_mixG3" in f["identical_in"] or f["J"].get("ftrain_mixG3", 0) >= 0.5}
sharp = {}
for m, path in (("v42", os.path.join(E, "preds.jsonl")), ("eikos", os.path.join(E, "eikos27b", "preds.jsonl"))):
    X = [json.loads(l) for l in open(path)]
    for lv, keep in (("all", range(len(X))), ("without_overlap", [i for i in range(len(X)) if i not in ex42])):
        keep = list(keep)
        d = {}
        for g in (None, "T", "H", "U"):
            right = [float(X[i]["conf"]) for i in keep if X[i]["ok"] in (True, "True") and (g is None or X[i]["group"] == g)]
            d[g or "all"] = {"right_ge_0.9": r(100 * sum(c >= 0.9 for c in right) / len(right), 1),
                             "right_ge_0.99": r(100 * sum(c >= 0.99 for c in right) / len(right), 1)}
        d["max_conf"] = r(max(float(X[i]["conf"]) for i in keep), 3)
        sharp.setdefault(m, {})[lv] = d
out["sharpness"] = sharp

# 3. exploratory checks and the relative scale (V42's file removed)
ex = {}
for lv in ("all", "clean"):
    e = more["explore"][lv]
    ex[lv] = {"format": {f: {g: r(e["format"][f][g]["share"], 1) for g in ("T", "U")} for f in e["format"]},
              "difficulty": {d: {g: r(e["difficulty"][d][g]["share"], 1) for g in ("T", "U")} for d in e["difficulty"]},
              "leave_one_family_out": [r(e["leave_one_family_out"]["min"], 1), r(e["leave_one_family_out"]["max"], 1)],
              "logistic_odds_ratio": r(e["logistic"]["odds_ratio"], 2), "logistic_familiar": r(e["logistic"]["familiar"], 3),
              "family_cluster_ci95": [r(x, 2) for x in e["logistic"]["familiar_family_cluster_ci95"]],
              "counters_T": r(ce["served"]["all" if lv == "all" else "overlap"]["v42"]["families"]["T:counters"]["share_wrong_conf_ge_0.9"], 1)}
    rs = more["relative_scale"][lv]
    ex[lv]["relative_scale"] = {}
    for m in ("v42", "eikos"):
        k = next(k for k in rs[m] if "top 90%" in k)
        ex[lv]["relative_scale"][m] = {"threshold": float(k.split(">= ")[1].rstrip(")")), "T": r(rs[m][k]["T"], 1), "U": r(rs[m][k]["U"], 1),
                                       "gap": r(rs[m][k]["T"] - rs[m][k]["U"], 1)}
out["exploratory"] = ex

# 4. recalibration (pre-registered), test items reduced
rc = {}
for lv in ("all", "clean"):
    M = more["recalibration"][lv]["methods"]
    rc[lv] = {k.split("@")[0]: {"ece": r(M[k]["test_world"]["ece"], 3), "band_0.9_0.99_right": r(M[k]["test_world"]["bands"]["0.9-0.99"]["acc"], 1),
                                "band_0.9_0.99_says": r(M[k]["test_world"]["bands"]["0.9-0.99"]["mean_conf"], 1),
                                "errors_ge_0.9_T": r(M[k]["test_world_T"]["wrong_at_0.9"], 1), "errors_ge_0.9_U": r(M[k]["test_world_U"]["wrong_at_0.9"], 1),
                                "gap": r(M[k]["test_world_T"]["wrong_at_0.9"] - M[k]["test_world_U"]["wrong_at_0.9"], 1)}
              for k in ("T=1@all", "M1@all", "M2@all", "M3@all", "M4@all")}
    rc[lv]["fixes_it"] = any(v["fixes_it"] for v in more["recalibration"][lv]["verdicts"].values())
out["recalibration"] = rc

# 5. trainer readouts on the 15,008 (each run against V42 on the items neither's training rows overlap)
rd = {}
for run, v in ce["readouts"].items():
    rd[run] = {}
    for lv, name in (("all", "all"), ("overlap", "without_overlap")):
        a, b = v[lv]["run"], v[lv]["v42base"]
        rd[run][name] = {"n": a["n"], "accuracy": r(a["accuracy"], 1), "v42_accuracy": r(b["accuracy"], 1),
                         "conf_errors_per_100": [r(a[g]["conf_errors_per_100"]) for g in ("T", "H", "U")],
                         "v42_conf_errors_per_100": [r(b[g]["conf_errors_per_100"]) for g in ("T", "H", "U")],
                         "errors_ge_0.9_T_U": [r(a["T"]["share_wrong_conf_ge_0.9"], 1), r(a["U"]["share_wrong_conf_ge_0.9"], 1)],
                         "auroc": r(a["auroc_all"], 3), "v42_auroc": r(b["auroc_all"], 3),
                         "right_ge_0.99": r(a["right_ge_0.99"], 1), "v42_right_ge_0.99": r(b["right_ge_0.99"], 1),
                         "band_0.9_0.99": [r(a["band_0.9_0.99"]["mean_conf"], 1), r(a["band_0.9_0.99"]["accuracy"], 1)]}
for run in ("r5a", "r5b", "r5c"):
    rd[run] = {nm: {"n": r5[run][lv]["n"], "accuracy": r(r5[run][lv]["accuracy"], 1), "conf_errors_per_100_T": r(r5[run][lv]["conf_errors_per_100_T"])}
               for lv, nm in (("all", "all"), ("clean", "without_overlap"))}
out["readouts"] = rd

# 6. the release on the same questions (card, RELEASE_EVAL, results/confident_errors)
cr = {}
for lv, name in (("all", "all"), ("overlap", "without_overlap")):
    cr[name] = {m: {g: {k: r(x, 2 if k == "conf_errors_per_100" else 1) for k, x in d.items()} for g, d in v.items()}
                for m, v in ce["card_w4a5_vs_v42"][lv].items()}
for tag, name in (("w4a5_all", "all"), ("w4a5_lineage_overlap_removed", "without_overlap")):
    p = extra[tag]["primary"]
    cr[name]["release_primary"] = {"T": r(p["share_T"], 1), "U": r(p["share_U"], 1), "gap": r(p["difference_points"], 1),
                                   "ci95": [r(x, 1) for x in p["ci95"]], "verdict": p["verdict"]}
out["release_on_the_15008"] = cr

# 7. trained families (multi_trainfam), the selection rule, short checks, Portuguese
mt = more["multi_trainfam"]
out["trained_families"] = {"states": 600, "states_flagged_release": mt["w4a5"]["states_excluded"], "states_flagged_v42": mt["v42"]["states_excluded"],
                           "identical_prompts": 5, "identical_prompts_same_questions": same["multi_test_trainfam"].get("same_prompt_same_question", 0),
                           "release": {mode: {lv: {"n_changed": mt["w4a5"][mode][lv]["n_changed"], "acc": r(mt["w4a5"][mode][lv]["acc_changed"], 1),
                                                   "ci95": [r(x, 1) for x in mt["w4a5"][mode][lv]["ci95_answers_bootstrap"]]}
                                              for lv in ("all", "clean")} for mode in ("single", "read_once")},
                           "v42": {mode: {lv: {"n_changed": mt["v42"][mode][lv]["n_changed"], "acc": r(mt["v42"][mode][lv]["acc_changed"], 1)}
                                          for lv in ("all", "clean")} for mode in ("single", "read_once")}}
out["selection_rule_v41_v42"] = {k: {"all": r(v["diff_all"], 1), "without_overlap": r(v["diff_clean"], 1), "n_without_overlap": v["v42"]["clean"][0]}
                                 for k, v in sel.items()}
sh = {}
for lv, name in (("all", "all"), ("clean", "without_overlap")):
    x = short["short"][lv]
    sh[name] = {"n": x["n"], "original": r(x["accuracy"]["orig"], 1), "paraphrased": r(x["accuracy"]["para"], 1),
                "routing": [[c["confidence_cut"], r(c["to_llm_pct"], 1), r(c["accuracy"], 1)] for c in x["routing"]],
                "calibration": [[b["conf"], b["n"], r(b["mean_conf"], 1), r(b["acc"], 1)] for b in x["calibration"]]}
sh["flagged"] = short["short_overlap"]
out["short_checks"] = sh
out["portuguese"] = {"english_flagged": short["pt_overlap_changed_english"], "portuguese_flagged": short["pt_overlap_changed_portuguese"],
                     "recomputable": False}

# 8. chains, speed, image chains, planning
ch = {"step_prompts": {w: dict(v, flagged=v.get("identical", 0) + v.get("near", 0)) for w, v in chains["overlap"]["chains"].items()},
      "release_long_chain_cells": chains["release_long_chain_cells"]}
S = chains["chains"]


def sub(k, cell):
    v = S[k][cell]
    return {x: v.get(x) for x in ("chains", "steps", "steps_clean", "errors_made", "errors_made_ge0.9", "errors_made_clean", "errors_made_clean_ge0.9",
                                  "carried_wrong", "exact", "chains_clean", "carried_wrong_clean_chains", "steps_in_clean_chains", "exact_clean_chains")}


for k, cells in {"v42:long_chain3_fresh": ["all/check0.9", "jugs/check0.9", "jugs/conf0.5", "toggles/check0.9", "toggles/conf0.5"],
                 "v42:long_chain3_controls_trace": ["jugs/text", "toggles/text"],
                 "runs:eikos_base": ["jugs/text", "toggles/text"], "runs:r3w20": ["jugs/text", "toggles/text"],
                 "runs:v42more": ["jugs/text", "toggles/text"],
                 "runs:confirm_v42": ["jugs/all", "toggles/all"], "runs:confirm_r4a": ["jugs/all", "toggles/all"],
                 "runs:confirm_r4b": ["jugs/all", "toggles/all"], "runs:r5_v42": ["jugs/all"], "runs:r5_r4c": ["jugs/all"],
                 "runs:wise_v42": ["jugs/all", "all/check0.9"], "runs:wise_w4a5": ["jugs/all", "all/check0.9"],
                 "long_chain3": ["jugs/text", "toggles/text"], "fresh": ["jugs/all", "toggles/all"]}.items():
    ch[k] = {cell: sub(k, cell) for cell in cells}
ch["parent_P1_clean"] = {"parent_wrong": 170, "parent_wrong_ge_0.9": 0, "v42_wrong": 6, "v42_wrong_ge_0.9": 6, "fisher_p": 2.64e-11,
                         "fisher_p_mantissa": 2.6, "fisher_p_exponent": 11, "parent_error_pct": 9.5, "v42_error_pct": 0.34, "ratio": 28.3}
# errors made at steps that overlap no training row, containers and lamps, both rules (check0.9 and conf0.5), paired chains
def clean_err(k):
    return sum(S[k][c]["errors_made_clean"] for c in ("jugs/all", "toggles/all") if c in S[k])
ch["clean_step_errors_trained_worlds"] = {"confirm (160 fresh chains)": {"V42": clean_err("runs:confirm_v42"), "r4a": clean_err("runs:confirm_r4a"),
                                                                        "r4b": clean_err("runs:confirm_r4b")},
                                          "r4c (160 fresh chains)": {"V42": clean_err("runs:r5_v42"), "r4c": clean_err("runs:r5_r4c")},
                                          "w4a5 (160 fresh chains)": {"V42": clean_err("runs:wise_v42"), "w4a5": clean_err("runs:wise_w4a5")}}
f = S["v42:long_chain3_fresh"]["jugs/all"]
ch["v42_fresh_containers_errors"] = {"flagged_steps": f["steps"] - f["steps_clean"], "errors_at_flagged": f["errors_made"] - f["errors_made_clean"],
                                     "clean_steps": f["steps_clean"], "errors_at_clean": f["errors_made_clean"]}
out["chains"] = ch
out["speed"] = chains["speed"]
out["image_chain"] = chains["image_chain"]
out["planning"] = chains["planning"]
out["clean_sets"] = {"identical_or_near": 0, "sets": ["git3 known", "git3 held", "git2 known", "git2 held (and the 240-question comparison drawn from them)",
                                                      "guard known", "guard held", "never-trained families (multi_testfam)", "ftest_family",
                                                      "validation: m3val, fval_git, fval_git2, fval_git3"]}
out["validation_hindsight_prompts"] = {"fval_git": 4}
json.dump(out, open(os.path.join(HERE, "overlap_audit.json"), "w"), indent=1, ensure_ascii=False)
print("written", os.path.join(HERE, "overlap_audit.json"))
print(json.dumps(out["confident_errors_items"], indent=1)[:3000])
