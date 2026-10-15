#!/bin/bash
exec >> /root/frontier.log 2>&1
until grep -q R1_DONE /root/v50p/r1.log && grep -q DL_DONE /root/dl_agentworld.log; do sleep 60; done
echo "vllm inicio $(date -u +%T)"
setsid vllm serve /root/Qwen-AgentWorld-35B-A3B --served-model-name aw --host 127.0.0.1 --port 8100 --max-model-len 32768 --gpu-memory-utilization 0.90 > /root/aw_vllm.log 2>&1 < /dev/null &
for i in $(seq 1 120); do curl -sf localhost:8100/v1/models >/dev/null && break; sleep 10; done
curl -sf localhost:8100/v1/models >/dev/null || { echo "AW NAO SUBIU"; tail -20 /root/aw_vllm.log; exit 1; }
cd /root/v50p && mkdir -p frontier
for s in "git_long 900" "guard_known 800" "fhorizon 700" "latent_test 800"; do set -- $s; python3 frontier_eval.py $1 $2 frontier/aw_$1.jsonl; done
for p in $(pgrep -f "[v]llm serve /root/Qwen-AgentWorld"); do kill $p; done
echo FRONTIER_DONE $(date -u +%T)
