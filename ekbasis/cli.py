"""Command line.

  ekbasis git-check [--repo DIR] [--fetch] [--json] [--lost-threshold P] -- "git checkout feature" "git stash pop"
      What the commands will do before they run. Exit code 0: no risk found; 2: risky (may lose uncommitted work);
      1: error (for example, the server is not reachable).
  ekbasis predict --rules TEXT --state TEXT --action A [--action B ...] --question TEXT [--options a,b,c]
      One typed question about the outcome (yes/no when --options is not given).
  ekbasis health
Server: EKBASIS_URL (default http://127.0.0.1:8000) or --url.
"""
from __future__ import annotations

import argparse
import json
import sys

from . import git as G
from . import prompts as P
from .client import Ekbasis, EkbasisError


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ekbasis", description="Ekbasis: what happens if I do this? (typed, calibrated, one pass)")
    ap.add_argument("--url", default=None, help="server (default: EKBASIS_URL or http://127.0.0.1:8000)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("git-check", help="check git commands before running them")
    g.add_argument("--repo", default=".")
    g.add_argument("--fetch", action="store_true", help="git fetch first, so the state shows the real remote")
    g.add_argument("--json", action="store_true")
    g.add_argument("--lost-threshold", type=float, default=0.2)
    g.add_argument("--fail-threshold", type=float, default=0.5)
    g.add_argument("commands", nargs="+", help='each command as one argument, e.g. "git checkout main"')
    p = sub.add_parser("predict", help="one question about the outcome of some actions")
    p.add_argument("--rules", required=True)
    p.add_argument("--state", required=True)
    p.add_argument("--action", action="append", required=True)
    p.add_argument("--question", required=True)
    p.add_argument("--options", default=None, help="comma-separated answers (default: yes/no)")
    sub.add_parser("health")
    a = ap.parse_args(argv)
    client = Ekbasis(url=a.url)
    try:
        if a.cmd == "health":
            print(json.dumps(client.health()))
            return 0
        if a.cmd == "predict":
            q = P.choice(a.question, [x.strip() for x in a.options.split(",")]) if a.options else P.yes_no(a.question)
            ans = client.ask(P.world_state(a.rules, a.state, a.action), {"q": q})["q"]
            print(json.dumps({"answer": ans.value, "confidence": round(ans.confidence, 4),
                              "probabilities": {k: round(v, 4) for k, v in ans.probabilities.items()}}))
            return 0
        v = G.check(a.commands, repo=a.repo, client=client, fetch=a.fetch, lost_threshold=a.lost_threshold,
                    fail_threshold=a.fail_threshold)
        if a.json:
            print(json.dumps({"risky": v.risky, "p_lost": v.p_lost, "p_fail": v.p_fail, "p_in_progress": v.p_in_progress,
                              "branch": v.branch, "reasons": v.reasons, "commands": v.commands}))
        else:
            print(v.summary())
        return 2 if v.risky else 0
    except (EkbasisError, ValueError) as e:
        print(f"ekbasis: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
