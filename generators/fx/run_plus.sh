#!/bin/bash
# WS-FX second pass for scale (more unique rows; same families, new seed range 23,000,000+, part "trainplus").
set -u
cd /root/decis/mission/FX/factory
D=/root/decis/mission/FX/data/raw
while read fam cap; do
  out=$D/${fam}__trainplus.jsonl.gz
  [ -f $out ] && { echo "$(date -u +%H:%M:%S) skip $fam"; continue; }
  echo "$(date -u +%H:%M:%S) start $fam trainplus cap $cap"
  /usr/bin/python3 fx_run.py $fam trainplus $cap $out 64 200000 || echo "$(date -u +%H:%M:%S) FAILED $fam"
done <<JOBS
sh_remove 5000
sh_copy 5000
sh_move 5000
sh_redirect 5000
sh_links 5000
sh_archive 5000
sh_edit_misc 5000
sh_status_pipes 4000
sh_glob_brace 4000
sh_find_select 4000
sh_write_modes 4000
sh_archive2 4000
ext_shio_cmds 15000
git_reset 3000
git_checkout_restore 3000
git_stash 3000
git_clean 3000
git_merge_pull 3000
git_rebase_cherry_revert 3000
git_branch_commit 3000
git_sparse_remote 3000
JOBS
echo "$(date -u +%H:%M:%S) PLUS DONE"
