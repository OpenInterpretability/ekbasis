#!/bin/bash
# WS-RA, coordinator 2026-10-06 (GPUs go to training): the Claude conditions that need the Ekbasis replica (see, guard)
# run first while rig :8544 is up; the ones that do not need it (blind, docs, placebo, facts, oracle_llm: the adapter is
# local) follow. Each step pauses by itself when the replica goes down (run_study_ra.py checks before every Ekbasis run);
# resumable: re-running this script skips every judged run. <= 3 Claude agents at a time; safety stop US$40.
set -u
H="$(cd "$(dirname "$0")" && pwd)"; RA="$(cd "$H/.." && pwd)"; cd "$RA"
p=$(cat logs/pids/study_current_claude.pid 2>/dev/null); while [ -n "$p" ] && kill -0 "$p" 2>/dev/null; do sleep 20; done
run() { echo "$(date -u +%H:%M:%S) START $*"; python3 harness/run_study_ra.py --parallel 3 --cap 40 "$@"; echo "$(date -u +%H:%M:%S) END $*"; }
run --agent haiku0 --conds blind see --seeds 1 2 --prefix h                 # H1 (finishes anything left of reps 1-2)
run --agent haiku0 --conds guard --seeds 1 2 --prefix h                     # needs Ekbasis
run --agent sonnet --conds guard --seeds 1 --prefix s                       # needs Ekbasis
run --agent sonnet --conds see --seeds 1 --prefix s --tasks harm            # needs Ekbasis
run --agent sonnet --conds blind --seeds 1 2 --prefix s                     # H2 (no Ekbasis needed)
run --agent haiku0 --conds docs --seeds 1 --prefix h --tasks harm
run --agent haiku0 --conds placebo --seeds 1 --prefix h --tasks harm
run --agent haiku0 --conds facts --seeds 1 --prefix h --tasks harm
harness/services.sh start oracle > /dev/null
run --agent haiku0 --conds oracle_llm --seeds 1 --prefix h --tasks harm
echo "$(date -u +%H:%M:%S) ALL CLAUDE RUNS DONE (any step that paused for the Ekbasis replica is listed above)"
