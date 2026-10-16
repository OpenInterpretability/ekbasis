#!/bin/bash
# Pre-launch battery, PRELAUNCH_EVAL.md Part A (P1, P3-P12; P2 was done by the main thread: P2/p2_git3_by_type.json),
# on the GPU machine (one RTX PRO 6000), ordered by GPU state so each build is loaded once. Copy this folder to $PRE
# (default /root/prelaunch) and run:   PHASES="0 A B C D E F" bash run_all.sh  > $OUTROOT/run_all.log 2>&1
# Mac-side steps (P10, through a tunnel to $API_PORT) are printed where they belong; the main thread runs them.
# Estimates on one GPU (the release ran its accuracy items on 3 replicas; ~3x its wall time here):
#   0  inputs, checks ......................................... 5 min (+ ~15-30 min to download Ekbasis-27B bf16, 54 GB)
#   A  Skopos bf16: P5 speed alone 10 min; then P1, P3, P4, P6, P7, P8 and the P12 preflight substitute
#      concurrently, as the release ran them ............................................................ 6-10 h
#   B  Ekbasis-27B bf16: P5 speed 10 min; P6 (no published per-item answers) 2 min; P1, P8 identity re-runs 3 min;
#      preflight substitute 1 min ........................................................................... 20 min
#   C  no server, PyTorch: P9 Skopos (rig: 57 min on the same GPU model) ~1 h; Ekbasis-27B (seconds and puzzle
#      identity; EK_P9=0 to skip) ~1 h ..................................................................... 1-2 h
#   D  Skopos INT4: P12 intent replay (8,560 states, concurrency 3) 15-40 min; preflight substitute 1 min ... ~45 min
#   E  Ekbasis-27B INT4 (control for the hosted reference): the same ....................................... ~45 min
#   F  memory caps, no other server: P11, 4 caps ............................................................ ~40 min
#   total about 10-15 h of GPU time; then the compares (seconds, CPU).
set -u
. "$(dirname "$0")/common/env.sh"; . "$PRE/common/serve.sh"
PHASES=${PHASES:-0 A B C D E F}
say() { echo "[$(date -u +%FT%TZ)] $*"; }
has() { [[ " $PHASES " == *" $1 "* ]]; }
mac() { say "MAC STEP (main thread): tunnel 127.0.0.1:18603 -> GPU:$API_PORT, then on the Mac: OUTROOT=<mac dir> EKBASIS_URL=http://127.0.0.1:18603 EXPECT_MODEL=$2 bash P10/run_mac.sh $1"; }

if has 0; then
  say "phase 0: inputs and checks"
  bash "$PRE/common/fetch_data.sh" items || exit 1
  "$PY" -c "import scipy, PIL, transformers, torch, vllm" || { say "missing python packages"; exit 1; }
  "$PY" -c "import peft" || say "WARNING: peft missing (P9 needs it)"
  command -v git > /dev/null && command -v patch > /dev/null || { say "need git and patch (P12 client)"; exit 1; }
  for m in "$SKOPOS_BF16" "$SKOPOS_INT4" "$SKOPOS_FP8"; do [ -f "$m/serve_vllm.sh" ] || { say "missing model folder $m"; exit 1; }; done
  for d in release_r4 release_r4_fp8 release_r4_int4; do [ -f "$RELREAD/$d/preds_git3_test_held.jsonl" ] || { say "missing $RELREAD/$d (P11 reference)"; exit 1; }; done
  # the items this machine's Python regenerates from seeds are the published run's (fails loudly otherwise)
  "$PY" "$PRE/common/identity_offline.py" "$OUTROOT/identity_offline.json" --data "$DATA/fac" > /dev/null || exit 1
  "$PY" - "$OUTROOT/identity_offline.json" <<'PY' || { say "IDENTITY CHECK FAILED: items differ from the published run"; exit 1; }
import json, sys
d = json.load(open(sys.argv[1]))
ok = [all(v.values()) for v in [{k: x for k, x in d["P1"][s].items() if isinstance(x, bool)} for s in d["P1"]]]
ok += [d["P3"]["depends_on_start_per_world_and_length"], d["P4"]["n_vars_as_published"], d["P5"]["items_as_published"],
       d["P6"]["printed_example_equal"], d["P7"]["items_as_release_run"]]
ok += [v["question_counts_multiple_of_actions_x_variables"] == "180/180" for v in d["P9"].values()]
print("identity checks:", sum(ok), "of", len(ok)); sys.exit(0 if all(ok) else 1)
PY
  df -h /root | tail -1
  bash "$PRE/common/fetch_data.sh" ekbasis_bf16 ekbasis_int4 || exit 1
fi

