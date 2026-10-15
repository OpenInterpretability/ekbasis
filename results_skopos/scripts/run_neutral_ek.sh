#!/bin/bash
# Neutral suite, Ekbasis side, rerun: the first run OOMed (eval batch 48 x ~4k-token contexts) and the base mode also
# scores 'ceiling', which these items lack. Batch 6; data copy with ceiling = floor. Scoring unchanged.
exec >> /root/v50p/neutral.log 2>&1
until grep -q DIAG_DONE /root/v50p/diag.log 2>/dev/null; do sleep 60; done
cd /root/v50p && python3 -c "
import json
with open('data/awb_neutral.jsonl', 'w') as f:
    for l in open('/root/v50p/awb_neutral.jsonl'):
        r = json.loads(l); r['ceiling'] = r['floor']; f.write(json.dumps(r) + '\n')
"
export MODEL=/root/Ekbasis-27B DATA=/root/v50p/data PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True MULTI_STYLE=turns SAVE_PROBS=1 SPLITS=awb_neutral EVAL_BS=6
echo "neutro ekbasis (rerun, lote 6) inicio $(date -u +%T)"
OUT=/root/v50p/neutral_base MODE=eval_base python3 train_conseq_v50.py
OUT=/root/v50p/neutral_r1 MODE=eval_adapter ADAPTER=/root/v50p/run_r1/adapter python3 train_conseq_v50.py
OUT=/root/v50p/neutral_r2 MODE=eval_adapter ADAPTER=/root/v50p/run_r2/adapter python3 train_conseq_v50.py
echo NEUTRAL_EK_DONE $(date -u +%T)
python3 /root/backup_hf.py neutral-ek-done
