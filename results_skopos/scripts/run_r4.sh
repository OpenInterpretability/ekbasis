#!/bin/bash
exec >> /root/v50p/r4.log 2>&1
until grep -q SKOPOS_CMP_DONE /root/v50p/skopos_cmp.log 2>/dev/null; do sleep 60; done
cd /root/v50p
export MODEL=/root/Skopos-27B DATA=/root/v50p/data PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True MULTI_STYLE=turns SAVE_PROBS=1
export SPLITS=fac_val,git_long,git_long_val,fhorizon,latent_test,git3_test_known,git3_test_held,guard_known,ftest_family,m3val,fval_git3,sess_val
echo "R4 treino inicio $(date -u +%T)"
OUT=/root/v50p/run_r4 TRAIN=ftrain_r2 VAL=fval_git3 JEPA=3 LAYERS=16,32,48,64 JEPA_POS=ev BS=8 MICRO=4 LR=1.5e-5 STEPS=1200 SEED=2 RANK=64 SAVE_EVERY=1200 CKPT_EVERY=150 MIX="floorG3:0.1925,floorG2:0.055,floorG:0.0275,multi:0.0825,floor:0.055,floor3:0.0385,read:0.022,replay:0.077,floorPL:0.15,floorPLG:0.15,floorRX:0.15" python3 train_conseq_v50.py
echo "R4 treino fim rc=$? $(date -u +%T)"
SPLITS=awb_neutral EVAL_BS=6 OUT=/root/v50p/neutral_r4 MODE=eval_adapter ADAPTER=/root/v50p/run_r4/adapter python3 train_conseq_v50.py
echo R4_DONE $(date -u +%T)
python3 /root/backup_hf.py r4-done
