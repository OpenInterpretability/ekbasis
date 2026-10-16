#!/bin/bash
# Self-test of every compare.py (no model, no GPU): Ekbasis-27B's own published files put in Skopos' place must give a
# difference of 0 on every measure, no blocker and no flag, and reproduce the published numbers they print.
#   bash common/selftest.sh [python]
set -eu
PRE=$(cd "$(dirname "$0")/.." && pwd); PY=${1:-python3}; T=$(mktemp -d); R=$PRE/ref
mkdir -p "$T"/{p3,p4,p7,p8,p9}
ln -s "$R/release_eval/release_long_chain.jsonl" "$T/p3/long_chain.jsonl"
ln -s "$R/release_eval/long_chain3.jsonl" "$T/p4/long_chain3_rules.jsonl"
ln -s "$R/release_eval/long_chain3_fresh.jsonl" "$T/p4/long_chain3_fresh.jsonl"
ln -s "$R/release_eval/long_chain3_fresh_text.jsonl" "$T/p4/long_chain3_fresh_text.jsonl"
ln -s "$R/handoff/image_chain_w4a5.json" "$T/p7/image_chain.json"
ln -s "$R/release_eval/short_eval_release.json" "$T/p8/short_eval_release.json"
"$PY" "$PRE/P8/make_saved.py" "$T/p8/short_eval_saved.json" > /dev/null
for s in agent agent_hard; do
  "$PY" -c "import json, sys; d = json.load(open(sys.argv[1])); json.dump({'selftest': d['Ekbasis (release)']}, open(sys.argv[2], 'w'))" \
    "$R/release_eval/search_w4a5rel_$s.json" "$T/p9/search_selftest_$s.json"
  grep "seconds:" "$R/release_eval/plan_search.out" | sed -n "$([ $s = agent ] && echo 1 || echo 2)p" | sed "s/Ekbasis (release)/selftest/" > "$T/p9/search_$s.log"
done
run() { local n=$1; shift; "$PY" "$@" --out "$T/$n.json" > /dev/null
  "$PY" - "$T/$n.json" "$n" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
nz = [m["measure"] for m in d["measures"] if abs(m.get("difference", 0)) > 1e-12 or (m.get("rule") == "counts" and m["skopos"] != m["ekbasis27b"])]
s = d["summary"]
ok = not nz and not s["release_blockers"] and not s["flagged_worse_by_2"]
print(f"{sys.argv[2]:4s} {'ok' if ok else 'FAIL'}: {len(d['measures'])} measures, nonzero {nz[:3]}, summary {s}")
PY
}
run P1 "$PRE/P1/compare.py" --skopos "$R/release_eval"
run P3 "$PRE/P3/compare.py" --skopos "$T/p3"
run P4 "$PRE/P4/compare.py" --skopos "$T/p4"
run P5 "$PRE/P5/compare.py" --skopos "$R/release_eval/speed_bf16" --ekbasis "$R/release_eval/speed_bf16"
run P7 "$PRE/P7/compare.py" --skopos "$T/p7"
run P8 "$PRE/P8/compare.py" --skopos "$T/p8"
run P9 "$PRE/P9/compare.py" --skopos "$T/p9" --skopos-tag selftest
run P10 "$PRE/P10/compare.py" --skopos "$R/handoff/realuse_pm_pred_w4a5.json"
run P11 "$PRE/P11/compare.py" --skopos "$R/handoff/quant_w4a5_memory_tests.json"
run P12 "$PRE/P12/intent/compare.py" --skopos "$R/intent_replay"
"$PY" -c "
import json, sys; d = json.load(open(sys.argv[1]))
t = d['tables']['rules_compared [skopos, ekbasis27b]']
print('P4 rules as published (exact, wrong/100, looks/100):', [(r['rule'], r['exact'][1], round(r['wrong_steps_per_100_actions'][1], 2), round(r['looks_per_100_actions'][1], 1)) for r in t])" "$T/P4.json"
rm -rf "$T"
