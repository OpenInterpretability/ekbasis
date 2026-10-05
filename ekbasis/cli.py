"""Command line.

  ekbasis git-check [--repo DIR] [--fetch] [--json] [--lost-threshold P] -- "git checkout feature" "git stash pop"
      What the commands will do before they run.
  ekbasis shell-check [--cwd DIR] [--json] [--lost-threshold P] [--shell bash|zsh] -- "rm -r build/" "sort f > f"
      Prototype: what shell command lines will do to the files of a folder before they run (each argument is one line).
      --show-state prints the exact text the model read.
  Exit codes of both checks: 0 no risk found; 2 risky (may lose work or file content); 3 cannot judge (the server
  could not be reached or did not answer in time, the repository or folder could not be read, or the line has parts
  the guard cannot evaluate): treat 3 as risky; 1 a usage error. The checks fail closed: --fail-open turns "cannot
  judge" into 0, with a warning on stderr.
  ekbasis predict --rules TEXT --state TEXT --action A [--action B ...] --question TEXT [--options a,b,c] [--recap]
      One typed question about the outcome (yes/no when --options is not given). --recap repeats the rules right before
      the question; --recap-rule TEXT (repeatable) repeats only the rules you name.
  ekbasis health
Server: EKBASIS_URL (default http://127.0.0.1:8000) or --url; --timeout SECONDS for each request (default 120).
"""
from __future__ import annotations

import argparse
import json
import sys

from . import git as G
from . import prompts as P
from . import shell as S
from .client import CannotJudge, Ekbasis, EkbasisError

OK, ERROR, RISKY, CANNOT_JUDGE = 0, 1, 2, 3


def _cannot_judge(a, why: str) -> int:
    if a.fail_open:
        print(f"ekbasis: cannot judge ({why}); --fail-open: not treated as risky", file=sys.stderr)
        return OK
    if a.json:
        print(json.dumps({"risky": True, "judged": False, "cannot_judge": why}))
    else:
        print(f"Ekbasis: CANNOT JUDGE  ({why})\n  treat it as risky: run it only after checking it yourself")
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
    g.add_argument("--fail-open", action="store_true", help="exit 0 (with a warning) when it cannot judge")
    g.add_argument("commands", nargs="+", help='each command as one argument, e.g. "git checkout main"')
    s = sub.add_parser("shell-check", help="check shell command lines before running them (prototype)")
    s.add_argument("--cwd", default=".", help="the folder the commands would run in")
    s.add_argument("--json", action="store_true")
    s.add_argument("--lost-threshold", type=float, default=0.2)
    s.add_argument("--fail-threshold", type=float, default=0.5)
    s.add_argument("--shell", choices=["bash", "zsh"], default=None, help="default: from $SHELL, else bash")
    s.add_argument("--no-notes", action="store_true", help="leave out the shell rules (for comparisons)")
    s.add_argument("--show-state", action="store_true", help="print the exact text the model read")
    s.add_argument("--fail-open", action="store_true", help="exit 0 (with a warning) when it cannot judge")
    s.add_argument("commands", nargs="+", help='each command line as one argument, e.g. "rm -r build/"')
    p = sub.add_parser("predict", help="one question about the outcome of some actions")
    p.add_argument("--rules", required=True)
    p.add_argument("--state", required=True)
    p.add_argument("--action", action="append", required=True)
    p.add_argument("--question", required=True)
    p.add_argument("--options", default=None, help="comma-separated answers (default: yes/no)")
    p.add_argument("--recap", action="store_true", help="repeat the rules right before the question")
    p.add_argument("--recap-rule", action="append", default=None, help="repeat only this rule (repeatable)")
    sub.add_parser("health")
    a = ap.parse_args(argv)
    client = Ekbasis(url=a.url, timeout=a.timeout)
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
        if a.cmd == "shell-check":
            v = S.check(a.commands, cwd=a.cwd, client=client, lost_threshold=a.lost_threshold,
                        fail_threshold=a.fail_threshold, notes=not a.no_notes, shell=a.shell, fail_closed=not a.fail_open)
            if a.json:
                print(json.dumps({"risky": v.risky, "judged": v.judged, "cannot_judge": v.cannot_judge,
                                  "p_lost": v.p_lost, "p_fail": v.p_fail, "reasons": v.reasons, "unread": v.unread,
                                  "notes": v.notes, "commands": v.commands, **({"state": v.state} if a.show_state else {})}))
            else:
                print(v.summary())
                if a.show_state:
                    print("\n--- what the model read ---\n" + v.state)
            if v.lost_risky:
                return RISKY
            if v.unread and a.fail_open:
                print("ekbasis: cannot judge every part of the line; --fail-open: not treated as risky", file=sys.stderr)
            return CANNOT_JUDGE if v.cannot_judge else OK
        v = G.check(a.commands, repo=a.repo, client=client, fetch=a.fetch, lost_threshold=a.lost_threshold,
                    fail_threshold=a.fail_threshold, fail_closed=not a.fail_open)
        if a.json:
            print(json.dumps({"risky": v.risky, "judged": True, "p_lost": v.p_lost, "p_fail": v.p_fail,
                              "p_in_progress": v.p_in_progress, "branch": v.branch, "reasons": v.reasons,
                              "commands": v.commands}))
        else:
            print(v.summary())
        return RISKY if v.risky else OK
    except CannotJudge as e:
        if a.cmd in ("git-check", "shell-check"):
            return _cannot_judge(a, str(e))
        print(f"ekbasis: {e}", file=sys.stderr)
        return ERROR
    except (EkbasisError, ValueError) as e:
        print(f"ekbasis: {e}", file=sys.stderr)
        return ERROR


if __name__ == "__main__":
    sys.exit(main())
