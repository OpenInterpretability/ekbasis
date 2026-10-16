#!/bin/bash
exec >> /root/v50p/skopos_cmp.log 2>&1
until grep -q R3_DONE /root/v50p/r3.log 2>/dev/null; do sleep 60; done
echo "inicio $(date -u +%T)"; rm -rf /root/Qwen-AgentWorld-35B-A3B; df -h /root | tail -1
python3 -c "from huggingface_hub import snapshot_download; snapshot_download('caiovicentino1/Ekbasis-Skopos-27B', revision='1e48ae09a3', local_dir='/root/Skopos-27B')" || { echo DL_FALHOU; exit 1; }
du -sh /root/Skopos-27B
cd /root/v50p
export MODEL=/root/Skopos-27B DATA=/root/v50p/data PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True MULTI_STYLE=turns SAVE_PROBS=1
SPLITS=fac_val,git_long,git_long_val,fhorizon,latent_test,git3_test_known,git3_test_held,guard_known,ftest_family,m3val,fval_git3,sess_val OUT=/root/v50p/skopos_eval MODE=eval_base python3 train_conseq_v50.py
SPLITS=awb_neutral EVAL_BS=6 OUT=/root/v50p/neutral_skopos MODE=eval_base python3 train_conseq_v50.py
echo SKOPOS_CMP_DONE $(date -u +%T)
python3 /root/backup_hf.py skopos-cmp
