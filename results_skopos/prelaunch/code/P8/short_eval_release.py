# PRELAUNCH PORT (P8) of _orig/short_eval_release.py: every changed line is marked PORT; the full diff is CHANGES.diff in this folder.
"""Short checks (1-3 actions, one question the actions change; the items of short_eval.py: robust_eval 'orig' and 'para',
seed 77) on the exact release weights through the System One API, and the routing rule recomputed with the Qwen3.8-27B
answers saved by short_eval.py on the same items (the LLM does not depend on the release).
  acc    accuracy and routing (env CQ_URL, PAR)
  time   latency one request at a time and throughput at 16 in parallel, on one GPU (env CQ_URL)"""
import concurrent.futures as cf, json, os, random, sys, time, urllib.request
sys.argv, MODE = [sys.argv[0]], sys.argv[1]
sys.path.insert(0, os.environ.get("LIB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib")))  # PORT
import robust_eval as R
from worldgen import Jugs, Machines, Toggles

URL = os.environ.get("CQ_URL", "http://127.0.0.1:8503/v1/systemone")
OUT = os.environ.get("OUT_JSON", "/dev/shm/conseq/release_eval/short_eval_release.json")  # quantized builds: their own file
R.BIG = False
rng = random.Random(77)
items = [(fam, gold, name, text, q) for F in (Machines, Toggles, Jugs) for fam, gold, v in R.items(F, rng, 40)
         for name, (text, q) in v.items() if name in ("orig", "para")]
saved = json.load(open(os.environ["SAVED_JSON"]))  # PORT: the rig-only /dev/shm/conseq/short_eval.json, rebuilt by make_saved.py
assert [tuple(x) for x in saved["items"]] == [it[:3] for it in items], "items differ from short_eval.py's"


def cq(it):
    t0 = time.time()
    req = urllib.request.Request(URL, data=json.dumps({"state": it[3], "questions": {"q": it[4]}}).encode(),
                                 headers={"Content-Type": "application/json"})
    a = json.load(urllib.request.urlopen(req, timeout=600))["answers"]["q"]
    return {"ok": a["choice"] == it[1], "conf": a["confidence"], "s": time.time() - t0}


rep = json.load(open(OUT)) if os.path.exists(OUT) else {}
if MODE == "acc":
    with cf.ThreadPoolExecutor(int(os.environ.get("PAR", "16"))) as ex:
        res = list(ex.map(cq, items))
    think, nothink = saved["res"]["think"], saved["res"]["nothink"]
    acc = lambda rs, v: 100 * sum(r["ok"] for r, it in zip(rs, items) if it[2] == v) / sum(1 for it in items if it[2] == v)
    rep["items"] = len(items)
    rep["accuracy"] = {name: {v: acc(rs, v) for v in ("orig", "para")}
                       for name, rs in (("Ekbasis (release)", res), ("Qwen3.8-27B thinking", think))}  # PORT: no at-once row (its per-item answers were rig-only)
    rep["qwen_thinking_tokens_per_item"] = sum(r["tok"] for r in think) / len(items)
    rep["routing"] = []
    for t in (0.5, 0.9, 0.95, 0.99):
        go = [i for i, r in enumerate(res) if r["conf"] < t]
        a = sum((think[i] if i in go else res[i])["ok"] for i in range(len(items))) / len(items)
        rep["routing"].append({"confidence_cut": t, "to_llm_pct": 100 * len(go) / len(items), "accuracy": 100 * a})
    bins = [(0.5, 0.9), (0.9, 0.99), (0.99, 1.01)]
    rep["calibration"] = [{"conf": f"[{lo}, {hi})", "n": len(s), "mean_conf": 100 * sum(r["conf"] for r in s) / max(1, len(s)),
                           "acc": 100 * sum(r["ok"] for r in s) / max(1, len(s))}
                          for lo, hi in bins for s in [[r for r in res if lo <= r["conf"] < hi]]]
    rep["predictions"] = res
else:
    for par in (1, 16):
        t0 = time.time()
        with cf.ThreadPoolExecutor(par) as ex:
            res = list(ex.map(cq, items))
        secs = sorted(r["s"] for r in res)
        rep[f"timing_par{par}"] = {"p50_s": secs[len(secs) // 2], "p90_s": secs[int(0.9 * len(secs))],
                                   "checks_per_s": len(items) / (time.time() - t0)}
json.dump(rep, open(OUT, "w"), indent=1)
print(json.dumps({k: v for k, v in rep.items() if k != "predictions"}, indent=1))
