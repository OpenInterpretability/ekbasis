"""P2, git v3 held-out tests per question type: Skopos' release-read predictions (runs/release_r4/, the bf16 build served
on the RTX, PREREG_R4_RELEASE_READ.md) against Ekbasis-27B's published ones (results/release_eval/preds_git3_test_*.jsonl),
item by item (same rows, same order). The groups and formulas of release_eval.py (lines 61-76): accuracy on all
questions and per question type, the RELEASE_EVAL table's groups (lost, fails, in_progress, state the commands change =
other types with known0 and gold0 != gold), AUROC of P(lost), work-losing caught at a 10% false-alarm rate (the
threshold at the 10% quantile of the negatives) and at the guard's 0.2 flag. Rule: paired bootstrap where n >= 100;
counts below (per type in a split can be < 100; the caught/false-alarm counts too).
  python3 P2/compare.py --skopos <release_r4 dir> --data <dir with git3_test_known/held.jsonl> --out <json>"""
import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "common"))
from paired import counts, dump, paired, summary  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--skopos", required=True)
ap.add_argument("--data", required=True)
ap.add_argument("--out", required=True)
a = ap.parse_args()
L = lambda p: [json.loads(x) for x in open(p)]
norm = lambda g: {True: "yes", False: "no"}[g] if isinstance(g, bool) else str(g)


def auroc(pos, neg):  # release_eval.py line 40-41
    return sum((x > y) + 0.5 * (x == y) for x in pos for y in neg) / (len(pos) * len(neg))


def guard(rows, P):  # release_eval.py lines 69-76
    lost = [(p["p_yes"], r["gold"]) for r, p in zip(rows, P) if r["qtype"] == "lost"]
    pos = [p for p, g in lost if g]
    neg = sorted((p for p, g in lost if not g), reverse=True)
    thr = neg[max(0, int(0.10 * len(neg)) - 1)]
    return {"auroc": auroc(pos, neg), "caught_at_10pct_false_alarm": sum(x > thr for x in pos), "flagged_at_0.2": sum(x >= 0.2 for x in pos),
            "false_alarms_at_0.2": sum(x >= 0.2 for x in neg), "work_losing": len(pos), "safe": len(neg)}


recs, extra = [], {}
for split, name in (("git3_test_known", "known command types"), ("git3_test_held", "never-seen command types")):
    rows = L(pathlib.Path(a.data) / f"{split}.jsonl")
    S, E = L(pathlib.Path(a.skopos) / f"preds_{split}.jsonl"), L(HERE.parent / "ref" / "release_eval" / f"preds_{split}.jsonl")
    assert len(rows) == len(S) == len(E)
    assert all(norm(r["gold"]) == s["gold"] == e["gold"] and r["qtype"] == s["qtype"] == e["qtype"] for r, s, e in zip(rows, S, E))
    ok = lambda P, i: P[i]["pred"] == P[i]["gold"]
    groups = {"all questions": lambda r: True, "will uncommitted work be lost? (lost)": lambda r: r["qtype"] == "lost",
              "will the command fail? (fails)": lambda r: r["qtype"] == "fails",
              "is an operation left in progress? (in_progress)": lambda r: r["qtype"] == "in_progress",
              "state the commands change": lambda r: r["qtype"] not in ("lost", "fails", "in_progress") and r["known0"] and norm(r["gold0"]) != norm(r["gold"])}
    for q in sorted({r["qtype"] for r in rows} - {"lost", "fails", "in_progress"}):
        groups[f"question type {q} (all its questions)"] = (lambda q: lambda r: r["qtype"] == q)(q)
    for g, sel in groups.items():
        idx = [i for i, r in enumerate(rows) if sel(r)]
        recs.append(paired([ok(S, i) for i in idx], [ok(E, i) for i in idx], f"{name}: {g} ({len(idx)})"))
    gs, ge = guard(rows, S), guard(rows, E)
    recs.append(counts(f"{name}: work-losing caught at a 10% false-alarm rate (of {gs['work_losing']})", gs["caught_at_10pct_false_alarm"], ge["caught_at_10pct_false_alarm"], gs["work_losing"]))
    recs.append(counts(f"{name}: work-losing flagged at P(lost) >= 0.2 (of {gs['work_losing']})", gs["flagged_at_0.2"], ge["flagged_at_0.2"], gs["work_losing"]))
    recs.append(counts(f"{name}: false alarms at P(lost) >= 0.2 (of {gs['safe']})", gs["false_alarms_at_0.2"], ge["false_alarms_at_0.2"], gs["safe"], higher_is_better=False))
    extra[name] = {"auroc_p_lost [skopos, ekbasis27b]": [gs["auroc"], ge["auroc"]]}
dump(a.out, {"item": "P2", "reference": "ref/release_eval/preds_git3_test_*.jsonl (Ekbasis-27B, published)",
             "skopos_predictions": "the release read (results_skopos/runs/release_r4/, bf16 served on the RTX)",
             "summary": summary(recs), "measures": recs, "auroc": extra,
             "note": "Supersedes the main thread's P2/p2_git3_by_type.json for the report: the same per-item files, with the rule's split (paired bootstrap only where n >= 100, counts otherwise) and the RELEASE_EVAL groups."})
