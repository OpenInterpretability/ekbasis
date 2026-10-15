#!/bin/bash
# WS-FX Addendum 5 side-effect families + the core git scale pass that the root-disk guard stopped; outputs on the RAM disk.
set -u
cd /root/decis/mission/FX/factory
D=/dev/shm/fx/raw2
while read fam part cap w; do
  out=$D/${fam}__${part}.jsonl.gz
  [ -f $out ] && { echo "$(date -u +%H:%M:%S) skip $fam $part"; continue; }
  echo "$(date -u +%H:%M:%S) start $fam $part cap $cap"
  /usr/bin/python3 fx_run.py $fam $part $cap $out $w 200000 || echo "$(date -u +%H:%M:%S) FAILED $fam $part"
done <<JOBS
se_shell train 8000 64
se_shell val 400 64
se_sql train 8000 64
se_sql val 400 64
se_git train 6000 64
se_git val 300 64
se_vikunja train 4000 16
se_vikunja val 200 16
mm_side_effects eval 3000 8
git_checkout_restore trainplus 3000 64
git_stash trainplus 3000 64
git_clean trainplus 3000 64
git_merge_pull trainplus 3000 64
git_rebase_cherry_revert trainplus 3000 64
git_branch_commit trainplus 3000 64
git_sparse_remote trainplus 3000 64
JOBS
echo "$(date -u +%H:%M:%S) SE DONE"
