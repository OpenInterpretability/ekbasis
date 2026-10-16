#!/bin/bash
# PRELAUNCH PORT (P11) of the 24 GB block of _orig/run_mem_tests_w4a5.sh (lines 13-38): INT4 on a 24 GB card at 0.95,
# text only, eager, 4k context, 4 sequences, 2,048 batched tokens: the same vLLM flags. Changes: the GPU ($GPU, it was
# the rig's GPU UUID), the folders ($OUTROOT/P11 for /dev/shm/conseq/quant_w4a5; vLLM from PATH, it was
# /root/vllm_new_env), serve.py of the build's own folder with $PY (it was serve 1.3's with /opt/sglang/bin/python), the
# item file ($DATA/fac), and the per-item answers saved.   usage: [F24=<fraction>] mem_int4_24gb.sh <model_dir> <ref_preds>
set -u
M=$1; REF=$2; QW=$OUTROOT/P11; Q=$QW; G=$GPU; L=$QW/memtest_int4_24.log
setsid nohup bash -c "echo \$\$ > $QW/memtest24_vllm.pid; exec env CUDA_VISIBLE_DEVICES=$G VLLM_CACHE_ROOT=$Q/vllm_cache vllm serve $M --host 127.0.0.1 --port 30150 --served-model-name decider --dtype bfloat16 --gpu-memory-utilization ${F24:-0.233} --max-model-len 4096 --max-num-batched-tokens 2048 --enable-prefix-caching --mamba-cache-mode align --logprobs-mode processed_logprobs --max-logprobs 600 --max-num-seqs 4 --enforce-eager --limit-mm-per-prompt '{\"image\": 0, \"video\": 0}'" > $L 2>&1 < /dev/null &
sleep 3; VP=$(cat $QW/memtest24_vllm.pid)
ok=0; for i in $(seq 1 60); do curl -s -m 2 127.0.0.1:30150/health -o /dev/null && { ok=1; break; }; [ -d /proc/$VP ] || break; sleep 5; done
{ echo "== int4, 24 GB card at 0.95, text only, eager, 4k context, 4 sequences: vLLM up=$ok"
  grep -E "Maximum concurrency|GPU KV cache size|Model loading took|CUDA out of memory|No available memory|Error" $L | sed "s/^.*\] //" | head -5; }
if [ $ok = 1 ]; then
  cd $M
  setsid nohup bash -c "echo \$\$ > $QW/memtest24_api.pid; exec env CUDA_VISIBLE_DEVICES= $PY serve.py --model $M --vllm-url http://127.0.0.1:30150 --host 127.0.0.1 --port 8510" > $QW/memtest24_api.log 2>&1 < /dev/null &
  sleep 2; until curl -s -m 2 127.0.0.1:8510/health | grep -q ok; do sleep 2; done
  $PY - "$REF" "$QW/answers_int4_24GB.jsonl" <<"PY"
import json, os, sys, time, urllib.request
rows = [json.loads(l) for l in open(os.environ["DATA"] + "/fac/git3_test_held.jsonl")][:60]
ref = [json.loads(l) for l in open(sys.argv[1])][:60]
out = open(sys.argv[2], "w")
same, t0 = 0, time.time()
for k, (r, x) in enumerate(zip(rows, ref)):
    req = urllib.request.Request("http://127.0.0.1:8510/v1/systemone", data=json.dumps({"state": r["floor"], "questions": {"q": r["question"]}}).encode(), headers={"Content-Type": "application/json"})
    a = json.load(urllib.request.urlopen(req, timeout=300))["answers"]["q"]
    pred = ("yes" if a["value"] else "no") if r["question"]["type"] in ("noul", "boolean") else a["choice"]
    same += pred == x["pred"]
    out.write(json.dumps({"k": k, "pred": pred, "full_memory": x["pred"]}) + "\n")
print(f"   60 held-out git questions: {same}/60 same answer as at full memory; {(time.time() - t0) / 60:.2f} s per question")
PY
  P=$(cat $QW/memtest24_api.pid); tr "\0" " " < /proc/$P/cmdline | grep -q "port 8510" && kill $P
fi
tr "\0" " " < /proc/$VP/cmdline 2>/dev/null | grep -q "port 30150" && kill $VP
sleep 20
