"""Command line.

  ekbasis git-check [--repo DIR] [--fetch] [--json] [--lost-threshold P] -- "git checkout feature" "git stash pop"
      What the commands will do before they run. When they are risky, also the safer route: the alternative with the
      same intent that Ekbasis checked and found safe (ekbasis.safer), or "none"; --no-safer (or EKBASIS_SAFER=0) skips it.
  ekbasis shell-check [--cwd DIR] [--json] [--lost-threshold P] [--shell bash|zsh] -- "rm -r build/" "sort f > f"
      Prototype: what shell command lines will do to the files of a folder before they run (each argument is one line).
      --show-state prints the exact text the model read.
  Exit codes of both checks: 0 no risk found; 2 risky (may lose work or file content); 3 cannot foresee (the server
  could not be reached or did not answer in time, the repository or folder could not be read, or the line has parts
  the guard cannot evaluate): treat 3 as risky; 1 a usage error. The checks fail closed: --fail-open turns "cannot
  foresee" into 0, with a warning on stderr.
  ekbasis preflight [--cwd DIR] [--json] [--no-rows] -- "sqlite3 app.db < migrations/0012.sql"
      Before a multi-step change runs (a sqlite3 run of several statements, a shell script, a chain of commands): which
      step fails first on the current state, and whether the failure would leave the change half applied. Exit codes:
      0 nothing found (or not a multi-step change, or cannot judge); 2 a failure would leave the change half applied;
      3 cannot foresee, with --fail-closed. It runs the plan on a copy when it can (local files and SQLite; shell steps
      only inside the macOS sandbox, SQL where the sqlite3 tool is installed; --no-copy asks the model instead). --sql
      DB FILE checks a SQL file as `sqlite3 DB < FILE` would run it; --show-state prints what the model read.
  ekbasis migrate-check [--base REF] [--head REF] [--glob G] [--pg-url URL] [--stats-url URL] [--setup-sql PATH] [--autocommit]
                        [--policy rule|model] [--json] [FILE ...]
      Before a pull request is merged: will its new PostgreSQL migrations lose data or fail? The schema is built by
      applying the base's migrations to a scratch database (EKBASIS_PG_URL); optional row counts and NULL fractions come
      from a read-only replica's planner statistics (EKBASIS_DB_STATS_URL; aggregates only, never values). A file runs
      as one transaction, as Prisma, Diesel and golang-migrate run it; --autocommit for psql -f semantics. Exit codes:
      0 no risk found; 2 risky; 3 cannot foresee (treat as risky; --fail-open turns it into 0). --policy rule (default):
      a rule written from the PostgreSQL documentation decides, and the model only asks for a review (exit 0);
      --policy model: the model decides (0.1.21). See docs/MIGRATION_GUARD.md. --bundle FILE checks a framework bundle
      (below) instead of SQL files.
  ekbasis migrate-gen --framework django|alembic --base REF [--image IMAGE] [--setup CMD] [--workdir DIR]
                      [--env K=V ...] [--migrate CMD] [--command CMD] [-o bundle.json]
      Django and Alembic keep migrations as code: render the new ones as SQL with the framework itself, inside a
      container with no network and no secrets (needs docker), and write a bundle for migrate-check --bundle. Python
      that is not SQL (RunPython, no offline SQL) is listed for review by hand (--on-code warn, default) or fails
      closed (--on-code block).
  ekbasis predict --rules TEXT --state TEXT --action A [--action B ...] --question TEXT [--options a,b,c] [--recap]
      One typed question about the outcome (yes/no when --options is not given). --recap repeats the rules right before
      the question; --recap-rule TEXT (repeatable) repeats only the rules you name.
  ekbasis health
  ekbasis mcp
      The MCP server (stdio), as `ekbasis-mcp`: needs the extra, pip install "ekbasis[mcp]" (Python >= 3.10).
Server: EKBASIS_URL (default http://127.0.0.1:8000) or --url; --timeout SECONDS for each request (default 120).
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from . import git as G
from . import migrations as M
from . import preflight as PF
from . import prompts as P
from . import recover as R
from . import safer as SF
from . import shell as S
from .client import VERDICTS, CannotJudge, Ekbasis, EkbasisError, FeedbackRejected

OK, ERROR, RISKY, CANNOT_JUDGE = 0, 1, 2, 3
CANNOT_FORESEE = CANNOT_JUDGE  # 0.1.8 wording; same exit code
FEEDBACK_REJECTED = 4  # `ekbasis feedback` only: the server refused it (unknown id, already sent, rate limit, no key)


def _cannot_judge(a, why: str) -> int:
    if a.fail_open:
        print(f"ekbasis: cannot foresee ({why}); --fail-open: not treated as risky", file=sys.stderr)
        return OK
    if a.json:
        print(json.dumps({"risky": True, "judged": False, "cannot_judge": why, "cannot_foresee": why}))
    else:
        print(f"Ekbasis: CANNOT FORESEE  ({why})\n  treat it as risky: run it only after checking it yourself")
    return CANNOT_JUDGE


def _text_arg(v: str) -> str:
    """A text argument, or the contents of @FILE."""
    if v.startswith("@"):
        with open(v[1:], encoding="utf-8") as f:
            return f.read().strip()
    return v


def _harm_questions(presets, asks):
    harm = {}
    if presets or not asks:
        harm.update(P.harms(*(presets or ())))
    for i, q in enumerate(asks or (), 1):
        harm[f"ask{i}"] = P.yes_no(q)
    return harm


def _plan_check(a, client) -> int:
    """plan-check: exit 0 = every step forecast harmless with confidence (run them all); 2 = run the first N (maybe 0),
    then look at the real state before step N+1 (flagged or uncertain); 3 = cannot foresee."""
    if a.cases:
        return _plan_cases(a, client)
    from .plan import check_plan
    actions = [l.strip() for l in open(a.steps_file, encoding="utf-8") if l.strip()] if a.steps_file else list(a.actions)
    if not actions or a.state is None:
        print("ekbasis plan-check: give --state and the actions (as arguments or with --steps-file)", file=sys.stderr)
        return ERROR
    harm = _harm_questions(a.harm, a.ask)
    if any(k in P.HARMS or k in P.MONITOR for k in harm) and not a.request:
        print("ekbasis plan-check: the preset harm questions ask about what the user's request does not ask for; "
              "pass --request (or use --ask with your own questions)", file=sys.stderr)
        return ERROR
    try:
        pc = check_plan(client, _text_arg(a.rules), _text_arg(a.state), actions, harm, look_below=a.look_below,
                        parallel=a.parallel, request=a.request)
    except CannotJudge as e:
        return _cannot_judge(a, str(e))
    if a.json:
        print(json.dumps({"ok": pc.ok, "safe": pc.safe, "reason": pc.reason, "step": pc.step, "flags": pc.flags,
                          "prefixes": pc.prefixes, "requests": pc.requests}))
    elif pc.ok:
        print(f"Ekbasis: OK  all {len(actions)} steps forecast harmless with confidence")
    else:
        at = next((x for x in pc.prefixes if x["step"] == pc.step), None)
        labels = {**P.HARM_LABELS, **{f"ask{i}": q for i, q in enumerate(a.ask or (), 1)}}
        print(f"Ekbasis: STOP BEFORE STEP {pc.step}  {actions[pc.step - 1]}")
        if at:
            ranked = sorted(at["p_yes"].items(), key=lambda kv: -kv[1])
            if pc.reason == "flagged":
                print("  at stake:")
                for k, p in ranked:
                    if k in pc.flags:
                        print(f"    {p:4.0%}  {labels.get(k, k)}")
            else:
                k, p = ranked[0]
                print(f"  unsure (confidence {at['confidence']:.2f}); closest to harm: {labels.get(k, k)} {p:.0%}")
        first = "step 1" if pc.safe == 1 else f"steps 1-{pc.safe}"
        print(f"  run {first} now, then look at the real state and check the rest" if pc.safe else
              "  look at the real state before running anything, then check again")
    return OK if pc.ok else RISKY


def _case_expect(c):
    """A case's expectation: ("ok", None), ("stop", None) = stop anywhere, ("stop", N) = stop at step N or before."""
    e = c.get("expect")
    if e == "ok":
        return "ok", None
    if e == "stop":
        return "stop", None
    if isinstance(e, dict) and isinstance(e.get("stop_by"), int) and e["stop_by"] >= 1:
        return "stop", e["stop_by"]
    raise ValueError('"expect" must be "ok", "stop" or {"stop_by": STEP}')


