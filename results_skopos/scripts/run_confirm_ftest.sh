#!/bin/bash
exec >> /root/v50p/confirm_ftest.log 2>&1
cd /root/v50p
for p in $(pgrep -f "^python3 serve.py --model /root/Skopos-R4-27B"); do kill $p; done
for p in $(pgrep -f "[v]llm serve /root/Skopos-R4-27B"); do kill $p; done
sleep 20; nvidia-smi --query-gpu=memory.used --format=csv,noheader
rm -rf /root/Skopos-27B; df -h /root | tail -1
python3 -c "from huggingface_hub import snapshot_download; snapshot_download('caiovicentino1/Ekbasis-27B', local_dir='/root/Ekbasis-27B')" || { echo DL_FALHOU; exit 1; }
export DATA=/root/v50p/data PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True MULTI_STYLE=turns SAVE_PROBS=1 SPLITS=ftest_fresh
echo "release inicio $(date -u +%T)"; MODEL=/root/Ekbasis-27B OUT=/root/v50p/confirm_rel MODE=eval_base python3 train_conseq_v50.py
echo "r4 inicio $(date -u +%T)"; MODEL=/root/Skopos-R4-27B OUT=/root/v50p/confirm_r4 MODE=eval_base python3 train_conseq_v50.py
python3 analyze_confirm_ftest.py /root/v50p > confirm_r4/CONFIRM_FTEST.txt 2>&1; tail -30 confirm_r4/CONFIRM_FTEST.txt
echo CONFIRM_FTEST_DONE $(date -u +%T)
python3 /root/backup_hf.py confirm-ftest
