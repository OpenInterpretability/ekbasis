#!/bin/bash
# One real agent session on the demo desktop: the stage (browser) for a scenario, then Claude Code in print mode with only
# the desk tools (no shell, no files), then the session log is saved. The agent's own transcript is kept next to it.
#   run_agent.sh <scenario.json> <session-name> [see|blind] [model] [en|pt]
# en: Caio's user settings are left out (they make the agent answer in Portuguese); pt: they are kept. MAXT sets max turns.
set -u
D="$(cd "$(dirname "$0")" && pwd)"; cd "$D"
SCN="$1"; NAME="$2"; MODE="${3:-see}"; MODEL="${4:-sonnet}"; LANGX="${5:-en}"
SOURCES="project,local"; [ "$LANGX" = pt ] && SOURCES="user,project,local"
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
mkdir -p sessions agent_cwd
node stage.mjs "$SCN" --port $PORT > "sessions/$NAME.stage.log" 2>&1 &
STAGE=$!
for i in $(seq 1 60); do curl -sf -m 2 -X POST "127.0.0.1:$PORT/look" > /dev/null && break; sleep 0.5; done
BLIND=0; [ "$MODE" = blind ] && BLIND=1
cat > "agent_cwd/mcp_$NAME.json" <<EOF
{"mcpServers": {"desk": {"command": "node", "args": ["$D/agent_mcp.mjs"], "env": {"STAGE_URL": "http://127.0.0.1:$PORT", "BLIND": "$BLIND"}}}}
EOF
SYS="$D/agent_system_$MODE.txt"
TASK=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['meta']['task'])" "$SCN")
TOOLS="mcp__desk__look,mcp__desk__open_app,mcp__desk__click,mcp__desk__type_text,mcp__desk__say,mcp__desk__done"
[ "$MODE" = blind ] || TOOLS="$TOOLS,mcp__desk__foresee"
(cd agent_cwd && env -u CLAUDECODE -u CLAUDE_CODE_ENTRYPOINT claude -p "$TASK" --model "$MODEL" --tools "" \
   --mcp-config "mcp_$NAME.json" --strict-mcp-config --allowedTools "$TOOLS" \
   --append-system-prompt "$(cat "$SYS")" --output-format stream-json --verbose --max-turns "${MAXT:-40}" --no-session-persistence \
   --setting-sources "$SOURCES" \
   > "../sessions/$NAME.agent.jsonl" 2> "../sessions/$NAME.agent.err")
echo "agent exit $?"
curl -s -X POST "127.0.0.1:$PORT/save?name=$NAME"; echo
curl -s -m 3 -X POST "127.0.0.1:$PORT/quit" > /dev/null; wait $STAGE 2>/dev/null
