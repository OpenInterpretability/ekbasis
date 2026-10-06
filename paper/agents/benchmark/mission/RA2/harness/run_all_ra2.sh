#!/bin/bash
# WS-RA2 study chain (SPEC §7 + addendum A order). Each step is resumable; on the plan's usage limit (HTTP 429) or an
# Ekbasis outage the step stops itself and this chain waits and re-runs it. The US$25 cap is enforced by the runner.
set -u
H="$(cd "$(dirname "$0")" && pwd)"; R2="$(cd "$H/.." && pwd)"; cd "$R2"
step() {
  for attempt in $(seq 1 30); do
    echo "$(date -u +%H:%M:%S) START $* (attempt $attempt)"
    python3 harness/run_study_ra2.py --parallel 3 --cap 25 "$@" > logs/step_last.log 2>&1; cat logs/step_last.log
    echo "$(date -u +%H:%M:%S) END $*"
    if grep -q "cap reached" logs/step_last.log; then echo "$(date -u +%H:%M:%S) CAP REACHED: stopping the chain"; echo "RA2 STUDY CHAIN DONE (cap)"; exit 0; fi
    if grep -q "usage limit hit" logs/step_last.log; then echo "usage limit: waiting 20 min"; sleep 1200; continue; fi
    if grep -q "Ekbasis bridge is down" logs/step_last.log; then echo "Ekbasis down: restarting own services, waiting 5 min"; "$H/services.sh" start > /dev/null 2>&1; sleep 300; continue; fi
    break
  done
}
step --agent haiku0 --conds blind ask_ekbasis ask_always --seeds 1 --prefix h
step --agent haiku0 --conds blind ask_ekbasis ask_always --seeds 2 --prefix h
step --agent haiku0 --conds guard guard_alt --seeds 1 --prefix h
step --agent haiku0 --conds guard guard_alt --seeds 2 --prefix h
step --agent haiku0 --conds guard_goal --seeds 1 2 --prefix h
step --agent sonnet --conds blind guard_goal ask_ekbasis --seeds 1 --prefix s
echo "RA2 STUDY CHAIN DONE"
