"""Confirmatory test of ekbasis/PREREG_confident_errors.md: are the release model's wrong answers more confident in the
world families (and question types) it was trained on than in the families it never saw?
  python confident_errors.py gen    items for every family x question type x 1-3 actions (worldgen.fbalanced)
  python confident_errors.py eval   every item answered by the System One API (one prompt per question)
env: OUT (/dev/shm/conseq/confident_errors), N (120 items per cell), URL (several, comma-separated, used in turn), PAR."""
import concurrent.futures as cf, itertools, json, os, random, sys, time, urllib.request
from pathlib import Path

sys.path.insert(0, "/root/v50p/worldgen")
from worldgen import TEST, TRAIN, VAL, fbalanced

OUT = Path(os.environ.get("OUT", "/dev/shm/conseq/confident_errors"))
OUT.mkdir(parents=True, exist_ok=True)
N = int(os.environ.get("N", "120"))
norm = lambda g: {True: "yes", False: "no"}[g] if isinstance(g, bool) else str(g)
FAMS = {F.family: F for F in TRAIN + VAL + TEST}


def group(F, q):
    if F in TRAIN:
        return "H" if q == F.HELD_Q else "T"
    return "U"


def cell(job):
    fam, q, steps = job
    F = FAMS[fam]
    rng = random.Random(f"ce-{fam}-{q}-{steps}-20261003")
    items = fbalanced(F, steps, q, rng, N, change_balance=True)
    return [{"world": fam, "qtype": q, "steps": steps, "group": group(F, q), "floor": ex["floor"], "question": ex["question"],
             "gold": norm(ex["gold"]), "changed": bool(ex["known0"] and ex["gold0"] is not None and norm(ex["gold0"]) != norm(ex["gold"]))}
            for ex in items]


if sys.argv[1] == "gen":
    jobs = [(F.family, q, s) for F in TRAIN + VAL + TEST for q in F.QTYPES for s in (1, 2, 3)]
    t0 = time.time()
    with cf.ProcessPoolExecutor(int(os.environ.get("WORKERS", "32"))) as ex:
        cells = list(ex.map(cell, jobs))
    with open(OUT / "items.jsonl", "w") as f:
        for c in cells:
            for r in c:
                f.write(json.dumps(r) + "\n")
    short = [(j, len(c)) for j, c in zip(jobs, cells) if len(c) < N]
    print(f"{sum(map(len, cells))} items in {len(jobs)} cells, {time.time() - t0:.0f} s; cells short of {N}: {short}", flush=True)

if sys.argv[1] == "eval":
    URLS = [u.strip() for u in os.environ.get("URL", "http://127.0.0.1:8503").split(",") if u.strip()]
    turn = itertools.count()

    def post(body):
        url = URLS[next(turn) % len(URLS)]
        req = urllib.request.Request(f"{url}/v1/systemone", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
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
        return {k: r[k] for k in ("world", "qtype", "steps", "group", "gold", "changed")} | {
            "pred": pred, "conf": a["confidence"], "ok": pred == r["gold"]}

    rows = [json.loads(l) for l in open(OUT / "items.jsonl")]
    t0 = time.time()
    with cf.ThreadPoolExecutor(int(os.environ.get("PAR", "64"))) as ex:
        preds = list(ex.map(one, rows))
    with open(OUT / "preds.jsonl", "w") as f:
        for p in preds:
            f.write(json.dumps(p) + "\n")
    for g in ("T", "H", "U"):
        sel = [p for p in preds if p["group"] == g]
        wrong = [p for p in sel if not p["ok"]]
        print(f"group {g}: {len(sel)} answers, {len(wrong)} wrong, {sum(p['conf'] >= 0.9 for p in wrong)} of them at confidence >= 0.9", flush=True)
    print(f"answered in {time.time() - t0:.0f} s", flush=True)
