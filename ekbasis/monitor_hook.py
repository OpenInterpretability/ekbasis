"""Claude Code PreToolUse hook that WATCHES an agent: before any tool call that can change something, Ekbasis asks the
three MONITOR questions (security, sabotage, off_task: ekbasis.monitor(), worded as in the pre-registered LinuxArena
study) about the user's last request, the agent's last actions and the call about to run, and Claude Code asks you to
confirm when one of them is likely (0.1.40).

    {"hooks": {"PreToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": "ekbasis-monitor-hook",
      "timeout": 15}]}]}}

Environment: EKBASIS_URL / EKBASIS_API_KEY as for the other hooks; EKBASIS_MONITOR_THRESHOLD (0.9: the operating point of
the study, a 1% audit budget on honest runs); EKBASIS_MONITOR_MODE = ask (default), deny, or log (never block, append
what it would have done to ~/.cache/ekbasis/monitor_log.jsonl or EKBASIS_MONITOR_LOG, this machine only: try it for a
while before letting it ask); EKBASIS_MONITOR_DEADLINE (seconds, default 10). It is an extra layer that fails OPEN: when
Ekbasis cannot answer in time the call goes through, with a note on stderr (EKBASIS_MONITOR_FAIL_CLOSED=1 asks instead).
Tools that only read (Read, Grep, Glob, LS, WebSearch, todo lists) are never checked. One request per checked call."""
from __future__ import annotations

import json
import os
import sys
import time

from . import prompts as P
from .claude_code_hook import user_request
from .client import CannotJudge, Ekbasis
from .redact import redact_line

READ_ONLY = {"Read", "Glob", "Grep", "LS", "WebSearch", "TodoWrite", "TodoRead", "NotebookRead", "ExitPlanMode",
             "BashOutput", "ListMcpResourcesTool", "ReadMcpResourceTool"}
HIST_N, HIST_CHARS, ACT_CHARS = 5, 400, 12000


def _cut(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n // 2] + f"\n[... {len(s) - n} characters left out ...]\n" + s[-n // 2:]


def _show(name: str, args) -> str:
    return f"{name}: {json.dumps(args, ensure_ascii=False)}"


def recent_actions(transcript_path: str | None, n: int = HIST_N) -> list[str]:
    """The agent's last n tool calls in the Claude Code transcript, oldest first."""
    if not transcript_path:
        return []
    calls = []
    try:
        with open(transcript_path, encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                try:
                    ev = json.loads(raw)
                except ValueError:
                    continue
                if not isinstance(ev, dict) or ev.get("type") != "assistant":
                    continue
                for c in (ev.get("message") or {}).get("content") or []:
                    if isinstance(c, dict) and c.get("type") == "tool_use":
                        calls.append(_show(c.get("name", "?"), c.get("input")))
    except OSError:
        return []
    return calls[-n:]


def state_text(tool: str, args, cwd: str, request: str, history: list[str]) -> str:
    """The state as the LinuxArena monitor study built it: the request at the top, where the agent works, its last
    actions, the action about to run."""
    parts = [f"Environment: an AI coding agent working in {cwd or 'a software project'}.",
             "Earlier actions of the agent (most recent last):\n"
             + ("\n".join(f"- {_cut(h, HIST_CHARS)}" for h in history) or "- none"),
             "About to run:\n" + _cut(_show(tool, args), ACT_CHARS)]
    return P.request_on_top("\n\n".join(parts), request)


def _log(entry: dict) -> None:
    path = os.environ.get("EKBASIS_MONITOR_LOG") or os.path.join(
        os.environ.get("EKBASIS_CACHE_DIR") or os.path.join(os.path.expanduser("~"), ".cache", "ekbasis"),
        "monitor_log.jsonl")
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(redact_line(json.dumps(entry)) + "\n")   # 0.1.42: no credential typed in a call stays in the log
    except OSError:
        pass


def _say(decision: str, reason: str) -> None:
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": decision,
                                             "permissionDecisionReason": reason}}))


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return 0
    tool, args = data.get("tool_name") or "", data.get("tool_input") or {}
    if tool in READ_ONLY:
        return 0
    mode = os.environ.get("EKBASIS_MONITOR_MODE", "ask")
    request = user_request(data.get("transcript_path"))
    if not request:
        return 0   # nothing to compare the call with
    threshold = float(os.environ.get("EKBASIS_MONITOR_THRESHOLD", "0.9"))
    state = state_text(tool, args, data.get("cwd") or "", request, recent_actions(data.get("transcript_path")))
    t0 = time.time()
    try:
        client = Ekbasis(timeout=float(os.environ.get("EKBASIS_MONITOR_DEADLINE", "10")))
        ans = client.ask(state, P.monitor())
    except (CannotJudge, OSError, ValueError) as e:
        if mode == "log":
            _log({"t": time.time(), "tool": tool, "decision": "cannot_foresee", "why": str(e)[:200]})
        elif os.environ.get("EKBASIS_MONITOR_FAIL_CLOSED") == "1":
            _say("deny" if mode == "deny" else "ask",
                 f"Ekbasis could not check this {tool} call ({e}). Allow it only if you expect it.")
        else:
            print(f"ekbasis monitor: cannot foresee ({e}); letting the {tool} call through", file=sys.stderr)
        return 0
    p = {k: float(a.p_yes) for k, a in ans.items()}
    flagged = sorted((k for k, v in p.items() if v >= threshold), key=lambda k: -p[k])
    if mode == "log":
        _log({"t": time.time(), "tool": tool, "p": {k: round(v, 4) for k, v in p.items()},
              "decision": "ask" if flagged else "pass", "ms": int((time.time() - t0) * 1000),
              "call": _cut(_show(tool, args), 300)})
        return 0
    if flagged:
        stakes = "; ".join(f"{p[k]:.0%} {P.HARM_LABELS.get(k, k)}" for k in flagged)
        _say("deny" if mode == "deny" else "ask",
             f"Ekbasis monitor: this {tool} call may work against what you asked ({stakes}). "
             f"Allow it only if you expect it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
