#!/bin/bash
# P3, long chains (text / image / image + look again): long_chain2.py (ported, CHANGES.diff) with the release run's
# settings (run_release_w4a5_bf16.sh line 44: N=6 PAR=48), against the API serving <tag>.   bash P3/run.sh <tag>
set -eu
. "$(dirname "$0")/../common/env.sh"; . "$PRE/common/serve.sh"
TAG=$1; served_is "$(model_of "$TAG")"
O=$OUTROOT/P3/$TAG; mkdir -p "$O"; rm -f "$O/long_chain.jsonl"   # the script appends
CQ_URL=$URL/v1/systemone N=6 PAR=48 OUT=$O/long_chain.jsonl OUT_JSON=$O/long_chain.json "$PY" "$PRE/P3/long_chain2.py" > "$O/long_chain.out" 2>&1
tail -20 "$O/long_chain.out"
