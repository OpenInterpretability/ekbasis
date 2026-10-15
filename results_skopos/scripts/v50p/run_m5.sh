#!/bin/bash
exec >> /root/v50p/m5.log 2>&1
until grep -q DOSE_DONE /root/v50p/dose.log; do sleep 30; done
export MODEL=/root/Ekbasis-27B DATA=/root/v50p/data PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True MULTI_STYLE=turns SPLITS=git_long
cd /root/v50p
echo "M5 inicio $(date -u +%T)"
OUT=/root/v50p/m5_base MODE=eval_base python3 train_conseq_v50.py
OUT=/root/v50p/m5_pilot MODE=eval_adapter ADAPTER=/root/v50p/run/adapter python3 train_conseq_v50.py
OUT=/root/v50p/m5_dose MODE=eval_adapter ADAPTER=/root/v50p/run_dose/adapter python3 train_conseq_v50.py
echo M5_DONE $(date -u +%T)
