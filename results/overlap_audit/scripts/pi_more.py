"""WS-PI, part 2: the other published numbers that rest on items overlapping the training rows.
  1. multi_test_trainfam ("trained families", 902 changed answers): accuracy on the changed answers, one prompt per
     question and read-once, the release and V42, on all 600 states and on the states whose floor does not overlap
     the model's training rows (pi_overlap_byfile.py flags).
  2. The paper's exploratory checks on the 15,008 questions (answer format, leave one family out, logistic regression,
     family-cluster bootstrap) and the relative scale, V42 and the parent, on the items that do not overlap V42's rows.
  3. The pre-registered recalibration test (recalib_fit.py, unchanged) with its test items reduced the same way.
usage: python pi_more.py   (in /root/decis/mission/PI; writes more_recompute.json)"""
from __future__ import annotations

import json
import os
import random
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
FAC = "/dev/shm/conseq/fac"
V42 = ["ftrain_mixG3"]
W4A5 = ["ftrain_mixG3", "mined_wide", "mined_chain"]


def jl(p):
    return [json.loads(l) for l in open(p)]


BY = json.load(open(os.path.join(HERE, "overlap_byfile.json")))["flags"]


def flagged(split, files):
    return {f["i"] for f in BY[split] if any(n in f["identical_in"] or f["J"].get(n, 0) >= 0.5 for n in files)}


def run_script(script, args):
    p = subprocess.run([sys.executable, os.path.join(HERE, "analysis", script)] + args, capture_output=True, text=True)
    if p.returncode:
        raise SystemExit(p.stderr[-2000:])
    return p.stdout


res = {}
# 1. trained families, multi-question states
states = jl(f"{FAC}/multi_test_trainfam.jsonl")


def nrm(v):  # release_eval.py's norm: booleans as yes/no, everything else as a lower-cased string
    if isinstance(v, bool):
        return "yes" if v else "no"
    return str(v).strip().lower()


def acc_changed(preds, keep, n_boot=2000, seed=0):
    """release_eval.py's rule: a question counts as changed when its pre-action answer is known and differs."""
    ans = []
    for i in keep:
        st, p = states[i], preds[i]
        assert [nrm(g) for g in st["golds"]] == [nrm(g) for g in p["golds"]]
        for k, g in enumerate(st["golds"]):
            g0 = st["gold0s"][k]
            if st["known0s"][k] and g0 is not None and nrm(g0) != nrm(g):
                ans.append(p["preds"][k] == p["golds"][k])  # as scored: the file keeps both, normalized
    rng = random.Random(seed)  # release_eval.py's boot()
    m = sorted(sum(rng.choice(ans) for _ in ans) / len(ans) for _ in range(n_boot))
    return {"n_changed": len(ans), "acc_changed": 100 * sum(ans) / len(ans),
            "ci95_answers_bootstrap": [100 * m[int(0.025 * n_boot)], 100 * m[int(0.975 * n_boot)]]}


res["multi_trainfam"] = {}
for model, files, d in (("w4a5", W4A5, "release_eval_w4a5"), ("v42", V42, "release_eval_v42")):
    ex = flagged("multi_test_trainfam", files)
    res["multi_trainfam"][model] = {"states_excluded": len(ex)}
    for mode in ("single", "read_once"):
        P = jl(os.path.join(HERE, "served", d, f"preds_multi_test_trainfam_{mode}.jsonl"))
        assert len(P) == len(states)
        res["multi_trainfam"][model][mode] = {"all": acc_changed(P, range(len(states))),
                                              "clean": acc_changed(P, [i for i in range(len(states)) if i not in ex])}

# 2. exploratory checks and the relative scale, V42's clean items
items = jl(os.path.join(HERE, "served", "items_local.jsonl"))
ex = flagged("ce_items", V42)
keep = [i for i in range(len(items)) if i not in ex]


def relative_scale(preds):  # reproduce.py's function, unchanged
    right = sorted(float(p["conf"]) for p in preds if p["ok"] in (True, "True"))
    out = {}
    for q, label in ((0.10, 90), (0.25, 75), (0.50, 50)):
        t = right[int(q * len(right))]
        key = f"as confident as the top {label}% of its right answers (conf >= {t:.3f})"
        out[key] = {}
        for g in ("T", "H", "U"):
            wrong = [float(p["conf"]) for p in preds if p["group"] == g and p["ok"] not in (True, "True")]
            out[key][g] = 100 * sum(c >= t for c in wrong) / len(wrong)
    return out


res["explore"], res["relative_scale"] = {}, {}
with tempfile.TemporaryDirectory() as d:
    for lv, ix in (("all", list(range(len(items)))), ("clean", keep)):
        ip = os.path.join(d, f"items_{lv}.jsonl")
        with open(ip, "w") as f:
            for i in ix:
                f.write(json.dumps(items[i]) + "\n")
        for m, path in (("v42", "served/v42/preds.jsonl"), ("eikos", "served/eikos/preds.jsonl")):
            P = jl(os.path.join(HERE, path))
            pp = os.path.join(d, f"{m}_{lv}.jsonl")
            with open(pp, "w") as f:
                for i in ix:
                    f.write(json.dumps(P[i]) + "\n")
            if m == "v42":
                out = os.path.join(d, f"explore_{lv}.json")
                run_script("confident_errors_explore.py", [ip, pp, out])
                res["explore"][lv] = json.load(open(out))
            res["relative_scale"].setdefault(lv, {})[m] = relative_scale([P[i] for i in ix])

    # 3. recalibration: the same fit rows; test_world reduced to V42's clean items (answers.jsonl keeps the items' order)
    A = jl(os.path.join(HERE, "recal", "answers.jsonl"))
    tw = [a for a in A if a["set"] == "test_world"]
    assert len(tw) == len(items) and all(a["world"] == it["world"] and str(a["gold"]) == str(it["gold"]) for a, it in zip(tw, items))
    keepset = set(keep)
    res["recalibration"] = {}
    for lv in ("all", "clean"):
        k, rows = 0, []
        for a in A:
            if a["set"] == "test_world":
                if lv == "all" or k in keepset:
                    rows.append(a)
                k += 1
            else:
                rows.append(a)
        ap = os.path.join(d, f"answers_{lv}.jsonl")
        with open(ap, "w") as f:
            for a in rows:
                f.write(json.dumps(a) + "\n")
        od = os.path.join(d, f"recal_{lv}")
        run_script("recalib_fit.py", [ap, od])
        res["recalibration"][lv] = json.load(open(os.path.join(od, "report.json")))

json.dump(res, open(os.path.join(HERE, "more_recompute.json"), "w"), indent=1)
for m, v in res["multi_trainfam"].items():
    print("multi_trainfam", m, "excluded states", v["states_excluded"],
          {mode: {lv: (v[mode][lv]["n_changed"], round(v[mode][lv]["acc_changed"], 2), [round(x, 1) for x in v[mode][lv]["ci95_answers_bootstrap"]])
                  for lv in ("all", "clean")} for mode in ("single", "read_once")})
for lv in ("all", "clean"):
    e = res["explore"][lv]
    print("explore", lv, json.dumps({k: e[k] for k in e if k in ("format",)})[:600])
    print("   lofo", json.dumps(e.get("leave_one_family_out"))[:500])
    print("   other keys", [k for k in e if k not in ("format", "leave_one_family_out")], json.dumps({k: e[k] for k in e if k not in ("format", "leave_one_family_out", "difficulty")})[:700])
    print("relative", lv, json.dumps(res["relative_scale"][lv])[:900])
