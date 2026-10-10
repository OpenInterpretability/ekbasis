"""Entry points of the Claude Code plugin (.claude-plugin/ at the root of the repository), run from the plugin's own
copy of this package by scripts/claude_plugin.py:

  claude_plugin.py session-start   SessionStart hook: when Ekbasis is not set up, one line saying how, and the git guard
                                   stays off; when it is set up, nothing
  claude_plugin.py hook            PreToolUse hook (Bash): ekbasis.claude_code_hook, unchanged, when Ekbasis is set up;
                                   when it is not, it says nothing and Claude Code's normal permission flow applies
  claude_plugin.py mcp             the MCP server (ekbasis.mcp_server)

Set up means EKBASIS_URL or EKBASIS_API_KEY is set (in the shell, or in the "env" block of Claude Code's settings.json).
A key without a URL means the hosted API. The plugin does not call the default http://127.0.0.1:8000 on its own: an
unconfigured plugin would otherwise ask to confirm every git command that can change files ("cannot reach the server").
Once either variable is set, the hook is the same fail-closed hook as `ekbasis-claude-hook`: a server that cannot be
reached or a missing key on the hosted URL makes it ask, exactly as before.
"""
from __future__ import annotations

import json
import os
import sys

HOSTED_URL = "https://openinterp.org/api/v1"
CONSOLE = "https://openinterp.org/console"
SETUP = (f"Ekbasis plugin: not set up, so the git guard is off. Get a key at {CONSOLE} and set EKBASIS_API_KEY=ekb_... "
         "(shell, or \"env\" in ~/.claude/settings.json), or set EKBASIS_URL to your own server; then restart Claude Code.")


def configure(env=None) -> bool:
    """Whether Ekbasis is set up. A key without a URL points the client at the hosted API (env is changed in place)."""
    env = os.environ if env is None else env
    url, key = env.get("EKBASIS_URL", "").strip(), env.get("EKBASIS_API_KEY", "").strip()
    if key and not url:
        env["EKBASIS_URL"] = HOSTED_URL
    return bool(url or key)


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


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    run = {"session-start": session_start, "hook": hook, "mcp": mcp}.get(argv[0] if argv else "")
    if run is None:
        print("usage: claude_plugin.py session-start | hook | mcp", file=sys.stderr)
        return 1
    return run()


if __name__ == "__main__":
    sys.exit(main())
