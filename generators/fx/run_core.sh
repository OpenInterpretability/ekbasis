#!/bin/bash
# WS-FX core families: WS-F generators with new seeds, one family at a time, train cap 5000 rows + val cap 250 rows.
set -u
cd /root/decis/mission/FX/factory
D=/root/decis/mission/FX/data/raw; mkdir -p $D
FAMS=$(/usr/bin/python3 -c "from fx_registry import CORE; print(\" \".join(CORE))")
for fam in $FAMS; do
  for part in train val; do
    cap=5000; [ $part = val ] && cap=250
    out=$D/${fam}__${part}.jsonl.gz
    [ -f $out ] && { echo "$(date -u +%H:%M:%S) skip $fam $part (exists)"; continue; }
    echo "$(date -u +%H:%M:%S) start $fam $part"
    /usr/bin/python3 fx_run.py $fam $part $cap $out 64 60000 || echo "$(date -u +%H:%M:%S) FAILED $fam $part rc $?"
  done
done
echo "$(date -u +%H:%M:%S) CORE DONE"
