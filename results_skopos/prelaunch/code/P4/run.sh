#!/bin/bash
# P4, predict, observe, correct: long_chain3.py (ported, CHANGES.diff) with the three runs of the release
# (run_release_w4a5_bf16.sh lines 45-51, same ONLY / N / OLD_N / PAR / TRACE), concurrently as there, against the API
# serving <tag>. The rules run is what results/release_eval/long_chain3.jsonl publishes.   bash P4/run.sh <tag>
set -eu
. "$(dirname "$0")/../common/env.sh"; . "$PRE/common/serve.sh"
TAG=$1; served_is "$(model_of "$TAG")"
O=$OUTROOT/P4/$TAG; mkdir -p "$O"; rm -f "$O"/long_chain3_*.jsonl   # the script appends
U=$URL/v1/systemone; S=$PRE/P4/long_chain3.py
RULES=$( { for m in text obs50 conf0.5 conf0.9 step0.9 dual dual_conf0.9 until0.5 check0.5 until0.9 check0.9; do printf "cards:%s," $m; done
           for f in toggles machines jugs; do for m in text conf0.5 conf0.9 step0.9 until0.5 check0.5 until0.9 check0.9; do printf "%s:%s," $f $m; done; done; } )
CQ_URL=$U N=8 PAR=64 TRACE=1 ONLY=$RULES OUT=$O/long_chain3_rules.jsonl "$PY" "$S" > "$O/long_chain3_rules.out" 2>&1 &
FRESH=$(for f in cards toggles machines jugs; do for m in conf0.5 check0.9; do printf "%s:%s," $f $m; done; done)
CQ_URL=$U OLD_N=8 N=48 PAR=64 TRACE=1 ONLY=$FRESH OUT=$O/long_chain3_fresh.jsonl "$PY" "$S" > "$O/long_chain3_fresh.out" 2>&1 &
TEXT=$(for f in cards toggles machines jugs; do printf "%s:text," $f; done)
CQ_URL=$U OLD_N=8 N=16 PAR=32 TRACE=1 ONLY=$TEXT OUT=$O/long_chain3_fresh_text.jsonl "$PY" "$S" > "$O/long_chain3_fresh_text.out" 2>&1 &
wait
for f in rules fresh fresh_text; do tail -2 "$O/long_chain3_$f.out"; done
