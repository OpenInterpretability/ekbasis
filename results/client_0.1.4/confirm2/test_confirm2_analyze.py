"""Code test of confirm2_analyze.py on DEV data posing as fresh (no fresh item, no confirm-1 data, no model call):
WS-P's rows of the five suites, their perturbations and part 2's self-check, a FAKE abstain answer (seeded random,
for the code path only), the dev accumulation A/B results. Numbers are meaningless; the code must run end to end."""
import json
import os
import random
import subprocess

T = "/root/decis/mission/U/confirm2/test_harness"
os.makedirs(f"{T}/cap/accumulation", exist_ok=True)
os.makedirs(f"{T}/out", exist_ok=True)
keep = {"rules_stress", "sql_wild", "shell_wild", "git_wild", "accumulation"}
with open(f"{T}/fresh_rows.jsonl", "w") as f:
    for l in open("/root/decis/mission/P/data/dataset.jsonl"):
        r = json.loads(l)
        if r["suite"] in keep:
            r.pop("prompt")
            r.update(rid=f"dev|{r['qid']}", exclude=None)
            f.write(json.dumps(r) + "\n")
ver = {j["qid"]: j for j in map(json.loads, open("/root/decis/mission/U/results/part2_live.jsonl")) if j["kind"] == "verify" and "error" not in j}
rng = random.Random(0)
with open(f"{T}/extra.jsonl", "w") as f:
    for s in map(json.loads, open("/root/decis/mission/P/results/infer_raw.jsonl")):
        if s["qid"] in ver:
            pu = rng.random() * 0.3
            f.write(json.dumps({"rid": f"dev|{s['qid']}", "reorder": s["reorder"], "para": s["para"],
                                "verify": {"probabilities": ver[s["qid"]]["probabilities"]},
                                "abstain": {"probabilities": {"yes": 1 - pu, "unsure": pu}}}) + "\n")
os.system(f"cp /root/decis/capability/accumulation/results.jsonl {T}/cap/accumulation/results.jsonl")
p = subprocess.run(["/opt/sglang/bin/python", "confirm2_analyze.py"], cwd="/root/decis/mission/U/confirm2",
                   env=dict(os.environ, CONFIRM2_DIR=T, CONFIRM2_OUT=f"{T}/out"), capture_output=True, text=True)
print("rc", p.returncode, p.stderr[-1500:])
d = json.load(open(f"{T}/out/confirm2.json"))
print("keys", sorted(d), "| criteria", d["criteria"])
print("ltt a02 hierarchical", {k: v for k, v in d["ltt"]["a02"]["hierarchical"].items() if k != "groups"})
print("arm", d["accumulation_arm_replication"])
print("ci keys", sorted(d["ci95"]))
