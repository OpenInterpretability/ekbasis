#!/bin/bash
# WS-X GLM agent study: one real agent session on the demo desktop (stage_x.mjs), then opencode (GLM-5.3-flash) with only
# the desk tools. Mirror of run_agent_x.sh. MODE: blind | see | router (see + the escalation note when Ekbasis is unsure).
#   run_agent_glm.sh <scenario.json> <session-name> [blind|see|router] [en|pt]
set -u
X="$(cd "$(dirname "$0")" && pwd)"; D="$X/../../../launch_video"; D="$(cd "$D" && pwd)"; cd "$D"
SCN="$1"; NAME="$2"; MODE="${3:-see}"; LANGX="${4:-en}"
MODEL="${GLM_MODEL:?set GLM_MODEL to the opencode provider/model id of the agent}"; PREFIX="${GLM_PREFIX:-glmrun}"
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
WEB_ROOT="$X/web" FORESEE_MODE=model FORESEE_URL="${FORESEE_URL:-http://127.0.0.1:8761/foresee}" node stage_x.mjs "$SCN" --port "$PORT" > "sessions/$NAME.stage.log" 2>&1 &
STAGE=$!
for i in $(seq 1 60); do curl -sf -m 2 -X POST "127.0.0.1:$PORT/look" > /dev/null && break; sleep 0.5; done
BLIND=1; ROUTER=0
case "$MODE" in see|router) BLIND=0;; esac; [ "$MODE" = router ] && ROUTER=1
RDIR="agent_cwd/${PREFIX}_${NAME//\//_}"
OUTD="$D/sessions/$NAME"; mkdir -p "$OUTD"
mkdir -p "$RDIR/.opencode/agent"
cat > "$RDIR/opencode.json" <<EOF
{"\$schema": "https://opencode.ai/config.json", "provider": {"${GLM_PID:-qwen35}": {"npm": "@ai-sdk/openai-compatible", "name": "${GLM_PNAME:-Qwen3.5-4B}", "options": {"baseURL": "${GLM_BASEURL:-http://127.0.0.1:18593/v1}"}, "models": {"${GLM_MID:-qwen35-4b}": {"limit": {"context": ${GLM_CTX:-16384}, "output": 4096}}}}}, "mcp": {"desk": {"type": "local",
  "command": ["node", "$D/agent_mcp_glm.mjs"], "environment": {"STAGE_URL": "http://127.0.0.1:$PORT", "BLIND": "$BLIND", "ROUTER": "$ROUTER"}}}}
EOF
SYS="$D/agent_system_see.txt"; [ "$MODE" = blind ] && SYS="$D/agent_system_blind.txt"
{ echo '---'; echo 'description: Computer-use agent on the demo desktop (desk tools only).'; echo 'mode: primary';
  echo 'tools:'; echo '  bash: false'; echo '  edit: false'; echo '  write: false'; echo '  read: false';
  echo '  grep: false'; echo '  glob: false'; echo '  webfetch: false'; echo '  todowrite: false';
  echo '  task: false'; echo '---'; cat "$SYS";
  echo ''; echo 'Work in at most 40 tool actions, then call done.'; } > "$RDIR/.opencode/agent/desk-${PREFIX}.md"
TASK=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['meta']['task'])" "$SCN")
(cd "$RDIR" && env -u CLAUDECODE -u CLAUDE_CODE_ENTRYPOINT opencode run "$TASK" --model "$MODEL" \
   --agent "desk-${PREFIX}" --pure --format json > "$OUTD.agent.jsonl" 2> "$OUTD.agent.err")
echo "agent exit $?"
curl -s -X POST "127.0.0.1:$PORT/save?name=$NAME"; echo
curl -s -m 3 -X POST "127.0.0.1:$PORT/quit" > /dev/null; wait $STAGE 2>/dev/null
