#!/bin/bash
exec >> /root/v50p/serve_r4.log 2>&1
until grep -q "MERGE_DONE\|Error\|Traceback" /root/v50p/merge_r4.log; do sleep 10; done
grep -q MERGE_DONE /root/v50p/merge_r4.log || { echo MERGE_FALHOU; tail -5 /root/v50p/merge_r4.log; exit 1; }
cd /root/Skopos-R4-27B
setsid bash serve_vllm.sh /root/Skopos-R4-27B 8601 0.85 > /root/v50p/vllm_r4.log 2>&1 < /dev/null &
for i in $(seq 1 180); do curl -sf localhost:8601/v1/models >/dev/null && break; sleep 10; done
curl -sf localhost:8601/v1/models >/dev/null || { echo VLLM_NAO_SUBIU; tail -20 /root/v50p/vllm_r4.log; exit 1; }
setsid python3 serve.py --model /root/Skopos-R4-27B --vllm-url http://127.0.0.1:8601 --port 8603 --host 127.0.0.1 > /root/v50p/front_r4.log 2>&1 < /dev/null &
for i in $(seq 1 60); do grep -q "ready at" /root/v50p/front_r4.log && break; sleep 5; done
grep "ready at" /root/v50p/front_r4.log && echo SERVE_R4_READY $(date -u +%T) || { echo FRONT_NAO_SUBIU; tail -20 /root/v50p/front_r4.log; }
