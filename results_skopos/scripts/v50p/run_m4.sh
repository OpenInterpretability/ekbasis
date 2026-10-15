#!/bin/bash
exec >> /root/v50p/m4.log 2>&1
cd /root/v50p
for w in base cand; do python3 m4.py $w /root/v50p/m4_$w && cp /root/lat/index.json /root/v50p/m4_$w/; done
for w in base cand; do
  python3 - <<PY
import sys, re
src = open("/root/diag1.py").read()
src = src.replace("for L in [16, 32, 48, 63]:", "for L in [32, 48]:")
src = src.replace('json.dump(out, open("diag1_out.json", "w"), indent=1)', 'json.dump(out, open("/root/v50p/m4_$w.json", "w"), indent=1)')
sys.argv = ["diag1", "/root/v50p/m4_$w", "/root/data.jsonl"]
print("== M4 $w")
exec(compile(src, "diag1", "exec"))
PY
done
echo M4_DONE
