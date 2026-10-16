#!/bin/bash
# P6, Portuguese: pt_eval_api.py (ported, CHANGES.diff: paths, and the per-item answers saved) against the API serving
# <tag>. Ekbasis-27B's per-item answers were not kept, so it is re-run here (bash P6/run.sh ekbasis_bf16).
set -eu
. "$(dirname "$0")/../common/env.sh"; . "$PRE/common/serve.sh"
TAG=$1; served_is "$(model_of "$TAG")"
O=$OUTROOT/P6/$TAG; mkdir -p "$O"
CQ_URL=$URL/v1/systemone OUT_JSONL=$O/pt_items.jsonl "$PY" "$PRE/P6/pt_eval_api.py" > "$O/pt.out" 2>&1
tail -5 "$O/pt.out"
