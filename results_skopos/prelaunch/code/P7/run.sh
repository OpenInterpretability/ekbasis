#!/bin/bash
# P7, chains that start from an image: image_chain.py (ported, CHANGES.diff) with the release run's settings
# (run_release_w4a5_bf16.sh line 43: N=30 PAR=16) against the API serving <tag>.   bash P7/run.sh <tag>
set -eu
. "$(dirname "$0")/../common/env.sh"; . "$PRE/common/serve.sh"
TAG=$1; served_is "$(model_of "$TAG")"
O=$OUTROOT/P7/$TAG; mkdir -p "$O"
CQ_URL=$URL/v1/systemone N=30 PAR=16 OUT_JSON=$O/image_chain.json "$PY" "$PRE/P7/image_chain.py" > "$O/image_chain.out" 2>&1
cat "$O/image_chain.out"
