#!/bin/bash
# PREREG_CERTIFIED_CARRYOVER.md, one served model per call (Skopos INT4, then bf16), after the pre-registration is sealed:
#   EKBASIS_URL=http://127.0.0.1:8000 TAG=skopos-int4 bash run_carryover.sh
#   EKBASIS_URL=http://127.0.0.1:8000 TAG=skopos-bf16 bash run_carryover.sh
# Needs: python3 with numpy and the pinned client (pip install ekbasis==0.1.41); the folder as sealed (MANIFEST.sha256);
# data/overlap_excluded.json (overlap_step.py). Writes results/<TAG>_raw.jsonl, <TAG>_meta.json, <TAG>_summary.json.
set -euo pipefail
H="$(cd "$(dirname "$0")" && pwd)"
: "${EKBASIS_URL:?EKBASIS_URL is required}"; : "${TAG:?TAG is required}"
cd "$H"
sha256sum -c --quiet MANIFEST.sha256 || { echo "the folder differs from the sealed manifest: stop"; exit 1; }
[ -s data/overlap_excluded.json ] || { echo "data/overlap_excluded.json is missing (overlap_step.py): stop"; exit 1; }
python3 -B run_carryover.py 2>&1 | tee -a "results/${TAG}_run.log"
TAG="$TAG" python3 -B analyze_carryover.py > "results/${TAG}_analysis_stdout.json"
python3 - "$TAG" <<'PY'
import json, sys
d = json.load(open(f"results/{sys.argv[1]}_summary.json"))
L2 = d["model"]["a02"]["L2"]
print(f"{sys.argv[1]}: scenarios {d['scenarios_done']} (excluded {d['scenarios_excluded_overlap']}, failed {d['requests_failed']}), "
      f"L2 accepted {L2['accepted']}, errors {L2['errors_among_accepted']}, weighted {L2['error_rate_among_accepted_weighted']}, "
      f"95% upper {L2['cp95_upper_overall']}, verified (weighted) {L2['verified_share_weighted']}; criteria {d['criteria']}")
PY
echo "for the card: copy results/${TAG}_summary.json to release_skopos/results/certified_carryover_${TAG//-/_}.json after review"
