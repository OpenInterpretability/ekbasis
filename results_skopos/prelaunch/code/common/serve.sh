# Serving for the pre-launch runners, exactly as the Skopos release read served its builds (serve_r4.sh): the model
# folder's serve_vllm.sh on $VLLM_PORT at 0.85 of the GPU, then the folder's serve.py on $API_PORT in front of it.
# Source after env.sh.  serve_up <model_dir> <tag>   serve_down   served_is <model_dir>
# Every failure stops the caller loudly (exit 1); processes are stopped by their own PID (command line checked).

_pidcmd() { tr "\0" " " < "/proc/$1/cmdline" 2>/dev/null; }

serve_down() {
  local f p want
  for f in "$LOGS/front.pid" "$LOGS/vllm.pid"; do
    [ -f "$f" ] || continue
    p=$(cut -d' ' -f1 "$f"); want=$(cut -d' ' -f2- "$f")
    if [ -n "$p" ] && _pidcmd "$p" | grep -qF "$want"; then
      kill "$p"; for i in $(seq 1 60); do [ -d "/proc/$p" ] || break; sleep 2; done
      [ -d "/proc/$p" ] && kill -- -"$p" 2>/dev/null   # setsid made it a group leader: its EngineCore children too
    fi
    rm -f "$f"
  done
  for i in $(seq 1 30); do [ -z "$(nvidia-smi -i "$GPU" --query-compute-apps=pid --format=csv,noheader 2>/dev/null)" ] && break; sleep 3; done
  for p in $(pgrep -f "^VLLM::EngineCore"); do echo "serve_down: engine $p left running: stopped"; kill "$p"; done   # FIX 2026-10-16
  for i in $(seq 1 60); do   # the GPU is free again before the next build starts
    [ -z "$(nvidia-smi -i "$GPU" --query-compute-apps=pid --format=csv,noheader 2>/dev/null)" ] && return 0; sleep 3
  done
  echo "serve_down: GPU $GPU still has compute processes:"; nvidia-smi -i "$GPU"; exit 1
}

serve_up() {
  local M=$1 TAG=$2
  [ -f "$M/serve_vllm.sh" ] && [ -f "$M/serve.py" ] || { echo "serve_up: $M is not a model folder"; exit 1; }
  serve_down
  ( cd "$M" && CUDA_VISIBLE_DEVICES=$GPU setsid bash serve_vllm.sh "$M" "$VLLM_PORT" 0.85 > "$LOGS/vllm_$TAG.log" 2>&1 < /dev/null &
  )   # FIX 2026-10-16: the pid file gets the real vLLM pid below, not the launching subshell's $!
  for i in $(seq 1 180); do curl -sf "localhost:$VLLM_PORT/v1/models" > /dev/null && break; sleep 10; done
  curl -sf "localhost:$VLLM_PORT/v1/models" > /dev/null || { echo "VLLM DID NOT START ($TAG)"; tail -20 "$LOGS/vllm_$TAG.log"; exit 1; }
  echo "$(pgrep -f "^/usr/bin/python3 /usr/local/bin/vllm serve $M " | head -1) vllm serve $M" > "$LOGS/vllm.pid"
  ( cd "$M" && setsid "$PY" serve.py --model "$M" --vllm-url "http://127.0.0.1:$VLLM_PORT" --port "$API_PORT" --host 127.0.0.1 \
      > "$LOGS/front_$TAG.log" 2>&1 < /dev/null &
  )
  for i in $(seq 1 60); do grep -q "ready at" "$LOGS/front_$TAG.log" && break; sleep 5; done
  grep -q "ready at" "$LOGS/front_$TAG.log" || { echo "SERVE.PY DID NOT START ($TAG)"; tail -20 "$LOGS/front_$TAG.log"; exit 1; }
  echo "$(pgrep -f "^$PY serve.py --model $M " | head -1) serve.py --model $M" > "$LOGS/front.pid"
  served_is "$M"
  { echo "== $TAG $(date -u +%FT%TZ)"; grep "ready at" "$LOGS/front_$TAG.log"; curl -s "$URL/health"; echo
    "$PY" -c "import vllm, torch, transformers; print('vllm', vllm.__version__, 'torch', torch.__version__, 'transformers', transformers.__version__)"
    nvidia-smi -i "$GPU" --query-gpu=name,memory.total,driver_version --format=csv,noheader; } >> "$LOGS/served.txt"
  echo "served $TAG $(date -u +%T)"
}

served_is() {   # the API answers for this model folder, or the caller stops
  local h; h=$(curl -s -m 10 "$URL/health")
  # serve.py's /health reports --model as given (serve.py: self.name = a.model)
  echo "$h" | "$PY" -c "import json, sys; h = json.load(sys.stdin); sys.exit(0 if h.get('ok') and str(h.get('model')).rstrip('/') == sys.argv[1].rstrip('/') else 1)" "$1" \
    || { echo "THE API AT $URL DOES NOT SERVE $1: $h"; exit 1; }
}
