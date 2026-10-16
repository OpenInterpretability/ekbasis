#!/bin/bash
# P10, real use on real repositories: realuse_guard.py (ported, CHANGES.diff) ON THE MAC, where the 4 Oct copies of the two
# repositories are (BASE), against the GPU machine's API through a tunnel (the release run reached the rig the same way;
# the main thread opens it, e.g. ssh -L 18603:127.0.0.1:8603). Steps:
#   1. the client that ran (ekbasis 0.1.0 in venv_launch, installed 4 Oct 09:53, before the run): file hashes checked;
#   2. truth again, with no model: every scenario re-executed on fresh copies of BASE; it must equal the published run's
#      truth.json scenario by scenario, or the base copies have changed and nothing is predicted (loud stop);
#   3. predictions of <tag> (the hook and git.check, as published).
#   OUTROOT=<dir on the Mac> EKBASIS_URL=http://127.0.0.1:18603 EXPECT_MODEL=/root/Skopos-R4-27B bash P10/run_mac.sh <tag>
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
: "${OUTROOT:?set OUTROOT (a folder on the Mac)}" "${EKBASIS_URL:?the tunnel to the GPU machine API}" "${EXPECT_MODEL:?the model folder the API must serve}"
TAG=$1; O=$OUTROOT/P10; mkdir -p "$O"
export BASE=${BASE:-$HERE/base_backup}   # the main thread's backup of realuse2/base_* (private); the truth re-check below validates it
export CLIENT_VENV=${CLIENT_VENV:-<mac-scratch>/venv_launch}
for n in code_eikos openinterp_web; do [ -d "$BASE/base_$n/.git" ] || { echo "MISSING $BASE/base_$n: P10 cannot run as published"; exit 1; }; done
( cd "$CLIENT_VENV/lib/python3.9/site-packages" && shasum -a 256 -c "$HERE/client_venv_launch.sha256" ) || { echo "CLIENT CHANGED"; exit 1; }
"$CLIENT_VENV/bin/python" -c "import ekbasis, sys; sys.exit(ekbasis.__version__ != '0.1.0')" || { echo "CLIENT IS NOT 0.1.0"; exit 1; }
curl -s -m 20 "$EKBASIS_URL/health" | /usr/bin/python3 -c "import json, sys; h = json.load(sys.stdin); sys.exit(0 if h.get('ok') and h['model'].rstrip('/') == sys.argv[1].rstrip('/') else 1)" "$EXPECT_MODEL" \
  || { echo "THE API AT $EKBASIS_URL DOES NOT SERVE $EXPECT_MODEL"; exit 1; }
if [ ! -f "$O/truth_ok" ]; then   # once per session: the base copies still give the published truth
  mkdir -p "$O/truth"; W=$(mktemp -d /tmp/p10truth.XXXXXX)   # internal APFS disk, as the original's folder
  WORK=$W OUT=$O/truth /usr/bin/python3 "$HERE/realuse_guard.py" truth | tee "$O/truth/truth.log"
  rm -rf "$W"
  /usr/bin/python3 - "$O/truth/truth.json" "$HERE/../_orig/realuse/truth.json" <<'PY' || { echo "TRUTH DIFFERS FROM THE PUBLISHED RUN: base copies changed, P10 not run"; exit 1; }
import json, sys
a, b = (json.load(open(p)) for p in sys.argv[1:])
k = lambda r: (r["repo"], r["sid"], r["name"], tuple(r["commands"]), r["lost"], tuple(r["fails"]), r["n_lost"])
bad = [x for x, y in zip(map(k, a), map(k, b)) if x != y]
print(f"truth re-check: {len(a) - len(bad)}/{len(b)} scenarios identical"); sys.exit(1 if bad or len(a) != len(b) else 0)
PY
  touch "$O/truth_ok"
fi
W=$(mktemp -d /tmp/p10pred.XXXXXX)
WORK=$W OUT=$O /usr/bin/python3 "$HERE/realuse_guard.py" predict "$TAG" "$EKBASIS_URL" | tee "$O/predict_$TAG.log"
rm -rf "$W"
