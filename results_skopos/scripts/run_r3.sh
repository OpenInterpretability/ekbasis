#!/bin/bash
exec >> /root/v50p/r3.log 2>&1
cd /root/v50p
python3 gen_session.py data/fac_rx.jsonl data/fac_sess.jsonl floorSX
python3 gen_session.py data/fac_val.jsonl data/sess_val.jsonl floorSX
cat data/ftrain_r2.jsonl data/fac_sess.jsonl > data/ftrain_r3.jsonl
export MODEL=/root/Ekbasis-27B DATA=/root/v50p/data PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True MULTI_STYLE=turns SAVE_PROBS=1
export SPLITS=sess_val,fac_val,git_long,fhorizon,latent_test,git3_test_known,git3_test_held,guard_known,ftest_family,m3val,fval_git3
echo "R3 treino inicio $(date -u +%T)"
OUT=/root/v50p/run_r3 TRAIN=ftrain_r3 VAL=fval_git3 JEPA=3 LAYERS=16,32,48,64 JEPA_POS=ev BS=8 MICRO=4 LR=1.5e-5 STEPS=1200 SEED=2 RANK=64 SAVE_EVERY=1200 CKPT_EVERY=150 MIX="floorG3:0.1575,floorG2:0.045,floorG:0.0225,multi:0.0675,floor:0.045,floor3:0.0315,read:0.018,replay:0.063,floorPL:0.15,floorPLG:0.15,floorRX:0.15,floorSX:0.10" python3 train_conseq_v50.py
echo "R3 treino fim rc=$? $(date -u +%T)"
SPLITS=sess_val OUT=/root/v50p/base_sessval MODE=eval_base python3 train_conseq_v50.py
SPLITS=sess_val OUT=/root/v50p/r2_sessval MODE=eval_adapter ADAPTER=/root/v50p/run_r2/adapter python3 train_conseq_v50.py
SPLITS=awb_neutral EVAL_BS=6 OUT=/root/v50p/neutral_r3 MODE=eval_adapter ADAPTER=/root/v50p/run_r3/adapter python3 train_conseq_v50.py
echo R3_DONE $(date -u +%T)
python3 /root/backup_hf.py r3-done
