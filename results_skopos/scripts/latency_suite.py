"""PREREG_ADDENDUM A5: latency and cost on the 200 fixed items (mac_items.json of A4), one served build at a time.
    python3 latency_suite.py URL ITEMS OUT"""
import json, sys, time, statistics, urllib.request, concurrent.futures as cf
URL, items, OUT = sys.argv[1], json.load(open(sys.argv[2])), sys.argv[3]
def post(it):
    body = json.dumps({"state": it["state"], "questions": {"q": it["question"]}}).encode()
    t = time.time(); r = json.load(urllib.request.urlopen(urllib.request.Request(URL + "/v1/systemone", body, {"Content-Type": "application/json"}), timeout=600))
    return time.time() - t, r.get("usage", {}).get("input_tokens")
for it in items[:20]: post(it)
one = [post(it) for it in items]
lat = sorted(x[0] for x in one); tok = [x[1] for x in one if x[1] is not None]
t0 = time.time()
with cf.ThreadPoolExecutor(16) as ex: par = list(ex.map(post, items))
wall = time.time() - t0
out = {"n": len(items), "one_at_a_time": {"median_s": statistics.median(lat), "p90_s": lat[int(0.9 * len(lat))], "mean_s": sum(lat) / len(lat)},
       "parallel16": {"requests_per_s": len(items) / wall, "wall_s": wall, "median_s": statistics.median(x[0] for x in par)},
       "input_tokens_per_request": {"mean": sum(tok) / len(tok) if tok else None, "median": statistics.median(tok) if tok else None}}
json.dump(out, open(OUT, "w"), indent=1); print(json.dumps(out))
