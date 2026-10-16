#!/bin/bash
# PREREG_R4_RELEASE_READ.md: the release protocol on the merged R4 served on :8603.
exec >> /root/v50p/release_r4.log 2>&1
cd /root/v50p
export URL=http://127.0.0.1:8603 PAR=16 OUT=/root/v50p/release_r4
mkdir -p $OUT
echo "git v3 + multi inicio $(date -u +%T)"; python3 release_eval.py
echo "ftest inicio $(date -u +%T)"; python3 release_eval_extra_rtx.py
echo "guard inicio $(date -u +%T)"; OUT=/root/v50p/release_r4 READOUT=r4_readout python3 guard_big_served_rtx.py
python3 compare_release.py release_ref release_r4 > release_r4/COMPARE.json && tail -14 release_r4/COMPARE.json
echo RELEASE_R4_DONE $(date -u +%T)
python3 /root/backup_hf.py release-r4
