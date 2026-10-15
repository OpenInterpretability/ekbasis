#!/bin/bash
# PREREG_ADDENDUM.md A3 on FP8 and MLX (after the bf16 part and T3c). Same scorer, each build through its own server.
exec >> /root/v50p/addendum_builds.log 2>&1
echo "inicio $(date -u +%T)"
for p in $(pgrep -f "^python3 serve.py --model /root/Skopos-R4-27B "); do kill $p; done
for p in $(pgrep -f "^/usr/bin/python3 /usr/local/bin/vllm serve /root/Skopos-R4-27B "); do kill $p; done
sleep 20
cd /root/Skopos-R4-27B-FP8
setsid bash serve_vllm.sh /root/Skopos-R4-27B-FP8 8601 0.85 > /root/v50p/vllm_fp8_add.log 2>&1 < /dev/null &
for i in $(seq 1 180); do curl -sf localhost:8601/v1/models >/dev/null && break; sleep 10; done
setsid python3 serve.py --model /root/Skopos-R4-27B-FP8 --vllm-url http://127.0.0.1:8601 --port 8603 --host 127.0.0.1 > /root/v50p/front_fp8_add.log 2>&1 < /dev/null &
for i in $(seq 1 60); do grep -q "ready at" /root/v50p/front_fp8_add.log && break; sleep 5; done
grep -q "ready at" /root/v50p/front_fp8_add.log || { echo FP8_NAO_SUBIU; exit 1; }
cd /root/v50p && URLS=http://127.0.0.1:8603 PAR=16 python3 score_calib_build.py calib_items.json calib_scores_skopos_fp8.jsonl
echo "A3_FP8_DONE $(date -u +%T)"
for p in $(pgrep -f "^python3 serve.py --model /root/Skopos-R4-27B-FP8"); do kill $p; done
for p in $(pgrep -f "^/usr/bin/python3 /usr/local/bin/vllm serve /root/Skopos-R4-27B-FP8"); do kill $p; done
sleep 20
cd /root/Skopos-R4-27B-MLX-4bit
for port in 8605 8606; do setsid /root/mlx_venv/bin/python mlx_serve.py /root/Skopos-R4-27B-MLX-4bit --port $port --cache-gb 2 > /root/v50p/mlx_add_$port.log 2>&1 < /dev/null & sleep 60; done
for i in $(seq 1 120); do curl -sf localhost:8606/health >/dev/null && curl -sf localhost:8605/health >/dev/null && break; sleep 5; done
cd /root/v50p && URLS=http://127.0.0.1:8605,http://127.0.0.1:8606 PAR=2 python3 score_calib_build.py calib_items.json calib_scores_skopos_mlx.jsonl
echo "A3_MLX_DONE $(date -u +%T)"
for p in $(pgrep -f "^/root/mlx_venv/bin/python mlx_serve.py"); do kill $p; done
python3 /root/backup_hf.py addendum-builds
echo ADDENDUM_BUILDS_DONE
