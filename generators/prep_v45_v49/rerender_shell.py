"""Re-renders the factory's shell rows in the layout of client 0.1.2's shell guard, frozen 2026-10-05 13:37 BRT
(PLAN_v45.md, Addendum 3). Per scenario side, the folder is rebuilt from struct.tree with the factory's builder, the
commands run again as nobody with the factory's executor (truth by execution, checked against every stored gold), and
the frozen guard reads that same folder before and after them, as nobody too (the user who runs the commands, so
read-only and unreadable files look as they do to the guard):
    view = S.inspect(cmds, cwd=box, shell="bash", salt=salt); floor = S.shell_prompt(view, notes=True)
- salt = "rxsh-<seed>": fixed per scenario, so the fingerprints are reproducible; the two flip-twin sides share it (their
  unchanged files keep the same fingerprints) and no two scenarios do;
- questions: S.SHELL_LOST and S.shell_fails(k); exists/kind keep the factory's wording; content and count rows are dropped
  (the guard's state has no file contents, and it lists only what the commands could touch);
- time: the guard's clock is pinned to the freeze instant NOW0 (2026-10-05T16:37:02Z: time.time() as the guard reads it,
  in _age only, inside its forked process; the package files are untouched) and the folder is built 30 minutes before
  NOW0, a tree age `a` becoming (a-1) days + 1 hour before that; so the guard writes "modified a-1 days ago" ("today" for
  a = 1) and the tree's archives have fixed bytes, whenever this runs. The map is increasing, so every order and every
  tie between mtimes (rsync's quick check) is kept. The commands run at the real time, later, so what they create or
  change reads "today" afterwards; an archive they make from such a file is the one thing whose fingerprint can differ
  between runs, and only in the ceiling;
- where/coreutils are read from this machine (the rig that executes the commands), as the guard reads them: the first
  inspect reads the versions, in the guard's own order, and the forked workers inherit them.
Refuses to run unless ekbasis/shell.py and prompts.py match FROZEN.sha256.
/usr/bin/python3 rerender_shell.py [--files train,val] [--limit N] [--workers W] [--check] [--det N]
  --check: render the first 20 scenario sides of the train file, print one row and the summary; writes nothing
  --det N: render the first N scenario sides of each file twice, compare byte for byte; report in rerender_det.json"""
import collections
import datetime
import hashlib
import json
import os
import re
import sys
import tempfile
import time
from multiprocessing import Pool

F = "/root/decis/mission/F"
C012 = "/root/decis/capability/client_012"
sys.path.insert(0, f"{F}/factory")
sys.path.insert(0, f"{C012}/ekbasis")
import shell as SH  # noqa: E402  (the factory family)
from ekbasis import shell as GS  # noqa: E402  (the frozen guard)

FILES = {"train": (f"{F}/data/train_shell.jsonl", f"{F}/data/train_shell_c012.jsonl"),
         "val": (f"{F}/data/val_shell.jsonl", f"{F}/data/val_shell_c012.jsonl")}
DROP = {"content", "count"}
NOW0 = int(datetime.datetime(2026, 10, 5, 16, 37, 2, tzinfo=datetime.timezone.utc).timestamp())  # C012's freeze
LEAD = 1800  # the folder is built 30 minutes before NOW0
Q_EXISTS = re.compile(r"^After these commands, does (.+) exist \(as a file, folder or link\)\?$")
Q_KIND = re.compile(r"^After these commands, what is (.+)\?$")


def days_age(a):
    return (max(a, 1) - 1) * 86400 + 3600


SH.age_s = days_age


def frozen():
    want = {}
    for l in open(f"{C012}/FROZEN.sha256"):
        if l.strip() and not l.startswith("#"):
            h, p = l.split()
            want[p] = h
    got = {}
    for p in ("ekbasis/ekbasis/shell.py", "ekbasis/ekbasis/prompts.py"):
        got[p] = hashlib.sha256(open(f"{C012}/{p}", "rb").read()).hexdigest()
        if got[p] != want.get(p):
            sys.exit(f"{p} does not match FROZEN.sha256 ({got[p]} vs {want.get(p)})")
    if os.path.realpath(GS.__file__) != os.path.realpath(f"{C012}/ekbasis/ekbasis/shell.py"):
        sys.exit(f"imported {GS.__file__}, not the frozen package")
    return got


def warm():
    """One inspect reads the versions (ls, bash) in the guard's own order; the rules text it gives every row."""
    os.makedirs("/tmp/rxF", exist_ok=True)
    d = tempfile.mkdtemp(prefix="warm", dir="/tmp/rxF")
    try:
        return GS.inspect(["ls"], cwd=d, shell="bash", salt="warm").rules
    finally:
        os.rmdir(d)


class Clock:
    """The time module as the guard sees it while rendering: time() pinned to NOW0, everything else the real module."""

    def time(self):
        return NOW0

    def __getattr__(self, k):
        return getattr(time, k)


