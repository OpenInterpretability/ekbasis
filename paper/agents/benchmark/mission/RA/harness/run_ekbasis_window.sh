#!/bin/bash
# WS-RA (addenda F, G): when the Ekbasis replica answers again on rig :8544 (GPU 2), run every remaining run that needs it
# FIRST: pause the no-Ekbasis queue at its next job (logs/pause_nonekbasis), wait for in-flight Claude runs to end (<= 3
# Claude agents), run the Ekbasis steps in the registered order, then lift the pause and resume the no-Ekbasis queue.
# Each step pauses by itself if the replica goes down again (resumable: re-run this script).
set -u
H="$(cd "$(dirname "$0")" && pwd)"; RA="$(cd "$H/.." && pwd)"; cd "$RA"
# if the replica is still up when this starts (a GPU slot is about to take it), wait for it to go down first
if [ "${WAIT_DOWN:-0}" = 1 ]; then
  while curl -sf -m 20 127.0.0.1:8781/health | grep -q '"ok": true'; do sleep 30; done
  echo "$(date -u +%H:%M:%S) Ekbasis went down (GPU slot); waiting for it to come back"
fi
until curl -sf -m 20 127.0.0.1:8781/health | grep -q '"ok": true'; do
  "$H/services.sh" start > /dev/null 2>&1   # restarts only our own tunnel / bridge if they died; never anything on the rig
  sleep 30
done
echo "$(date -u +%H:%M:%S) Ekbasis is up"
# the plan's usage limit (HTTP 429) resets at NOT_BEFORE_UTC (HH:MM): wait until then before launching agents
if [ -n "${NOT_BEFORE_UTC:-}" ]; then
  until [ "$(date -u +%H%M)" \> "$(echo "$NOT_BEFORE_UTC" | tr -d :)" ]; do sleep 20; done
  echo "$(date -u +%H:%M:%S) past $NOT_BEFORE_UTC UTC (usage limit reset)"
fi
touch logs/pause_nonekbasis
while ps -ax -o command= | grep -v grep | grep -q -- "--setting-sources project,local"; do sleep 15; done
echo "$(date -u +%H:%M:%S) no Claude run in flight; starting the Ekbasis runs"
run() { echo "$(date -u +%H:%M:%S) START $*"; python3 harness/run_study_ra.py --parallel 3 --cap 40 "$@"; echo "$(date -u +%H:%M:%S) END $*"; }
run --agent haiku0 --conds see --seeds 1 2 --prefix h
run --agent haiku0 --conds guard --seeds 1 2 --prefix h
run --agent sonnet --conds guard --seeds 1 --prefix s
run --agent haiku0 --conds guard_goal --seeds 1 --prefix h
run --agent sonnet --conds see --seeds 1 --prefix s --tasks harm
run --agent haiku0 --conds guard_goal --seeds 2 --prefix h
echo "$(date -u +%H:%M:%S) EKBASIS WINDOW RUNS DONE"
rm -f logs/pause_nonekbasis
exec "$H/run_all_claude2.sh"
