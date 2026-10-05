"""The shell guard on real folders. Each scenario's folder is built for real in a throwaway place (shell_wild's own
builder), the guard reads it with a fixed fingerprint key per scenario and asks the served model; the truth comes from
running bash (stored with the scenario). Conditions: notes (the candidate as shipped) and no_notes (the same state
without the shell rules). Every prompt is checked for file contents: none may appear.
  python3 eval/shell_run.py dev [notes,no_notes]       shell_wild's 408 scenarios (design set)
  python3 eval/shell_run.py confirm [notes,no_notes]   results/shell_confirm_items.jsonl (after the freeze only)
-> results/shell_<set>_<condition>.jsonl"""
from __future__ import annotations

import concurrent.futures as cf
import os
import shutil
import sys
import tempfile
import time

from common import CAP, OUT, VENDOR, WORKERS, client, read_jsonl, require_frozen, write_jsonl

sys.path.insert(0, os.path.join(VENDOR, "shell_wild"))
import shell_wild as SW  # noqa: E402

from ekbasis import shell as S  # noqa: E402
from ekbasis.client import CannotJudge  # noqa: E402

SET = sys.argv[1] if len(sys.argv) > 1 else "dev"
CONDS = (sys.argv[2] if len(sys.argv) > 2 else "notes,no_notes").split(",")
if SET == "confirm":
    require_frozen()
ITEMS = os.path.join(CAP, "shell_wild", "items.jsonl") if SET == "dev" else os.path.join(OUT, "shell_confirm_items.jsonl")
TMP = tempfile.mkdtemp(prefix=f"c012_{SET}_")


def contents(state: dict) -> list:
    """Every line of content the folder holds (files and archive members): none may reach a prompt."""
    out = []
    for e in state.values():
        if e["t"] == "f" and e.get("c"):
            out += [x for x in e["c"].splitlines() if x.strip()]
        elif e["t"] == "a":
            out += [x for v in e["m"].values() for x in str(v).splitlines() if x.strip()]
    return out


def one(item: dict, cond: str, cl) -> dict:
    work = os.path.join(TMP, f"{cond}_{item['id'].replace('/', '_').replace('#', '_')}")
    try:
        SW.materialize(work, item["state"])
        err, v = None, None
        for attempt in range(4):
            try:
                t0 = time.time()
                v = S.check(item["cmds"], cwd=work, client=cl, salt=f"{SET}-{item['id']}", notes=(cond == "notes"))
                ms = round(1000 * (time.time() - t0))
                break
            except CannotJudge as e:  # the server: retried, then recorded
                err = str(e)
                time.sleep(3 * (attempt + 1))
        if v is None:
            return {"id": item["id"], "cond": cond, "error": err}
        leaks = [c for c in contents(item["state"]) if c in v.state]
        return {"id": item["id"], "cond": cond, "family": item.get("family"), "form": item.get("form"),
                "variant": item.get("variant"), "canonical": item.get("canonical"), "note": item.get("note"),
                "cmds": item["cmds"], "truth": item["truth"], "dropped": item.get("dropped", []),
                "p_lost": v.p_lost, "p_fail": v.p_fail, "unread": v.unread, "cannot_judge": v.cannot_judge,
                "notes": [k for k, n in S.NOTES if n in v.notes], "leaks": leaks, "prompt": v.state, "ms": ms}
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main():
    items = read_jsonl(ITEMS)
    cl = client()
    print("health:", cl.health(), "|", len(items), "scenarios", flush=True)
    for cond in CONDS:
        t0 = time.time()
        with cf.ThreadPoolExecutor(WORKERS) as ex:
            rows = list(ex.map(lambda it: one(it, cond, cl), items))
        write_jsonl(os.path.join(OUT, f"shell_{SET}_{cond}.jsonl"), rows)
        bad = sum(1 for r in rows if r.get("error"))
        leaks = sum(len(r.get("leaks", [])) for r in rows)
        print(f"{cond}: {len(rows)} scenarios in {time.time() - t0:.0f} s, {bad} errors, {leaks} content leaks", flush=True)
    shutil.rmtree(TMP, ignore_errors=True)


if __name__ == "__main__":
    main()