if has A; then
  say "phase A: Skopos bf16"; serve_up "$SKOPOS_BF16" skopos_bf16
  bash "$PRE/P5/run.sh" skopos_bf16                       # speed first, alone on the GPU
  say "A: accuracy items, concurrently"
  ( bash "$PRE/P1/run.sh" skopos_bf16; bash "$PRE/P8/run.sh" skopos_bf16; bash "$PRE/P6/run.sh" skopos_bf16
    bash "$PRE/P12/preflight_substitute/run.sh" skopos_bf16 ) > "$LOGS/A_short.log" 2>&1 &
  bash "$PRE/P7/run.sh" skopos_bf16 > "$LOGS/A_P7.log" 2>&1 &
  bash "$PRE/P3/run.sh" skopos_bf16 > "$LOGS/A_P3.log" 2>&1 &
  bash "$PRE/P4/run.sh" skopos_bf16 > "$LOGS/A_P4.log" 2>&1 &
  mac skopos_bf16 "$SKOPOS_BF16"
  wait; say "phase A done"
fi

if has B; then
  say "phase B: Ekbasis-27B bf16"; serve_up "$EKBASIS_BF16" ekbasis_bf16
  bash "$PRE/P5/run.sh" ekbasis_bf16
  for p in P6 P1 P8; do bash "$PRE/$p/run.sh" ekbasis_bf16; done
  bash "$PRE/P12/preflight_substitute/run.sh" ekbasis_bf16
  mac ekbasis_bf16 "$EKBASIS_BF16"; say "(the Ekbasis-27B P10 run is the same-tunnel timing control: optional)"
  say "phase B done"
fi

if has C; then
  say "phase C: P9 (PyTorch, no server)"; serve_down
  bash "$PRE/P9/run.sh" skopos_bf16
  [ "${EK_P9:-1}" = 1 ] && bash "$PRE/P9/run.sh" ekbasis_bf16
  say "phase C done"
fi

if has D; then
  say "phase D: Skopos INT4"; serve_up "$SKOPOS_INT4" skopos_int4
  bash "$PRE/P12/intent/run.sh" skopos_int4
  bash "$PRE/P12/preflight_substitute/run.sh" skopos_int4
  mac skopos_int4 "$SKOPOS_INT4"; say "(wait for the Mac step before phase E)"
  say "phase D done"
fi

if has E; then
  say "phase E: Ekbasis-27B INT4"; serve_up "$EKBASIS_INT4" ekbasis_int4
  bash "$PRE/P12/intent/run.sh" ekbasis_int4
  bash "$PRE/P12/preflight_substitute/run.sh" ekbasis_int4
  say "phase E done"
fi

if has F; then
  say "phase F: P11 memory caps"; serve_down
  bash "$PRE/P11/run.sh"
  say "phase F done"
fi
serve_down

if has G || has F; then
  say "compares"; C=$OUTROOT/compare; mkdir -p "$C"; O=$OUTROOT
  "$PY" "$PRE/P1/compare.py" --skopos "$O/P1/skopos_bf16" --ekbasis-rerun "$O/P1/ekbasis_bf16" --out "$C/P1.json"
  "$PY" "$PRE/P3/compare.py" --skopos "$O/P3/skopos_bf16" --out "$C/P3.json"
  "$PY" "$PRE/P4/compare.py" --skopos "$O/P4/skopos_bf16" --out "$C/P4.json"
  "$PY" "$PRE/P5/compare.py" --skopos "$O/P5/skopos_bf16" --ekbasis "$O/P5/ekbasis_bf16" --skopos-p8 "$O/P8/skopos_bf16" --ekbasis-p8 "$O/P8/ekbasis_bf16" --out "$C/P5.json"
  "$PY" "$PRE/P6/compare.py" --skopos "$O/P6/skopos_bf16" --ekbasis "$O/P6/ekbasis_bf16" --out "$C/P6.json"
  "$PY" "$PRE/P7/compare.py" --skopos "$O/P7/skopos_bf16" --out "$C/P7.json"
  "$PY" "$PRE/P8/compare.py" --skopos "$O/P8/skopos_bf16" --ekbasis-rerun "$O/P8/ekbasis_bf16" --out "$C/P8.json"
  EKR=(); [ -d "$O/P9/ekbasis_bf16" ] && EKR=(--ekbasis-rerun "$O/P9/ekbasis_bf16" --ekbasis-tag ekbasis_bf16)
  "$PY" "$PRE/P9/compare.py" --skopos "$O/P9/skopos_bf16" --skopos-tag skopos_bf16 "${EKR[@]}" --out "$C/P9.json"
  "$PY" "$PRE/P11/compare.py" --skopos "$O/P11/memory_tests.json" --out "$C/P11.json"
  "$PY" "$PRE/P12/intent/compare.py" --skopos "$O/P12/intent/skopos_int4" --ekbasis-rerun "$O/P12/intent/ekbasis_int4" --out "$C/P12_intent.json"
  for b in bf16 int4; do
    "$PY" "$PRE/P12/preflight_substitute/compare.py" --skopos "$O/P12/preflight_substitute/skopos_$b.jsonl" \
      --ekbasis "$O/P12/preflight_substitute/ekbasis_$b.jsonl" --out "$C/P12_preflight_substitute_$b.json"
  done
  say "P10 compares run on the Mac: python3 P10/compare.py --skopos <mac OUTROOT>/P10/pred_skopos_bf16.json [--ekbasis-rerun .../pred_ekbasis_bf16.json] --out ..."
fi
say "run_all done"
