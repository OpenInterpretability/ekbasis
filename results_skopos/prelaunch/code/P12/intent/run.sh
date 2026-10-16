#!/bin/bash
# P12, intent_check replay (cookbook studies/intent-check-replay and its heldout/; as-run folder
# ekbasis-studies-archive/2026-10-11/blindagem/replay): run_replay.py and the two fixed analyses, unchanged, in the
# study's folder layout, with the study's client (setup_client.sh), against the API serving <tag> instead of the hosted
# API (EKBASIS_URL; no key). The runs (runs.jsonl, the trajectories rebuilt from AgentDojo's published logs) are the
# as-run files in ref/intent_replay/.   bash P12/intent/run.sh <tag>   (skopos_int4; ekbasis_int4 as the same-machine control)
set -eu
. "$(dirname "$0")/../../common/env.sh"; . "$PRE/common/serve.sh"
TAG=$1; served_is "$(model_of "$TAG")"
H=$PRE/P12/intent; R=$PRE/ref/intent_replay; W=$OUTROOT/P12/intent/$TAG
mkdir -p "$W/heldout"
bash "$H/setup_client.sh" "$W"
cp "$H/run_replay.py" "$H/analyze_replay.py" "$W/"; cp "$H/heldout/analyze_heldout.py" "$H/heldout/dest_rules.py" "$W/heldout/"
for f in runs.jsonl runs_excluded.jsonl; do ln -sf "$R/$f" "$W/$f"; ln -sf "$R/heldout/$f" "$W/heldout/$f"; done
cd "$W"
EKBASIS_URL=$URL PYTHONPATH=client "$PY" -W ignore run_replay.py runs.jsonl out >> run.log 2>&1
PYTHONPATH=client "$PY" analyze_replay.py runs.jsonl out > analysis.txt
cd heldout
EKBASIS_URL=$URL PYTHONPATH=../client:.. "$PY" -W ignore ../run_replay.py runs.jsonl out >> run.log 2>&1
PYTHONPATH=../client:.. "$PY" analyze_heldout.py > analysis.txt
head -4 "$W/analysis.txt"; head -6 "$W/heldout/analysis.txt"
