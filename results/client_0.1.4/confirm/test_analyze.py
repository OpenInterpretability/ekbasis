"""Code test of confirm_analyze.py on DEV data (no fresh item, no model call): WS-P's rows as if they were fresh, the
extra signals from WS-P's perturbation run and part 2's self-check, the dev accumulation A/B results. The accumulation
arm must give the dev numbers at τ_acc exactly; the rest only has to run and look sane (the sample is error-enriched)."""
import json
import os
import subprocess

T = "/root/decis/mission/U/confirm/test_harness"
os.makedirs(f"{T}/cap/accumulation", exist_ok=True)
os.makedirs(f"{T}/out", exist_ok=True)
keep = {"rules_stress", "sql_wild", "shell_wild", "git_wild", "accumulation", "planning_probe"}
with open(f"{T}/fresh_rows.jsonl", "w") as f:
    for l in open("/root/decis/mission/P/data/dataset.jsonl"):
        r = json.loads(l)
        if r["suite"] in keep:
            r.pop("prompt")
            r.update(rid=f"dev|{r['qid']}", exclude=None)
            if r["suite"] == "accumulation":
                r["req"] = r["req"]
            f.write(json.dumps(r) + "\n")
ver = {}
for j in map(json.loads, open("/root/decis/mission/U/results/part2_live.jsonl")):
    if j["kind"] == "verify" and "error" not in j:
        ver[j["qid"]] = j
with open(f"{T}/extra.jsonl", "w") as f:
    for s in map(json.loads, open("/root/decis/mission/P/results/infer_raw.jsonl")):
        if s["qid"] in ver:
            f.write(json.dumps({"rid": f"dev|{s['qid']}", "reorder": s["reorder"], "para": s["para"],
                                "verify": {"probabilities": ver[s["qid"]]["probabilities"]}}) + "\n")
os.system(f"cp /root/decis/capability/accumulation/results.jsonl {T}/cap/accumulation/results.jsonl")
p = subprocess.run(["/opt/sglang/bin/python", "confirm_analyze.py"], cwd="/root/decis/mission/U/confirm",
                   env=dict(os.environ, CONFIRM_DIR=T, CONFIRM_OUT=f"{T}/out"), capture_output=True, text=True)
print(p.stdout[-200:], p.stderr[-2000:])
d = json.load(open(f"{T}/out/confirm.json"))
print(json.dumps({k: d[k] for k in ("rows", "primary")}, indent=1))
print(json.dumps(d["secondary"]["auroc_weighted"]))
print(json.dumps(d["accumulation_arm"], indent=1))
