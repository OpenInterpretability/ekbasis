#!/bin/bash
# PREREG_ADDENDUM A6 (bf16 equivalence saved) and A5 (latency/cost: Skopos INT4 vs Ekbasis-27B-INT4, same GPU and serving).
exec >> /root/v50p/addendum_a5a6.log 2>&1
echo "inicio $(date -u +%T)"
until grep -q ADDENDUM_BUILDS_DONE /root/v50p/addendum_builds.log; do sleep 30; done
serve() {  # folder
  for p in $(pgrep -f "^python3 serve.py --model "); do kill $p; done
  for p in $(pgrep -f "^/usr/bin/python3 /usr/local/bin/vllm serve "); do kill $p; done
  sleep 20; cd "$1"
  setsid bash serve_vllm.sh "$1" 8601 0.85 > /root/v50p/vllm_a5.log 2>&1 < /dev/null &
  for i in $(seq 1 180); do curl -sf localhost:8601/v1/models >/dev/null && break; sleep 10; done
  setsid python3 serve.py --model "$1" --vllm-url http://127.0.0.1:8601 --port 8603 --host 127.0.0.1 > /root/v50p/front_a5.log 2>&1 < /dev/null &
  for i in $(seq 1 60); do grep -q "ready at" /root/v50p/front_a5.log 2>/dev/null && break; sleep 5; done
  grep -q "ready at" /root/v50p/front_a5.log && echo "served $1 $(date -u +%T)" || { echo "NAO_SUBIU $1"; exit 1; }
  cd /root/v50p
}
serve /root/Skopos-R4-27B
python3 equiv_r4_save.py /root/v50p/served_equivalence_bf16.json && echo "A6_DONE $(date -u +%T)"
serve /root/Skopos-R4-27B-INT4
python3 latency_suite.py http://127.0.0.1:8603 mac_items.json latency_skopos_int4.json && echo "A5_SKOPOS_DONE $(date -u +%T)"
python3 -c "from huggingface_hub import snapshot_download as s; print(s(\"caiovicentino1/Ekbasis-27B-INT4\", local_dir=\"/dev/shm/Ekbasis-27B-INT4\"))"
serve /dev/shm/Ekbasis-27B-INT4
python3 latency_suite.py http://127.0.0.1:8603 mac_items.json latency_ekbasis_int4.json && echo "A5_EKBASIS_DONE $(date -u +%T)"
for p in $(pgrep -f "^python3 serve.py --model "); do kill $p; done
for p in $(pgrep -f "^/usr/bin/python3 /usr/local/bin/vllm serve "); do kill $p; done
python3 /root/backup_hf.py addendum-a5a6
echo A5A6_DONE
