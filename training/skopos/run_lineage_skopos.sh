#!/bin/bash
# The training lineage of Ekbasis-Skopos-27B (README.md here): Ekbasis-27B's release adapter (w4a5, run_lineage.sh) ->
# v49f, 900 steps from it -> the first Skopos, the exact interpolation halfway between w4a5 and v49f, merged into
# Eikos-27B -> R4, a new LoRA on the first Skopos, 1,200 steps -> R4 merged: Ekbasis-Skopos-27B.
# Needs one GPU with ~96 GB (a 27B model in bf16 plus a LoRA, gradient checkpointing, micro-batch 4 x 2), ~150 GB of disk
# for two merged checkpoints, and the CPU memory to merge one (bf16, ~55 GB). On an RTX PRO 6000 Blackwell the V49 runs
# took ~9 s per step at micro-batch 4, R4 112 min. Set EIKOS_SRC to the `eikos/` folder of
# github.com/caiovicentino/eikos (decision_core.py).
#   bash run_lineage_skopos.sh <work_dir>
set -euo pipefail
W="${1:?work dir}"; D="$W/data"; H="$(cd "$(dirname "$0")" && pwd)"
PY="${PY:-python3}"
BASE="${BASE:-caiovicentino1/Eikos-27B}"
# Ekbasis-27B's release adapter (rank 128): the public lineage, then wise_lora.py (only merged weights are published)
[ -s "$W/release/adapter_model.safetensors" ] || MODEL="$BASE" bash "$H/../run_lineage.sh" "$W"
[ -s "$D/ftrain_r2.jsonl" ] || $PY "$H/stage_files_skopos.py" "$D"
export DATA="$D" LAYERS=16,32,48,64 BS=8 MICRO=4 SEED=2 JEPA=3 JEPA_POS=ev MULTI_STYLE=turns SAVE_PROBS=1 \
       PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

# v49f: continues w4a5 (INIT, rank 128) on Eikos-27B, whose frozen copy (adapter off) is the hindsight teacher.
# It ran batch 8 until an out-of-memory error at step ~500, then from the start at micro-batch 4 x 2 (PLAN_v49 Addendum D).
if [ ! -s "$W/v49f/ckpt_900/adapter_model.safetensors" ]; then
  env OUT="$W/v49f" MODEL="$BASE" INIT="$W/release" RANK=128 TRAIN=ftrain_mixG3 VAL=fval_git3 STEPS=900 SAVE_EVERY=900 \
      TRAIN_EXTRA=v45_v44git,v45rx_shell,v45rx_git,v45rx_sql,mined_chain,v46_anchor,v49_anchor2,v49_fx \
      LR=1.5e-5 EVAL_BS=16 SPLITS=git3_test_held \
      MIX="multi:0.0735,floor:0.0490,floor3:0.0343,read:0.0196,replay:0.0686,floorG3:0.1715,floorG2:0.0490,floorG:0.0245,floorGV:0.0227,floorRXsh:0.0444,floorRXgit:0.0394,floorRXsql:0.0296,floorC:0.0189,floorGA:0.2000,floorFX:0.1550" \
      $PY "$H/train_conseq_v49.py" > "$W/v49f.log" 2>&1
fi

# The first Skopos (v49f_w50): W0 + 1/2 dW(w4a5) + 1/2 dW(v49f) as one adapter of rank 256, merged into Eikos-27B.
[ -s "$W/wise_v49f_w50/adapter_model.safetensors" ] || \
  $PY "$H/wise_lora.py" "$W/release" "$W/v49f/ckpt_900" 0.5 "$W/wise_v49f_w50"
[ -s "$W/Skopos-first/model.safetensors.index.json" ] || \
  CUDA_VISIBLE_DEVICES="" MERGE_BASE="$BASE" $PY "$H/merge_lora_v45.py" "$W/wise_v49f_w50" "$W/Skopos-first"

# R4: a new LoRA (rank 64) on the first Skopos, which is also its own hindsight teacher (adapter off).
if [ ! -s "$W/R4/adapter/adapter_model.safetensors" ]; then
  env OUT="$W/R4" MODEL="$W/Skopos-first" RANK=64 TRAIN=ftrain_r2 VAL=fval_git3 STEPS=1200 SAVE_EVERY=1200 CKPT_EVERY=150 \
      LR=1.5e-5 SPLITS=fac_val,git_long,git_long_val,fhorizon,latent_test,git3_test_known,git3_test_held,guard_known,ftest_family,m3val,fval_git3,sess_val \
      MIX="floorG3:0.1925,floorG2:0.055,floorG:0.0275,multi:0.0825,floor:0.055,floor3:0.0385,read:0.022,replay:0.077,floorPL:0.15,floorPLG:0.15,floorRX:0.15" \
      $PY "$H/train_conseq_v50.py" > "$W/R4.log" 2>&1
fi

# The release: R4 merged into the first Skopos (W += 2 B A in float32, cast back; the vision tower is copied unchanged).
[ -s "$W/Ekbasis-Skopos-27B/model.safetensors.index.json" ] || \
  $PY "$H/merge_lora.py" "$W/Skopos-first" "$W/R4/adapter" "$W/Ekbasis-Skopos-27B"
echo "Ekbasis-Skopos-27B: $W/Ekbasis-Skopos-27B (quantized builds: quantize/README in this folder's README)"
