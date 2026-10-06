#!/bin/bash
# WS-RA addendum E: Qwen 3.5 9B blind / see / guard x 2 repetitions on all 32 tasks (free), in parallel with the Claude
# queue; Qwen 3.5 4B blind / see / guard x 1 only if Caio's server at rig :30193 is up (never restarted by us).
set -u
H="$(cd "$(dirname "$0")" && pwd)"; RA="$(cd "$H/.." && pwd)"; cd "$RA"
p=$(cat logs/pids/study_q.pid 2>/dev/null); while [ -n "$p" ] && kill -0 "$p" 2>/dev/null; do sleep 20; done
run() { echo "$(date -u +%H:%M:%S) START $*"; python3 harness/run_study_ra.py --parallel 2 --cap 40 "$@"; echo "$(date -u +%H:%M:%S) END $*"; }
run --agent qwen9b --conds blind see guard --seeds 1 2 --prefix q
if curl -sf -m 10 127.0.0.1:18596/v1/models > /dev/null; then
  run --agent qwen4b --conds blind see guard --seeds 1 --prefix q4
else
  echo "$(date -u +%H:%M:%S) Qwen 4B server (rig :30193) is down: 4B runs skipped"
fi
echo "$(date -u +%H:%M:%S) ALL QWEN RUNS DONE"
