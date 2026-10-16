#!/bin/bash
# After the ftest confirmation: build R4's INT4 (production recipe), serve it like production, check it against the
# bf16 trainer readout (equivalence) and run the release read on the INT4 files (compare_release vs the public release).
exec >> /root/v50p/int4_r4.log 2>&1
until grep -q CONFIRM_FTEST_DONE /root/v50p/confirm_ftest.log 2>/dev/null; do sleep 60; done
cd /root/v50p
echo "quantizacao inicio $(date -u +%T)"
/root/lc_venv/bin/python quantize_r4.py /root/Skopos-R4-27B /root/Skopos-R4-27B-INT4 int4 || { echo QUANT_FALHOU; exit 1; }
for f in serve.py serve_vllm.sh letter_adapter.py decision_core.py LICENSE LICENSE-Eikos LICENSE-Qwen NOTICE; do
  [ -f /root/Skopos-R4-27B/$f ] && cp -n /root/Skopos-R4-27B/$f /root/Skopos-R4-27B-INT4/; done
du -sh /root/Skopos-R4-27B-INT4
cd /root/Skopos-R4-27B-INT4
setsid bash serve_vllm.sh /root/Skopos-R4-27B-INT4 8601 0.85 > /root/v50p/vllm_r4_int4.log 2>&1 < /dev/null &
for i in $(seq 1 180); do curl -sf localhost:8601/v1/models >/dev/null && break; sleep 10; done
curl -sf localhost:8601/v1/models >/dev/null || { echo VLLM_INT4_NAO_SUBIU; tail -20 /root/v50p/vllm_r4_int4.log; exit 1; }
setsid python3 serve.py --model /root/Skopos-R4-27B-INT4 --vllm-url http://127.0.0.1:8601 --port 8603 --host 127.0.0.1 > /root/v50p/front_r4_int4.log 2>&1 < /dev/null &
for i in $(seq 1 60); do grep -q "ready at" /root/v50p/front_r4_int4.log && break; sleep 5; done
cd /root/v50p && echo "equivalencia INT4 x trainer bf16" && python3 equiv_r4.py
export URL=http://127.0.0.1:8603 PAR=16 OUT=/root/v50p/release_r4_int4
mkdir -p $OUT
python3 release_eval.py && python3 release_eval_extra_rtx.py && OUT=/root/v50p/release_r4_int4 READOUT=r4_readout python3 guard_big_served_rtx.py
python3 compare_release.py release_ref release_r4_int4 > release_r4_int4/COMPARE.json && tail -14 release_r4_int4/COMPARE.json
echo INT4_R4_DONE $(date -u +%T)
python3 /root/backup_hf.py int4-r4
