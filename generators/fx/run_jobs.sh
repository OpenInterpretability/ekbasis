#!/bin/bash
# WS-FX generation driver: one family/part at a time (fx_run.py, 64 workers); skips outputs that already exist.
set -u
cd /root/decis/mission/FX/factory
D=/root/decis/mission/FX/data/raw; mkdir -p $D
/usr/bin/python3 /root/decis/mission/FX/plan_jobs.py "$@" | while read fam part cap workers; do
  out=$D/${fam}__${part}.jsonl.gz
  [ -f $out ] && { echo "$(date -u +%H:%M:%S) skip $fam $part"; continue; }
  echo "$(date -u +%H:%M:%S) start $fam $part cap $cap"
  /usr/bin/python3 fx_run.py $fam $part $cap $out ${workers:-64} 200000 || echo "$(date -u +%H:%M:%S) FAILED $fam $part"
done
echo "$(date -u +%H:%M:%S) JOBS DONE $*"
