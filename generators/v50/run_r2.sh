#!/bin/bash
exec >> /root/v50p/r2.log 2>&1
until grep -q FACTORY_DONE /root/factory_gen.log && grep -q FRONTIER_DONE /root/frontier.log 2>/dev/null; do sleep 60; done
cd /root/factory
python3 run_family.py sqlfam 200000 200 /root/fac/val_sql.jsonl 16; python3 run_family.py pyfam 200000 200 /root/fac/val_python.jsonl 16
python3 run_family.py shell 200000 200 /root/fac/val_shell.jsonl 16; python3 run_family.py gitfam 200000 200 /root/fac/val_git.jsonl 16
python3 - <<PY
import json, random, hashlib
tr = {json.loads(l)["floor"] for l in open("/root/v50p/data/fac_rx.jsonl")}
n = 0
with open("/root/v50p/data/fac_val.jsonl", "w") as f:
    for fam in ["sql", "python", "shell", "git"]:
        for l in open(f"/root/fac/val_{fam}.jsonl"):
            r = json.loads(l)
            if r["floor"] in tr or r.get("quarantined"): continue
            q = r["question"]
            if q["type"] == "choice":  # same deterministic option shuffle as pack.py (raw rows are not shuffled)
                items = list(q["criteria"].items())
                random.Random(int(hashlib.md5(r["id"].encode()).hexdigest()[:8], 16)).shuffle(items)
                q["criteria"] = dict(items)
            r["world"] = "fac_" + fam; f.write(json.dumps(r) + "\n"); n += 1
print("fac_val", n)
PY
cd /root/v50p && cat data/ftrain_r1.jsonl data/fac_rx.jsonl > data/ftrain_r2.jsonl
export MODEL=/root/Ekbasis-27B DATA=/root/v50p/data PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True MULTI_STYLE=turns SAVE_PROBS=1
export SPLITS=fac_val,git_long,fhorizon,latent_test,git3_test_known,git3_test_held,guard_known,ftest_family,m3val,fval_git3
echo "R2 treino inicio $(date -u +%T)"
OUT=/root/v50p/run_r2 TRAIN=ftrain_r2 VAL=fval_git3 JEPA=3 LAYERS=16,32,48,64 JEPA_POS=ev BS=8 MICRO=4 LR=1.5e-5 STEPS=1200 SEED=2 RANK=64 SAVE_EVERY=1200 CKPT_EVERY=150 MIX="floorG3:0.1925,floorG2:0.055,floorG:0.0275,multi:0.0825,floor:0.055,floor3:0.0385,read:0.022,replay:0.077,floorPL:0.15,floorPLG:0.15,floorRX:0.15" python3 train_conseq_v50.py
echo "R2 treino fim rc=$? $(date -u +%T)"
SPLITS=fac_val OUT=/root/v50p/base_facval MODE=eval_base python3 train_conseq_v50.py
SPLITS=fac_val OUT=/root/v50p/r1_facval MODE=eval_adapter ADAPTER=/root/v50p/run_r1/adapter python3 train_conseq_v50.py
echo R2_DONE $(date -u +%T)
python3 /root/backup_hf.py r2-done
