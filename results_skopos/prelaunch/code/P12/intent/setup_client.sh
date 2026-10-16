#!/bin/bash
# The intent_check client the replay study ran (README: "intent_check 0.1.19"; go.sh: PYTHONPATH=client): the published
# wheel ekbasis 0.1.19 (sha256 pinned below) with the study's client.diff applied (its base blob f0ad2d6 is 0.1.19's
# ekbasis/intent.py; the result must be blob b5b88b0421f1..., the diff's target). Standard library only.
#   bash setup_client.sh <dir>      -> <dir>/client/ekbasis
set -eu
HERE=$(cd "$(dirname "$0")" && pwd); W=$1; mkdir -p "$W"; cd "$W"
PY=${PY:-python3}
[ -f ekbasis-0.1.19-py3-none-any.whl ] || "$PY" -m pip download ekbasis==0.1.19 --no-deps -d . -q
"$PY" -c "import hashlib, sys; sys.exit(hashlib.sha256(open(sys.argv[1], 'rb').read()).hexdigest() != sys.argv[2])" \
  ekbasis-0.1.19-py3-none-any.whl dd66236edfe1af67d8934b0ae8fe963cf936fcedfafbbedbcc877877c8769bba || { echo "WHEEL HASH DIFFERS"; exit 1; }
rm -rf client && mkdir client && "$PY" -m zipfile -e ekbasis-0.1.19-py3-none-any.whl client
[ "$(git hash-object client/ekbasis/intent.py)" = f0ad2d6f41e75981761d66d4f2d416b1f3ad1f8b ] || { echo "BASE intent.py DIFFERS"; exit 1; }
( cd client && patch -p1 -s < "$HERE/../../_orig/intent_replay/client.diff" )
[ "$(git hash-object client/ekbasis/intent.py)" = b5b88b0421f18807663b18f2a8d070c640db4c24 ] || { echo "PATCHED intent.py DIFFERS"; exit 1; }
echo "client ok: ekbasis 0.1.19 + client.diff (intent.py blob b5b88b0)"
