#!/bin/bash
# P8, short checks, two wordings (accuracy): short_eval_release.py acc (ported, CHANGES.diff; PAR 16 as the release
# run) against the API serving <tag>. Its timing part runs in P5/run.sh (alone on the GPU).   bash P8/run.sh <tag>
set -eu
. "$(dirname "$0")/../common/env.sh"; . "$PRE/common/serve.sh"
TAG=$1; served_is "$(model_of "$TAG")"
O=$OUTROOT/P8/$TAG; mkdir -p "$O"
[ -f "$O/short_eval_saved.json" ] && [ -f "$O/deviation.json" ] || "$PY" "$PRE/P8/make_saved.py" "$O/short_eval_saved.json"
CQ_URL=$URL/v1/systemone SAVED_JSON=$O/short_eval_saved.json OUT_JSON=$O/short_eval_release.json \
  "$PY" "$PRE/P8/short_eval_release.py" acc > "$O/short_acc.out" 2>&1
"$PY" -c "import json, sys; print(json.load(open(sys.argv[1]))['deviation'])" "$O/deviation.json" | tee -a "$O/short_acc.out"
head -12 "$O/short_acc.out"
