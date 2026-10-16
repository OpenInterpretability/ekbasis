"""PREREG_ADDENDUM A7: the 15,008 confident-errors items, one prompt per question through a served build's
/v1/systemone, saving every option's probability (A2 kept only the top confidence). Gold normalized to yes/no strings
as in A2's re-scoring. usage: URL=http://127.0.0.1:8603 PAR=16 python3 ce_probs.py ITEMS OUT.jsonl"""
import concurrent.futures as cf, json, os, sys, time, urllib.request
URL, PAR = os.environ.get("URL", "http://127.0.0.1:8603"), int(os.environ.get("PAR", "16"))
items = [json.loads(l) for l in open(sys.argv[1])]
norm = lambda g: {True: "yes", False: "no"}[g] if isinstance(g, bool) else str(g)
def one(k):
    r = items[k]; body = json.dumps({"state": r["floor"], "questions": {"q": r["question"]}}).encode()
    for a in range(4):
        try:
            ans = json.load(urllib.request.urlopen(urllib.request.Request(URL + "/v1/systemone", body, {"Content-Type": "application/json"}), timeout=600))["answers"]["q"]
            probs = ans["probabilities"] if "probabilities" in ans else {"yes": ans["probability"], "no": 1 - ans["probability"]}
            return {"k": k, "world": r["world"], "qtype": r["qtype"], "group": r["group"], "changed": r["changed"], "gold": norm(r["gold"]), "probs": probs}
        except Exception as e:
            err = str(e)[:120]; time.sleep(3 * (a + 1))
    return {"k": k, "error": err}
t = time.time()
with open(sys.argv[2], "w") as f, cf.ThreadPoolExecutor(PAR) as ex:
    for res in ex.map(one, range(len(items))):
        f.write(json.dumps(res) + "\n")
print("CE_PROBS_DONE", len(items), round(time.time() - t), "s", flush=True)
