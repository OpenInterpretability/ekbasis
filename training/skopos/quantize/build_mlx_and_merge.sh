#!/bin/bash
# Provenance: the commands that built Ekbasis-Skopos-27B (bf16) and its MLX 4-bit build on the RTX PRO 6000 research
# machine on 2026-10-15, copied verbatim from the session that ran them (they were typed, not kept in a script).
# venv for MLX: /root/mlx_venv with mlx-cuda-13 0.32.4 (mlx-cuda-12 failed on JIT headers); mlx-lm as installed there.

# 1) R4 merged into the first Skopos (bf16): merge_lora.py BASE_DIR ADAPTER_DIR OUT_DIR (log: /root/v50p/merge_r4.log)
python3 merge_lora.py /root/Skopos-27B /root/v50p/run_r4/adapter /root/Skopos-R4-27B

# 2) MLX 4-bit (affine, groups of 64) from the merged bf16
mlx_lm convert --hf-path /root/Skopos-R4-27B --mlx-path /root/Skopos-R4-27B-MLX-4bit -q --q-bits 4 --q-group-size 64

# 3) The build ships no multi-token-prediction layer: declare none (as Ekbasis-27B-MLX-4bit's config does), then the
#    serving files: mlx_serve.py and mlx_decide.py from the public Ekbasis-27B-MLX-4bit repo (downloaded to
#    /root/mlx_ref), the decision/calibration/licence files from the bf16 folder; the vLLM-only files removed.
cd /root/Skopos-R4-27B-MLX-4bit && python3 - <<PY
import json
c = json.load(open("config.json")); c["text_config"]["mtp_num_hidden_layers"] = 0
json.dump(c, open("config.json", "w"), indent=2); print("mtp ->", c["text_config"]["mtp_num_hidden_layers"])
PY
cp /root/mlx_ref/mlx_serve.py /root/mlx_ref/mlx_decide.py . && for f in calib.json decision_config.json LICENSE LICENSE-Eikos LICENSE-Qwen NOTICE; do cp /root/Skopos-R4-27B/$f .; done; rm -f serve.py letter_adapter.py
