"""P10, real use (72 scenarios on the 4 Oct copies of two real repositories): Skopos against Ekbasis-27B's predictions of
the published run (eval_handoff/realuse_pm/pred_w4a5.json, scored by stage_release_results.py into real_use_summary.json;
the same truth.json). Counts (72 < 100): work-losing caught by the hook (of 28), false alarms (of 44), "will it fail?"
right (p_fail >= 0.5 against the exit code, of 96), median seconds per check through the client; Skopos worse by 2 or
more is flagged. Seconds compare only with an Ekbasis-27B run through the same tunnel (--ekbasis-rerun).
  python3 P10/compare.py --skopos <pred_tag.json> [--ekbasis-rerun <pred.json>] --out <json>"""
import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "common"))
from paired import counts, dump, summary  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--skopos", required=True)
ap.add_argument("--ekbasis-rerun")
ap.add_argument("--out", required=True)
ap.add_argument("--note", action="append", default=[], help="run conditions to record (repeatable)")
a = ap.parse_args()
truth = {(r["repo"], r["sid"]): r for r in json.load(open(HERE.parent / "_orig" / "realuse" / "truth.json"))}


def score(path):  # stage_release_results.py lines 104-116
    pred = {(r["repo"], r["sid"]): r for r in json.load(open(path))}
    assert set(pred) == set(truth) and not any("error" in p for p in pred.values()), path
    lost = [k for k in truth if truth[k]["lost"]]
    safe = [k for k in truth if not truth[k]["lost"]]
    fails = [(pf >= 0.5) == tf for k in truth for pf, tf in zip(pred[k]["p_fail"], truth[k]["fails"])]
    return {"scenarios": len(truth), "work_losing": len(lost), "caught": sum(pred[k]["hook"] == "ask" for k in lost),
            "safe": len(safe), "false_alarms": sum(pred[k]["hook"] == "ask" for k in safe), "fails_questions": len(fails),
            "fails_right": sum(fails), "median_seconds": sorted(p["seconds"] for p in pred.values())[len(pred) // 2],
            "hook_by_scenario": {f"{k[0]}#{k[1]}": pred[k]["hook"] for k in sorted(truth)},
            # the hook fails open (any error or a client timeout of 120 s: allow); its time is not recorded, so its
            # decision is checked against git.check's own verdict on the same scenario, which did complete
            "hook_agrees_with_completed_git_check": sum((pred[k]["hook"] == "ask") == bool(pred[k]["risky"]) for k in truth),
            "git_check_seconds_max": max(p["seconds"] for p in pred.values())}


e = score(HERE.parent / "ref" / "handoff" / "realuse_pm_pred_w4a5.json")
pub = json.load(open(HERE.parent / "ref" / "release_eval" / "real_use_summary.json"))
assert all(e[k] == pub[k] for k in ("caught", "false_alarms", "fails_right", "fails_questions", "median_seconds")), "reference does not reproduce real_use_summary.json"
s = score(a.skopos)
recs = [counts("work-losing scenarios caught (of 28)", s["caught"], e["caught"], 28),
        counts("false alarms (of 44)", s["false_alarms"], e["false_alarms"], 44, higher_is_better=False),
        counts("'will it fail?' right (of 96)", s["fails_right"], e["fails_right"], 96)]
diff = {k: [s["hook_by_scenario"][k], e["hook_by_scenario"][k]] for k in s["hook_by_scenario"] if s["hook_by_scenario"][k] != e["hook_by_scenario"][k]}
r = score(a.ekbasis_rerun) if a.ekbasis_rerun else None
dump(a.out, {"item": "P10", "reference": "ref/handoff/realuse_pm_pred_w4a5.json (Ekbasis-27B, the published run's predictions)",
             "summary": summary(recs), "measures": recs, "median_seconds": {"skopos": s["median_seconds"], "ekbasis27b_published": e["median_seconds"],
             "ekbasis27b_rerun_same_tunnel": r["median_seconds"] if r else None},
             "hook_decisions_that_differ [skopos, ekbasis27b]": diff,
             "ekbasis27b_rerun": {k: r[k] for k in ("caught", "false_alarms", "fails_right")} if r else None,
             "checks": {"hook_agrees_with_completed_git_check [skopos, ekbasis27b]": [s["hook_agrees_with_completed_git_check"], e["hook_agrees_with_completed_git_check"]],
                        "git_check_seconds_max [skopos, ekbasis27b]": [s["git_check_seconds_max"], e["git_check_seconds_max"]],
                        "reference_reproduces_real_use_summary.json": True},
             "run_conditions": a.note})
