"""WS-AL analysis, as pre-registered in SPEC.md: per task (mean over seeds), paired across conditions, 95% CIs by
bootstrap over tasks (10,000 resamples, seed 20261005). Uses the valid row of each (task, condition, seed): rows with
success = null (runs lost to the stage bug, SPEC Addendum 2) are dropped when a valid rerun exists.
    python3 analyze_al.py -> summary.json (and prints the tables)"""
import glob
import json
import os
import random
import statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))
B, SEED = 10000, 20261005


def load(prefixes):
    rows = {}
    for pre in prefixes:
        p = os.path.join(HERE, f"runs_{pre}.jsonl")
        if not os.path.exists(p):
            continue
        for l in open(p):
            r = json.loads(l)
            k = (r["id"], r["cond"], r["seed"])
            if r.get("success") is None and k in rows and rows[k].get("success") is not None:
                continue
            rows[k] = r
    return [r for r in rows.values() if r.get("success") is not None], [r for r in rows.values() if r.get("success") is None]


def per_task(rows, cond, metric, ids):
    out = {}
    for i in ids:
        v = [float(r[metric]) for r in rows if r["id"] == i and r["cond"] == cond and r.get(metric) is not None]
        if v:
            out[i] = sum(v) / len(v)
    return out


def boot_diff(a, b, ids):
    ids = [i for i in ids if i in a and i in b]
    if not ids:
        return None
    rng = random.Random(SEED)
    d = [a[i] - b[i] for i in ids]
    est = sum(d) / len(d)
    bs = sorted(sum(rng.choice(d) for _ in d) / len(d) for _ in range(B))
    return {"diff_points": round(100 * est, 1), "ci95": [round(100 * bs[int(0.025 * B)], 1), round(100 * bs[int(0.975 * B) - 1], 1)], "tasks": len(ids)}


def cond_table(rows, conds, metric_list):
    out = {}
    for c in conds:
        rs = [r for r in rows if r["cond"] == c]
        if not rs:
            continue
        out[c] = {"runs": len(rs)}
        for m in metric_list:
            v = [r.get(m) for r in rs if r.get(m) is not None]
            if not v:
                continue
            if isinstance(v[0], bool):
                out[c][m] = {"k": sum(v), "n": len(v), "rate": round(sum(v) / len(v), 4)}
            else:
                out[c][m] = {"mean": round(st.mean(v), 4), "median": round(st.median(v), 4)}
        ms = [x for r in rs for x in (r.get("ekb_ms") or [])]
        if ms:
            out[c]["ekbasis_ms_median"] = round(st.median(ms), 1)
        out[c]["cost_usd_total"] = round(sum(r.get("cost_usd") or 0 for r in rs), 4)
    return out


def look_ahead():
    rows, lost = load(["la_a", "la_b", "la_c"])
    tasks = [json.loads(l)["meta"] for l in open(os.path.join(HERE, "tasks_la.jsonl"))]
    trap = [t["id"] for t in tasks if t["kind"] == "trap"]
    ctrl = [t["id"] for t in tasks if t["kind"] == "control"]
    conds = ["blind", "see", "ahead", "manual"]
    out = {"runs_valid": len(rows), "runs_lost_not_rerun": len(lost),
           "by_condition_all": cond_table(rows, conds, ["success", "harm", "actions", "tool_calls", "turns", "cost_usd", "seconds"]),
           "by_condition_trap": cond_table([r for r in rows if r["id"] in trap], conds, ["success", "harm", "actions"]),
           "by_condition_control": cond_table([r for r in rows if r["id"] in ctrl], conds, ["success", "harm", "actions"])}
    S = {c: per_task(rows, c, "success", trap + ctrl) for c in conds}
    H = {c: per_task(rows, c, "harm", trap + ctrl) for c in conds}
    A = {c: per_task(rows, c, "actions", trap + ctrl) for c in conds}
    C = {c: per_task(rows, c, "cost_usd", trap + ctrl) for c in conds}
    out["primary_ahead_minus_blind_success_trap"] = boot_diff(S["ahead"], S["blind"], trap)
    out["secondary"] = {
        "ahead_minus_see_success_trap": boot_diff(S["ahead"], S["see"], trap),
        "ahead_minus_manual_success_trap": boot_diff(S["ahead"], S["manual"], trap),
        "see_minus_blind_success_trap": boot_diff(S["see"], S["blind"], trap),
        "manual_minus_blind_success_trap": boot_diff(S["manual"], S["blind"], trap),
        "ahead_minus_blind_harm_trap": boot_diff(H["ahead"], H["blind"], trap),
        "ahead_minus_blind_success_control": boot_diff(S["ahead"], S["blind"], ctrl),
    }
    out["steps_and_cost"] = {c: {"actions_mean_per_task": round(st.mean(A[c].values()), 2) if A[c] else None,
                                 "cost_mean_per_run": round(st.mean(C[c].values()), 4) if C[c] else None} for c in conds}
    p = out["primary_ahead_minus_blind_success_trap"]
    out["primary_bar_met"] = bool(p and p["diff_points"] >= 15 and p["ci95"][0] > 0)
    # per task, success per condition (for the report)
    out["per_task_success"] = {i: {c: S[c].get(i) for c in conds} for i in trap + ctrl}
    return out


