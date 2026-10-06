"""Code test of confirm3_analyze.py on confirm-2 data posing as fresh (no new item, no model call). Confirm-2 is part of
the calibration set, so the numbers are in sample and mean nothing; the code must run end to end."""
import json
import os
import subprocess

U = "/root/decis/mission/U"
T = f"{U}/confirm3/test_harness"
os.makedirs(f"{T}/out", exist_ok=True)
for f in ("fresh_rows.jsonl", "extra.jsonl"):
    if not os.path.exists(f"{T}/{f}"):
        os.symlink(f"{U}/confirm2/{f}", f"{T}/{f}")
p = subprocess.run(["/opt/sglang/bin/python", "confirm3_analyze.py"], cwd=f"{U}/confirm3",
                   env=dict(os.environ, CONFIRM3_DIR=T, CONFIRM3_OUT=f"{T}/out"), capture_output=True, text=True)
print("rc", p.returncode, p.stderr[-1500:])
d = json.load(open(f"{T}/out/confirm3.json"))
print("units", d["n_units"], "criteria", d["criteria"])
for rule in ("L1", "L2"):
    r = d["ltt"]["a02"][rule]
    print(rule, {k: r[k] for k in ("accepted", "verified_share", "error_rate_among_accepted", "errors_caught_share")})
print("per-domain", d["per_domain_rule"]["overall"])
