"""Freeze 2: the verified task set (tasks/frozen_tasks.json, with every dropped task and why), the SPEC and the harness
as they will run, hashed into FROZEN.sha256 together with addendum A (stage fixes found while verifying)."""
import glob
import hashlib
import json
import os
import time

HERE = os.path.dirname(os.path.abspath(__file__))
RA = os.path.abspath(os.path.join(HERE, ".."))
import sys
sys.path.insert(0, HERE)
import ra_tasks  # noqa: E402

ver = {os.path.basename(f)[:-5]: json.load(open(f)) for f in glob.glob(os.path.join(HERE, "verify", "*.json"))}
ids, dropped = [], {}
for t in ra_tasks.TASKS:
    v = ver.get(t["id"])
    if v and v.get("verified"):
        ids.append(t["id"])
    else:
        dropped[t["id"]] = "not verified: " + json.dumps((v or {}).get("checks", "never verified"))[:300]
json.dump({"frozen_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "ids": ids, "dropped": dropped,
           "harm": [i for i in ids if ra_tasks.by_id(i)["kind"] == "harm"], "control": [i for i in ids if ra_tasks.by_id(i)["kind"] == "control"],
           "tasks": {i: {k: ra_tasks.by_id(i)[k] for k in ("app", "kind", "family", "task", "visible")} for i in ids}},
          open(os.path.join(HERE, "frozen_tasks.json"), "w"), indent=1, ensure_ascii=False)
files = ["SPEC.md", "tasks/ra_tasks.py", "tasks/frozen_tasks.json", "tasks/verify_tasks.py", "tasks/predict_paths.py",
         "adapters/spec_server.py", "harness/stage_real.mjs", "harness/agent_mcp_real.mjs", "harness/foresee_ra.py", "harness/oracle_ra.py",
         "harness/run_agent_ra.sh", "harness/run_agent_ra_qwen.sh", "harness/run_study_ra.py", "harness/analyze_ra.py", "harness/app_docs.py",
         "harness/agent_system_see_ra.txt", "harness/agent_system_blind_ra.txt", "harness/login.mjs", "apps/ra_lib.py", "apps/docker-compose.yml"]
with open(os.path.join(RA, "FROZEN.sha256"), "a") as f:
    f.write("\n# Addendum A (stage changes after freeze 1, found while verifying the tasks; none changes what the adapters receive or ask):\n"
            "# the page text now lists the options inside container controls (Gitea's owner dropdown); reads the page again while it is\n"
            "# navigating after a click (Roundcube's Send); lists icon-only controls such as a recipient's remove 'x', named by icon and context.\n"
            "# adapters/spec_server.py, foresee_ra.py, oracle_ra.py and ra_lib.py are byte-identical to freeze 1.\n")
    f.write(f"# Freeze 2 — verified task set ({len(ids)} tasks: {len([i for i in ids if ra_tasks.by_id(i)['kind']=='harm'])} harm, "
            f"{len([i for i in ids if ra_tasks.by_id(i)['kind']=='control'])} controls; dropped {len(dropped)}), SPEC and harness as run. "
            f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}, before the first agent run.\n")
    for p in files:
        f.write(f"{hashlib.sha256(open(os.path.join(RA, p), 'rb').read()).hexdigest()}  {p}\n")
print(len(ids), "frozen;", "dropped:", dropped)
