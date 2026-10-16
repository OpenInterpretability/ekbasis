"""Image check of PREREG_IMAGE.md, through the SERVED API (as a client sends images): the worlds and drawings of
conseq/image_eval.py (lamps drawn as bulbs, containers drawn with the water level), a fresh seed, N per world, half with
an answer the actions change. Three prompts per item: text (state as text), image (state as an image, actions as text),
read (the final state as an image: can it read the picture at all?).  python3 image_served.py NAME URL N"""
import base64, io, json, os, random, sys, urllib.request, concurrent.futures as cf
os.environ["PROMPT_STYLE"] = "semif"
sys.path.insert(0, "/root/v50p/worldgen")
from PIL import Image, ImageDraw
from worldgen import Jugs, Toggles
NAME, URL, N = sys.argv[1], sys.argv[2], int(sys.argv[3])


def draw_lamps(w, s):
    n = w.n
    img = Image.new("RGB", (110 * n + 20, 190), "white")
    d = ImageDraw.Draw(img)
    colors = {"off": (70, 70, 70), "on": (255, 205, 0), "bright": (255, 205, 0), "dim": (240, 228, 160)}
    for i, x in enumerate(s["st"]):
        cx = 65 + 110 * i
        st = w.states[x]
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
        x0, top = 40 + 130 * i, 20 + hmax - w.cap[x] * unit
        bottom = 20 + hmax
        level = s["v"][x]
        if level:
            d.rectangle((x0, bottom - level * unit, x0 + 70, bottom), fill=(70, 130, 225))
        d.rectangle((x0, top, x0 + 70, bottom), outline="black", width=3)
        for k in range(1, w.cap[x]):
            d.line((x0, bottom - k * unit, x0 + 12, bottom - k * unit), fill="black", width=1)
        d.text((x0, bottom + 12), f"{x} (holds {w.cap[x]} L)", fill="black")
    return img


DRAW = {"toggles": draw_lamps, "jugs": draw_jugs}
label = lambda g: ("yes" if g else "no") if isinstance(g, bool) else str(g)


def uri(img):
    b = io.BytesIO()
    img.save(b, format="PNG")
    return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()




def ask(text, q, img):
    body = {"state": text, "questions": {"q": q}}
    if img is not None:
        body["images"] = [uri(img)]
    a = json.load(urllib.request.urlopen(urllib.request.Request(f"{URL}/v1/systemone", json.dumps(body).encode(),
                 {"Content-Type": "application/json"}), timeout=600))["answers"]["q"]
    return ("yes" if a["value"] else "no") if a["type"] in ("noul", "boolean") else str(a["choice"])


rng = random.Random("image-fresh-20261015")
items = []
for F in (Toggles, Jugs):
    got = {True: 0, False: 0}
    while got[True] + got[False] < N:
        w = F(rng)
        w.name = F.family
        s0 = s = w.sample_state(rng)
        acts = []
        for _ in range(rng.randint(1, 3)):
            a = w.sample_action(rng, s)
            s, _ = w.step(s, a)
            acts.append(a)
        qtype = rng.choice(F.QTYPES)
        st = rng.getstate()
        q, gold = w.ask(rng, s, [], qtype)
        r0 = random.Random()
        r0.setstate(st)
        changed = label(w.ask(r0, s0, [], qtype)[1]) != label(gold)
        if got[changed] >= N // 2:
            continue
        got[changed] += 1
        items.append((F.family, w, s0, acts, s, q, label(gold), changed))
print(f"{len(items)} items", flush=True)


def one(it):
    fam, w, s0, acts, sT, q, gold, changed = it
    act = "\n".join(f"{i + 1}. {w.render_action(a)}" for i, a in enumerate(acts))
    text_p = f"{w.rules}\n\nCurrent state:\n{w.render(s0)}\n\nActions, in order:\n{act}\n\n{w.floor_note()}"
    img_p = f"{w.rules}\n\nCurrent state: shown in the attached image.\n\nActions, in order:\n{act}\n\n{w.floor_note()}"
    read_p = f"{w.rules}\n\nState after the actions: shown in the attached image.\n\n{w.ceiling_note()}"
    row = {"fam": fam, "changed": changed, "gold": gold}
    for cond, text, img in (("text", text_p, None), ("image", img_p, DRAW[fam](w, s0)), ("read", read_p, DRAW[fam](w, sT))):
        row[cond] = ask(text, q, img) == gold
    return row


with cf.ThreadPoolExecutor(8) as ex:
    res = list(ex.map(one, items))
json.dump(res, open(f"/root/v50p/image_{NAME}.json", "w"))
for fam in ("toggles", "jugs", "all"):
    g = [r for r in res if fam == "all" or r["fam"] == fam]
    print(fam, len(g), {c: round(100 * sum(r[c] for r in g) / len(g), 1) for c in ("text", "image", "read")},
          "changed:", {c: round(100 * sum(r[c] for r in g if r["changed"]) / max(1, sum(r["changed"] for r in g)), 1) for c in ("text", "image", "read")})
print("IMAGE_DONE", NAME)
