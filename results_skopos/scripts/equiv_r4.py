"""Served (merged R4 via vLLM + serve.py :8603) vs trainer (R4 adapter, HF) on the same items: same answer? prob gap?"""
import json, random, urllib.request, concurrent.futures as cf, statistics as st
D = "/root/v50p"
def L(p): return [json.loads(l) for l in open(p)]
items = []
for split, n in (("git_long", 300), ("guard_known", 200)):
    rows, preds = L(f"{D}/data/{split}.jsonl"), L(f"{D}/run_r4/preds_{split}_floor.jsonl")
    for i in sorted(random.Random(7).sample(range(len(rows)), n)):
        items.append((split, rows[i], preds[i]))
def one(t):
    split, r, p = t
    body = json.dumps({"state": r["floor"], "questions": {"q": r["question"]}}).encode()
    a = json.load(urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8603/v1/evaluate", body, {"Content-Type": "application/json"}), timeout=300))["answers"]["q"]
    served = (("yes" if a["value"] else "no") if a["type"] in ("noul", "boolean") else str(a["choice"]))
    conf = a["confidence"]
    return split, served == p["pred"], abs(conf - p["conf"]), served == p["gold"], p["ok"]
with cf.ThreadPoolExecutor(8) as ex:
    R = list(ex.map(one, items))
for s in ("git_long", "guard_known", None):
    X = [r for r in R if s is None or r[0] == s]
    print(s or "todos", "n", len(X), "mesma resposta", round(sum(r[1] for r in X) / len(X), 4),
          "|conf| med", round(st.median(r[2] for r in X), 4), "p95", round(sorted(r[2] for r in X)[int(.95 * len(X))], 4),
          "acerto servido", round(sum(r[3] for r in X) / len(X), 4), "acerto trainer", round(sum(r[4] for r in X) / len(X), 4))
print("EQUIV_DONE")
