#!/bin/bash
# Diagnosis on the git_long validation twin (seeds 40000+): which commands/questions still fail, for designing R3
# on validation instead of on the test. No decision rides on it.
exec >> /root/v50p/diag.log 2>&1
until grep -q NEUTRAL_DONE /root/v50p/neutral.log 2>/dev/null; do sleep 60; done
cd /root/v50p
export MODEL=/root/Ekbasis-27B DATA=/root/v50p/data PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True MULTI_STYLE=turns SAVE_PROBS=1 SPLITS=git_long_val
echo "diag inicio $(date -u +%T)"
OUT=/root/v50p/diag_base MODE=eval_base python3 train_conseq_v50.py
OUT=/root/v50p/diag_r1 MODE=eval_adapter ADAPTER=/root/v50p/run_r1/adapter python3 train_conseq_v50.py
OUT=/root/v50p/diag_r2 MODE=eval_adapter ADAPTER=/root/v50p/run_r2/adapter python3 train_conseq_v50.py
echo DIAG_DONE $(date -u +%T)
python3 /root/backup_hf.py diag-done
