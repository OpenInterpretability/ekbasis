#!/bin/bash
# Inputs of the pre-launch battery on the GPU machine. Source of the item files: the public dataset
# caiovicentino1/ekbasis-data, raw/ (the files the release evaluation read from /dev/shm/conseq/fac), each checked against
# the sha256 of the dataset's MANIFEST.sha256 (values copied below on 2026-10-15). Ekbasis-27B's builds: its public repos
# (the INT4 one is usually already in /root/Ekbasis-27B-INT4 from run_image.sh). The commit of each download is logged.
#   bash fetch_data.sh [items] [ekbasis_bf16] [ekbasis_int4]      (no argument: all three)
set -eu
. "$(dirname "$0")/env.sh"
what=${*:-items ekbasis_bf16 ekbasis_int4}
shaok() { [ -f "$2" ] && "$PY" -c "import hashlib, sys; sys.exit(hashlib.sha256(open(sys.argv[2], 'rb').read()).hexdigest() != sys.argv[1])" "$1" "$2"; }
if [[ " $what " == *" items "* ]]; then
  mkdir -p "$DATA/fac"
  while read -r sha f; do
    if ! shaok "$sha" "$DATA/fac/$f"; then
      "$PY" -c "from huggingface_hub import hf_hub_download; import shutil, sys; shutil.copy(hf_hub_download('caiovicentino1/ekbasis-data', 'raw/' + sys.argv[1], repo_type='dataset'), sys.argv[2])" "$f" "$DATA/fac/$f"
      shaok "$sha" "$DATA/fac/$f" || { echo "SHA256 MISMATCH: $f"; exit 1; }
    fi
    echo "ok $f"
  done <<'EOF'
5d4f4ed2bf36451b13faa37d6d69397d714bd2effb490ceb423a5f9c2be1a92e git2_test_known.jsonl
0ea7c0b6c1afc9a02dcae780c55bfecde375dbd0ac9af0101bbccbc85fe990b4 git2_test_held.jsonl
c9f4db0ac4de2cb99746fe11dffacf3df7fb09a11db0298c6d5b183d3dae135f git3_test_held.jsonl
f20d23f5725d333b243d89cfb81a1b6dda6dfee92739a512d7f74afe16945667 ftest_family.jsonl
66bd7240dfb15ecfc5e7984e390afe4f80780d63f28671d04da9b3e026b2590d gold0_ftest_family.jsonl
EOF
fi
dl() {  # repo, folder: download if the folder has no weights; log the repo commit
  if ! ls "$2"/*.safetensors > /dev/null 2>&1; then
    "$PY" -c "from huggingface_hub import snapshot_download; import sys; snapshot_download(sys.argv[1], local_dir=sys.argv[2])" "$1" "$2"
  fi
  "$PY" -c "from huggingface_hub import HfApi; import sys; print(sys.argv[1], HfApi().model_info(sys.argv[1]).sha)" "$1" | tee -a "$LOGS/model_commits.txt"
  [ -f "$2/serve_vllm.sh" ] && [ -f "$2/serve.py" ] || { echo "no serving files in $2"; exit 1; }
}
[[ " $what " == *" ekbasis_bf16 "* ]] && dl caiovicentino1/Ekbasis-27B "$EKBASIS_BF16"
[[ " $what " == *" ekbasis_int4 "* ]] && dl caiovicentino1/Ekbasis-27B-INT4 "$EKBASIS_INT4"
echo "fetch done $(date -u +%T)"
