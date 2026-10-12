#!/bin/bash
# The training lineage of Ekbasis-27B, stage by stage (recipes.json in the dataset), then the release interpolation.
# Needs one GPU with ~80 GB (a 27B model in bf16 plus a rank-64 LoRA, gradient checkpointing, batch 8); each stage
# took 50-120 min on an RTX PRO 6000 Blackwell. Set EIKOS_SRC to the `eikos/` folder of github.com/caiovicentino/eikos
# (it holds decision_core.py, the prompt format). Optional: flash-linear-attention on PYTHONPATH (faster attention).
#   bash run_lineage.sh <work_dir>
set -euo pipefail
W="${1:?work dir}"; D="$W/data"; H="$(cd "$(dirname "$0")" && pwd)"
PY="${PY:-python3}"
[ -s "$D/ftrain_V42.jsonl" ] || $PY "$H/stage_files.py" "$D"
export DATA="$D" MODEL="${MODEL:-caiovicentino1/Eikos-27B}" LAYERS=16,32,48,64 BS=8 RANK=64 JEPA=3 JEPA_POS=ev \
       PROMPT_STYLE=semif PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
stage() {  # name init train val steps lr mix [multi_style]
  local name=$1 init=$2 train=$3 val=$4 steps=$5 lr=$6 mix=$7 ms=${8:-json}
  [ -s "$W/$name/ckpt_$steps/adapter_model.safetensors" ] && { echo "$name: done"; return; }
  echo "$name: from ${init:-the base model}, $steps steps"
  env OUT="$W/$name" ${init:+INIT="$init"} TRAIN="$train" VAL="$val" STEPS="$steps" SAVE_EVERY="$steps" LR="$lr" \
      MIX="$mix" MULTI_STYLE="$ms" SPLITS="$val" $PY "$H/train_conseq.py" > "$W/$name.log" 2>&1
}
stage 27s1 ""                        ftrain_27s1 m3val     1000 5e-5   "floor3:0.85,read:0.15"
stage V35  "$W/27s1/ckpt_1000"       ftrain_V35  fval_git  600  1.5e-5 "floor:0.15,floor3:0.15,floorG:0.30,read:0.05,replay:0.35"
stage V37  "$W/V35/ckpt_600"         ftrain_V37  fval_git2 600  1.5e-5 "floorG2:0.40,floorG:0.10,floor:0.10,floor3:0.10,read:0.05,replay:0.25"
stage V41  "$W/V37/ckpt_600"         ftrain_V41  fval_git2 400  1.5e-5 "multi:0.40,floorG2:0.15,floorG:0.05,floor:0.10,floor3:0.08,read:0.04,replay:0.18" turns
stage V42  "$W/V41/ckpt_400"         ftrain_V42  fval_git3 400  1.5e-5 "floorG3:0.35,floorG2:0.10,floorG:0.05,multi:0.15,floor:0.10,floor3:0.07,read:0.04,replay:0.14" turns
stage r4a  "$W/V42/ckpt_400"         ftrain_r4a  fval_git3 300  1e-5   "floorG3:0.245,floorG2:0.07,floorG:0.035,multi:0.105,floor:0.07,floor3:0.049,read:0.028,replay:0.098,floorM:0.20,floorC:0.10" turns
# The release: the exact interpolation halfway between V42 and r4a (one adapter of rank 128), to merge into Eikos-27B.
[ -s "$W/release/adapter_model.safetensors" ] || $PY "$H/wise_lora.py" "$W/V42/ckpt_400" "$W/r4a/ckpt_300" 0.5 "$W/release"
echo "release adapter: $W/release (merge it into $MODEL with peft's merge_and_unload to get Ekbasis-27B)"
