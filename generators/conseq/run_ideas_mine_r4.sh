#!/bin/bash
# PLAN_loop_ideas.md + PLAN_v43_round4.md. Research replicas of the release weights on GPUs 1-3 (+ GPU 0's vLLM behind
# 8503) answer (1) the loop ideas on the 120 earlier chains and (2) the round-4 mining chains, at the same time; then the
# replicas are stopped by their pid files (each PID checked against its command line), the chain items are collected,
# and the three round-4 runs start on GPUs 1-3. Not production.
D=/dev/shm/conseq; C=/root/decis/conseq; PY=/opt/sglang/bin/python
for g in 1 2 3; do
  CUDA_DEVICE_ORDER=PCI_BUS_ID CUDA_VISIBLE_DEVICES=$g setsid nohup /root/vllm_new_env/bin/vllm serve $D/merged_v42 \
    --host 127.0.0.1 --port 3014$g --served-model-name decider --dtype bfloat16 --gpu-memory-utilization 0.85 \
    --max-model-len 16384 --enable-prefix-caching --mamba-cache-mode align --logprobs-mode processed_logprobs \
    --max-logprobs 600 --max-num-seqs 64 > $D/trace_vllm_$g.log 2>&1 < /dev/null &
  echo $! > $D/trace_vllm_$g.pid
done
for g in 1 2 3; do n=0; until curl -sf -m 3 127.0.0.1:3014$g/health > /dev/null; do n=$((n + 1)); [ $n -gt 120 ] && break; sleep 10; done; done
cd /root/decis/ekbasis_dev/eikos
setsid nohup $PY serve.py --model $D/merged_v42 \
  --vllm-url http://127.0.0.1:30141,http://127.0.0.1:30142,http://127.0.0.1:30143,http://127.0.0.1:30131 \
  --host 127.0.0.1 --port 8513 > $D/trace_api.log 2>&1 < /dev/null &
echo $! > $D/trace_api.pid
n=0; until curl -sf -m 3 127.0.0.1:8513/health > /dev/null; do n=$((n + 1)); [ $n -gt 60 ] && break; sleep 5; done
echo "served $(date -u +%H:%M) UTC"
cd $C
IDEAS=$(for f in cards toggles machines jugs; do for m in check0.9E adapt0.9E views0.9E views0.5E; do printf "%s:%s," $f $m; done; done)
CQ_URL=http://127.0.0.1:8513/v1/systemone N=8 PAR=48 TRACE=1 ONLY=$IDEAS OUT=$D/long_chain3_ideas.jsonl \
  $PY long_chain3.py > $D/long_chain3_ideas.out 2>&1 &
P1=$!
rm -f $D/mine_chain_raw.jsonl
CQ_URL=http://127.0.0.1:8513/v1/systemone N=2100 OLD_N=2000 PAR=48 ONLY=jugs:text,toggles:text MINE_OUT=$D/mine_chain_raw.jsonl \
  OUT=$D/long_chain3_mine.jsonl $PY long_chain3.py > $D/long_chain3_mine.out 2>&1 &
P2=$!
wait $P1 $P2
echo "ideas and mining done $(date -u +%H:%M) UTC"
stop() {
  local P; P=$(cat "$1" 2>/dev/null)
  if [ -n "$P" ] && tr "\0" " " < /proc/$P/cmdline 2>/dev/null | grep -qF "$2"; then kill "$P" && echo "stopped $P ($1)"; fi
}
stop $D/trace_api.pid "serve.py --model $D/merged_v42 --vllm-url http://127.0.0.1:30141"
for g in 1 2 3; do stop $D/trace_vllm_$g.pid "vllm serve $D/merged_v42 --host 127.0.0.1 --port 3014$g"; done
WRONG=$($PY - <<'PY'
import json
rows = [json.loads(l) for l in open("/dev/shm/conseq/mine_chain_raw.jsonl")]
keep = ("world", "qtype", "steps", "question", "gold", "floor", "ceiling", "kind")
with open("/dev/shm/conseq/fac/mined_chain.jsonl", "w") as f:
    for r in rows:
        f.write(json.dumps({k: r[k] for k in keep}) + "\n")
w = sum(r["wrong"] for r in rows)
import sys
print(f"chain items: {len(rows)} ({w} wrong, {len(rows) - w} right below 0.99)", file=sys.stderr)
print(w)
PY
)
echo "wrong chain items: $WRONG"
if [ "${WRONG:-0}" -lt 30 ]; then echo "fewer than 30 wrong chain items: round 4 does not start"; exit 0; fi
sleep 20
export PYTHONPATH=/root/decis/conseq/pkgs_fla PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
COMMON="DATA=$D/fac TRAIN=ftrain_mixG3 VAL=fval_git3 MULTI_STYLE=turns MODEL=/root/decis/release_final/models/Eikos-27B \
LAYERS=16,32,48,64 BS=8 EVAL_BS=16 RANK=64 LR=1e-5 JEPA=3 JEPA_POS=ev SAVE_PROBS=1 \
SPLITS=git3_test_known,git3_test_held,multi_test_testfam,ftest_family,ce_items"
launch() {  # $1 gpu, $2 name, $3 init, $4 steps, $5 extra files, $6 mix
  setsid nohup env CUDA_DEVICE_ORDER=PCI_BUS_ID CUDA_VISIBLE_DEVICES=$1 $COMMON OUT=$D/sw_$2 INIT=$3 STEPS=$4 SAVE_EVERY=$4 \
    TRAIN_EXTRA=$5 MIX=$6 $PY train_conseq.py > $D/sw_$2.log 2>&1 < /dev/null &
  echo $! > $D/sw_$2.pid
  echo "launched sw_$2 on GPU $1: PID $(cat $D/sw_$2.pid)"
}
launch 1 r4a $D/sw_v42/ckpt_400 300 mined_wide,mined_chain floorG3:0.245,floorG2:0.07,floorG:0.035,multi:0.105,floor:0.07,floor3:0.049,read:0.028,replay:0.098,floorM:0.20,floorC:0.10
launch 2 r4b $D/sw_r3w20/ckpt_300 200 mined_wide,mined_chain floorG3:0.2625,floorG2:0.075,floorG:0.0375,multi:0.1125,floor:0.075,floor3:0.0525,read:0.03,replay:0.105,floorM:0.10,floorC:0.15
launch 3 r4c $D/sw_v42/ckpt_400 300 mined_chain floorG3:0.28,floorG2:0.08,floorG:0.04,multi:0.12,floor:0.08,floor3:0.056,read:0.032,replay:0.112,floorC:0.20
