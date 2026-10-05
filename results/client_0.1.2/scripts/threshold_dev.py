"""Compare in code on fresh accumulation items (ACC_SEED; never the published items):
  A  the outcome asked once, with every action (as asking the model directly does);
  B  the released simulate, the outcome and the running quantity in the state, the outcome read from the model;
  T  simulate.threshold on that same simulation: the outcome decided in code from the carried quantity, by each kind's
     rule (it holds once the total reaches the limit for counters, lockouts, timers, trials and budgets: when="ever";
     a rate limit and a discount decide on the total before the last action: when="before_last").
python3 eval/threshold_dev.py -> results/threshold_dev.jsonl, results/threshold_dev_summary.json"""
from __future__ import annotations

import collections
import concurrent.futures as cf
import json
import os
import sys

from common import CAP, OUT, VENDOR, WORKERS, client, rate, read_jsonl, write_jsonl

os.environ.setdefault("ACC_SEED", "77012502")
sys.path.insert(0, os.path.join(VENDOR, "accumulation"))
import accum as A  # noqa: E402

from ekbasis import prompts as P  # noqa: E402
from ekbasis.simulate import threshold  # noqa: E402

LATCHING = ("counter", "lockout", "timer", "trial", "budget")


def decide(rec: dict, t) -> object:
    """The outcome the kind's rule gives for the carried quantity (as the capability map's analysis decided it)."""
    crit = list(rec["out_q"].get("criteria", {}))
    if rec["kind"] in LATCHING:
        return t.holds
    if rec["kind"] == "ratelimit":
        return crit[2] if t.holds else crit[1]
    return rec["discounted_price"] if t.holds else rec["full_price"]


def one(rec: dict, cl) -> dict:
    base = {k: rec[k] for k in ("id", "kind", "setting", "d", "L", "instance")}
    try:
        cl_a = cl.ask(P.world_state(rec["rules"], A.state_text(rec, rec["run_initial"], rec["out_initial"]), rec["actions"]),
                      {"outcome": rec["out_q"]})["outcome"]
        when, limit = ("ever", rec["theta_real"]) if rec["kind"] in LATCHING else \
            ("before_last", rec["theta"] if rec["kind"] == "ratelimit" else rec["theta_real"])
        t = threshold(cl, rec["rules"], {"outcome": rec["out_initial"], "run": rec["run_initial"]}, rec["actions"],
                      {"outcome": rec["out_q"], "run": rec["run_q"]},
                      lambda st: A.state_text(rec, st["run"], st["outcome"]), quantity="run", op=">=", limit=limit,
                      when=when)
    except Exception as e:  # noqa: BLE001
        return {**base, "error": str(e)}
    truth = rec["out_truth"]
    same = lambda v: str(v) == str(truth)  # noqa: E731
    return {**base, "truth": truth, "A": cl_a.value, "B": t.simulation.final["outcome"], "T": decide(rec, t),
            "A_right": same(cl_a.value), "B_right": same(t.simulation.final["outcome"]), "T_right": same(decide(rec, t)),
            "trace": t.trace, "run_truth": rec["run_truth"], "chain": t.confidence}


def summarize(rows: list) -> dict:
    ok = [r for r in rows if "truth" in r]
    out = {"items": len(rows), "errors": len(rows) - len(ok)}
    for c in ("A", "B", "T"):
        out[c] = rate(sum(r[f"{c}_right"] for r in ok), len(ok))
        bd = [r for r in ok if r["d"] in (-1, 0)]
        out[f"{c}_boundary_d-1_d0"] = rate(sum(r[f"{c}_right"] for r in bd), len(bd))
    inst = collections.defaultdict(dict)
    for r in ok:
        inst[r["instance"]][r["d"]] = r
    pairs = [(v[-1], v[0]) for v in inst.values() if -1 in v and 0 in v]
    for c in ("A", "B", "T"):
        out[f"{c}_pairs_both_right"] = rate(sum(a[f"{c}_right"] and b[f"{c}_right"] for a, b in pairs), len(pairs))
    out["by_kind"] = {k: {c: f"{sum(r[f'{c}_right'] for r in ok if r['kind'] == k)}/{sum(1 for r in ok if r['kind'] == k)}"
                          for c in ("A", "B", "T")} for k in sorted({r["kind"] for r in ok})}
    return out


def main():
    items = A.make_items()
    published = {json.dumps([r["rules"], r["actions"], r["state_full"]]) for r in read_jsonl(os.path.join(CAP, "accumulation", "items.jsonl"))}
    fresh = [r for r in items if json.dumps([r["rules"], r["actions"], r["state_full"]]) not in published]
    print(f"{len(fresh)} fresh items of {len(items)} (seed {os.environ['ACC_SEED']})", flush=True)
    cl = client()
    print("health:", cl.health(), flush=True)
    with cf.ThreadPoolExecutor(WORKERS) as ex:
        rows = list(ex.map(lambda r: one(r, cl), fresh))
    write_jsonl(os.path.join(OUT, "threshold_dev.jsonl"), rows)
    s = summarize(rows)
    json.dump(s, open(os.path.join(OUT, "threshold_dev_summary.json"), "w"), indent=1)
    print(json.dumps({k: (v["pct"] if isinstance(v, dict) and "pct" in v else v) for k, v in s.items() if k != "by_kind"}))


if __name__ == "__main__":
    main()
