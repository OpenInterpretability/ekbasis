# Defaults for every pre-launch runner (PRELAUNCH_EVAL.md, Part A). Source it; override any value in the environment.
# The GPU machine's layout is the one of the Skopos release read (serve_r4.sh, run_int4_r4.sh, run_fp8.sh, run_image.sh).
export PRE=${PRE:-/root/prelaunch}                 # this folder (RS/prelaunch), copied to the GPU machine
export DATA=${DATA:-/root/prelaunch_data}          # $DATA/fac/<split>.jsonl: ekbasis-data raw/ files (common/fetch_data.sh)
export OUTROOT=${OUTROOT:-/root/prelaunch_out}     # every output: $OUTROOT/<Pn>/<model tag>/...
export LOGS=${LOGS:-$OUTROOT/logs}
export VLLM_PORT=${VLLM_PORT:-8601} API_PORT=${API_PORT:-8603}
export URL=${URL:-http://127.0.0.1:$API_PORT}      # serve.py, the System One API (/v1/systemone)
export PY=${PY:-python3}
export GPU=${GPU:-0}                               # the one RTX PRO 6000 the runs use
# model folders (bf16 / INT4 / FP8 of Skopos as in the release read; Ekbasis-27B downloaded by fetch_data.sh)
export SKOPOS_BF16=${SKOPOS_BF16:-/root/Skopos-R4-27B}
export SKOPOS_INT4=${SKOPOS_INT4:-/root/Skopos-R4-27B-INT4}
export SKOPOS_FP8=${SKOPOS_FP8:-/root/Skopos-R4-27B-FP8}
export EKBASIS_BF16=${EKBASIS_BF16:-/root/Ekbasis-27B}
export EKBASIS_INT4=${EKBASIS_INT4:-/root/Ekbasis-27B-INT4}
# the Skopos release read's full-memory predictions (the reference of P11's capped runs)
export RELREAD=${RELREAD:-/root/v50p}
mkdir -p "$OUTROOT" "$LOGS"
model_of() {  # model tag -> folder
  case $1 in
    skopos_bf16) echo "$SKOPOS_BF16";; skopos_int4) echo "$SKOPOS_INT4";; skopos_fp8) echo "$SKOPOS_FP8";;
    ekbasis_bf16) echo "$EKBASIS_BF16";; ekbasis_int4) echo "$EKBASIS_INT4";;
    *) echo "unknown model tag: $1" >&2; exit 1;;
  esac
}
