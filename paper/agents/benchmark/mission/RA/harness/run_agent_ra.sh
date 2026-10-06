#!/bin/bash
# WS-RA: one real agent session on a real app. Port of mission/X/agent/run_agent_x.sh: the stage (headless browser on the
# seeded app, signed in) for a run context, then Claude Code in print mode with ONLY the web tools (no shell, no files),
# then the session is saved. MODE: blind | see | placebo | facts | oracle_llm | docs
#   blind/docs: no foresee tool (docs adds the app's frozen rules to the system prompt)
#   see/placebo/facts/oracle_llm: the same foresee tool and the same "see" system prompt; only what foresee returns differs
#   run_agent_ra.sh <run_ctx.json> <out_prefix> <mode> <model>      (env: MAXT max turns, MAX_THINKING_TOKENS passes through)
set -u
H="$(cd "$(dirname "$0")" && pwd)"; RA="$(cd "$H/.." && pwd)"
CTX="$1"; OUT="$2"; MODE="$3"; MODEL="${4:-haiku}"
case "$MODE" in see) FM=model;; placebo) FM=placebo;; facts) FM=facts;; oracle_llm) FM=oracle_llm;; guard) FM=guard;; guard_goal) FM=guard_goal;; blind|docs) FM=none;; *) echo "bad mode $MODE"; exit 2;; esac
PORT=$(python3 -c "import socket
for _ in range(500):
  s=socket.socket(); s.bind(('127.0.0.1',0)); p=s.getsockname()[1]; s.close()
  if not 47100<=p<=47900: print(p); break")
mkdir -p "$(dirname "$OUT")"
node "$H/stage_real.mjs" --run "$CTX" --port "$PORT" --mode "$FM" > "$OUT.stage.log" 2>&1 &
STAGE=$!
for i in $(seq 1 120); do curl -sf -m 3 -X POST "127.0.0.1:$PORT/look" > /dev/null && break; sleep 0.5; done
BLIND=0; { [ "$FM" = none ] || [ "$FM" = guard ] || [ "$FM" = guard_goal ]; } && BLIND=1
WD="$OUT.cwd"; mkdir -p "$WD"
cat > "$WD/mcp.json" <<EOF
{"mcpServers": {"web": {"command": "node", "args": ["$H/agent_mcp_real.mjs"], "env": {"STAGE_URL": "http://127.0.0.1:$PORT", "BLIND": "$BLIND"}}}}
EOF
SYS="$(cat "$H/agent_system_see_ra.txt")"; [ "$FM" = none ] && SYS="$(cat "$H/agent_system_blind_ra.txt")"; { [ "$FM" = guard ] || [ "$FM" = guard_goal ]; } && SYS="$(cat "$H/agent_system_guard_ra.txt")"
if [ "$MODE" = docs ]; then
  APP=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['app'])" "$CTX")
  SYS="$SYS

$(python3 "$H/app_docs.py" "$APP")"
fi
TASK=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['task'])" "$CTX")
TOOLS="mcp__web__look,mcp__web__click,mcp__web__type_text,mcp__web__select_option,mcp__web__press_key,mcp__web__goto,mcp__web__say,mcp__web__done"
[ "$BLIND" = 1 ] || TOOLS="$TOOLS,mcp__web__foresee"
(cd "$WD" && env -u CLAUDECODE -u CLAUDE_CODE_ENTRYPOINT claude -p "$TASK" --model "$MODEL" --tools "" \
   --mcp-config mcp.json --strict-mcp-config --allowedTools "$TOOLS" \
   --append-system-prompt "$SYS" --output-format stream-json --verbose --max-turns "${MAXT:-40}" --no-session-persistence \
   --setting-sources project,local > "$OUT.agent.jsonl" 2> "$OUT.agent.err")
echo "agent exit $?"
OUTQ=$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))" "$OUT.session.json")
curl -s -m 30 -X POST "127.0.0.1:$PORT/save?out=$OUTQ" > /dev/null
curl -s -m 5 -X POST "127.0.0.1:$PORT/quit" > /dev/null; wait $STAGE 2>/dev/null
rm -rf "$WD"
