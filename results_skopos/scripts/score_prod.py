"""Score calibration items through the production front (/v1/evaluate on 127.0.0.1:8010), 2 concurrent.
Saves every option's probability as served (calib currently T1 = raw). Key read from /root/.ekb_key, never printed."""
import json, sys, time, urllib.request, concurrent.futures as cf
items = json.load(open(sys.argv[1])); out = sys.argv[2]
KEY = open("/root/.ekb_key").read().strip()
def one(k):
    it = items[k]
    body = json.dumps({"state": it["state"], "questions": {"q": it["question"]}}).encode()
    for a in range(4):
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8010/v1/evaluate", body,
                {"Content-Type": "application/json", "Authorization": "Bearer " + KEY}), timeout=300))
            ans = r["answers"]["q"]
            probs = ans["probabilities"] if "probabilities" in ans else {"yes": ans["probability"], "no": 1 - ans["probability"]}
            return {"k": k, "set": it["set"], "split": it["split"], "i": it["i"], "gold": it["gold"], "probs": probs,
                    "lat": r.get("latency_s")}
        except Exception as e:
            err = str(e)[:120]; time.sleep(3 * (a + 1))
    return {"k": k, "set": it["set"], "split": it["split"], "i": it["i"], "gold": it["gold"], "error": err}
t = time.time()
with open(out, "w") as f, cf.ThreadPoolExecutor(2) as ex:
    for res in ex.map(one, range(len(items))):
        f.write(json.dumps(res) + "\n")
print("SCORE_DONE", len(items), round(time.time() - t), "s")
