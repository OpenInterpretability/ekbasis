#!/bin/bash
# WS-U confirmatory test, the whole run on the rig (SPEC_confirm.md). Detached; log: chain.log; one step at a time, so
# never more than 16 requests in flight. Model calls ONLY on :8544. Resumable runners; a finished step is marked in done/.
set -u
cd /root/decis/mission/U/confirm
URL=http://127.0.0.1:8544
case "$URL" in *:8544) ;; *) echo "wrong API $URL"; exit 1 ;; esac
export EKBASIS_URL=$URL PYTHONPATH=/root/decis/capability/client
PY=/opt/sglang/bin/python
TOK=/dev/shm/conseq/merged_w4a5
mkdir -p done
step() {  # step <name> <command...>: skip if done, stop the chain on failure
  local n=$1; shift
  [ -e "done/$n" ] && { echo "$(date -u +%H:%M) skip $n (done)"; return 0; }
  echo "$(date -u +%H:%M) start $n"
  if "$@"; then touch "done/$n"; echo "$(date -u +%H:%M) done $n"; else echo "$(date -u +%H:%M) FAILED $n"; exit 1; fi
}
curl -sf -m 10 $URL/health > /dev/null || { echo "API $URL down"; exit 1; }

# 1. fresh items (new seeds; the patched copies were checked to give the dev items with the dev seeds)
step copies $PY make_fresh.py cap
step gen_rules bash -c "cd cap/rules_stress && FRESH_SEED=9100601 TOK=$TOK $PY make_items.py > gen.log 2>&1 && FRESH_SEED=9100601 TOK=$TOK $PY make_addendum.py >> gen.log 2>&1"
step gen_accum bash -c "cd cap/accumulation && FRESH_SEED=9100603 PER_CELL=4 $PY accum.py > gen.log 2>&1"
step gen_sql bash -c "cd cap/sql_wild && N_PAIRS=10 SEED_OFF=500 SEED_TRIES=400 $PY sql_wild.py \$PWD/items.jsonl > gen.log 2>&1"
step gen_shell bash -c "cd cap/shell_wild && FRESH_SEED=9100605 INST_MULT=2 I_OFF=100 $PY shell_wild.py gen > gen.log 2>&1"
# 2. the direct answers (the suites' own runners)
step ask_rules bash -c "cd cap/rules_stress && $PY run_rs.py $URL 16 > run.log 2>&1 && ITEMS=items_addendum.jsonl OUT=results_addendum.jsonl $PY run_rs.py $URL 16 >> run.log 2>&1"
step ask_sql bash -c "cd cap/sql_wild && SKIP_BLIND=1 $PY run_sql.py $URL 16 > run.log 2>&1"
step ask_shell bash -c "cd cap/shell_wild && FRESH_SEED=9100605 INST_MULT=2 I_OFF=100 INFLIGHT=16 $PY shell_wild.py ask > ask.log 2>&1"
step ask_git bash -c "cd cap/git_wild && GW_SALT=git_wild_fresh_9100606 REP_OFF=100 REP_MULT=2 $PY git_wild.py run --workers 16 > run.log 2>&1"
step ask_accum bash -c "cd cap/accumulation && $PY run_accum.py $URL 16 A,B > run.log 2>&1"
# 3. rows + overlap check, extra calls, primary analysis
step rows_primary bash -c "$PY fresh_rows.py > rows.log 2>&1"
step extra_primary bash -c "$PY extra_calls.py primary > extra_primary.log 2>&1"
step analyze_primary bash -c "$PY confirm_analyze.py > analyze.log 2>&1"
echo "$(date -u +%H:%M) PRIMARY RESULT READY"
# 4. secondary suite: planning (sampled worlds)
step ask_planning bash -c "$PY fresh_planning.py ask > planning.log 2>&1"
step rows_all bash -c "$PY fresh_rows.py > rows2.log 2>&1"
step extra_planning bash -c "$PY extra_calls.py planning > extra_planning.log 2>&1"
step analyze_all bash -c "$PY confirm_analyze.py > analyze2.log 2>&1"
echo "$(date -u +%H:%M) WSU CONFIRM DONE"
