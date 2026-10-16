#!/bin/bash
exec >> /root/v50p/image.log 2>&1
cd /root/v50p
echo "skopos int4 $(date -u +%T)"; python3 image_served.py skopos_int4 http://127.0.0.1:8603 200
for p in $(pgrep -f "^python3 serve.py --model /root/Skopos-R4-27B-INT4"); do kill $p; done
for p in $(pgrep -f "[v]llm serve /root/Skopos-R4-27B-INT4"); do kill $p; done
sleep 20
python3 -c "from huggingface_hub import snapshot_download; snapshot_download('caiovicentino1/Ekbasis-27B-INT4', local_dir='/root/Ekbasis-27B-INT4')" || { echo DL_FALHOU; exit 1; }
cd /root/Ekbasis-27B-INT4
setsid bash serve_vllm.sh /root/Ekbasis-27B-INT4 8601 0.85 > /root/v50p/vllm_ekb_int4.log 2>&1 < /dev/null &
for i in $(seq 1 180); do curl -sf localhost:8601/v1/models >/dev/null && break; sleep 10; done
setsid python3 serve.py --model /root/Ekbasis-27B-INT4 --vllm-url http://127.0.0.1:8601 --port 8603 --host 127.0.0.1 > /root/v50p/front_ekb_int4.log 2>&1 < /dev/null &
for i in $(seq 1 60); do grep -q "ready at" /root/v50p/front_ekb_int4.log && break; sleep 5; done
cd /root/v50p && echo "ekbasis int4 $(date -u +%T)" && python3 image_served.py ekbasis_int4 http://127.0.0.1:8603 200
echo IMAGE_ALL_DONE $(date -u +%T)
