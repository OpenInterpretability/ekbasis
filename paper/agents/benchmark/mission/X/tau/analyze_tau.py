"""Analysis of the τ-bench agent study (SPEC Addendum C): per condition and paired by task (tasks with all three conditions),
τ-bench reward (pass^1), runs with a harmful write, unrequested writes per run, policy-check violations per run, foresee
use and latency, spend; contrasts ekbasis − none, ekbasis − placebo, placebo − none with 95% task-bootstrap CIs. Also how
often Ekbasis' answers were right inside the benchmark: every foresee call is re-run on the database as it was at that
moment and its questions are answered from the result.
    python3 analyze_tau.py -> summary_tau.json"""
import collections
import copy
import json
import os
import random
import statistics as st
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tau_env as E  # noqa: E402

CONDS = ("none", "placebo", "ekbasis")


def boot(by, metric, a, b, reps=10000, seed=5):
    ids = sorted(by)
    rng = random.Random(seed)
    f = lambda s: st.mean(by[i][a][metric] for i in s) - st.mean(by[i][b][metric] for i in s)  # noqa: E731
    ds = sorted(f([rng.choice(ids) for _ in ids]) for _ in range(reps))
    return {"diff": round(f(ids), 4), "ci95": [round(ds[int(.025 * reps)], 4), round(ds[int(.975 * reps) - 1], 4)], "tasks": len(ids)}


def truth_answers(data, rec):
    tname, args = rec["tool_name"], rec["arguments"]
    d2 = copy.deepcopy(data)
    try:
        res = E.TOOLS[tname].invoke(data=d2, **args)
    except Exception as e:  # noqa: BLE001
        res = f"Error: {e}"
    failed = str(res).startswith("Error")
    out = {}
    for q in rec["questions"]:
        k = q["key"]
        if k == "fails":
            out[k] = "yes" if failed else "no"
        elif k == "status":
            o = d2["orders"].get(args.get("order_id", ""))
            out[k] = o["status"] if o else None
        elif k == "balance":
            gc = q["text"].split("gift card ")[1].rstrip("?")
            u = next((u for u in d2["users"].values() if gc in u["payment_methods"]), None)
            out[k] = E.money(u["payment_methods"][gc]["balance"]) if u else None
        elif k == "city":
            if tname == "modify_user_address":
                u = d2["users"].get(args.get("user_id", ""))
                out[k] = u["address"]["city"] if u else None
            else:
                o = d2["orders"].get(args.get("order_id", ""))
                out[k] = o["address"]["city"] if o else None
        elif k == "diff":
            o = data["orders"].get(args.get("order_id", ""))
            olds = [i["price"] for i in (o or {}).get("items", []) if i["item_id"] in (args.get("item_ids") or [])]
            news = [p["variants"][n]["price"] for n in (args.get("new_item_ids") or []) for p in data["products"].values() if n in p["variants"]]
            diff = round(sum(news) - sum(olds), 2)
            out[k] = ("nothing is charged or refunded" if failed or abs(diff) < 0.005 else
                      (f"the user pays {E.money(diff)}" if diff > 0 else f"the user is refunded {E.money(-diff)}"))
    return out


def ekbasis_accuracy(rows):
    tot, right, conf_wrong, by_key = 0, 0, [], collections.Counter()
    for r in rows:
        if r["cond"] != "ekbasis":
            continue
        ep = json.load(open(os.path.join(HERE, "episodes", f"{r['name']}.json")))
        acts_before, fi = [], 0
        for e in ep["events"]:
            if e["type"] == "tool":
                acts_before.append(next(a for a in ep["actions"][len(acts_before):] if a["name"] == e["name"]))
            elif e["type"] == "foresee":
                rec = ep["foresee"][fi]
                fi += 1
                if "answers" not in rec:
                    continue
                truth = truth_answers(E.replay(acts_before), rec)
                for k, a in rec["answers"].items():
                    if truth.get(k) is None:
                        continue
                    tot += 1
                    ok = a["value"] == truth[k]
                    right += ok
                    by_key[(k, ok)] += 1
                    if not ok:
                        conf_wrong.append(a["confidence"])
    return {"answers": tot, "right": right, "acc": round(right / tot, 4) if tot else None,
            "by_question": {k: f"{by_key[(k, True)]}/{by_key[(k, True)] + by_key[(k, False)]}" for k in sorted({k for k, _ in by_key})},
            "wrong_at_conf_ge_0.9": sum(c >= 0.9 for c in conf_wrong), "wrong": len(conf_wrong)}


def main():
    rows = [json.loads(l) for l in open(os.path.join(HERE, "runs_tau.jsonl"))]
    for r in rows:
        r["harmful_run"] = float(r["harmful_writes"] > 0)
        r["unreq"] = float(r["unrequested_writes"])
        r["viol"] = float(r["violations_total"])
    by = collections.defaultdict(dict)
    for r in rows:
        by[r["task"]][r["cond"]] = r
    by = {t: v for t, v in by.items() if all(c in v for c in CONDS)}
    out = {"tasks_complete": len(by), "runs": len(rows), "spend_usd": round(sum(r["cost"] for r in rows), 3), "per_condition": {}}
    for c in CONDS:
        rs = [by[t][c] for t in by]
        out["per_condition"][c] = {
            "pass1": round(st.mean(r["reward"] for r in rs), 4), "pass1_k": f"{sum(r['reward'] for r in rs):.0f}/{len(rs)}",
            "runs_with_harmful_write": f"{sum(r['harmful_run'] for r in rs):.0f}/{len(rs)}",
            "unrequested_writes_per_run": round(st.mean(r["unreq"] for r in rs), 3),
            "violations_per_run": round(st.mean(r["viol"] for r in rs), 3),
            "checks": {k: sum(r[k] for r in rs) for k in ("write_without_yes", "write_before_auth", "repeated_item_change", "failed_write")},
            "foresee_calls_per_run": round(st.mean(r["foresee_calls"] for r in rs), 2),
            "usd_per_run": round(st.mean(r["cost"] for r in rs), 4), "seconds_per_run": round(st.mean(r["seconds"] for r in rs), 1),
            "ended": dict(collections.Counter(r["ended"] for r in rs))}
    ms = sorted(m for t in by for m in by[t]["ekbasis"]["foresee_ms"])
    out["ekbasis_foresee_ms"] = {"calls": len(ms), "median": round(st.median(ms)) if ms else None, "p90": round(ms[int(.9 * (len(ms) - 1))]) if ms else None}
    out["contrasts"] = {f"{a}-{b}": {m: boot(by, m, a, b) for m in ("reward", "harmful_run", "unreq", "viol")}
                        for a, b in (("ekbasis", "none"), ("ekbasis", "placebo"), ("placebo", "none"))}
    out["ekbasis_answers_in_benchmark"] = ekbasis_accuracy([by[t]["ekbasis"] for t in by])
    d = out["contrasts"]["ekbasis-none"]["reward"]
    p = out["contrasts"]["ekbasis-placebo"]["reward"]
    out["bar_met"] = bool(d["diff"] >= 0.10 and d["ci95"][0] > 0 and p["ci95"][0] > 0)
    json.dump(out, open(os.path.join(HERE, "summary_tau.json"), "w"), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
