"""client_next runner (SPEC.md): for each item, the setup runs once, then every configuration reads the SAME repository
(read-only) and asks the model, then the commands run and the truth is git_wild's (snapshots before/after).
  python3 cn_run.py <items module .py> <out.jsonl> [--configs C0,C1,C2,C3] [--only T1,T2] [--reps N] [--workers 24] [--dry]
C0 = client 0.1.0 (the `ekbasis` package on PYTHONPATH, byte-identical to the published one); C1 = candidate, facts;
C2 = candidate, facts + notes; C3 = candidate, notes only; C = the frozen candidate with its defaults. The candidate is the
package `ekbasis_next` in ./pkg. --dry: setup + execution + truth, no model call."""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import importlib.util
import json
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "pkg"))  # pkg/ekbasis_next: a copy of the candidate client
API = os.environ.get("EKBASIS_URL", "http://127.0.0.1:8542")
CONFIGS = {"C0": None, "C1": {"facts": True, "notes": False}, "C2": {"facts": True, "notes": True},
           "C3": {"facts": False, "notes": True}, "C": {},
           # dev pass 2: where the notes go
           "C2r": {"facts": True, "notes": True, "notes_at": "rules"}, "C2s": {"facts": True, "notes": True, "notes_at": "state"},
           "C2c": {"facts": True, "notes": True, "notes_at": "commands"}, "C3s": {"facts": False, "notes": True, "notes_at": "state"}}


def load_items_module(path):
    spec = importlib.util.spec_from_file_location("items_mod", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["items_mod"] = mod
    spec.loader.exec_module(mod)
    return mod


def run_item(W, item, configs, clients):
    rec = {k: item[k] for k in ("id", "type", "variant", "rep", "commands", "hidden", "forms", "seen")}
    if shutil.disk_usage(HERE).free < 300e6:
        rec["error"] = "disk almost full: not run"
        return rec
    box = os.path.join(W.BOXES, item["id"])
    shutil.rmtree(box, ignore_errors=True)
    work = os.path.join(box, "work")
    os.makedirs(work)
    try:
        for i, s in enumerate(item["setup"]):
            when = f"{W.SETUP_T0 + 60 * i} +0000"
            rc, out, to = W.sh(s, work, env={"GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when})
            if rc != 0 or to:
                rec["error"] = f"setup failed: {s} -> {out[-300:]}".replace(box, "<box>")
                return rec
        rec["model"] = {}
        for name in configs:
            G, client = clients[name]
            t0 = time.time()
            kw = CONFIGS[name] or {}
            v = G.check(item["commands"], repo=work, client=client, **kw)
            rec["model"][name] = {"p_lost": v.p_lost, "p_fail": v.p_fail, "p_in_progress": v.p_in_progress, "branch": v.branch,
                                  "risky": v.risky, "seconds": round(time.time() - t0, 2), "state": v.state}
        before, rb = W.snapshot(box, with_adds=True), W.remote_snapshot(box, with_adds=True)
        codes, outs, timed_out = [], [], False
        for c in item["commands"]:
            rc, out, to = W.sh(c, work)
            codes.append(rc)
            outs.append(out[-300:].replace(box, "<box>"))
            timed_out |= to
        after, ra = W.snapshot(box), W.remote_snapshot(box)
        rec["truth"] = W.truth(before, after, rb, ra, codes, box)
        rec["outputs"] = outs
        if timed_out:
            rec["error"] = "a command timed out"
    except Exception as e:  # noqa: BLE001 - recorded, the item is dropped
        rec["error"] = f"{type(e).__name__}: {e}".replace(box, "<box>")
    finally:
        shutil.rmtree(box, ignore_errors=True)
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("items_module")
    ap.add_argument("out")
    ap.add_argument("--configs", default="C0,C1,C2,C3")
    ap.add_argument("--only", default=None)
    ap.add_argument("--reps", type=int, default=None)
    ap.add_argument("--workers", type=int, default=24)
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    W = load_items_module(os.path.abspath(a.items_module))
    items = W.make_items(a.reps, set(a.only.split(",")) if a.only else None)
    W.prepare_home()
    configs = [] if a.dry else a.configs.split(",")
    clients = {}
    if configs:
        import ekbasis.git as G0
        import ekbasis_next.git as Gn
        from ekbasis.client import Ekbasis
        assert not hasattr(G0, "inspect"), "C0 must be client 0.1.0"
        for name in configs:
            clients[name] = (G0 if name == "C0" else Gn, Ekbasis(url=API, timeout=300))
        print("server:", clients[configs[0]][1].health(), flush=True)
    with open(os.path.splitext(a.out)[0] + "_items.jsonl", "w") as f:
        for it in items:
            f.write(json.dumps(it) + "\n")
    t0, n, errs = time.time(), 0, 0
    with open(a.out, "w") as f, cf.ThreadPoolExecutor(a.workers) as ex:
        for fut in cf.as_completed([ex.submit(run_item, W, it, configs, clients) for it in items]):
            rec = fut.result()
            f.write(json.dumps(rec) + "\n")
            f.flush()
            n += 1
            errs += "error" in rec
            if n % 50 == 0 or n == len(items):
                print(f"{n}/{len(items)} done, {errs} errors, {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
