#!/bin/bash
# WS-RA2: one real agent session on a real app (copy of RA's run_agent_ra.sh with RA2's stage, spec server and modes).
#   MODE: blind | guard | guard_goal | guard_alt | ask_ekbasis | ask_always   (no foresee tool in any of them)
#   run_agent_ra2.sh <run_ctx.json> <out_prefix> <mode> <model>      (env: MAXT max turns, MAX_THINKING_TOKENS passes through)
set -u
H="$(cd "$(dirname "$0")" && pwd)"; RA="$(cd "$H/../../RA" && pwd)"
CTX="$1"; OUT="$2"; MODE="$3"; MODEL="${4:-haiku}"
case "$MODE" in blind) FM=none; SYSF=agent_system_blind.txt;; guard) FM=guard; SYSF=agent_system_guard.txt;; guard_goal) FM=guard_goal; SYSF=agent_system_guard.txt;;
  guard_alt) FM=guard_alt; SYSF=agent_system_guard_alt.txt;; ask_ekbasis) FM=ask_ekbasis; SYSF=agent_system_ask.txt;; ask_always) FM=ask_always; SYSF=agent_system_ask.txt;;
  *) echo "bad mode $MODE"; exit 2;; esac
PORT=$(python3 -c "import socket
for _ in range(500):
  s=socket.socket(); s.bind(('127.0.0.1',0)); p=s.getsockname()[1]; s.close()
  if not 47100<=p<=47900: print(p); break")
mkdir -p "$(dirname "$OUT")"
node "$H/stage_ra2.mjs" --run "$CTX" --port "$PORT" --mode "$FM" > "$OUT.stage.log" 2>&1 &
STAGE=$!
for i in $(seq 1 120); do curl -sf -m 3 -X POST "127.0.0.1:$PORT/look" > /dev/null && break; sleep 0.5; done
WD="$OUT.cwd"; mkdir -p "$WD"
cat > "$WD/mcp.json" <<JSON
{"mcpServers": {"web": {"command": "node", "args": ["$RA/harness/agent_mcp_real.mjs"], "env": {"STAGE_URL": "http://127.0.0.1:$PORT", "BLIND": "1"}}}}
JSON
SYS="$(cat "$H/$SYSF")"
TASK=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['task'])" "$CTX")
TOOLS="mcp__web__look,mcp__web__click,mcp__web__type_text,mcp__web__select_option,mcp__web__press_key,mcp__web__goto,mcp__web__say,mcp__web__done"
(cd "$WD" && env -u CLAUDECODE -u CLAUDE_CODE_ENTRYPOINT claude -p "$TASK" --model "$MODEL" --tools "" \
   --mcp-config mcp.json --strict-mcp-config --allowedTools "$TOOLS" \
   --append-system-prompt "$SYS" --output-format stream-json --verbose --max-turns "${MAXT:-40}" --no-session-persistence \
   --setting-sources project,local > "$OUT.agent.jsonl" 2> "$OUT.agent.err")
echo "agent exit $?"
OUTQ=$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))" "$OUT.session.json")
curl -s -m 30 -X POST "127.0.0.1:$PORT/save?out=$OUTQ" > /dev/null
curl -s -m 5 -X POST "127.0.0.1:$PORT/quit" > /dev/null; wait $STAGE 2>/dev/null
rm -rf "$WD"
