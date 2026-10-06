"""Verify every task on the real app BEFORE freezing: seed a fresh world, run the scripted harm path, judge (must be harm);
seed another fresh world, run the scripted safe path, judge (must be success without harm). Controls: the safe path only.
Results go to tasks/verify/<task>.json; tasks that fail are dropped from the study (recorded, never silently).
    python3 tasks/verify_tasks.py [--app gitea|nextcloud|mail] [--only id1,id2]"""
import argparse
import json
import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "harness"))
import ra_tasks  # noqa: E402
from drive import Stage  # noqa: E402

OUT = os.path.join(HERE, "verify")
os.makedirs(OUT, exist_ok=True)
CTX = os.path.join(HERE, "..", "logs", "verify_ctx")
os.makedirs(CTX, exist_ok=True)


def run_path(task, which, rid):
    ctx = task["seed"](rid, CTX)
    p = os.path.join(CTX, f"run_{rid}.json")
    json.dump(ctx, open(p, "w"))
    err = None
    with Stage(p, mode="none", log=os.path.join(CTX, f"stage_{rid}.log")) as st:
        try:
            task[which](st, ctx)
            time.sleep(2)
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {str(e)[:600]}"
    res = ra_tasks.score(task, ctx)
    return {"rid": rid, "path": which, "error": err, **res}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app")
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    keep = set(a.only.split(",")) if a.only else None
    stamp = time.strftime("%H%M%S")
    for i, t in enumerate(ra_tasks.TASKS):
        if (a.app and t["app"] != a.app) or (keep and t["id"] not in keep):
            continue
        rec = {"id": t["id"], "kind": t["kind"], "checks": []}
        try:
            if t["harm_path"]:
                rec["checks"].append(run_path(t, "harm_path", f"vh{stamp}{i:02d}"))
            rec["checks"].append(run_path(t, "safe_path", f"vs{stamp}{i:02d}"))
        except Exception as e:  # noqa: BLE001
            rec["checks"].append({"error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()[-800:]})
        ok = True
        for c in rec["checks"]:
            if c.get("path") == "harm_path":
                ok &= bool(c.get("harm")) and not c.get("error")
            elif c.get("path") == "safe_path":
                ok &= bool(c.get("success")) and not c.get("harm") and not c.get("error")
            else:
                ok = False
        rec["verified"] = ok
        json.dump(rec, open(os.path.join(OUT, f"{t['id']}.json"), "w"), indent=1)
        print(f"{t['id']:18s} verified={ok} " + " | ".join(f"{c.get('path','?')}: harm={c.get('harm')} success={c.get('success')} {c.get('detail','')} {('ERR ' + c['error'][:160]) if c.get('error') else ''}" for c in rec["checks"]), flush=True)


if __name__ == "__main__":
    main()
