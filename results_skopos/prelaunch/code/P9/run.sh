#!/bin/bash
# P9, planning by search with no LLM: search_eval.py (ported, CHANGES.diff) on the model folder of <tag>, in PyTorch, with
# no vLLM on the GPU, as the release ran it (run_quant_w4a5_eval.sh line 22-25: ONLY=base, RANK=64, BEAM 6, BS 48, no
# flash-linear-attention: its log shows the torch fallback). Puzzles: gen_puzzles.py.   bash P9/run.sh <tag>
set -eu
. "$(dirname "$0")/../common/env.sh"; . "$PRE/common/serve.sh"
TAG=$1; M=$(model_of "$TAG"); serve_down
Z=$OUTROOT/P9/puzzles; O=$OUTROOT/P9/$TAG; mkdir -p "$O"
[ -f "$Z/agent_hard/puzzles.pkl" ] || "$PY" "$PRE/P9/gen_puzzles.py" "$Z" > "$OUTROOT/P9/gen_puzzles.log" 2>&1
for d in agent agent_hard; do
  CUDA_VISIBLE_DEVICES=$GPU PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True MODEL=$M RANK=64 ONLY=base \
    TAG=${TAG}_$d BASE_LABEL="$TAG" "$PY" "$PRE/P9/search_eval.py" "$Z/$d" > "$O/search_$d.log" 2>&1
  cp "$Z/$d/search_${TAG}_$d.json" "$O/"
  tail -3 "$O/search_$d.log"
done
