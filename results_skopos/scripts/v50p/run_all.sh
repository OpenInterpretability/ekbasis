#!/bin/bash
exec >> /root/v50p/run_all.log 2>&1
export MODEL=/root/Ekbasis-27B DATA=/root/v50p/data PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True MULTI_STYLE=turns
export SPLITS=fhorizon,latent_test,git3_test_known,git3_test_held,guard_known,ftest_family,m3val,fval_git3,multi_test_testfam
cd /root/v50p
echo "TREINO inicio $(date -u +%T)"
OUT=/root/v50p/run TRAIN=ftrain_v50p VAL=fval_git3 JEPA=3 LAYERS=16,32,48,64 JEPA_POS=ev BS=8 MICRO=4 LR=1.5e-5 STEPS=600 SEED=2 RANK=64 SAVE_EVERY=600 CKPT_EVERY=150 MIX="floorG3:0.2975,floorG2:0.085,floorG:0.0425,multi:0.1275,floor:0.085,floor3:0.0595,read:0.034,replay:0.119,floorPL:0.15" python3 train_conseq_v50.py
echo "TREINO fim rc=$? $(date -u +%T)"
OUT=/root/v50p/base MODE=eval_base python3 train_conseq_v50.py
echo "BASE fim rc=$? $(date -u +%T)"
echo V50P_DONE