def guard_view(box, cmds, salt):
    """The frozen guard's prompt (notes on) and state for box, read as nobody (uid/gid 65534) in a forked child."""
    r, w = os.pipe()
    pid = os.fork()
    if pid == 0:
        code = 0
        try:
            os.close(r)
            os.setgroups([])
            os.setgid(SH.NOBODY)
            os.setuid(SH.NOBODY)
            os.chdir("/")
            GS.time = Clock()
            v = GS.inspect(list(cmds), cwd=box, shell="bash", salt=salt)
            out = {"prompt": GS.shell_prompt(v, notes=True), "rules": v.rules, "state": v.state, "unread": v.unread,
                   "notes": len(GS.shell_notes(v))}
        except BaseException as e:  # noqa: BLE001
            out, code = {"error": f"{type(e).__name__}: {e}"[:300]}, 1
        with os.fdopen(w, "w") as f:
            f.write(json.dumps(out))
        os._exit(code)
    os.close(w)
    with os.fdopen(r) as f:
        data = f.read()
    os.waitpid(pid, 0)
    out = json.loads(data)
    if "error" in out:
        raise RuntimeError(out["error"])
    return out


def spec_of(r):
    """(factory question key, argument) of a row, as SH.golds takes it."""
    qt = r["qtype"]
    if qt == "lost":
        return ("lost", None)
    if qt == "fails":
        k = int(re.search(r"-fails(\d+)", r["id"]).group(1))
        return (f"fails{k}", k)
    return (qt, (Q_EXISTS if qt == "exists" else Q_KIND).match(r["question"]["instructions"]).group(1))


def question_of(r, spec):
    if spec[0] == "lost":
        return GS.SHELL_LOST
    if spec[0].startswith("fails"):
        return GS.shell_fails(spec[1])
    return r["question"]


def render_job(job):
    """One scenario side: execute it with the guard reading the folder before and after; its rows rebuilt."""
    key, salt, tree, cmds, codes, rows = job
    views = {}
    SH.BASE_T = NOW0 - LEAD
    try:
        res = SH.execute(tree, cmds, f"rr{os.getpid()}_{key}",
                         observe=lambda moment, box: views.__setitem__(moment, guard_view(box, cmds, salt)))
    except Exception as e:  # noqa: BLE001
        return {"key": key, "error": f"{type(e).__name__}: {e}"[:300]}
    if res is None or set(views) != {"before", "after"}:
        return {"key": key, "error": "execution or guard read failed"}
    what = "; ".join(f"command {k}: exit {c}" + (f" ({e})" if c and e else "")
                     for k, (c, e) in enumerate(zip(res["codes"], res["errs"]), 1))
    lost = bool(SH.pool(res["before"]) - SH.pool(res["after"]))
    what += f". File content lost for good: {'yes' if lost else 'no'}."
    ceiling = (f"{views['after']['rules']}\n\nState after the actions:\n{views['after']['state']}\n\n"
               f"This is the state after all the actions.\nWhat happened: {what}")
    out, mismatch = [], []
    for i, r in rows:
        spec = spec_of(r)
        g = SH.golds([(spec[0], spec[1], None)], res)[spec]
        if g != r["gold"]:
            mismatch.append([r["id"], r["gold"], g])
        r2 = dict(r)
        r2.update(floor=views["before"]["prompt"], ceiling=ceiling, question=question_of(r, spec), layout="c012", salt=salt)
        out.append((i, r2))
    return {"key": key, "rows": out, "mismatch": mismatch, "codes_same": res["codes"] == codes,
            "unread": bool(views["before"]["unread"]), "notes": views["before"]["notes"]}


def jobs_of(src, limit=None):
    rows = [json.loads(l) for l in open(src)]
    groups, order, dropped = {}, [], collections.Counter()
    for i, r in enumerate(rows):
        if r["qtype"] in DROP:
            dropped[r["qtype"]] += 1
            continue
        m = re.match(r"^(rxsh-\d+)-([ab])-", r["id"])
        key = f"{m.group(1)}-{m.group(2)}"
        if key not in groups:
            groups[key] = (m.group(1), r["struct"]["tree"], r["struct"]["cmds"], r["struct"]["codes"], [])
            order.append(key)
        g = groups[key]
        if g[1] != r["struct"]["tree"] or g[2] != r["struct"]["cmds"]:
            sys.exit(f"{r['id']}: rows of one scenario side disagree on struct")
        g[4].append((i, r))
    order = order[:limit] if limit else order
    return [(k,) + groups[k] for k in order], len(rows), dict(dropped)


def render(jobs, workers):
    with Pool(workers) as p:
        return list(p.imap(render_job, jobs, chunksize=4))


def leaks(r):
    """Tree contents (file lines, archive members) that show up in the floor or the ceiling but not in the commands."""
    tree, cmds = r["struct"]["tree"], " ".join(r["struct"]["cmds"])
    texts = {e["c"] for e in tree.values() if e["t"] == "f"} | \
            {m for e in tree.values() if e["t"] == "tgz" for m in e["members"].values()}
    texts = {t for t in texts if t and t not in cmds}
    return [t for t in texts if t in r["floor"]], [t for t in texts if t in r["ceiling"]]


