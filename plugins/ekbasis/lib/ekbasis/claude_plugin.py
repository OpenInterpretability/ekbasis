"""Entry points of the Claude Code plugin (plugins/ekbasis/), which runs its own copy of this package (plugins/ekbasis/lib,
kept identical by scripts/sync_plugin.py) through plugins/ekbasis/scripts/run.sh and claude_plugin.py:

  session-start   SessionStart hook: when Ekbasis is not set up, one line saying how (the git guard stays off); when it
                  is set up, nothing
  hook            PreToolUse hook (Bash): ekbasis.claude_code_hook, unchanged, when Ekbasis is set up; when it is not,
                  it says nothing and Claude Code's normal permission flow applies
  mcp             the MCP server (ekbasis.mcp_server)
  bin/ekbasis     the command line (ekbasis.cli); not set up, it says so and exits 3 (cannot foresee)

Set up means EKBASIS_URL or EKBASIS_API_KEY is set (in the shell, or in the "env" block of Claude Code's settings.json).
A key without a URL means the hosted API. The plugin does not call the default http://127.0.0.1:8000 on its own: an
unconfigured plugin would otherwise ask to confirm every git command that can change files ("cannot reach the server").
Once either variable is set, the hook is the same fail-closed hook as `ekbasis-claude-hook`, and the launcher turns any
failure of the hook itself (an import error, a crash, a Python too old or missing, no answer in time) into an "ask".
"""
from __future__ import annotations

import json
import os
import sys

HOSTED_URL = "https://openinterp.org/api/v1"
CONSOLE = "https://openinterp.org/console"
SETUP = (f"Ekbasis plugin: not set up, so the git guard is off. Get a key at {CONSOLE} and set EKBASIS_API_KEY=ekb_... "
         "(shell, or \"env\" in ~/.claude/settings.json), or set EKBASIS_URL to your own server; then restart Claude Code.")
NOT_SET_UP = 3   # the CLI's "cannot foresee" exit code


def configured(env=None) -> bool:
    env = os.environ if env is None else env
    return bool(env.get("EKBASIS_URL", "").strip() or env.get("EKBASIS_API_KEY", "").strip())


def configure(env=None) -> bool:
    """Whether Ekbasis is set up. A key without a URL points the client at the hosted API (env is changed in place)."""
    env = os.environ if env is None else env
    if env.get("EKBASIS_API_KEY", "").strip() and not env.get("EKBASIS_URL", "").strip():
        env["EKBASIS_URL"] = HOSTED_URL
    return configured(env)


def session_start(env=None) -> int:
    if not configure(env):
        print(json.dumps({"systemMessage": SETUP,
                          "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": SETUP}}))
    return 0


def hook(env=None) -> int:
    if not configure(env):
        return 0
    from . import claude_code_hook
    return claude_code_hook.main()


def mcp(env=None) -> int:
    configure(env)
    from . import mcp_server
    mcp_server.main()
    return 0


def cli(argv=None, env=None) -> int:
    """bin/ekbasis: the command line, but not set up it says so (exit 3, cannot foresee) instead of calling
    http://127.0.0.1:8000; --help, and --url given on the command line, still work."""
    argv = sys.argv[1:] if argv is None else argv
    wants_help = not argv or any(a in ("-h", "--help") for a in argv)
    if not configure(env) and not wants_help and not any(a == "--url" or a.startswith("--url=") for a in argv):
        print(SETUP.replace("so the git guard is off", "so it cannot foresee anything"), file=sys.stderr)
        return NOT_SET_UP
    from . import cli as C
    return C.main(argv)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    run = {"session-start": session_start, "hook": hook, "mcp": mcp}.get(argv[0] if argv else "")
    if run is None:
        print("usage: claude_plugin.py session-start | hook | mcp", file=sys.stderr)
        return 1
    return run()


if __name__ == "__main__":
    sys.exit(main())
