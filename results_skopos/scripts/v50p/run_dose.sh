#!/bin/bash
exec >> /root/v50p/dose.log 2>&1
export MODEL=/root/Ekbasis-27B DATA=/root/v50p/data PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True MULTI_STYLE=turns
export SPLITS=fhorizon,latent_test,git3_test_known,git3_test_held,guard_known,ftest_family,m3val,fval_git3,multi_test_testfam
cd /root/v50p
echo "DOSE treino inicio $(date -u +%T)"
OUT=/root/v50p/run_dose TRAIN=ftrain_v50p VAL=fval_git3 JEPA=3 LAYERS=16,32,48,64 JEPA_POS=ev BS=8 MICRO=4 LR=1.5e-5 STEPS=1200 SEED=2 RANK=64 SAVE_EVERY=1200 CKPT_EVERY=150 MIX="floorG3:0.245,floorG2:0.07,floorG:0.035,multi:0.105,floor:0.07,floor3:0.049,read:0.028,replay:0.098,floorPL:0.30" python3 train_conseq_v50.py
echo "DOSE treino fim rc=$? $(date -u +%T)"
mkdir -p /root/v50p/dose_eval && ln -sfn /root/v50p/run_dose /root/v50p/dose_eval/run && ln -sfn /root/v50p/base /root/v50p/dose_eval/base
python3 analyze.py /root/v50p/dose_eval
echo "DOSE analise fim $(date -u +%T)"
ADAPTER=/root/v50p/run_dose/adapter python3 m4.py cand /root/v50p/m4_dose && cp /root/lat/index.json /root/v50p/m4_dose/
python3 /root/v50p/m4_readout.py /root/v50p/m4_dose /root/v50p/m4_dose.json
echo DOSE_DONE
