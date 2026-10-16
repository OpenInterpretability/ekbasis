# PRELAUNCH PORT (P7) of _orig/image_chain.py: every changed line is marked PORT; the full diff is CHANGES.diff in this folder.
"""Chaining from an IMAGE: see the start once, then simulate in text. Containers and lamps (drawn as in image_eval.py),
10-20 actions given in text, one question about the final state. Served model: Ekbasis (merged, multimodal) through
the System One API (vLLM backend, images on).
  text    the chain starts from the true state in text (as in speed_bench.py cq)
  image   step 0 reads every variable from the picture; the chain then goes on in text from what it read
  image1  the first step reads the picture AND applies the first action in one pass; then text
Also: how often the whole starting state is read right. env: CQ_URL, N (items per world, 30), PAR (8)."""
import base64, concurrent.futures as cf, io, json, math, os, random, sys, time, urllib.request
sys.path.insert(0, os.environ.get("LIB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib")))  # PORT
from envs import qchoice
from PIL import Image, ImageDraw
from worldgen import Jugs, Toggles

CQ_URL = os.environ.get("CQ_URL", "http://127.0.0.1:8501/v1/systemone")
N, PAR = int(os.environ.get("N", "30")), int(os.environ.get("PAR", "8"))


def draw_lamps(w, s):
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


def draw_jugs(w, s):
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


def variables(w):
    if w.family == "jugs":
        return [(x, qchoice(f"How many liters are in {x}?", [(str(k), f"{k} liters") for k in range(w.cap[x] + 1)])) for x in w.names]
    return [(j, qchoice(f"What state is {w.lamp} {j + 1} in?", [(x, x) for x in w.states])) for j in range(w.n)]


def build(w, A):
    if w.family == "jugs":
        return {"v": {x: int(A[x]) for x in w.names}}
    return {"st": [w.states.index(A[j]) for j in range(w.n)]}


def read_all(text, keys_qs, images=None):
    body = {"state": text, "questions": {f"v{j}": q for j, (_, q) in enumerate(keys_qs)}}
    if images:
        body["images"] = images
    r = post(body)["answers"]
    return {k: r[f"v{j}"]["choice"] for j, (k, _) in enumerate(keys_qs)}


def item(i):
    F = (Jugs, Toggles)[i % 2]
    rng = random.Random(7000 + i)
    while True:
        w = F(rng)
        if (F is Jugs and len(w.names) == 3) or (F is Toggles and w.n >= 5):
            break
    w.name = F.family
    s0 = s = w.sample_state(rng)
    acts = []
    for _ in range(rng.randint(10, 20)):
        a = w.sample_action(rng, s)
        s, _ = w.step(s, a)
        acts.append(a)
    keys_qs = variables(w)
    key = rng.randrange(len(keys_qs))
    return w, s0, acts, s, keys_qs, keys_qs[key][0]


def value(w, s, k):
    return str(s["v"][k]) if w.family == "jugs" else w.states[s["st"][k]]


def chain(w, S, acts, keys_qs):
    for a in acts:
        text = f"{w.rules}\n\nCurrent state:\n{w.render(S)}\n\nActions, in order:\n1. {w.render_action(a)}\n\n{w.floor_note()}"
        S = build(w, read_all(text, keys_qs))
    return S


def run(i):
    w, s0, acts, sT, keys_qs, key = item(i)
    img = [uri((draw_jugs if w.family == "jugs" else draw_lamps)(w, s0))]
    gold = value(w, sT, key)
    out = {"fam": w.family, "n_act": len(acts)}
    t0 = time.time()
    out["text"] = value(w, chain(w, s0, acts, keys_qs), key) == gold
    out["t_text"] = time.time() - t0
    t0 = time.time()
    seen = read_all(f"{w.rules}\n\nState after the actions: shown in the attached image.\n\n{w.ceiling_note()}", keys_qs, img)
    S0 = build(w, seen)
    out["read_ok"] = all(value(w, S0, k) == value(w, s0, k) for k, _ in keys_qs)
    out["read_vars"] = sum(value(w, S0, k) == value(w, s0, k) for k, _ in keys_qs) / len(keys_qs)
    out["image"] = value(w, chain(w, S0, acts, keys_qs), key) == gold
    out["t_image"] = time.time() - t0
    first = (f"{w.rules}\n\nCurrent state: shown in the attached image.\n\nActions, in order:\n1. {w.render_action(acts[0])}\n\n"
             f"{w.floor_note()}")
    S1 = build(w, read_all(first, keys_qs, img))
    out["image1"] = value(w, chain(w, S1, acts[1:], keys_qs), key) == gold
    return out


with cf.ThreadPoolExecutor(PAR) as ex:
    res = list(ex.map(run, range(2 * N)))
json.dump(res, open(os.environ["OUT_JSON"], "w"))  # PORT: it wrote /dev/shm/conseq/image_chain.json (item i = position i)
print(f"{len(res)} items (10-20 actions each), Ekbasis V41 merged; accuracy of the final answer")
print(f"{'world':10s} {'text start':>11s} {'image start':>12s} {'image+1st action':>17s} {'start read whole':>17s} {'vars read':>10s}")
for fam in ("jugs", "toggles", "all"):
    g = [r for r in res if fam == "all" or r["fam"] == fam]
    pct = lambda k: 100 * sum(r[k] for r in g) / len(g)
    print(f"{fam:10s} {pct('text'):11.1f} {pct('image'):12.1f} {pct('image1'):17.1f} {pct('read_ok'):17.1f} "
          f"{100 * sum(r['read_vars'] for r in g) / len(g):10.1f}")
print(f"mean seconds per item: text {sum(r['t_text'] for r in res) / len(res):.1f}, image {sum(r['t_image'] for r in res) / len(res):.1f}")
