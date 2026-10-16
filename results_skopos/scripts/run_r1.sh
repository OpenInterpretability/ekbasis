#!/bin/bash
exec >> /root/v50p/r1.log 2>&1
until grep -q "git_plan_train" /root/v50p/gen_git.log; do sleep 30; done
cd /root/v50p && cat data/ftrain_v50p.jsonl data/git_plan_train.jsonl > data/ftrain_r1.jsonl && wc -l data/ftrain_r1.jsonl
export MODEL=/root/Ekbasis-27B DATA=/root/v50p/data PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True MULTI_STYLE=turns SAVE_PROBS=1
export SPLITS=git_long,fhorizon,latent_test,git3_test_known,git3_test_held,guard_known,ftest_family,m3val,fval_git3
echo "R1 treino inicio $(date -u +%T)"
OUT=/root/v50p/run_r1 TRAIN=ftrain_r1 VAL=fval_git3 JEPA=3 LAYERS=16,32,48,64 JEPA_POS=ev BS=8 MICRO=4 LR=1.5e-5 STEPS=1200 SEED=2 RANK=64 SAVE_EVERY=1200 CKPT_EVERY=150 MIX="floorG3:0.245,floorG2:0.07,floorG:0.035,multi:0.105,floor:0.07,floor3:0.049,read:0.028,replay:0.098,floorPL:0.15,floorPLG:0.15" python3 train_conseq_v50.py
echo "R1 treino fim rc=$? $(date -u +%T)"
OUT=/root/v50p/base_probs MODE=eval_base python3 train_conseq_v50.py
echo "BASE probs fim $(date -u +%T)"
python3 analyze_r1.py /root/v50p/run_r1 /root/v50p/base_probs
echo R1_DONE $(date -u +%T)
