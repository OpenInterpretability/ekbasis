"""The pre-registered gate for the Ekbasis quantized builds (ekbasis/PREREG_quantized.md): each build against the bf16
release, from the files the release evaluation scripts write (release_eval.py, release_eval_extra.py,
release_eval_t3c.py), item by item.
argv: bf16_dir build_dir bf16_t3c.json build_t3c.json name out.json"""
import json
import sys
from pathlib import Path

B, Q = Path(sys.argv[1]), Path(sys.argv[2])
T3B, T3Q, NAME, OUT = sys.argv[3], sys.argv[4], sys.argv[5], sys.argv[6]


def rows(d, f):
    return [json.loads(line) for line in open(d / f)]


def ece(p, bins=10):
    tot, n = 0.0, len(p)
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        s = [r for r in p if lo <= r["conf"] < hi or (b == bins - 1 and r["conf"] == 1.0)]
        if s:
            tot += len(s) / n * abs(sum(r["pred"] == r["gold"] for r in s) / len(s) - sum(r["conf"] for r in s) / len(s))
    return tot


rep_b, rep_q = json.load(open(B / "report_server_side.json")), json.load(open(Q / "report_server_side.json"))
ext_b, ext_q = json.load(open(B / "report_server_side_extra.json")), json.load(open(Q / "report_server_side_extra.json"))
g3b = rows(B, "preds_git3_test_known.jsonl") + rows(B, "preds_git3_test_held.jsonl")
g3q = rows(Q, "preds_git3_test_known.jsonl") + rows(Q, "preds_git3_test_held.jsonl")
ffb, ffq = rows(B, "preds_ftest_family.jsonl"), rows(Q, "preds_ftest_family.jsonl")
mtb = [p for r in rows(B, "preds_multi_test_testfam_single.jsonl") for p in r["preds"]]
mtq = [p for r in rows(Q, "preds_multi_test_testfam_single.jsonl") for p in r["preds"]]
assert len(g3b) == len(g3q) and len(ffb) == len(ffq) and len(mtb) == len(mtq)
assert all(a["gold"] == b["gold"] for a, b in zip(g3b, g3q)) and all(a["gold"] == b["gold"] for a, b in zip(ffb, ffq))

acc = lambda p: 100 * sum(r["pred"] == r["gold"] for r in p) / len(p)
res, checks = {"build": NAME}, []


def check(label, value, ref, ok, fmt="{:.2f}"):
    checks.append({"criterion": label, "build": value, "bf16": ref, "pass": bool(ok)})
    print(f"  {'PASS' if ok else 'FAIL'}  {label:58s} build {fmt.format(value):>8s}   bf16 {fmt.format(ref):>8s}")


print(f"== {NAME} against bf16")
# 1. accuracy within one point
check("git3 known+held, all questions (%)", acc(g3q), acc(g3b), acc(g3q) - acc(g3b) >= -1.0)
for mode in ("one prompt per question", "read-once"):
    k = f"multi_test_testfam ({mode})"
    if k in rep_q:
        a, b = rep_q[k]["acc_changed"], rep_b[k]["acc_changed"]
        check(f"multi_test_testfam changed, {mode} (%)", a, b, a - b >= -1.0)
k = "ftest_family (answers the actions change)"
check("ftest_family changed (%)", ext_q[k]["acc_changed"], ext_b[k]["acc_changed"],
      ext_q[k]["acc_changed"] - ext_b[k]["acc_changed"] >= -1.0)
# 2. the guard
t3b, t3q = json.load(open(T3B))["primary"], json.load(open(T3Q))["primary"]
fl_q = sum(r["p_lost"] >= 0.2 for r in t3q if r["truth"]["lost"])
fa_q = sum(r["p_lost"] >= 0.2 for r in t3q if not r["truth"]["lost"])
fl_b = sum(r["p_lost"] >= 0.2 for r in t3b if r["truth"]["lost"])
fa_b = sum(r["p_lost"] >= 0.2 for r in t3b if not r["truth"]["lost"])
check("T3c work-losing flagged (of 3)", fl_q, fl_b, fl_q == 3, "{:.0f}")
res["t3c"] = {"flagged": fl_q, "false_alarms": fa_q, "fails_right": sum((x >= 0.5) == f for r in t3q for x, f in zip(r["p_fail"], r["truth"]["fails"]))}
for s in ("git3_test_known", "git3_test_held"):
    a, b = rep_q[s]["lost_flagged_at_0.2"], rep_b[s]["lost_flagged_at_0.2"]
    check(f"{s}: work-losing flagged at 0.2 (%)", a, b, a >= b - 1.0)
    a, b = rep_q[s]["false_alarm_at_0.2"], rep_b[s]["false_alarm_at_0.2"]
    check(f"{s}: false alarms at 0.2 (%)", a, b, a <= b + 1.0)
# 3. calibration
check("ECE, git3 pooled (10 bins)", ece(g3q), ece(g3b), ece(g3q) <= ece(g3b) + 0.01, "{:.4f}")
# 4. agreement with bf16
same = [a["pred"] == b["pred"] for a, b in zip(g3q, g3b)] + [a == b for a, b in zip(mtq, mtb)] + \
       [a["pred"] == b["pred"] for a, b in zip(ffq, ffb)]
conf = [a["pred"] == b["pred"] for a, b in zip(g3q + ffq, g3b + ffb) if b["conf"] >= 0.9]
check(f"agreement with bf16, {len(same)} answers (%)", 100 * sum(same) / len(same), 100.0, sum(same) / len(same) >= 0.97)
check(f"agreement on bf16-confident answers, {len(conf)} (%)", 100 * sum(conf) / len(conf), 100.0, sum(conf) / len(conf) >= 0.99)
res["checks"] = checks
res["pass"] = all(c["pass"] for c in checks)
res["extra"] = {"git3 known / held (%)": [rep_q["git3_test_known"]["all"]["acc"], rep_q["git3_test_held"]["all"]["acc"]],
                "lost AUROC known / held": [rep_q["git3_test_known"]["lost_auroc"], rep_q["git3_test_held"]["lost_auroc"]],
                "multi_test_trainfam changed, one prompt / read-once (%)": [
                    rep_q.get("multi_test_trainfam (one prompt per question)", {}).get("acc_changed"),
                    rep_q.get("multi_test_trainfam (read-once)", {}).get("acc_changed")],
                "240-question comparison": {k: v for k, v in ext_q.items() if "240" in k}}
print(f"  => {'PASS' if res['pass'] else 'does not pass: ' + ', '.join(c['criterion'] for c in checks if not c['pass'])}")
json.dump(res, open(OUT, "w"), indent=1)
