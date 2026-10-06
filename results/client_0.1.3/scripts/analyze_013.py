"""Measures of the 0.1.3 re-run (see ../SPEC_ADDENDUM_013.md, "Measures"), from results_013/sessions (Sonnet, s*) and
results_013/sessions_explore (Haiku, y*): asks per 100, needless asks, real losses caught, latency, completion,
preservation; 0.1.3 against 0.1.2 on the same fresh calls (0.1.2 offline on each call's before-state), and against
the 0.1.2 study's own sessions.

usage: python3 analyze_013.py       (writes results_013/summary.json and prints it)
"""
from __future__ import annotations

import json
import os
import random
import re
import statistics

from common import RESULTS, read_jsonl, wilson

ASK = ("ask", "deny")
OLD = os.path.join(os.path.dirname(RESULTS), "results")      # the 0.1.2 study
BOOT_SEED, BOOT_N = 77012613, 10000


def share(k, n):
    lo, hi = wilson(k, n) if n else (None, None)
    return {"k": k, "n": n, "p": (k / n) if n else None, "ci": [lo, hi]}


def lat(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    rnd = random.Random(BOOT_SEED)
    meds = sorted(statistics.median([xs[rnd.randrange(len(xs))] for _ in xs]) for _ in range(2000))
    return {"n": len(xs), "median": statistics.median(xs), "median_ci": [meds[50], meds[1949]],
            "p90": xs[int(0.9 * (len(xs) - 1))], "mean": statistics.mean(xs), "max": xs[-1], "total": sum(xs)}


def load(sub, prefix):
    sessions, calls = [], []
    root = os.path.join(RESULTS, sub)
    for sid in sorted(os.listdir(root)) if os.path.isdir(root) else []:
        if not sid.startswith(prefix):
            continue
        s = json.load(open(os.path.join(root, sid, "session.json")))
        m = re.match(r"[a-z](\d+)_(\d+)_(.+)_([HC])$", sid)
        s["round"] = int(m.group(1))
        sessions.append(s)
        for c in read_jsonl(os.path.join(root, sid, "calls.jsonl")):
            c["task"], c["round"] = s["task"], s["round"]
            c["cls"] = (c.get("truth") or {}).get("class")
            c["v013"] = ((c.get("ekbasis") or {}).get("decision") if c["arm"] == "H" else
                         (c.get("shadow") or {}).get("decision"))
            c["v012"] = (c.get("shadow012") or {}).get("decision")
            calls.append(c)
    return sessions, calls


def old_study(sub, prefix):
    """The 0.1.2 study's sessions of the same kind: H asks per 100 (live), completion, preservation."""
    sessions, calls = [], []
    root = os.path.join(OLD, sub)
    for sid in sorted(os.listdir(root)):
        if sid.startswith(prefix):
            sessions.append(json.load(open(os.path.join(root, sid, "session.json"))))
            calls += [dict(c, task=sessions[-1]["task"]) for c in read_jsonl(os.path.join(root, sid, "calls.jsonl"))]
    h = [c for c in calls if c["arm"] == "H"]
    out = {"h_asks": share(sum(1 for c in h if (c.get("ekbasis") or {}).get("decision") in ASK), len(h)),
           "h_asks_by_class": {k: sum(1 for c in h if (c.get("ekbasis") or {}).get("decision") in ASK and
                                     (c.get("truth") or {}).get("class") == k) for k in "abcd"}}
    for arm in "HC":
        ss = [s for s in sessions if s["arm"] == arm]
        out[f"done_{arm}"] = share(sum(1 for s in ss if (s.get("check") or {}).get("done")), len(ss))
        tt = [s for s in ss if (s.get("preserved") or {}).get("total")]
        out[f"preserved_{arm}"] = share(sum(1 for s in tt if s["preserved"]["share"] == 1.0), len(tt))
        out[f"class_a_ran_{arm}"] = sum(1 for c in calls if c["arm"] == arm and c.get("executed") and
                                        (c.get("truth") or {}).get("class") == "a")
    return out


def phase(sessions, calls):
    H = [c for c in calls if c["arm"] == "H"]
    out = {"sessions": len(sessions), "calls": len(calls), "h_calls": len(H)}
    # 1. annoyance, live in H
    asks = [c for c in H if c["v013"] in ASK]
    out["h_asks_013"] = share(len(asks), len(H))
    out["h_asks_013_by_class"] = {k: sum(1 for c in asks if c["cls"] == k) for k in "abcd"}
    out["h_asks_013_per_session"] = len(asks) / max(1, sum(1 for s in sessions if s["arm"] == "H"))
    out["h_asks_013_list"] = [{"sid": c["sid"], "cls": c["cls"], "command": c["command"][:220],
                               "reason": ((c.get("ekbasis") or {}).get("reason") or "")[:220]} for c in asks]
    # paired on the same fresh calls: 0.1.3 (live in H, offline in C) against 0.1.2 (offline everywhere)
    for v in ("013", "012"):
        a = [c for c in calls if c["v" + v] in ASK]
        out[f"all_asks_{v}"] = share(len(a), len(calls))
        out[f"all_asks_{v}_by_class"] = {k: sum(1 for c in a if c["cls"] == k) for k in "abcd"}
        out[f"needless_{v}"] = {"d": share(sum(1 for c in a if c["cls"] == "d"), len(calls)),
                                "c": share(sum(1 for c in a if c["cls"] == "c"), len(calls))}
        out[f"class_a_caught_{v}"] = share(sum(1 for c in calls if c["cls"] == "a" and c["v" + v] in ASK),
                                           sum(1 for c in calls if c["cls"] == "a"))
        out[f"class_a_missed_{v}"] = [{"sid": c["sid"], "command": c["command"][:200]} for c in calls
                                      if c["cls"] == "a" and c["v" + v] not in ASK]
    out["h_live_vs_offline_013_agree"] = share(sum(1 for c in H if c.get("shadow") and
                                                   ((c.get("ekbasis") or {}).get("decision") in ASK) ==
                                                   (c["shadow"]["decision"] in ASK)), sum(1 for c in H if c.get("shadow")))
    # 4. latency: live 0.1.3 in H; offline, C calls only, each version on the calls where it ran first
    out["latency_live_013"] = lat((c.get("ekbasis") or {}).get("wall") for c in H)
    C = [c for c in calls if c["arm"] == "C"]
    out["latency_offline_C_first_013"] = lat(c["shadow"]["wall"] for c in C if (c.get("shadow") or {}).get("ran_first"))
    out["latency_offline_C_first_012"] = lat(c["shadow012"]["wall"] for c in C
                                             if (c.get("shadow012") or {}).get("ran_first"))
    out["latency_offline_C_all_013"] = lat((c.get("shadow") or {}).get("wall") for c in C)
    out["latency_offline_C_all_012"] = lat((c.get("shadow012") or {}).get("wall") for c in C)
    # 5. completion and preservation
    for arm in "HC":
        ss = [s for s in sessions if s["arm"] == arm]
        out[f"done_{arm}"] = share(sum(1 for s in ss if (s.get("check") or {}).get("done")), len(ss))
        tt = [s for s in ss if (s.get("preserved") or {}).get("total")]
        out[f"preserved_{arm}"] = share(sum(1 for s in tt if s["preserved"]["share"] == 1.0), len(tt))
        out[f"class_a_ran_{arm}"] = [{"sid": c["sid"], "command": c["command"][:200]} for c in calls
                                     if c["arm"] == arm and c.get("executed") and c["cls"] == "a"]
        out[f"usd_{arm}"] = sum(s["usd"] for s in ss)
    out["not_done"] = [{"sid": s["sid"], "check": {k: v for k, v in (s.get("check") or {}).items() if k != "tests_tail"},
                        "final": ((s.get("result") or {}).get("result") or "")[:400]}
                       for s in sessions if not (s.get("check") or {}).get("done")]
    out["classes"] = {arm: {k: sum(1 for c in calls if c["arm"] == arm and c["cls"] == k) for k in "abcd"} for arm in "HC"}
    rc = [c for c in calls if c.get("replay_check") and c["cls"]]
    out["replay_check"] = share(sum(1 for c in rc if c["replay_check"]["class"] == c["cls"]), len(rc))
    out["truth_missing"] = sum(1 for c in calls if not c["cls"])
    return out


def main():
    S = {}
    s1, c1 = load("sessions", "s")
    s2, c2 = load("sessions_explore", "y")
    S["sonnet"] = phase(s1, c1) if s1 else None
    S["haiku"] = phase(s2, c2) if s2 else None
    S["study_012_sonnet"] = old_study("sessions", "r")
    S["study_012_haiku"] = old_study("sessions_explore", "x")
    led = read_jsonl(os.path.join(RESULTS, "ledger.jsonl"))
    S["spend"] = {"total": round(sum(float(r["usd"]) for r in led), 4), "entries": len(led),
                  "all_from_result_events": all(r.get("from_result", True) for r in led if r.get("kind") == "session")}
    srv = read_jsonl(os.path.join(RESULTS, "server_log.jsonl"))
    S["server_samples"] = len(srv)
    with open(os.path.join(RESULTS, "summary.json"), "w") as fh:
        json.dump(S, fh, indent=1)
    print(json.dumps(S, indent=1)[:30000])


if __name__ == "__main__":
    main()
