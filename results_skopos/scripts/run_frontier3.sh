#!/bin/bash
# Addendum B: thinking off, 8,192 tokens, 64 concurrent, smaller samples (the 4,096-token thinking run truncated 55/66).
exec >> /root/frontier.log 2>&1
echo "adendo B inicio $(date -u +%T)"
if ! curl -sf localhost:8100/v1/models >/dev/null; then
  setsid vllm serve /root/Qwen-AgentWorld-35B-A3B --served-model-name aw --host 127.0.0.1 --port 8100 --max-model-len 32768 --gpu-memory-utilization 0.90 --language-model-only --max-num-seqs 64 > /root/aw_vllm.log 2>&1 < /dev/null &
  for i in $(seq 1 240); do curl -sf localhost:8100/v1/models >/dev/null && break; sleep 10; done
fi
if curl -sf localhost:8100/v1/models >/dev/null; then
  cd /root/v50p && mkdir -p frontier
  [ -f frontier/aw_git_long.jsonl ] && mv frontier/aw_git_long.jsonl frontier/aw_git_long.v1_truncado.jsonl
  export AW_THINK=0 AW_MAX=8192 AW_CONC=64
  for s in "git_long 300" "guard_known 200" "fhorizon 300" "latent_test 200"; do set -- $s; python3 frontier_eval.py $1 $2 frontier/aw_$1.jsonl; done
else
  echo "AW NAO SUBIU -- FRONTIER_FAILED (a fila segue)"; tail -20 /root/aw_vllm.log
fi
for p in $(pgrep -f "[v]llm serve /root/Qwen-AgentWorld"); do kill $p; done
echo FRONTIER_DONE $(date -u +%T)
