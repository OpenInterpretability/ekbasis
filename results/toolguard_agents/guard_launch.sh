#!/bin/bash
# The guard in front of the desk MCP server, per condition (B: session only; C: + read-only probe with `inspect`;
# D: the app's backend spec as the state; Cinj: C with planted text in the screens). The study key is read here from
# its file and never written to any config.   guard_launch.sh <B|C|D|Cinj> <log.jsonl> -- <server command...>
set -u
COND="$1"; LOG="$2"; shift 2
export EKBASIS_API_KEY="$(cat "${EKB_KEY_FILE:-$HOME/.config/ekbasis/study_api_key}")"
export EKBASIS_URL="${EKBASIS_URL:-https://openinterp.org/api/v1}" EKBASIS_SURFACE="toolguard-agents"
# the gateway can hold an internal account's request up to 120 s (AMENDMENT_2): wait for it rather than fail closed
export EKBASIS_TOOL_DEADLINE="${EKBASIS_TOOL_DEADLINE:-150}"
export PYTHONPATH="${EKB_SRC:?}${PYTHONPATH:+:$PYTHONPATH}"
ALLOW="look,open_app,type_text,say,done"
COMMON=(--no-repeat --no-request-flags --request "$TG_REQUEST" --allow "$ALLOW" --log "$LOG")
case "$COND" in
  B) exec python3 -m ekbasis.mcp_guard --no-probe "${COMMON[@]}" "$@";;
  C|Cinj) exec python3 -m ekbasis.mcp_guard --probe-only inspect "${COMMON[@]}" "$@";;
  D) exec python3 "$(dirname "$0")/guard_backend.py" --no-probe --probe-only backend_spec "${COMMON[@]}" "$@";;
esac
echo "unknown condition $COND" >&2; exit 1