def tracker_accuracy(prefix):
    steps = tot = 0
    wrong_steps = looks = 0
    for p in glob.glob(os.path.join(HERE, "sessions", prefix, "*_tracker_s*.json")):
        tr = json.load(open(p))["meta"].get("tracker") or {}
        for s in tr.get("steps", []):
            tot += 1
            if any(abs(s["pred"][a] - s["truth"][a]) > 0.005 for a in s["pred"]):
                wrong_steps += 1
        looks += len(tr.get("looks", []))
        steps += 1
    return {"sessions": steps, "steps": tot, "steps_with_a_wrong_balance": wrong_steps, "looks": looks}


def ledger():
    rows, lost = load(["st"])
    ids = [json.loads(l)["meta"]["id"] for l in open(os.path.join(HERE, "tasks_st.jsonl"))]
    conds = ["alone", "tracker"]
    out = {"runs_valid": len(rows), "runs_lost_not_rerun": len(lost),
           "by_condition": cond_table(rows, conds, ["report_exact", "success", "harm", "balances_right", "decisions_right",
                                                    "overdrafts", "checks_used", "actions", "turns", "cost_usd", "seconds"])}
    E = {c: per_task(rows, c, "report_exact", ids) for c in conds}
    H = {c: per_task(rows, c, "harm", ids) for c in conds}
    D = {c: per_task(rows, c, "decisions_right", ids) for c in conds}
    out["primary_tracker_minus_alone_report_exact"] = boot_diff(E["tracker"], E["alone"], ids)
    out["secondary"] = {"tracker_minus_alone_overdraft_runs": boot_diff(H["tracker"], H["alone"], ids),
                        "tracker_minus_alone_decisions_right_of_3": (lambda d: d and {**d, "diff_points": round(d["diff_points"] / 100, 3), "ci95": [round(x / 100, 3) for x in d["ci95"]], "unit": "decisions"})(boot_diff(D["tracker"], D["alone"], ids))}
    p = out["primary_tracker_minus_alone_report_exact"]
    out["primary_bar_met"] = bool(p and p["diff_points"] >= 20 and p["ci95"][0] > 0)
    out["tracker_itself"] = tracker_accuracy("st")
    out["per_task_report_exact"] = {i: {c: E[c].get(i) for c in conds} for i in ids}
    return out


def main():
    out = {"look_ahead": look_ahead(), "state_tracker": ledger(),
           "spend_usd_all_AL_runs": round(sum((json.loads(l).get("cost_usd") or 0) for p in glob.glob(os.path.join(HERE, "runs_*.jsonl")) for l in open(p)), 4)}
    json.dump(out, open(os.path.join(HERE, "summary.json"), "w"), indent=1)
    la, stt = out["look_ahead"], out["state_tracker"]
    print("LOOK-AHEAD (trap tasks):", json.dumps({c: v.get("success") for c, v in la["by_condition_trap"].items()}))
    print("  primary ahead-blind:", la["primary_ahead_minus_blind_success_trap"], "bar met:", la["primary_bar_met"])
    print("  secondary:", json.dumps(la["secondary"]))
    print("  steps/cost:", json.dumps(la["steps_and_cost"]))
    print("STATE TRACKER:", json.dumps({c: (v.get("report_exact"), v.get("harm")) for c, v in stt["by_condition"].items()}))
    print("  primary tracker-alone:", stt["primary_tracker_minus_alone_report_exact"], "bar met:", stt["primary_bar_met"])
    print("  tracker itself:", stt["tracker_itself"])
    print("AL spend: $%.2f" % out["spend_usd_all_AL_runs"])


if __name__ == "__main__":
    main()
