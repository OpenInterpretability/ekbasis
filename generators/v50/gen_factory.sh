#!/bin/bash
# Regenerate F's factory data (shell/sql/python/git, executed for real) with fresh seeds, pack it, firewall it.
exec >> /root/factory_gen.log 2>&1
cd /root/factory && mkdir -p /root/fac
echo "inicio $(date -u +%T)"
python3 run_family.py sqlfam 100000 2600 /root/fac/sql.jsonl 20
python3 run_family.py pyfam 100000 5800 /root/fac/python.jsonl 20
python3 run_family.py shell 100000 2300 /root/fac/shell.jsonl 20
python3 run_family.py gitfam 100000 2200 /root/fac/git.jsonl 20
echo "familias $(date -u +%T)"; wc -l /root/fac/*.jsonl
python3 pack.py /root/fac && cat /root/fac/pack.json | head -c 1500; echo
python3 - <<PY
import json, glob
tests = set()
for p in ["git_long","git3_test_known","git3_test_held","guard_known","fval_git3","m3val","ftest_family","fhorizon"]:
    for l in open(f"/root/v50p/data/{p}.jsonl"):
        tests.add(json.loads(l)["floor"])
rows = [json.loads(l) for l in open("/root/fac/train_rx.jsonl")]
kept = [r for r in rows if r["floor"] not in tests]
with open("/root/v50p/data/fac_rx.jsonl", "w") as f:
    for r in kept: f.write(json.dumps(r) + "\n")
print("fac_rx", len(kept), "dropped by firewall", len(rows) - len(kept))
PY
echo FACTORY_DONE $(date -u +%T)
