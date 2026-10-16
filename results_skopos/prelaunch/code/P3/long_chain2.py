# PRELAUNCH PORT (P3) of _orig/long_chain2.py: every changed line is marked PORT; the full diff is CHANGES.diff in this folder.
"""Very long chains: 100 and 200 actions, one action per step, every variable asked at every step (System One API, one
question per prompt), the next state rebuilt from the answers. Worlds: containers, lamps, machines, cards.
  text       start from the true state in text, never look again
  image      (containers, lamps) read the start from a picture, then text
  image_obs  as image, and every OBS steps look at a picture of the TRUE current state and re-read it (predict, observe,
             correct: the loop of a world model with perception)
Per item: the final answer, whether the whole final state is right, the first step where the simulated state goes wrong,
and whether the final answer depends on the start at all (the same chain run from another start). env: CQ_URL, N (per
world and length, 8), PAR (16), OBS (50)."""
import base64, concurrent.futures as cf, io, json, os, random, sys, time, urllib.request
sys.path.insert(0, os.environ.get("LIB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib")))  # PORT
from envs import qchoice
from PIL import Image, ImageDraw
from scipy.optimize import linear_sum_assignment
from worldgen import Cards, Jugs, Machines, Toggles
import math

CQ_URL = os.environ.get("CQ_URL", "http://127.0.0.1:8501/v1/systemone")
N, PAR, OBS = int(os.environ.get("N", "8")), int(os.environ.get("PAR", "16")), int(os.environ.get("OBS", "50"))


def draw(w, s):
    if w.family == "toggles":
        img = Image.new("RGB", (110 * w.n + 20, 190), "white")
        d = ImageDraw.Draw(img)
        colors = {"off": (70, 70, 70), "on": (255, 205, 0), "bright": (255, 205, 0), "dim": (240, 228, 160)}
        for i, x in enumerate(s["st"]):
            cx, st = 65 + 110 * i, w.states[x]
            if st in ("on", "bright"):
                d.ellipse((cx - 46, 34, cx + 46, 126), fill=(255, 240, 170))
            d.ellipse((cx - 36, 44, cx + 36, 116), fill=colors[st], outline="black", width=2)
            d.rectangle((cx - 14, 116, cx + 14, 134), fill=(150, 150, 150), outline="black")
            d.text((cx - 22, 150), f"{w.lamp} {i + 1}", fill="black")
        return img
    unit = 22
    hmax = max(w.cap.values()) * unit
    img = Image.new("RGB", (130 * len(w.names) + 20, hmax + 90), "white")
    d = ImageDraw.Draw(img)
    for i, x in enumerate(w.names):
        x0, top, bottom = 40 + 130 * i, 20 + hmax - w.cap[x] * unit, 20 + hmax
        if s["v"][x]:
            d.rectangle((x0, bottom - s["v"][x] * unit, x0 + 70, bottom), fill=(70, 130, 225))
        d.rectangle((x0, top, x0 + 70, bottom), outline="black", width=3)
        for k in range(1, w.cap[x]):
            d.line((x0, bottom - k * unit, x0 + 12, bottom - k * unit), fill="black", width=1)
        d.text((x0, bottom + 12), f"{x} (holds {w.cap[x]} L)", fill="black")
    return img


def uri(img):
    b = io.BytesIO()
    img.save(b, format="PNG")
    return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()


def post(body):
    req = urllib.request.Request(CQ_URL, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=900))


VARS = {"jugs": lambda w: [(x, qchoice(f"How many liters are in {x}?", [(str(k), f"{k} liters") for k in range(w.cap[x] + 1)])) for x in w.names],
        "toggles": lambda w: [(j, qchoice(f"What state is {w.lamp} {j + 1} in?", [(x, x) for x in w.states])) for j in range(w.n)],
        "machines": lambda w: [(d, qchoice(f"In which state is {d}?", [(x, x) for x in w.cycle])) for d in w.devs],
        "cards": lambda w: [(k, qchoice(f"Which card is at position {k + 1}?", [(x, x) for x in w.labels])) for k in range(w.n)]}


def value(w, s, k):
    return {"jugs": lambda: str(s["v"][k]), "toggles": lambda: w.states[s["st"][k]], "machines": lambda: w.cycle[s["st"][k]],
            "cards": lambda: s["xs"][k]}[w.family]()


def read(w, text, keys_qs, images=None):
    body = {"state": text, "questions": {f"v{j}": q for j, (_, q) in enumerate(keys_qs)}}
    if images:
        body["images"] = images
    r = post(body)["answers"]
    D = {k: r[f"v{j}"]["probabilities"] for j, (k, _) in enumerate(keys_qs)}
    if w.family == "cards":
        _, cols = linear_sum_assignment([[-math.log(D[k].get(c, 0.0) + 1e-9) for c in w.labels] for k in range(w.n)])
        return {"xs": [w.labels[c] for c in cols]}
    top = {k: max(D[k], key=D[k].get) for k in D}
    if w.family == "jugs":
        return {"v": {x: int(top[x]) for x in w.names}}
    if w.family == "toggles":
        return {"st": [w.states.index(top[j]) for j in range(w.n)]}
    return {"st": {d: w.cycle.index(top[d]) for d in w.devs}}


