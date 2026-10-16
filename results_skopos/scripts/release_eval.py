"""Pre-registered release evaluation (ekbasis/PREREG_release_eval.md), on the exact release weights served by vLLM and
the System One API. Parts run here (server side): git v3 held-out tests (primary 2), honest consequence accuracy on
never-trained world families, one prompt per question and read-once (primary 3). Writes every prediction for
recomputation. env: URL (http://127.0.0.1:8503; several, comma-separated, are used in turn), PAR (48), OUT (/dev/shm/conseq/release_eval)."""
import concurrent.futures as cf, itertools, json, os, random, time, urllib.request
from pathlib import Path

URL, PAR = os.environ.get("URL", "http://127.0.0.1:8503"), int(os.environ.get("PAR", "48"))
URLS = [u.strip() for u in URL.split(",") if u.strip()]  # several servers of the same build: requests go round-robin
_turn = itertools.count()
OUT = Path(os.environ.get("OUT", "/dev/shm/conseq/release_eval"))
OUT.mkdir(parents=True, exist_ok=True)
D = Path("/dev/shm/conseq/fac")
norm = lambda g: {True: "yes", False: "no"}[g] if isinstance(g, bool) else str(g)


def post(body):
    url = URLS[next(_turn) % len(URLS)]
    req = urllib.request.Request(f"{url}/v1/systemone", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    for attempt in range(3):
        try:
            return json.load(urllib.request.urlopen(req, timeout=900))
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2)


def answer(a, q):
    return ("yes" if a["value"] else "no") if q["type"] in ("noul", "boolean") else a["choice"]


def boot(xs, n=2000, seed=0):
    rng = random.Random(seed)
    m = [sum(rng.choice(xs) for _ in xs) / len(xs) for _ in range(n)]
    m.sort()
    return 100 * m[int(0.025 * n)], 100 * m[int(0.975 * n)]


def auroc(pos, neg):
    return sum((a > b) + 0.5 * (a == b) for a in pos for b in neg) / (len(pos) * len(neg))


report = {}
# primary 2: git v3 held-out tests
for split in ("git3_test_known", "git3_test_held"):
    rows = [json.loads(l) for l in open(D / f"{split}.jsonl")]

    def one(r):
        a = post({"state": r["floor"], "questions": {"q": r["question"]}})["answers"]["q"]
        p_yes = a.get("probability") if r["question"]["type"] == "noul" else None
        return {"pred": answer(a, r["question"]), "conf": a["confidence"], "p_yes": p_yes}

    t0 = time.time()
    with cf.ThreadPoolExecutor(PAR) as ex:
        preds = list(ex.map(one, rows))
    with open(OUT / f"preds_{split}.jsonl", "w") as f:
        for r, p in zip(rows, preds):
            f.write(json.dumps({**p, "gold": norm(r["gold"]), "qtype": r["qtype"]}) + "\n")
    res = {}
    for k, sel in (("lost", lambda r: r["qtype"] == "lost"), ("fails", lambda r: r["qtype"] == "fails"),
                   ("in_progress", lambda r: r["qtype"] == "in_progress"),
                   ("changed state", lambda r: r["qtype"] not in ("lost", "fails", "in_progress") and r["known0"]
                    and norm(r["gold0"]) != norm(r["gold"])),
                   ("all", lambda r: True)):
        ok = [p["pred"] == norm(r["gold"]) for r, p in zip(rows, preds) if sel(r)]
        lo, hi = boot(ok)
        res[k] = {"n": len(ok), "acc": 100 * sum(ok) / len(ok), "ci95": [lo, hi]}
    lost = [(p["p_yes"], r["gold"]) for r, p in zip(rows, preds) if r["qtype"] == "lost"]
    pos = [p for p, g in lost if g]
    neg = sorted((p for p, g in lost if not g), reverse=True)
    thr = neg[max(0, int(0.10 * len(neg)) - 1)]
    res["lost_auroc"] = auroc(pos, neg)
    res["lost_caught_at_10pct_false_alarm"] = 100 * sum(a > thr for a in pos) / len(pos)
    res["lost_flagged_at_0.2"] = 100 * sum(a >= 0.2 for a in pos) / len(pos)
    res["false_alarm_at_0.2"] = 100 * sum(a >= 0.2 for a in neg) / len(neg)
    res["seconds"] = time.time() - t0
    report[split] = res
    print(split, json.dumps(res, indent=None), flush=True)

# primary 3: honest consequence accuracy on world families (one prompt per question and read-once)
for split in ("multi_test_trainfam", "multi_test_testfam"):
    rows = [json.loads(l) for l in open(D / f"{split}.jsonl")]
    for ro in ((False,) if os.environ.get("SKIP_READ_ONCE") else (False, True)):  # SKIP_READ_ONCE: servers that answer read-once requests one prompt per question (the MLX server)
        def one(r):
            d = post({"state": r["floor"], "questions": {f"q{k}": q for k, q in enumerate(r["questions"])}, "read_once": ro})
            return [answer(d["answers"][f"q{k}"], q) for k, q in enumerate(r["questions"])], d["usage"]["input_tokens"]

        with cf.ThreadPoolExecutor(PAR) as ex:
            got = list(ex.map(one, rows))
        flat, chg = [], []
        for r, (preds, _) in zip(rows, got):
            for k, q in enumerate(r["questions"]):
                ok = preds[k] == norm(r["golds"][k])
                flat.append(ok)
                g0 = r["gold0s"][k]
                if r["known0s"][k] and g0 is not None and norm(g0) != norm(r["golds"][k]):
                    chg.append(ok)
        with open(OUT / f"preds_{split}_{'read_once' if ro else 'single'}.jsonl", "w") as f:
            for r, (preds, n) in zip(rows, got):
                f.write(json.dumps({"preds": preds, "golds": [norm(g) for g in r["golds"]], "tokens": n}) + "\n")
        key = f"{split} ({'read-once' if ro else 'one prompt per question'})"
        report[key] = {"n_changed": len(chg), "acc_changed": 100 * sum(chg) / len(chg), "ci95_changed": list(boot(chg)),
                       "acc_all": 100 * sum(flat) / len(flat), "prompt_tokens_per_state": sum(n for _, n in got) / len(got)}
        print(key, json.dumps(report[key]), flush=True)

json.dump(report, open(OUT / "report_server_side.json", "w"), indent=1)
print("release eval (server side) done", flush=True)
