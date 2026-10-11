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
  ekbasis migrate-check [--base REF] [--head REF] [--glob G] [--pg-url URL] [--stats-url URL] [--autocommit] [--json]
                        [FILE ...]
      Before a pull request is merged: will its new PostgreSQL migrations lose data or fail? The schema is built by
      applying the base's migrations to a scratch database (EKBASIS_PG_URL); optional row counts and NULL fractions come
      from a read-only replica's planner statistics (EKBASIS_DB_STATS_URL; aggregates only, never values). A file runs
      as one transaction, as Prisma, Diesel and golang-migrate run it; --autocommit for psql -f semantics. Exit codes:
      0 no risk found; 2 risky; 3 cannot foresee (treat as risky; --fail-open turns it into 0). See
      docs/MIGRATION_GUARD.md.
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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ekbasis", description="Ekbasis: what happens if I do this? (typed, calibrated, one pass)")
    ap.add_argument("--url", default=None, help="server (default: EKBASIS_URL or http://127.0.0.1:8000)")
    ap.add_argument("--timeout", type=float, default=120.0, help="seconds to wait for each answer (default 120)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("git-check", help="check git commands before running them")
    g.add_argument("--repo", default=".")
    g.add_argument("--fetch", action="store_true", help="git fetch first, so the state shows the real remote")
    g.add_argument("--json", action="store_true")
    g.add_argument("--lost-threshold", type=float, default=0.2)
    g.add_argument("--fail-threshold", type=float, default=0.5)
    g.add_argument("--fail-open", action="store_true", help="exit 0 (with a warning) when it cannot foresee")
    g.add_argument("--no-safer", action="store_true", help="when risky, do not look for a safer route (one round trip)")
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
    m.add_argument("--lost-threshold", type=float, default=M.LOST_THRESHOLD)
    m.add_argument("--fail-threshold", type=float, default=M.FAIL_THRESHOLD)
    m.add_argument("--json", action="store_true")
    m.add_argument("--show-state", action="store_true", help="print the exact text the model read")
    m.add_argument("--fail-open", action="store_true", help="exit 0 (with a warning) when it cannot foresee")
    m.add_argument("files", nargs="*", help="migration files to check (instead of --base)")
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
        if a.cmd == "migrate-check":
            v = M.check(repo=a.repo, base=a.base, head=a.head, files=a.files or None,
                        globs=tuple(a.glob) if a.glob else M.DEFAULT_GLOBS, pg_url=a.pg_url, stats_url=a.stats_url,
                        autocommit=a.autocommit, client=client, lost_threshold=a.lost_threshold,
                        fail_threshold=a.fail_threshold)
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
            v = S.check(a.commands, cwd=a.cwd, client=client, lost_threshold=a.lost_threshold,
                        fail_threshold=a.fail_threshold, notes=not a.no_notes, shell=a.shell, fail_closed=not a.fail_open)
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
                    fail_threshold=a.fail_threshold, fail_closed=not a.fail_open)
        route = None
        if v.risky and not a.no_safer and os.environ.get("EKBASIS_SAFER", "1") != "0":
            route = SF.search(v.commands, repo=a.repo, client=client, lost_threshold=a.lost_threshold,
                              fail_threshold=a.fail_threshold, fail_closed=not a.fail_open)
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
