#!/bin/bash
# WS-U confirm-2 (SPEC_confirm2.md): fresh items from NEW seeds (never dev, never confirm-1), the suites' own runners,
# rows + overlap check (dev and confirm-1), extra calls (perturbation, self-check, abstain), analysis.
# Usage on the rig, when the coordinator assigns a w4a5 replica:
#   EKBASIS_URL=http://127.0.0.1:<port> setsid -f bash -c "exec bash run_confirm2.sh >> chain.log 2>&1 < /dev/null"
# One step at a time (≤ 16 requests in flight); finished steps are marked in done/ and skipped on a rerun.
set -u
cd /root/decis/mission/U/confirm2
URL=${EKBASIS_URL:?set EKBASIS_URL to the assigned w4a5 replica}
export EKBASIS_URL=$URL PYTHONPATH=/root/decis/capability/client
PY=/opt/sglang/bin/python
TOK=/dev/shm/conseq/merged_w4a5
mkdir -p done
step() {
  local n=$1; shift
  [ -e "done/$n" ] && { echo "$(date -u +%H:%M) skip $n (done)"; return 0; }
  echo "$(date -u +%H:%M) start $n"
  if "$@"; then touch "done/$n"; echo "$(date -u +%H:%M) done $n"; else echo "$(date -u +%H:%M) FAILED $n"; exit 1; fi
}
curl -sf -m 10 $URL/health | grep -q merged_w4a5 || { echo "API $URL down or not w4a5"; exit 1; }
step copies $PY ../confirm/make_fresh.py cap
step gen_rules bash -c "cd cap/rules_stress && FRESH_SEED=9200601 TOK=$TOK $PY make_items.py > gen.log 2>&1 && FRESH_SEED=9200601 TOK=$TOK $PY make_addendum.py >> gen.log 2>&1"
step gen_accum bash -c "cd cap/accumulation && FRESH_SEED=9200603 PER_CELL=4 $PY accum.py > gen.log 2>&1"
step gen_sql bash -c "cd cap/sql_wild && N_PAIRS=10 SEED_OFF=200 SEED_TRIES=300 $PY sql_wild.py \$PWD/items.jsonl > gen.log 2>&1"
step gen_shell bash -c "cd cap/shell_wild && FRESH_SEED=9200605 INST_MULT=2 I_OFF=200 $PY shell_wild.py gen > gen.log 2>&1"
step ask_rules bash -c "cd cap/rules_stress && $PY run_rs.py $URL 16 > run.log 2>&1 && ITEMS=items_addendum.jsonl OUT=results_addendum.jsonl $PY run_rs.py $URL 16 >> run.log 2>&1"
step ask_sql bash -c "cd cap/sql_wild && SKIP_BLIND=1 $PY run_sql.py $URL 16 > run.log 2>&1"
step ask_shell bash -c "cd cap/shell_wild && FRESH_SEED=9200605 INST_MULT=2 I_OFF=200 INFLIGHT=16 $PY shell_wild.py ask > ask.log 2>&1"
step ask_git bash -c "cd cap/git_wild && GW_SALT=git_wild_fresh_9200606 REP_OFF=200 REP_MULT=2 $PY git_wild.py run --workers 16 > run.log 2>&1"
step ask_accum bash -c "cd cap/accumulation && $PY run_accum.py $URL 16 A,B > run.log 2>&1"
step rows bash -c "$PY fresh_rows2.py > rows.log 2>&1"
step extra bash -c "$PY extra_calls2.py > extra.log 2>&1"
step analyze bash -c "$PY confirm2_analyze.py > analyze.log 2>&1"
echo "$(date -u +%H:%M) WSU CONFIRM2 DONE"
