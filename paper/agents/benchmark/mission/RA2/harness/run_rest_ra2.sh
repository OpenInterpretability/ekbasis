#!/bin/bash
# WS-RA2 addendum B: the runs the US$25 cap left out, uncapped (--cap inf; the ledger keeps every cost), in the
# pre-registered order. Each step is repeated until the runner reports "0 runs to do"; HTTP 429 (plan usage limit) ->
# wait 20 min (the run was not recorded and is redone); Ekbasis bridge down -> restart own services, wait 5 min.
set -u
H="$(cd "$(dirname "$0")" && pwd)"; R2="$(cd "$H/.." && pwd)"; cd "$R2"
NB="${NOT_BEFORE_UTC:-2121}"
until [ "$(date -u +%H%M)" -ge "$NB" ]; do sleep 30; done
echo "$(date -u +%H:%M:%S) past ${NB} UTC (usage-limit reset)"
step() {
  for attempt in $(seq 1 40); do
    echo "$(date -u +%H:%M:%S) START $* (attempt $attempt)"
    python3 harness/run_study_ra2.py --parallel 3 --cap inf "$@" > logs/rest_last.log 2>&1; cat logs/rest_last.log
    echo "$(date -u +%H:%M:%S) END $*"
    if head -1 logs/rest_last.log | grep -q "^0 runs to do"; then return 0; fi
    if grep -q -E "usage limit hit|agent API error" logs/rest_last.log; then echo "usage limit: waiting 20 min"; sleep 1200; continue; fi
    if grep -q "Ekbasis bridge is down" logs/rest_last.log; then echo "Ekbasis down: restarting own services, waiting 5 min"; "$H/services.sh" start > /dev/null 2>&1; sleep 300; continue; fi
  done
  echo "$(date -u +%H:%M:%S) GAVE UP after 40 attempts: $*"
}
step --agent haiku0 --conds guard_goal --seeds 1 2 --prefix h
step --agent sonnet --conds blind guard_goal ask_ekbasis --seeds 1 --prefix s
echo "$(date -u +%H:%M:%S) RA2 REST CHAIN DONE"
