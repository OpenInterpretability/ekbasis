#!/bin/bash
# WS-RA addendum E: every registered Claude condition on all its tasks, one runner at a time (<= 3 Claude agents in
# parallel), H1/H2 first. Waits for the runner already going (logs/pids/study_h.pid). Safety stop US$40 (runner --cap).
set -u
H="$(cd "$(dirname "$0")" && pwd)"; RA="$(cd "$H/.." && pwd)"; cd "$RA"
p=$(cat logs/pids/study_h.pid 2>/dev/null); while [ -n "$p" ] && kill -0 "$p" 2>/dev/null; do sleep 20; done
run() { echo "$(date -u +%H:%M:%S) START $*"; python3 harness/run_study_ra.py --parallel 3 --cap 40 "$@"; echo "$(date -u +%H:%M:%S) END $*"; }
run --agent sonnet --conds blind --seeds 1 --prefix s                       # H2
run --agent haiku0 --conds blind see --seeds 2 --prefix h                   # H1, second repetition
run --agent sonnet --conds blind --seeds 2 --prefix s                       # H2, second repetition
run --agent haiku0 --conds guard --seeds 1 2 --prefix h
run --agent sonnet --conds guard --seeds 1 --prefix s
run --agent haiku0 --conds docs --seeds 1 --prefix h --tasks harm
run --agent haiku0 --conds placebo --seeds 1 --prefix h --tasks harm
run --agent haiku0 --conds facts --seeds 1 --prefix h --tasks harm
run --agent sonnet --conds see --seeds 1 --prefix s --tasks harm
harness/services.sh start oracle > /dev/null
run --agent haiku0 --conds oracle_llm --seeds 1 --prefix h --tasks harm
echo "$(date -u +%H:%M:%S) ALL CLAUDE RUNS DONE"
