#!/bin/bash
# WS-RA exploratory agents: Qwen 3.5 9B (default) or 4B (Caio's GLM-session vLLM servers on the rig, through our own
# tunnels :18595 -> :30194 and :18596 -> :30193) driven by opencode with ONLY the web tools, exactly like
# mission/X/agent/run_agent_glm.sh. MODE: blind | see | guard. Free (no API spend).
#   QWEN_BASEURL / QWEN_MODEL / QWEN_NAME select the model;  run_agent_ra_qwen.sh <run_ctx.json> <out_prefix> <blind|see|guard>
set -u
H="$(cd "$(dirname "$0")" && pwd)"; RA="$(cd "$H/.." && pwd)"
CTX="$1"; OUT="$2"; MODE="${3:-see}"
FM=none; [ "$MODE" = see ] && FM=model; [ "$MODE" = guard ] && FM=guard
QB="${QWEN_BASEURL:-http://127.0.0.1:18595/v1}"; QM="${QWEN_MODEL:-qwen35-9b}"; QN="${QWEN_NAME:-Qwen3.5-9B}"
PORT=$(python3 -c "import socket
for _ in range(500):
  s=socket.socket(); s.bind(('127.0.0.1',0)); p=s.getsockname()[1]; s.close()
  if not 47100<=p<=47900: print(p); break")
mkdir -p "$(dirname "$OUT")"
node "$H/stage_real.mjs" --run "$CTX" --port "$PORT" --mode "$FM" > "$OUT.stage.log" 2>&1 &
STAGE=$!
for i in $(seq 1 120); do curl -sf -m 3 -X POST "127.0.0.1:$PORT/look" > /dev/null && break; sleep 0.5; done
BLIND=1; [ "$FM" = model ] && BLIND=0
WD="$OUT.cwd"; mkdir -p "$WD/.opencode/agent"
cat > "$WD/opencode.json" <<EOF
{"\$schema": "https://opencode.ai/config.json", "provider": {"qwen35ra": {"npm": "@ai-sdk/openai-compatible", "name": "$QN", "options": {"baseURL": "$QB"}, "models": {"$QM": {"limit": {"context": 16384, "output": 4096}}}}},
 "mcp": {"web": {"type": "local", "command": ["node", "$H/agent_mcp_real.mjs"], "environment": {"STAGE_URL": "http://127.0.0.1:$PORT", "BLIND": "$BLIND"}}}}
EOF
SYS="$H/agent_system_see_ra.txt"; [ "$BLIND" = 1 ] && SYS="$H/agent_system_blind_ra.txt"; [ "$FM" = guard ] && SYS="$H/agent_system_guard_ra.txt"
{ echo '---'; echo 'description: Computer-use agent in a web browser (web tools only).'; echo 'mode: primary';
  echo 'tools:'; for t in bash edit write read grep glob webfetch todowrite task list patch; do echo "  $t: false"; done; echo '---'; cat "$SYS";
  echo ''; echo 'Work in at most 40 tool actions, then call done.'; } > "$WD/.opencode/agent/web-ra.md"
TASK=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['task'])" "$CTX")
(cd "$WD" && env -u CLAUDECODE -u CLAUDE_CODE_ENTRYPOINT timeout 900 opencode run "$TASK" --model "qwen35ra/$QM" \
   --agent web-ra --pure --format json > "$OUT.agent.jsonl" 2> "$OUT.agent.err")
echo "agent exit $?"
OUTQ=$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))" "$OUT.session.json")
curl -s -m 30 -X POST "127.0.0.1:$PORT/save?out=$OUTQ" > /dev/null
curl -s -m 5 -X POST "127.0.0.1:$PORT/quit" > /dev/null; wait $STAGE 2>/dev/null
rm -rf "$WD"
