#!/bin/bash
# P12 preflight SUBSTITUTE (not the published measurement; replay_requests.py says why): the 423 recorded requests
# against the API serving <tag>.   bash P12/preflight_substitute/run.sh <tag>
set -eu
. "$(dirname "$0")/../../common/env.sh"; . "$PRE/common/serve.sh"
TAG=$1; served_is "$(model_of "$TAG")"
O=$OUTROOT/P12/preflight_substitute; mkdir -p "$O"
"$PY" "$PRE/P12/preflight_substitute/replay_requests.py" "$URL" "$O/$TAG.jsonl"
