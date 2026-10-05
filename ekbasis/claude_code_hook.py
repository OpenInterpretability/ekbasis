"""Claude Code PreToolUse hook: before the Bash tool runs git commands, ask Ekbasis what they will do. If they may
permanently lose uncommitted work, Claude Code asks you to confirm (or blocks, EKBASIS_GUARD_MODE=deny), showing why.

It fails open: if the server cannot be reached, the folder is not a git repository or anything else goes wrong, the hook
says nothing and the command goes through Claude Code's normal permission flow.

Install (after `pip install ./ekbasis`), in .claude/settings.json (one project) or ~/.claude/settings.json (all):
  {"hooks": {"PreToolUse": [{"matcher": "Bash",
                             "hooks": [{"type": "command", "command": "ekbasis-claude-hook", "timeout": 30}]}]}}
env: EKBASIS_URL (server), EKBASIS_LOST_THRESHOLD (0.2), EKBASIS_GUARD_MODE (ask | deny), EKBASIS_FETCH (1: git fetch
first so the state shows the real remote; slower).
"""
from __future__ import annotations

import json
import os
import re
import shlex
import sys

from . import git as G


def git_commands(command: str) -> tuple[str | None, list[str]]:
    """The git commands in a shell command line (split on &&, ||, ;, | and new lines), and a leading `cd DIR`."""
    parts = [p.strip() for p in re.split(r"&&|\|\||;|\n|\|", command) if p.strip()]
    where = None
    if parts and parts[0].startswith("cd "):
        try:
            where = shlex.split(parts[0])[1]
        except (ValueError, IndexError):
            where = None
    return where, [p for p in parts if p.startswith("git ")]


def main() -> int:
    try:
        data = json.load(sys.stdin)
        if data.get("tool_name") != "Bash":
            return 0
        where, cmds = git_commands((data.get("tool_input") or {}).get("command", ""))
        if not cmds:
            return 0
        repo = data.get("cwd") or os.getcwd()
        if where:
            repo = os.path.normpath(os.path.join(repo, os.path.expanduser(where)))
        if G._git(repo, "rev-parse", "--is-inside-work-tree")[0] != 0:
            return 0
        v = G.check(cmds, repo=repo, fetch=os.environ.get("EKBASIS_FETCH") == "1",
                    lost_threshold=float(os.environ.get("EKBASIS_LOST_THRESHOLD", "0.2")))
    except Exception as e:  # fail open
        print(f"ekbasis hook: {e}", file=sys.stderr)
        return 0
    if v.risky:
        mode = "deny" if os.environ.get("EKBASIS_GUARD_MODE") == "deny" else "ask"
        reason = (f"Ekbasis: {'; '.join(v.reasons)}. Commands: {' ; '.join(cmds)}. "
                  "Consider saving the work first (commit, or git stash -u).")
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": mode,
                                                 "permissionDecisionReason": reason}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
