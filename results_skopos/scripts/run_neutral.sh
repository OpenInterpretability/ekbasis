#!/bin/bash
exec >> /root/v50p/neutral.log 2>&1
until grep -q R2_DONE /root/v50p/r2.log 2>/dev/null; do sleep 60; done
cd /root/v50p && cp /root/v50p/awb_neutral.jsonl data/awb_neutral.jsonl
export MODEL=/root/Ekbasis-27B DATA=/root/v50p/data PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True MULTI_STYLE=turns SAVE_PROBS=1 SPLITS=awb_neutral
echo "neutro ekbasis inicio $(date -u +%T)"
OUT=/root/v50p/neutral_base MODE=eval_base python3 train_conseq_v50.py
OUT=/root/v50p/neutral_r1 MODE=eval_adapter ADAPTER=/root/v50p/run_r1/adapter python3 train_conseq_v50.py
OUT=/root/v50p/neutral_r2 MODE=eval_adapter ADAPTER=/root/v50p/run_r2/adapter python3 train_conseq_v50.py
echo "neutro aw inicio $(date -u +%T)"
setsid vllm serve /root/Qwen-AgentWorld-35B-A3B --served-model-name aw --host 127.0.0.1 --port 8100 --max-model-len 32768 --gpu-memory-utilization 0.90 --language-model-only --max-num-seqs 64 > /root/aw_vllm2.log 2>&1 < /dev/null &
for i in $(seq 1 240); do curl -sf localhost:8100/v1/models >/dev/null && break; sleep 10; done
if curl -sf localhost:8100/v1/models >/dev/null; then
  AW_THINK=0 AW_MAX=8192 AW_CONC=64 python3 frontier_eval.py awb_neutral 9999 frontier/aw_awb_neutral.jsonl
else
  echo "AW NAO SUBIU (neutro)"; tail -20 /root/aw_vllm2.log
fi
for p in $(pgrep -f "[v]llm serve /root/Qwen-AgentWorld"); do kill $p; done
echo NEUTRAL_DONE $(date -u +%T)
python3 /root/backup_hf.py neutral-done
