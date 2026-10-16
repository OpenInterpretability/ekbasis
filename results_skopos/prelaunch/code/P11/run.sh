#!/bin/bash
# P11, GPU memory of each build, as Ekbasis-27B's builds were tested (run_mem_tests_w4a5.sh: mem_ceiling_test.sh with
# vLLM capped to what a smaller card gives on one RTX PRO 6000, 60 held-out git questions through serve.py, the answers
# compared with the same build at full memory; then collect_memory_tests.py). The same caps for Skopos' builds; "full
# memory" = the Skopos release read's predictions ($RELREAD/release_r4{,_fp8,_int4}/preds_git3_test_held.jsonl).
# The caps are fractions of the rig's GPU (torch total 101,974,081,536 bytes, its search log): on another card size the
# run stops, unless P11_RESCALE=1 (fractions scaled to the same bytes; reported as a deviation).   bash P11/run.sh
set -eu
. "$(dirname "$0")/../common/env.sh"; . "$PRE/common/serve.sh"
serve_down
O=$OUTROOT/P11; mkdir -p "$O"; LOG=$O/memory_tests.log; : > "$LOG"
SCALE=$(CUDA_VISIBLE_DEVICES=$GPU "$PY" -c "import torch; t = torch.cuda.get_device_properties(0).total_memory; print(101974081536 / t)")
echo "GPU total vs the rig's: scale $SCALE" | tee "$O/gpu_scale.txt"
f() { "$PY" -c "import sys; print(round(float(sys.argv[1]) * float(sys.argv[2]), 4))" "$1" "$SCALE"; }
if ! "$PY" -c "import sys; sys.exit(abs(float(sys.argv[1]) - 1) > 0.005)" "$SCALE"; then
  [ "${P11_RESCALE:-0}" = 1 ] || { echo "THIS GPU IS NOT THE RIG'S SIZE: the same fractions would cap other amounts (P11_RESCALE=1 to scale)"; exit 1; }
  echo "DEVIATION: fractions scaled by $SCALE" | tee -a "$O/gpu_scale.txt"
else SCALE=1; fi
for x in "$SKOPOS_BF16 release_r4" "$SKOPOS_FP8 release_r4_fp8" "$SKOPOS_INT4 release_r4_int4"; do set -- $x
  [ -f "$RELREAD/$2/preds_git3_test_held.jsonl" ] || { echo "missing full-memory predictions $RELREAD/$2"; exit 1; }; done
bash "$PRE/P11/mem_ceiling_test.sh" bf16_80GB "$SKOPOS_BF16" "$(f 0.695)" 64 "$RELREAD/release_r4/preds_git3_test_held.jsonl" >> "$LOG" 2>&1
bash "$PRE/P11/mem_ceiling_test.sh" fp8_48GB "$SKOPOS_FP8" "$(f 0.42)" 64 "$RELREAD/release_r4_fp8/preds_git3_test_held.jsonl" >> "$LOG" 2>&1
bash "$PRE/P11/mem_ceiling_test.sh" int4_32GB "$SKOPOS_INT4" "$(f 0.28)" 16 "$RELREAD/release_r4_int4/preds_git3_test_held.jsonl" >> "$LOG" 2>&1
F24=$(f 0.233) bash "$PRE/P11/mem_int4_24gb.sh" "$SKOPOS_INT4" "$RELREAD/release_r4_int4/preds_git3_test_held.jsonl" >> "$LOG" 2>&1
"$PY" "$PRE/P11/collect_memory_tests.py" "$O/memory_tests.json" "$LOG"
