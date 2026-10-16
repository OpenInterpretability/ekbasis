"""CONFIRM_FTEST on a served build: ftest_fresh through /v1/evaluate (:8603), changed-answer accuracy vs the release
(Ekbasis-27B bf16, trainer readout confirm_rel), paired bootstrap. python3 ftest_fresh_served.py NAME"""
import json, random, sys, urllib.request, concurrent.futures as cf
name = sys.argv[1]
rows = [json.loads(l) for l in open("/root/v50p/data/ftest_fresh.jsonl")]
rel = [json.loads(l) for l in open("/root/v50p/confirm_rel/preds_ftest_fresh_floor.jsonl")]
n = lambda g: {True: "yes", False: "no"}[g] if isinstance(g, bool) else str(g)
def one(r):
    a = json.load(urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8603/v1/evaluate",
        json.dumps({"state": r["floor"], "questions": {"q": r["question"]}}).encode(), {"Content-Type": "application/json"}), timeout=300))["answers"]["q"]
    pred = ("yes" if a["value"] else "no") if a["type"] in ("noul", "boolean") else str(a["choice"])
    return pred == n(r["gold"])
with cf.ThreadPoolExecutor(16) as ex:
    ok = list(ex.map(one, rows))
ch = [i for i, r in enumerate(rows) if r.get("known0") and r.get("gold0") is not None and str(r["gold0"]) != str(r["gold"])]
d = [int(ok[i]) - int(rel[i]["ok"]) for i in ch]
rng = random.Random(20261015); bs = sorted(sum(d[rng.randrange(len(d))] for _ in d) / len(d) for _ in range(2000))
out = {"build": name, "changed_n": len(ch), "build_acc": 100 * sum(ok[i] for i in ch) / len(ch), "release_acc": 100 * sum(rel[i]["ok"] for i in ch) / len(ch),
       "diff": 100 * sum(d) / len(d), "ci": [100 * bs[50], 100 * bs[1949]], "all_acc": 100 * sum(ok) / len(ok)}
json.dump(out, open(f"/root/v50p/ftest_fresh_{name}.json", "w"), indent=1); print(json.dumps(out))
