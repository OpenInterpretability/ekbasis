#!/bin/bash
# WS-AL: one real agent session (copy of WS-X's run_agent_x.sh). MODE: blind | see | ahead | manual (look-ahead study)
# | alone | tracker (ledger study). blind/manual/alone: desk tools only; see: + foresee; ahead: + advise; tracker: +
# balances. manual: the app's manual (meta.manual) is appended to the system prompt. The stage serves AL/web and calls
# FORESEE_URL (foresee_al.py). MAXT sets max turns.  run_agent_al.sh <scenario.json> <session-name> <mode> [model]
set -u
D="$(cd "$(dirname "$0")" && pwd)"; cd "$D"
SCN="$1"; NAME="$2"; MODE="$3"; MODEL="${4:-sonnet}"
PORT=${PORT:-}
[ -n "$PORT" ] || PORT=$(python3 -c "import socket,random
for _ in range(200):
  p=random.randrange(47100,47900,2); ok=True
  for q in (p,p+1):
    s=socket.socket()
    try: s.bind(('127.0.0.1',q))
    except OSError: ok=False
    finally: s.close()
  if ok: print(p); break")
mkdir -p "sessions/$(dirname "$NAME")" agent_cwd
BLIND=1; AHEAD=0; TRACK=0
TOOLS="mcp__desk__look,mcp__desk__open_app,mcp__desk__click,mcp__desk__type_text,mcp__desk__say,mcp__desk__done"
case "$MODE" in
  see) BLIND=0; TOOLS="$TOOLS,mcp__desk__foresee";;
  ahead) AHEAD=1; TOOLS="$TOOLS,mcp__desk__advise";;
  tracker) TRACK=1; TOOLS="$TOOLS,mcp__desk__balances";;
esac
TRACK="$TRACK" WEB_ROOT="$D/web" FORESEE_URL="${FORESEE_URL:-http://127.0.0.1:8771/foresee}" node stage_al.mjs "$SCN" --port $PORT > "sessions/$NAME.stage.log" 2>&1 &
STAGE=$!
for i in $(seq 1 60); do curl -sf -m 2 -X POST "127.0.0.1:$PORT/look" > /dev/null && break; sleep 0.5; done
MCPF="agent_cwd/mcp_$(echo "$NAME" | tr '/' '_').json"
cat > "$MCPF" <<JSON
{"mcpServers": {"desk": {"command": "node", "args": ["$D/agent_mcp_al.mjs"], "env": {"STAGE_URL": "http://127.0.0.1:$PORT", "BLIND": "$BLIND", "AHEAD": "$AHEAD", "TRACK": "$TRACK"}}}}
JSON
SYS="$(cat "$D/prompts/system_$MODE.txt")"
if [ "$MODE" = manual ]; then
  SYS="$SYS

The manual of the app you are using:
$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['meta']['manual'])" "$SCN")"
fi
TASK=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['meta']['task'])" "$SCN")
(cd agent_cwd && env -u CLAUDECODE -u CLAUDE_CODE_ENTRYPOINT claude -p "$TASK" --model "$MODEL" --tools "" \
   --mcp-config "$(basename "$MCPF")" --strict-mcp-config --allowedTools "$TOOLS" \
   --append-system-prompt "$SYS" --output-format stream-json --verbose --max-turns "${MAXT:-40}" --no-session-persistence \
   --setting-sources "project,local" \
   > "../sessions/$NAME.agent.jsonl" 2> "../sessions/$NAME.agent.err")
echo "agent exit $?"
curl -s -X POST "127.0.0.1:$PORT/save?name=$NAME"; echo
curl -s -m 3 -X POST "127.0.0.1:$PORT/quit" > /dev/null; wait $STAGE 2>/dev/null
