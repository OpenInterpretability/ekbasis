#!/bin/bash
# PREREG_ADDENDUM.md (sealed d8a01ee1) A2 + A3 on the bf16 build; the server stays up for A1 (T3c from the Mac).
exec >> /root/v50p/addendum_bf16.log 2>&1
echo "inicio $(date -u +%T)"
cd /root/Skopos-R4-27B
setsid bash serve_vllm.sh /root/Skopos-R4-27B 8601 0.85 > /root/v50p/vllm_r4_add.log 2>&1 < /dev/null &
for i in $(seq 1 180); do curl -sf localhost:8601/v1/models >/dev/null && break; sleep 10; done
curl -sf localhost:8601/v1/models >/dev/null || { echo VLLM_NAO_SUBIU; tail -20 /root/v50p/vllm_r4_add.log; exit 1; }
setsid python3 serve.py --model /root/Skopos-R4-27B --vllm-url http://127.0.0.1:8601 --port 8603 --host 127.0.0.1 > /root/v50p/front_r4_add.log 2>&1 < /dev/null &
for i in $(seq 1 60); do grep -q "ready at" /root/v50p/front_r4_add.log && break; sleep 5; done
grep -q "ready at" /root/v50p/front_r4_add.log || { echo FRONT_NAO_SUBIU; tail -20 /root/v50p/front_r4_add.log; exit 1; }
echo "SERVE_BF16_READY $(date -u +%T)"
cd /root/v50p
mkdir -p ce_r4 && python3 -c "from huggingface_hub import hf_hub_download as d; import shutil; shutil.copy(d(\"caiovicentino1/ekbasis-data\", \"raw/ce_items.jsonl\", repo_type=\"dataset\"), \"/root/v50p/ce_r4/items.jsonl\")"
wc -l ce_r4/items.jsonl
echo "A2 CE inicio $(date -u +%T)"
URL=http://127.0.0.1:8603 PAR=32 OUT=/root/v50p/ce_r4 python3 confident_errors.py eval
echo "A2_DONE $(date -u +%T)"
python3 score_calib_build.py calib_items.json calib_scores_skopos_bf16.jsonl
echo "A3_BF16_DONE $(date -u +%T)"
python3 /root/backup_hf.py addendum-bf16
