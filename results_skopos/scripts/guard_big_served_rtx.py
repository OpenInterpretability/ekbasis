"""The larger guard set (PLAN_guard_set.md) through the served release model: the exact release weights behind vLLM and
the System One API, the same request as release_eval.py's git part. Then, item by item, the agreement with the trainer's
readout that the pre-registered gate used (gd_v42 / gdh_v42). Not pre-registered: a check of the readout, and the served
numbers for the model card.
env: URL (http://127.0.0.1:8503), PAR (48), OUT (/dev/shm/conseq/guard_big_served), READOUT (a run folder, e.g. sw_w4a5)"""
import concurrent.futures as cf, itertools, json, os, time, urllib.request
from pathlib import Path

URL, PAR = os.environ.get("URL", "http://127.0.0.1:8503"), int(os.environ.get("PAR", "48"))
OUT = Path(os.environ.get("OUT", "/dev/shm/conseq/guard_big_served"))
OUT.mkdir(parents=True, exist_ok=True)
D = Path("/dev/shm/conseq")
norm = lambda g: {True: "yes", False: "no"}[g] if isinstance(g, bool) else str(g)


URLS = [u.strip() for u in URL.split(",") if u.strip()]
_turn = itertools.count()


def post(body):
    req = urllib.request.Request(f"{URLS[next(_turn) % len(URLS)]}/v1/systemone", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    for attempt in range(3):
        try:
            return json.load(urllib.request.urlopen(req, timeout=900))
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2)


def one(r):
    a = post({"state": r["floor"], "questions": {"q": r["question"]}})["answers"]["q"]
    pred = ("yes" if a["value"] else "no") if r["question"]["type"] in ("noul", "boolean") else a["choice"]
    return {"pred": pred, "conf": a["confidence"], "p_yes": a.get("probability")}


report = {}
READOUT = os.environ.get("READOUT")  # the run folder holding the trainer's readout of both splits (default: V42's)
for split, readout in ((("guard_known", READOUT), ("guard_held", READOUT)) if READOUT else (("guard_known", "gd_v42"), ("guard_held", "gdh_v42"))):
    rows = [json.loads(l) for l in open(D / "fac" / f"{split}.jsonl")]
    t0 = time.time()
    with cf.ThreadPoolExecutor(PAR) as ex:
        preds = list(ex.map(one, rows))
    with open(OUT / f"preds_{split}.jsonl", "w") as f:
        for r, p in zip(rows, preds):
            f.write(json.dumps({**p, "gold": norm(r["gold"]), "qtype": r["qtype"]}) + "\n")
    rp = D / readout / f"preds_{split}_floor.jsonl"
    tr = [json.loads(l) for l in open(rp)] if rp.exists() else [{"qtype": r["qtype"], "probs": [float("nan")]} for r in rows]
    assert len(tr) == len(rows) and all(t["qtype"] == r["qtype"] for t, r in zip(tr, rows)), "the readout's rows are not aligned"
    lost = [(p, t, r) for p, t, r in zip(preds, tr, rows) if r["qtype"] == "lost"]
    fails = [(p, r) for p, r in zip(preds, rows) if r["qtype"] == "fails"]
    pos = [(p, t) for p, t, r in lost if r["gold"]]
    neg = [(p, t) for p, t, r in lost if not r["gold"]]
    report[split] = {
        "work_losing": len(pos), "flagged_at_0.2": sum(p["p_yes"] >= 0.2 for p, _ in pos),
        "safe": len(neg), "false_alarms_at_0.2": sum(p["p_yes"] >= 0.2 for p, _ in neg),
        "fails_n": len(fails), "fails_right": sum(p["pred"] == norm(r["gold"]) for p, r in fails),
        "readout_flagged_at_0.2": sum(t["probs"][0] >= 0.2 for _, t in pos),
        "readout_false_alarms_at_0.2": sum(t["probs"][0] >= 0.2 for _, t in neg),
        "same_flag_decision": sum((p["p_yes"] >= 0.2) == (t["probs"][0] >= 0.2) for p, t in pos + neg),
        "lost_items": len(pos) + len(neg),
        "seconds": time.time() - t0}
    print(split, json.dumps(report[split]), flush=True)
json.dump(report, open(OUT / "report.json", "w"), indent=1)
print("done", flush=True)
