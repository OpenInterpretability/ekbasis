#!/bin/bash
# After the FP8 read (FP8 still served on :8603): fresh ftest on FP8, then re-serve INT4 and run it there too.
exec >> /root/v50p/ftest_builds.log 2>&1
until grep -q "FP8_R4_DONE\|FP8_FALHOU" /root/v50p/fp8_r4.log 2>/dev/null; do sleep 60; done
cd /root/v50p
curl -sf localhost:8603/health >/dev/null 2>&1 || curl -sf localhost:8601/v1/models >/dev/null && python3 ftest_fresh_served.py fp8
for p in $(pgrep -f "^python3 serve.py --model /root/Skopos-R4-27B-FP8"); do kill $p; done
for p in $(pgrep -f "[v]llm serve /root/Skopos-R4-27B-FP8"); do kill $p; done
sleep 20; cd /root/Skopos-R4-27B-INT4
setsid bash serve_vllm.sh /root/Skopos-R4-27B-INT4 8601 0.85 > /root/v50p/vllm_r4_int4b.log 2>&1 < /dev/null &
for i in $(seq 1 180); do curl -sf localhost:8601/v1/models >/dev/null && break; sleep 10; done
setsid python3 serve.py --model /root/Skopos-R4-27B-INT4 --vllm-url http://127.0.0.1:8601 --port 8603 --host 127.0.0.1 > /root/v50p/front_r4_int4b.log 2>&1 < /dev/null &
for i in $(seq 1 60); do grep -q "ready at" /root/v50p/front_r4_int4b.log && break; sleep 5; done
cd /root/v50p && python3 ftest_fresh_served.py int4
echo FTEST_BUILDS_DONE $(date -u +%T)
