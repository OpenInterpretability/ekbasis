#!/bin/bash
# P1, the 240-question git comparison: release_eval_extra.py (ported, CHANGES.diff) against the API serving <tag>, as
# run_v43_release_eval.sh ran it for the release (URL, PAR=48, OUT). It also answers ftest_family first (the same script).
#   bash P1/run.sh <tag>      (skopos_bf16 | ekbasis_bf16 for the identity check against the published predictions)
set -eu
. "$(dirname "$0")/../common/env.sh"; . "$PRE/common/serve.sh"
TAG=$1; served_is "$(model_of "$TAG")"
O=$OUTROOT/P1/$TAG; mkdir -p "$O"
URL=$URL PAR=48 OUT=$O DATA=$DATA "$PY" "$PRE/P1/release_eval_extra.py" > "$O/run.log" 2>&1
tail -3 "$O/run.log"
