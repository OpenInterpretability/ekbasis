#!/bin/sh
# Claude Code plugin hooks: run.sh session-start | hook. Runs claude_plugin.py with python3 and, when python3 is missing
# or dies without answering, still answers: for the PreToolUse hook, once EKBASIS_URL or EKBASIS_API_KEY is set, "ask"
# (EKBASIS_GUARD_MODE=deny: "deny"; EKBASIS_FAIL_OPEN=1: let it through, on stderr), never a silent pass; for
# SessionStart, a visible message. claude_plugin.py handles every failure after Python starts.
here=${0%/*}
mode=$1
out=$(python3 "$here/claude_plugin.py" "$mode")
rc=$?
if [ "$rc" -eq 0 ]; then
  [ -n "$out" ] && printf '%s\n' "$out"
  exit 0
fi
why="python3 failed with exit code $rc (python3 3.9 or later must be on PATH)"
[ "$rc" -eq 127 ] && why="python3 was not found on PATH (the plugin needs Python 3.9 or later)"
case "$mode" in
  hook)
    [ -z "$EKBASIS_URL$EKBASIS_API_KEY" ] && exit 0
    if [ "$EKBASIS_FAIL_OPEN" = "1" ]; then
      echo "ekbasis hook: cannot foresee ($why); EKBASIS_FAIL_OPEN=1: letting it through" >&2
      exit 0
    fi
    decision=ask
    [ "$EKBASIS_GUARD_MODE" = "deny" ] && decision=deny
    printf '{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "%s", "permissionDecisionReason": "Ekbasis could not foresee what this command will do (the Ekbasis hook could not run: %s). Confirm it only if you know it is safe."}}\n' "$decision" "$why"
    ;;
  *)
    printf '{"systemMessage": "Ekbasis plugin: %s, so the git guard cannot run."}\n' "$why"
    ;;
esac
exit 0