def summarize(name, results, n_in, dropped, seconds, workers):
    bad = {res["key"].rsplit("-", 1)[0] for res in results if "error" in res or res["mismatch"]}
    rows = [r2 for _, r2 in sorted((i, r2) for res in results if "rows" in res and res["key"].rsplit("-", 1)[0] not in bad
                                   for i, r2 in res["rows"])]
    ok = [res for res in results if "rows" in res]
    fl_leak = sum(1 for r in rows if leaks(r)[0])
    ce_leak = sum(1 for r in rows if leaks(r)[1])
    by_q = collections.Counter(r["qtype"] for r in rows)
    yes = {q: round(100 * sum(1 for r in rows if r["qtype"] == q and r["gold"] is True) / max(1, by_q[q]), 1)
           for q in ("lost", "fails", "exists")}
    informative = round(100 * sum(1 for r in rows if r.get("face") is not None and r["face"] != r["gold"]) / max(1, len(rows)), 1)
    errs = [res for res in results if "error" in res]
    mism = [m for res in ok for m in res["mismatch"]]
    return rows, {
        "file": name, "rows_in": n_in, "dropped": dropped, "scenario_sides": len(results), "rows_out": len(rows),
        "rows_by_qtype": dict(by_q), "yes_pct": yes, "informative_pct": informative,
        "errors": len(errs), "error_examples": [e["error"] for e in errs[:3]],
        "gold_mismatches": len(mism), "mismatch_examples": mism[:5], "scenarios_dropped": sorted(bad)[:20],
        "n_scenarios_dropped": len(bad), "codes_differ": sum(1 for res in ok if not res["codes_same"]),
        "unread_sides_pct": round(100 * sum(1 for res in ok if res["unread"]) / max(1, len(ok)), 1),
        "sides_with_notes_pct": round(100 * sum(1 for res in ok if res["notes"]) / max(1, len(ok)), 1),
        "floor_content_leaks": fl_leak, "ceiling_content_leaks": ce_leak,
        "seconds": round(seconds, 1), "workers": workers}


def main():
    args = sys.argv
    hashes = frozen()
    rules = warm()
    workers = int(args[args.index("--workers") + 1]) if "--workers" in args else 16
    names = args[args.index("--files") + 1].split(",") if "--files" in args else ["train", "val"]
    limit = int(args[args.index("--limit") + 1]) if "--limit" in args else None
    head = {"frozen_sha256": hashes, "rules": rules, "salt": "rxsh-<seed> per scenario (twin sides share it)",
            "ages": "tree age a -> (a-1) days + 1 h before the build; build = now - 30 min", "dropped_qtypes": sorted(DROP)}
    if "--check" in args:
        jobs, n_in, dropped = jobs_of(FILES["train"][0], 20)
        t0 = time.time()
        rows, rep = summarize("train(check)", render(jobs, min(workers, 8)), n_in, dropped, time.time() - t0, workers)
        r = next(x for x in rows if x["qtype"] == "lost")
        print(r["floor"]); print("----- question:", r["question"]); print("----- ceiling:"); print(r["ceiling"][-900:])
        print(json.dumps({**head, **rep}, indent=1))
        return
    if "--det" in args:
        n = int(args[args.index("--det") + 1])
        rep = dict(head)
        for name in names:
            jobs, n_in, dropped = jobs_of(FILES[name][0], n)
            a, _ = summarize(name, render(jobs, workers), n_in, dropped, 0, workers)
            time.sleep(2)
            b, _ = summarize(name, render(jobs, workers), n_in, dropped, 0, workers)
            same = lambda x, y, k: json.dumps(x[k], sort_keys=True) == json.dumps(y[k], sort_keys=True)  # noqa: E731
            ids = [x["id"] for x in a] == [y["id"] for y in b]
            diff = {k: [x["id"] for x, y in zip(a, b) if not same(x, y, k)] for k in ("floor", "ceiling", "question", "gold")}
            rep[name] = {"scenario_sides": len(jobs), "rows": [len(a), len(b)], "same_ids_in_order": ids,
                         "rows_differing": {k: len(v) for k, v in diff.items()}, "examples": {k: v[:5] for k, v in diff.items() if v}}
            print(name, rep[name])
        json.dump(rep, open(f"{F}/v45/rerender_det.json", "w"), indent=1)
        return
    rep = dict(head)
    for name in names:
        src, dst = FILES[name]
        jobs, n_in, dropped = jobs_of(src, limit)
        t0 = time.time()
        rows, rep[name] = summarize(name, render(jobs, workers), n_in, dropped, time.time() - t0, workers)
        if not limit:
            with open(dst, "w") as f:
                for r in rows:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
            rep[name]["out"] = dst
            rep[name]["out_sha256"] = hashlib.sha256(open(dst, "rb").read()).hexdigest()
        print(json.dumps(rep[name]))
    if not limit:
        json.dump(rep, open(f"{F}/v45/rerender_shell.json", "w"), indent=1)


if __name__ == "__main__":
    main()