def world(fam, rng):
    while True:
        w = {"jugs": Jugs, "toggles": Toggles, "machines": Machines, "cards": Cards}[fam](rng)
        if (fam == "jugs" and len(w.names) == 3) or (fam == "toggles" and w.n >= 5) or (fam == "machines" and len(w.devs) >= 4) \
           or (fam == "cards" and w.n >= 5):
            w.name = fam
            return w


def run(job):
    fam, length, i, mode = job
    rng = random.Random({"jugs": 1, "toggles": 2, "machines": 3, "cards": 4}[fam] * 100000 + length * 100 + i)
    w = world(fam, rng)
    s0 = w.sample_state(rng)
    acts, truth, s = [], [s0], s0
    for _ in range(length):
        a = w.sample_action(rng, s)
        s, _ = w.step(s, a)
        acts.append(a)
        truth.append(s)
    keys_qs = VARS[fam](w)
    key = keys_qs[rng.randrange(len(keys_qs))][0]
    other = w.sample_state(random.Random(i + 99))  # does the final answer depend on the start at all?
    so = other
    for a in acts:
        so, _ = w.step(so, a)
    t0 = time.time()
    if mode == "text":
        S = s0
    else:
        S = read(w, f"{w.rules}\n\nState after the actions: shown in the attached image.\n\n{w.ceiling_note()}", keys_qs, [uri(draw(w, s0))])
    start_ok = all(value(w, S, k) == value(w, s0, k) for k, _ in keys_qs)
    first_err = None if start_ok else 0
    for t, a in enumerate(acts, 1):
        text = f"{w.rules}\n\nCurrent state:\n{w.render(S)}\n\nActions, in order:\n1. {w.render_action(a)}\n\n{w.floor_note()}"
        S = read(w, text, keys_qs)
        if mode == "image_obs" and t % OBS == 0 and t < length:  # look again: a picture of the true current state
            S = read(w, f"{w.rules}\n\nState after the actions: shown in the attached image.\n\n{w.ceiling_note()}", keys_qs,
                     [uri(draw(w, truth[t]))])
        if first_err is None and not all(value(w, S, k) == value(w, truth[t], k) for k, _ in keys_qs):
            first_err = t
    return {"fam": fam, "len": length, "i": i, "mode": mode, "final_ok": value(w, S, key) == value(w, truth[-1], key),
            "state_ok": all(value(w, S, k) == value(w, truth[-1], k) for k, _ in keys_qs), "first_err": first_err,
            "start_ok": start_ok, "depends_on_start": value(w, so, key) != value(w, truth[-1], key), "seconds": time.time() - t0}


jobs = [(fam, L, i, mode) for L in (100, 200) for fam in ("jugs", "toggles", "machines", "cards") for i in range(N)
        for mode in (("text", "image", "image_obs") if fam in ("jugs", "toggles") else ("text",))]
t0 = time.time()
res = []
with cf.ThreadPoolExecutor(PAR) as ex:  # each chain is printed as soon as it ends (VERBOSE=1) and saved as it goes
    for fut in cf.as_completed([ex.submit(run, j) for j in jobs]):
        r = fut.result()
        res.append(r)
        with open(os.environ.get("OUT", "/dev/shm/conseq/long_chain.jsonl"), "a") as f:
            f.write(json.dumps(r) + "\n")
        if os.environ.get("VERBOSE"):
            print(f"[{(time.time() - t0) / 60:5.1f} min] {r['fam']:8s} {r['len']:3d} {r['mode']:9s} final {'ok' if r['final_ok'] else 'WRONG':5s} "
                  f"whole state {'ok' if r['state_ok'] else 'wrong':5s} exact until {r['first_err'] if r['first_err'] is not None else 'the end'} "
                  f"(answer depends on start: {r['depends_on_start']})", flush=True)
json.dump(res, open(os.environ["OUT_JSON"], "w"))  # PORT: it wrote /dev/shm/conseq/long_chain.json
print(f"{len(res)} chains in {(time.time() - t0) / 60:.1f} min (Ekbasis V41, one question per prompt, {N} items per world and length)")
print(f"{'world':9s} {'len':>4s} {'mode':>10s} | {'final ans':>9s} {'whole state':>11s} {'exact until (median step)':>26s} {'ans depends on start':>21s} {'s/item':>7s}")
for L in (100, 200):
    for fam in ("jugs", "toggles", "machines", "cards"):
        for mode in ("text", "image", "image_obs"):
            g = [r for r in res if r["fam"] == fam and r["len"] == L and r["mode"] == mode]
            if not g:
                continue
            fe = sorted(r["first_err"] if r["first_err"] is not None else L + 1 for r in g)
            med = fe[len(fe) // 2]
            print(f"{fam:9s} {L:4d} {mode:>10s} | {100 * sum(r['final_ok'] for r in g) / len(g):8.0f}% {100 * sum(r['state_ok'] for r in g) / len(g):10.0f}% "
                  f"{('all ' + str(L) if med > L else str(med)):>26s} {100 * sum(r['depends_on_start'] for r in g) / len(g):20.0f}% "
                  f"{sum(r['seconds'] for r in g) / len(g):7.0f}")
