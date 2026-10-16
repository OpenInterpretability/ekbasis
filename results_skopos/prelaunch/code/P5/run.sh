#!/bin/bash
# P5, speed (and P8's one-check timing): speed_bench.py (ported, CHANGES.diff) and short_eval_release.py time, with the
# release run's settings (run_release_w4a5_bf16.sh lines 31-35), alone on the GPU, against <tag> served by
# common/serve.sh (one replica: the release run also timed on one replica, its API on :8530).   bash P5/run.sh <tag>
# Ekbasis-27B is re-run here (bash P5/run.sh ekbasis_bf16): its published times are from the old rig.
set -eu
. "$(dirname "$0")/../common/env.sh"; . "$PRE/common/serve.sh"
TAG=$1; M=$(model_of "$TAG"); served_is "$M"
O=$OUTROOT/P5/$TAG; mkdir -p "$O"; S=$PRE/P5/speed_bench.py; V=http://127.0.0.1:$VLLM_PORT/v1/completions
CQ_URL=$URL/v1/systemone MODEL_DIR=$M N=80 PAR=16 "$PY" "$S" cq "$O/cq_par16.jsonl" > "$O/cq16.out" 2>&1
CQ_URL=$URL/v1/systemone MODEL_DIR=$M N=8 PAR=1 "$PY" "$S" cq "$O/cq_par1.jsonl" > "$O/cq1.out" 2>&1
MULTI_STYLE=turns MODEL_DIR=$M VLLM_URL=$V PROMPT_LP=4 N=80 PAR=16 "$PY" "$S" cqm "$O/cqm_par16.jsonl" > "$O/cqm16.out" 2>&1
MULTI_STYLE=turns MODEL_DIR=$M VLLM_URL=$V PROMPT_LP=4 N=8 PAR=1 "$PY" "$S" cqm "$O/cqm_par1.jsonl" > "$O/cqm1.out" 2>&1
P8=$OUTROOT/P8/$TAG; mkdir -p "$P8"
"$PY" "$PRE/P8/make_saved.py" "$P8/short_eval_saved.json"
CQ_URL=$URL/v1/systemone SAVED_JSON=$P8/short_eval_saved.json OUT_JSON=$P8/short_eval_release_timing.json \
  "$PY" "$PRE/P8/short_eval_release.py" time > "$P8/short_timing.out" 2>&1
MODEL_DIR=$M "$PY" "$S" sum "$O" | tee "$O/sum.out"
