#!/bin/bash
exec >> /root/v50p/fp8_r4.log 2>&1
until grep -q INT4_R4_DONE /root/v50p/int4_r4.log 2>/dev/null; do sleep 60; done
cd /root/v50p
for p in $(pgrep -f "^python3 serve.py --model /root/Skopos-R4-27B-INT4"); do kill $p; done
for p in $(pgrep -f "[v]llm serve /root/Skopos-R4-27B-INT4"); do kill $p; done
sleep 20
/root/lc_venv/bin/python quantize_r4.py /root/Skopos-R4-27B /root/Skopos-R4-27B-FP8 fp8 || { echo FP8_FALHOU; exit 1; }
for f in serve.py serve_vllm.sh letter_adapter.py decision_core.py LICENSE LICENSE-Eikos LICENSE-Qwen NOTICE; do
  [ -f /root/Skopos-R4-27B/$f ] && cp -n /root/Skopos-R4-27B/$f /root/Skopos-R4-27B-FP8/; done
cd /root/Skopos-R4-27B-FP8
setsid bash serve_vllm.sh /root/Skopos-R4-27B-FP8 8601 0.85 > /root/v50p/vllm_r4_fp8.log 2>&1 < /dev/null &
for i in $(seq 1 180); do curl -sf localhost:8601/v1/models >/dev/null && break; sleep 10; done
setsid python3 serve.py --model /root/Skopos-R4-27B-FP8 --vllm-url http://127.0.0.1:8601 --port 8603 --host 127.0.0.1 > /root/v50p/front_r4_fp8.log 2>&1 < /dev/null &
for i in $(seq 1 60); do grep -q "ready at" /root/v50p/front_r4_fp8.log && break; sleep 5; done
cd /root/v50p && python3 equiv_r4.py
export URL=http://127.0.0.1:8603 PAR=16 OUT=/root/v50p/release_r4_fp8
mkdir -p $OUT
python3 release_eval.py && python3 release_eval_extra_rtx.py && OUT=/root/v50p/release_r4_fp8 READOUT=r4_readout python3 guard_big_served_rtx.py
python3 compare_release.py release_ref release_r4_fp8 > release_r4_fp8/COMPARE.json && tail -14 release_r4_fp8/COMPARE.json
echo FP8_R4_DONE $(date -u +%T)
python3 /root/backup_hf.py fp8-r4
