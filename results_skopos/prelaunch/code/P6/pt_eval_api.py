# PRELAUNCH PORT (P6) of _orig/pt_eval_api.py: every changed line is marked PORT; the full diff is CHANGES.diff in this folder.
"""Portuguese transfer on the release weights through the System One API: pt_eval.py's items (same seed), English and
Portuguese, answered by the served model. env: CQ_URL."""
import json, os, sys, urllib.request
sys.argv = [sys.argv[0], "60"]
import importlib.util
LIB = os.environ.get("LIB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))  # PORT
sys.path.insert(0, LIB)  # PORT: envs/worldgen for pt_eval.py's items
spec = importlib.util.spec_from_file_location("pt", os.path.join(LIB, "pt_eval.py"))
src = open(os.path.join(LIB, "pt_eval.py")).read()
src = src[:src.index("res = {}")]  # items only: the old script asked a different API
ns = {"__name__": "pt_items"}
exec(compile(src, "pt_eval.py", "exec"), ns)
items = ns["items"]
URL = os.environ.get("CQ_URL", "http://127.0.0.1:8503/v1/systemone")


def ask(text, q):
    req = urllib.request.Request(URL, data=json.dumps({"state": text, "questions": {"q": q}}).encode(), headers={"Content-Type": "application/json"})
    a = json.load(urllib.request.urlopen(req, timeout=600))["answers"]["q"]
    return ("yes" if a["value"] else "no") if q["type"] == "noul" else a["choice"]


import concurrent.futures as cf
with cf.ThreadPoolExecutor(32) as ex:
    en = list(ex.map(lambda it: ask(it["en"], it["q"]) == it["gold"], items))
    pt = list(ex.map(lambda it: ask(it["pt"], it["qpt"]) == it["gpt"], items))
with open(os.environ["OUT_JSONL"], "w") as f:  # PORT: per-item outputs (the release run kept none)
    for k, it in enumerate(items):
        f.write(json.dumps({"k": k, "fam": it["fam"], "changed": it["changed"], "en_ok": en[k], "pt_ok": pt[k]}) + "\n")
print("world      n chg | English  Portuguese   (questions the actions change)")
for fam in ("machines", "toggles", "jugs", "all"):
    idx = [i for i, it in enumerate(items) if it["changed"] and (fam == "all" or it["fam"] == fam)]
    print(f"{fam:9s} {len(idx):5d} | {100 * sum(en[i] for i in idx) / len(idx):7.1f} {100 * sum(pt[i] for i in idx) / len(idx):11.1f}")