def _case_outcome(pc) -> dict:
    """What the check decided, with the number that decided it: the highest harm probability at the stopping step (or
    the confidence there when it was only unsure), or, when the plan passed, the highest harm probability seen."""
    if pc.ok:
        top = max((max(x["p_yes"].values()) for x in pc.prefixes), default=0.0)
        return {"outcome": "ok", "step": None, "why": None, "p": round(top, 3)}
    at = next((x for x in pc.prefixes if x["step"] == pc.step), None)
    if pc.reason == "flagged" and at:
        why, p = ", ".join(pc.flags), max(at["p_yes"].values())
    else:
        why, p = "unsure", (at["confidence"] if at else 0.0)
    return {"outcome": "stop", "step": pc.step, "why": why, "p": round(p, 3)}


def _plan_cases(a, client) -> int:
    """plan-check --cases FILE: run known cases (past incidents, plans that must pass) against the rules, and report
    which still come out as expected. Exit 0 = all as expected; 2 = at least one is not; 3 = some could not be judged
    (and none failed); 1 = a malformed case file."""
    from .plan import check_plan
    base = os.path.dirname(os.path.abspath(a.cases))

    def text(v, what, name):   # a case's own text: @FILE is next to the case file
        if not isinstance(v, str):
            raise ValueError(f"case {name!r}: {what} must be text or @FILE")
        if v.startswith("@") and not os.path.isabs(v[1:]):
            v = "@" + os.path.join(base, v[1:])
        return _text_arg(v)

    cases = []
    try:
        with open(a.cases, encoding="utf-8") as f:
            for n, line in enumerate(f, 1):
                if not line.strip() or line.lstrip().startswith("#"):
                    continue
                c = json.loads(line)
                name = str(c.get("name") or f"line {n}")
                acts = c.get("actions")
                if not isinstance(acts, list) or not acts or not all(isinstance(x, str) and x.strip() for x in acts):
                    raise ValueError(f"case {name!r}: \"actions\" must be a list of action strings")
                if not c.get("state") and a.state is None:
                    raise ValueError(f"case {name!r}: no \"state\" (and no --state)")
                try:
                    kind, by = _case_expect(c)
                except ValueError as e:
                    raise ValueError(f"case {name!r}: {e}") from None
                if by and by > len(acts):
                    raise ValueError(f"case {name!r}: stop_by {by} is past the last action")
                request = c.get("request", a.request)
                harm = _harm_questions(c.get("harm", a.harm), c.get("ask", a.ask))
                if any(k in P.HARMS or k in P.MONITOR for k in harm) and not request:
                    raise ValueError(f"case {name!r}: the preset harm questions need a \"request\" (or \"ask\")")
                cases.append({"name": name,
                              "rules": text(c["rules"], "rules", name) if "rules" in c else _text_arg(a.rules),
                              "state": text(c["state"], "state", name) if c.get("state") else _text_arg(a.state),
                              "request": request,
                              "actions": acts, "harm": harm, "kind": kind, "by": by})
    except (OSError, ValueError) as e:   # json.JSONDecodeError is a ValueError
        print(f"ekbasis plan-check --cases: {e}", file=sys.stderr)
        return ERROR
    if not cases:
        print("ekbasis plan-check --cases: no cases in the file", file=sys.stderr)
        return ERROR

    before = {}
    if a.compare and os.path.exists(a.compare):
        try:
            with open(a.compare, encoding="utf-8") as f:
                before = json.load(f).get("cases", {})
        except (OSError, ValueError):
            before = {}

    results, requests = [], 0
    for c in cases:
        try:
            pc = check_plan(client, c["rules"], c["state"], c["actions"], c["harm"], look_below=a.look_below,
                            parallel=a.parallel, request=c["request"])
        except CannotJudge as e:
            results.append({**c, "got": {"outcome": "cannot", "step": None, "why": str(e), "p": None}, "status": "cannot"})
            continue
        requests += pc.requests
        got = _case_outcome(pc)
        if c["kind"] == "ok":
            status = "pass" if got["outcome"] == "ok" else "false_alarm"
        elif got["outcome"] == "ok":
            status = "miss"
        else:
            status = "late" if c["by"] and got["step"] > c["by"] else "pass"
        results.append({**c, "got": got, "status": status})

    def said(g):
        if g["outcome"] == "cannot":
            return "cannot foresee"
        if g["outcome"] == "ok":
            return f"ok (highest harm p {g['p']:.2f})"
        return f"stop at {g['step']}: {g['why']} ({'confidence' if g['why'] == 'unsure' else 'p'} {g['p']:.2f})"

    def wanted(r):
        return "ok" if r["kind"] == "ok" else f"stop by {r['by']}" if r["by"] else "stop"

    label = {"pass": "PASS", "miss": "MISS", "late": "LATE", "false_alarm": "FALSE ALARM", "cannot": "CANNOT"}
    def decision(g):   # what a run decided: pass, or stop at a step because of a harm or because it was unsure
        return g.get("outcome"), g.get("step"), g.get("why") == "unsure"

    changed = [r for r in results if r["name"] in before and decision(before[r["name"]]) != decision(r["got"])]
    stops = [r for r in results if r["kind"] == "stop"]
    oks = [r for r in results if r["kind"] == "ok"]
    caught = sum(r["status"] == "pass" for r in stops)
    clear = sum(r["status"] == "pass" for r in oks)
    if a.json:
        print(json.dumps({"cases": [{"name": r["name"], "expect": wanted(r), "status": r["status"], **r["got"],
                                     "before": before.get(r["name"])} for r in results],
                          "stops_caught": [caught, len(stops)], "oks_clear": [clear, len(oks)],
                          "changed": [r["name"] for r in changed], "requests": requests}))
    else:
        width = max(len(r["name"]) for r in results)
        for r in results:
            line = f"{label[r['status']]:<11} {r['name']:<{width}}  {said(r['got'])}"
            if r["status"] != "pass":
                line += f"  (expected {wanted(r)})"
            if r in changed:
                line += f"  [was: {said(before[r['name']])}]"
            print(line)
        print(f"\nplans that must stop: {caught}/{len(stops)} stopped in time · plans that must pass: "
              f"{clear}/{len(oks)} passed · {requests} requests"
              + (f" · {len(changed)} changed since the last run" if before else ""))
    if a.compare:
        with open(a.compare, "w", encoding="utf-8") as f:
            json.dump({"cases": {r["name"]: r["got"] for r in results}}, f, indent=1)
    if any(r["status"] in ("miss", "late", "false_alarm") for r in results):
        return RISKY
    return CANNOT_JUDGE if any(r["status"] == "cannot" for r in results) else OK


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ekbasis", description="Ekbasis: what happens if I do this? (typed, calibrated, one pass)")
    ap.add_argument("--url", default=None, help="server (default: EKBASIS_URL or http://127.0.0.1:8000)")
    ap.add_argument("--timeout", type=float, default=120.0, help="seconds to wait for each answer (default 120)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("git-check", help="check git commands before running them")
    g.add_argument("--copy", action="store_true", help="0.1.33: find which commands fail by running them on a copy of "
                   "the repository (local commands only; the real repository is not touched; also EKBASIS_GIT_COPY=1)")
    g.add_argument("--repo", default=".")
    g.add_argument("--fetch", action="store_true", help="git fetch first, so the state shows the real remote")
    g.add_argument("--json", action="store_true")
    g.add_argument("--lost-threshold", type=float, default=0.2)
    g.add_argument("--fail-threshold", type=float, default=0.5)
    g.add_argument("--fail-open", action="store_true", help="exit 0 (with a warning) when it cannot foresee")
    g.add_argument("--no-safer", action="store_true", help="when risky, do not look for a safer route (one round trip)")
    g.add_argument("--request", default=None, help="experimental (0.1.23): what the user asked for, in their "
                   "words; the loss question leaves it out")
    g.add_argument("commands", nargs="+", help='each command as one argument, e.g. "git checkout main"')
    s = sub.add_parser("shell-check", help="check shell command lines before running them (prototype)")
    s.add_argument("--cwd", default=".", help="the folder the commands would run in")
    s.add_argument("--json", action="store_true")
    s.add_argument("--lost-threshold", type=float, default=0.2)
    s.add_argument("--fail-threshold", type=float, default=0.5)
    s.add_argument("--shell", choices=["bash", "zsh"], default=None, help="default: from $SHELL, else bash")
    s.add_argument("--no-notes", action="store_true", help="leave out the shell rules (for comparisons)")
    s.add_argument("--show-state", action="store_true", help="print the exact text the model read")
    s.add_argument("--fail-open", action="store_true", help="exit 0 (with a warning) when it cannot foresee")
    s.add_argument("--request", default=None, help="experimental (0.1.23): what the user asked for, in their words")
    s.add_argument("--no-shortcuts", action="store_true", help="ask the model even when everything the lines could "
                   "change is in git or ignored and rebuildable (the hook's shortcut; on by default since 0.1.23)")
    s.add_argument("commands", nargs="+", help='each command line as one argument, e.g. "rm -r build/"')
    f = sub.add_parser("preflight", help="check a multi-step change (migration, script, chain) before it runs")
    f.add_argument("--cwd", default=".", help="the folder the line would run in")
    f.add_argument("--json", action="store_true")
    f.add_argument("--fail-threshold", type=float, default=PF.FAIL_THRESHOLD)
    f.add_argument("--no-rows", action="store_true", help="SQL: send the schema, counts and facts, not the rows")
    f.add_argument("--sql", nargs=2, metavar=("DB", "FILE"), help="check FILE as `sqlite3 DB < FILE` would run it")
    f.add_argument("--show-state", action="store_true", help="print the exact text the model read")
    f.add_argument("--fail-closed", action="store_true", help="treat \"cannot foresee\" as risky (exit 3)")
    f.add_argument("--no-copy", action="store_true", help="never run the plan on a copy; ask the model")
    f.add_argument("line", nargs="*", help='the command line, e.g. "bash scripts/migrate.sh"')
    m = sub.add_parser("migrate-check", help="check new PostgreSQL migrations before a merge (data loss, failure)")
    m.add_argument("--repo", default=".")
    m.add_argument("--base", default=None, help="the base ref (e.g. origin/main): check the migrations added since")
    m.add_argument("--head", default="HEAD")
    m.add_argument("--glob", action="append", default=None,
                   help="which files are migrations (fnmatch on the path, repeatable; default: Prisma, Diesel, "
                        "*.up.sql and *migrations/*.sql)")
    m.add_argument("--pg-url", default=None, help="scratch PostgreSQL server (default: EKBASIS_PG_URL)")
    m.add_argument("--stats-url", default=None, help="read-only replica for planner statistics (default: "
                                                      "EKBASIS_DB_STATS_URL)")
    m.add_argument("--autocommit", action="store_true", help="statements commit one by one (psql -f), not one "
                                                             "transaction per file")
    m.add_argument("--setup-sql", default=None, metavar="PATH",
                   help="SQL run by the scratch server's admin connection before the base's migrations (a schema, role "
                        "or extension the platform creates outside the migrations; :guard_role names the role the "
                        "migrations run as). With --base it is read from the BASE ref, never from the pull request")
    m.add_argument("--lost-threshold", type=float, default=M.LOST_THRESHOLD)
    m.add_argument("--fail-threshold", type=float, default=M.FAIL_THRESHOLD)
    m.add_argument("--json", action="store_true")
    m.add_argument("--show-state", action="store_true", help="print the exact text the model read")
    m.add_argument("--fail-open", action="store_true", help="exit 0 (with a warning) when it cannot foresee")
    m.add_argument("--no-cache", action="store_true", help="always ask the model (default: reuse the answer for the same "
                                                           "migration, schema, client version and rules, 30 days)")
    m.add_argument("--policy", choices=list(M.POLICIES), default=M.DEFAULT_POLICY,
                   help="rule (default): the rule written from the PostgreSQL documentation decides whether the check "
                        "fails, and the model's second opinion can only ask for a review; model: the model decides "
                        "(the 0.1.21 behavior)")
    m.add_argument("--bundle", default=None, help="a framework bundle from migrate-gen (instead of files or --base)")
    m.add_argument("--on-code", choices=list(M.ON_CODE), default="warn",
                   help="bundle only: code that is not SQL (RunPython, no offline SQL) is listed for review by hand "
                        "and does not fail the check (warn, default), or fails closed as cannot foresee (block)")
    m.add_argument("files", nargs="*", help="migration files to check (instead of --base)")
    gg = sub.add_parser("migrate-gen", help="render Django/Alembic/Rails migrations as SQL in an isolated container")
    gg.add_argument("--framework", required=True, choices=["django", "alembic", "rails"])
    gg.add_argument("--repo", default=".")
    gg.add_argument("--base", default=None, help="the base ref; the migrations added since are rendered")
    gg.add_argument("--head", default="HEAD")
    gg.add_argument("--image", default=None, help="the generator image (default python:3.12-slim, ruby:3.3 for rails)")
    gg.add_argument("--setup", default=None, help="shell command run in the head tree, WITH network, before the "
                                                  "network is cut (e.g. pip install -r requirements.txt)")
    gg.add_argument("--workdir", default=".", help="where manage.py, alembic.ini or the Rails app is, in the repo")
    gg.add_argument("--env", action="append", default=[], help="K=V for the generator (${EKBASIS_DB_URL} is replaced "
                                                                "by the scratch database's URL); never put secrets here")
    gg.add_argument("--migrate", default=None, help="the command that migrates the base (default per framework)")
    gg.add_argument("--command", default=None, help="Alembic: alembic (default) or 'flask db'")
    gg.add_argument("--redis", choices=["auto", "on", "off"], default="auto",
                    help="a throwaway Redis on the generator's internal network (auto: when the Gemfile or Python "
                         "requirements depend on redis, sidekiq, celery...)")
    gg.add_argument("-o", "--output", default="-", help="the bundle file (default: stdout)")
    gg.add_argument("files", nargs="*", help="migration files to render (instead of --base)")
    pc = sub.add_parser("plan-check", help="check a list of actions before an agent runs them (look when unsure: "
                                            "run the safe prefix, look before the first flagged or uncertain step)")
    pc.add_argument("--rules", required=True, help="how this system works: text, or @FILE")
    pc.add_argument("--state", default=None, help="how things stand now: text, or @FILE")
    pc.add_argument("--request", default=None, help="what the user asked for, in their words (the --harm presets ask "
                                                    "about harm this request does not ask for)")
    pc.add_argument("--harm", action="append", default=None,
                    help=f"a preset harm question, repeatable ({', '.join(P.HARMS)}; default: those four; also, for watching an "
                         f"agent that may act against the user (0.1.39): {', '.join(P.MONITOR)})")
    pc.add_argument("--ask", action="append", default=None, metavar="QUESTION",
                    help="your own yes/no harm question (yes = the harm), repeatable; replaces the presets unless "
                         "--harm is also given")
    pc.add_argument("--look-below", type=float, default=0.9, help="confidence under which a step needs a look (0.9)")
    pc.add_argument("--parallel", type=int, default=4)
    pc.add_argument("--json", action="store_true")
    pc.add_argument("--fail-open", action="store_true", help="exit 0 (with a warning) when it cannot foresee")
    pc.add_argument("--steps-file", default=None, help="one action per line (instead of arguments)")
    pc.add_argument("--cases", default=None, metavar="FILE",
                    help="0.1.38: test the rules on known cases instead of checking a plan: JSON lines, each with "
                         "\"name\", \"state\", \"request\", \"actions\" and \"expect\" (\"ok\", \"stop\" or "
                         "{\"stop_by\": STEP}); exit 0 when every case comes out as expected, 2 when not")
    pc.add_argument("--compare", default=None, metavar="FILE",
                    help="with --cases: show what changed since the results saved in FILE, then save these there")
    pc.add_argument("actions", nargs="*", help='each action as one argument, in order, e.g. "kubectl delete pvc data-0"')
    p = sub.add_parser("predict", help="one question about the outcome of some actions")
    p.add_argument("--rules", required=True)
    p.add_argument("--state", required=True)
    p.add_argument("--action", action="append", required=True)
    p.add_argument("--question", required=True)
    p.add_argument("--options", default=None, help="comma-separated answers (default: yes/no)")
    p.add_argument("--recap", action="store_true", help="repeat the rules right before the question")
    p.add_argument("--recap-rule", action="append", default=None, help="repeat only this rule (repeatable)")
    sub.add_parser("health")
    sub.add_parser("mcp", help='run the MCP server on stdio (same as ekbasis-mcp; needs "ekbasis[mcp]")')
    fb = sub.add_parser("feedback", help="tell the hosted API how an answer turned out (free; helps measure the model)")
    fb.add_argument("request_id", nargs="?", default=None, help="the X-Ekbasis-Request-Id of the answer (req_...)")
    fb.add_argument("--last", action="store_true", help="the last answer this machine received")
    v = fb.add_mutually_exclusive_group(required=True)
    v.add_argument("--correct", dest="verdict", action="store_const", const="correct")
    v.add_argument("--wrong", dest="verdict", action="store_const", const="wrong")
    v.add_argument("--prevented-harm", dest="verdict", action="store_const", const="prevented_harm",
                   help="it warned and that stopped a real mistake")
    v.add_argument("--false-alarm", dest="verdict", action="store_const", const="false_alarm",
                   help="it warned about something that was safe")
    fb.add_argument("--note", default=None, help="optional, up to 500 characters (never include secrets)")
    a = ap.parse_args(argv)
    if a.cmd == "mcp":
        from . import mcp_server
        if a.url:
            os.environ["EKBASIS_URL"] = a.url
        mcp_server.main()
        return OK
    client = Ekbasis(url=a.url, timeout=a.timeout)
    if a.cmd != "feedback" and not getattr(client, "surface", None):
        client.surface = a.cmd  # X-Ekbasis-Surface: which command made the call (metadata only)
    if a.cmd == "feedback":
        if bool(a.request_id) == bool(a.last):
            print("ekbasis feedback: pass a request id or --last", file=sys.stderr)
            return ERROR
        try:
            r = client.feedback(a.verdict, request_id=a.request_id, note=a.note)
            print(f"Ekbasis: feedback recorded ({r.get('verdict', a.verdict)} on {r.get('request_id', a.request_id)})")
            return OK
        except FeedbackRejected as e:
            print(f"ekbasis feedback: rejected, {e}", file=sys.stderr)
            return FEEDBACK_REJECTED
        except CannotJudge as e:
            print(f"ekbasis feedback: {e}", file=sys.stderr)
            return CANNOT_JUDGE
        except ValueError as e:
            print(f"ekbasis feedback: {e}", file=sys.stderr)
            return ERROR
    try:
        if a.cmd == "health":
            print(json.dumps(client.health()))
            return OK
        if a.cmd == "plan-check":
            return _plan_check(a, client)
        if a.cmd == "predict":
            q = P.choice(a.question, [x.strip() for x in a.options.split(",")]) if a.options else P.yes_no(a.question)
            if a.recap_rule:
                q = P.recap(q, a.recap_rule)
            elif a.recap:
                q = P.recap(q, a.rules)
            ans = client.ask(P.world_state(a.rules, a.state, a.action), {"q": q})["q"]
            print(json.dumps({"answer": ans.value, "confidence": round(ans.confidence, 4),
                              "probabilities": {k: round(v, 4) for k, v in ans.probabilities.items()}}))
            return OK
        if a.cmd == "migrate-gen":
            from . import frameworks as FW
            env = dict(x.split("=", 1) for x in a.env if "=" in x)
            try:
                b = FW.generate(a.framework, repo=a.repo, base=a.base, head=a.head, paths=a.files or None,
                                image=a.image, setup=a.setup, workdir=a.workdir, env=env, migrate=a.migrate,
                                command=a.command, redis=a.redis)
            except FW.GenError as e:
                b = {"framework": a.framework, "migrations": [], "error": str(e), "notes": [str(e)]}
                print(f"ekbasis migrate-gen: {e}", file=sys.stderr)
            text = json.dumps(b)
            if a.output == "-":
                print(text)
            else:
                with open(a.output, "w") as fh:
                    fh.write(text)
            return CANNOT_JUDGE if b.get("error") else OK
        if a.cmd == "migrate-check" and a.bundle:
            try:
                with open(a.bundle) as fh:
                    bundle = json.load(fh)
                if not isinstance(bundle, dict):
                    raise ValueError("not a JSON object")
            except (OSError, ValueError) as e:  # no bundle (migrate-gen crashed or did not run), or not JSON
                raise CannotJudge(f"the framework bundle could not be read ({type(e).__name__}: {e})") from None
            if bundle.get("error"):
                raise CannotJudge(f"the framework bundle was not generated: {bundle['error']}")
            v = M.check_bundle(bundle, pg_url=a.pg_url, stats_url=a.stats_url, autocommit=a.autocommit,
                               client=client, lost_threshold=a.lost_threshold, fail_threshold=a.fail_threshold,
                               on_code=a.on_code, cache=M.VerdictCache(off=True) if a.no_cache else None,
                               policy=a.policy)
        elif a.cmd == "migrate-check":
            v = M.check(repo=a.repo, base=a.base, head=a.head, files=a.files or None,
                        globs=tuple(a.glob) if a.glob else M.DEFAULT_GLOBS, pg_url=a.pg_url, stats_url=a.stats_url,
                        autocommit=a.autocommit, client=client, lost_threshold=a.lost_threshold,
                        fail_threshold=a.fail_threshold,
                        cache=M.VerdictCache(off=True) if a.no_cache else None, setup_sql=a.setup_sql,
                        policy=a.policy)
        if a.cmd == "migrate-check":
            if a.json:
                print(json.dumps(v.as_json(state=a.show_state)))
            else:
                print(v.summary())
                if a.show_state:
                    for f in v.files:
                        print(f"\n--- what the model read for {f.path} ---\n{f.state}")
            if v.risky:
                return RISKY
            if v.cannot_judge:
                if a.fail_open:
                    print("ekbasis: cannot foresee every migration; --fail-open: not treated as risky", file=sys.stderr)
                    return OK
                return CANNOT_JUDGE
            return OK
        if a.cmd == "preflight":
            kw = {"fail_threshold": a.fail_threshold, "rows": not a.no_rows, "fail_closed": a.fail_closed,
                  "copy": not a.no_copy}
            if a.sql:
                with open(a.sql[1], errors="replace") as fh:
                    v = PF.check_sql(a.sql[0], fh.read(), client=client, cwd=a.cwd, **kw)
            elif a.line:
                v = PF.check_line(" ".join(a.line), a.cwd, client=client, **kw)
            else:
                print("ekbasis: preflight needs a command line or --sql DB FILE", file=sys.stderr)
                return ERROR
            if v is None:
                print(json.dumps({"multi_step": False}) if a.json else "Ekbasis preflight: not a multi-step change "
                      "(fewer than two steps that write); nothing to check")
                return OK
            if a.json:
                print(json.dumps({"multi_step": True, "risky": v.risky, "cannot_judge": v.cannot_judge, "cannot_foresee": v.cannot_judge, "by": v.by,
                                  "first": v.first, "p_any": round(v.p_any, 4), "p_fail": [round(x, 4) for x in v.p_fail],
                                  "steps": [s.text for s in v.plan.steps], "effects": [s.effect for s in v.plan.steps],
                                  "applied_before": v.applied_before, "runs_after": v.runs_after, "atomic": v.atomic,
                                  "error": v.error, "reason": v.reason, "reason_p": v.reason_p, "by_code": v.by_code,
                                  "by_numbers": v.by_numbers, "unread": v.plan.unread,
                                  "note": v.copy_note or None,
                                  "message": v.message() if v.risky else None,
                                  **({"state": v.state} if a.show_state else {})}))
            else:
                print(v.summary())
                if a.show_state:
                    print("\n--- what the model read ---\n" + v.state)
            if v.cannot_judge:
                if not a.fail_closed:
                    print("ekbasis preflight: cannot foresee (" + "; ".join(v.plan.unread) + "); not treated as risky",
                          file=sys.stderr)
                    return OK
                return CANNOT_JUDGE
            return RISKY if v.risky else OK
        if a.cmd == "shell-check":
            skip = None if a.no_shortcuts else (lambda view: R.touched_recoverable(view, a.cwd))
            v = S.check(a.commands, cwd=a.cwd, client=client, lost_threshold=a.lost_threshold,
                        fail_threshold=a.fail_threshold, notes=not a.no_notes, shell=a.shell, fail_closed=not a.fail_open,
                        skip=skip, request=a.request)
            if a.json:
                print(json.dumps({"risky": v.risky, "judged": v.judged, "cannot_judge": v.cannot_judge, "cannot_foresee": v.cannot_judge,
                                  "p_lost": v.p_lost, "p_fail": v.p_fail, "reasons": v.reasons, "unread": v.unread,
                                  "notes": v.notes, "commands": v.commands, **({"state": v.state} if a.show_state else {})}))
            else:
                print(v.summary())
                if a.show_state:
                    print("\n--- what the model read ---\n" + v.state)
            if v.lost_risky:
                return RISKY
            if v.unread and a.fail_open:
                print("ekbasis: cannot foresee every part of the line; --fail-open: not treated as risky", file=sys.stderr)
            return CANNOT_JUDGE if v.cannot_judge else OK
        v = G.check(a.commands, repo=a.repo, client=client, fetch=a.fetch, lost_threshold=a.lost_threshold,
                    fail_threshold=a.fail_threshold, fail_closed=not a.fail_open, request=a.request, simulate=a.copy or None)
        route = None
        if v.risky and not a.no_safer and os.environ.get("EKBASIS_SAFER", "1") != "0":
            route = SF.search(v.commands, repo=a.repo, client=client, lost_threshold=a.lost_threshold,
                              fail_threshold=a.fail_threshold, fail_closed=not a.fail_open, request=a.request)
        if a.json:
            print(json.dumps({"risky": v.risky, "judged": True, "p_lost": v.p_lost, "p_fail": v.p_fail,
                              "p_in_progress": v.p_in_progress, "branch": v.branch, "reasons": v.reasons,
                              "commands": v.commands, "safer": route.as_json() if route else None,
                              "safer_note": route.note if route and not route.route else None}))
        else:
            print(v.summary())
            if route:
                print(route.summary())
        return RISKY if v.risky else OK
    except CannotJudge as e:
        if a.cmd in ("git-check", "shell-check", "preflight", "migrate-check"):
            return _cannot_judge(a, str(e))
        print(f"ekbasis: {e}", file=sys.stderr)
        return ERROR
    except (EkbasisError, ValueError) as e:
        print(f"ekbasis: {e}", file=sys.stderr)
        return ERROR


if __name__ == "__main__":
    sys.exit(main())
