#!/bin/bash
# Tool-guard agent study: one GLM-5.3-Flash session (opencode, desk tools only, the blind system prompt) on the demo
# desktop, with the desk MCP server behind the condition's guard. Adapted from mission/X/agent/run_agent_glm_cb.sh
# (same stage, same agent config); stage_tg.mjs and agent_mcp_tg.mjs add the guard-only read tools.
#   run_agent_tg.sh <scenario.json> <session-name> <A|B|C|D|Cinj>
# env: LV (the harness's launch_video), XAGENT (mission/X/agent), GLM_* as in the earlier runs, EKB_SRC (this repo).
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
LV="${LV:-/Volumes/SSD Major/news/decision_model/launch_video}"; XAGENT="${XAGENT:-/Volumes/SSD Major/news/decision_model/mission/X/agent}"
EKB_SRC="${EKB_SRC:-$(cd "$HERE/../.." && pwd)}"
cd "$LV"
SCN="$1"; NAME="$2"; COND="$3"
MODEL="${GLM_MODEL:?}"; PREFIX="${GLM_PREFIX:-tgrun}"
PORT=$(python3 -c "import socket,random
for _ in range(200):
  p=random.randrange(47100,47900,2); ok=True
  for q in (p,p+1):
    s=socket.socket()
    try: s.bind(('127.0.0.1',q))
    except OSError: ok=False
    finally: s.close()
  if ok: print(p); break")
mkdir -p "sessions/$(dirname "$NAME")" agent_cwd
WEB_ROOT="$XAGENT/web" FORESEE_MODE=placebo node stage_tg.mjs "$SCN" --port "$PORT" > "sessions/$NAME.stage.log" 2>&1 &
STAGE=$!
for i in $(seq 1 60); do curl -sf -m 2 -X POST "127.0.0.1:$PORT/look" > /dev/null && break; sleep 0.5; done
RDIR="agent_cwd/${PREFIX}_${NAME//\//_}"
OUTD="$LV/sessions/$NAME"; mkdir -p "$RDIR/.opencode/agent"
TASK=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['meta']['task'])" "$SCN")
GLOG="$OUTD.guard.jsonl"; rm -f "$GLOG"
INSPECT=0; BACKEND=0; INJECT=""
case "$COND" in C|Cinj) INSPECT=1;; D) BACKEND=1;; esac
[ "$COND" = Cinj ] && INJECT="${TG_INJECT:?}"
SERVER="\"node\", \"$LV/agent_mcp_tg.mjs\""
case "$COND" in
  A) CMD="$SERVER";;
  *) CMD="\"bash\", \"$HERE/guard_launch.sh\", \"$COND\", \"$GLOG\", \"--\", $SERVER";;
esac
python3 - "$RDIR/opencode.json" "$CMD" "$PORT" "$INSPECT" "$BACKEND" "$INJECT" "$TASK" "$EKB_SRC" <<'PY'
import json, os, sys
out, cmd, port, inspect, backend, inject, task, src = sys.argv[1:]
cfg = {"$schema": "https://opencode.ai/config.json",
       "provider": {os.environ.get("GLM_PID", "qwen35"): {"npm": "@ai-sdk/openai-compatible", "name": os.environ.get("GLM_PNAME", "GLM"),
                    "options": {"baseURL": os.environ["GLM_BASEURL"], "apiKey": "{env:GLM_API_KEY}"},
                    "models": {os.environ["GLM_MID"]: {"limit": {"context": int(os.environ.get("GLM_CTX", "32768")), "output": 4096}}}}},
       "mcp": {"desk": {"type": "local", "command": json.loads("[" + cmd + "]"), "timeout": 60000,
                        "environment": {"STAGE_URL": f"http://127.0.0.1:{port}", "BLIND": "1", "ROUTER": "0",
                                        "INSPECT": inspect, "BACKEND": backend, "INJECT": inject,
                                        "TG_REQUEST": task, "EKB_SRC": src}}}}
json.dump(cfg, open(out, "w"), indent=1)
PY
{ echo '---'; echo 'description: Computer-use agent on the demo desktop (desk tools only).'; echo 'mode: primary';
  echo 'tools:'; echo '  bash: false'; echo '  edit: false'; echo '  write: false'; echo '  read: false';
  echo '  grep: false'; echo '  glob: false'; echo '  webfetch: false'; echo '  todowrite: false';
  echo '  task: false'; echo '---'; cat "$LV/agent_system_blind.txt";
  echo ''; echo 'Work in at most 40 tool actions, then call done.'; } > "$RDIR/.opencode/agent/desk-${PREFIX}.md"
(cd "$RDIR" && env -u CLAUDECODE -u CLAUDE_CODE_ENTRYPOINT opencode run "$TASK" --model "$MODEL" \
   --agent "desk-${PREFIX}" --pure --format json > "$OUTD.agent.jsonl" 2> "$OUTD.agent.err" < /dev/null)
echo "agent exit $?"
curl -s -X POST "127.0.0.1:$PORT/save?name=$NAME"; echo
curl -s -m 3 -X POST "127.0.0.1:$PORT/quit" > /dev/null; wait $STAGE 2>/dev/null
