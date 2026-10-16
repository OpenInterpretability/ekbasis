"""Does the consequence skill (trained in English only) carry over to Portuguese? The same items (machines, lamps,
containers; 1-3 actions) are written in English and in Portuguese (rules, state, actions and question translated by
templates) and answered through the consequence API by the base model and the 'rules' adapter. Half of the items have an
answer the actions change. argv: N items per world."""
import json, random, sys, urllib.request
sys.path.insert(0, "/root/decis/conseq")
from envs import qchoice, qnoul
from worldgen import Jugs, Machines, Toggles

N = int(sys.argv[1]) if len(sys.argv) > 1 else 40
WORD = {"green": "verde", "yellow": "amarelo", "red": "vermelho", "idle": "ocioso", "warming": "aquecendo", "running": "rodando",
        "cooling": "esfriando", "low": "baixo", "mid": "médio", "high": "alto", "closed": "fechado", "opening": "abrindo",
        "open": "aberto", "closing": "fechando", "off": "apagada", "on": "acesa", "dim": "fraca", "bright": "forte",
        "water": "água", "oil": "óleo", "juice": "suco", "sand": "areia"}
W = lambda x: WORD.get(x, x)
label = lambda g: ("yes" if g else "no") if isinstance(g, bool) else str(g)


def pt_rules(w):
    if w.family == "machines":
        cyc = " -> ".join(W(x) for x in w.cycle + [w.cycle[0]])
        return (f"Mundo: dispositivos {', '.join(w.devs)}. Cada um está em um estado do ciclo {cyc}. 'avançar' move todos os "
                f"dispositivos um passo no ciclo; 'avançar D' move só D; 'zerar D' devolve D para {W(w.cycle[0])}.")
    if w.family == "toggles":
        cyc = " -> ".join(W(x) for x in w.states + ["off"])
        top = W(w.states[-1])
        kinds = {"advance": f"move cada uma das suas lâmpadas um passo no ciclo {cyc}",
                 "on": f"coloca cada uma das suas lâmpadas em {top}", "off": "coloca cada uma das suas lâmpadas em apagada"}
        btn = "; ".join(f"{b} {kinds[w.kinds[b]]} ({', '.join(f'lâmpada {j + 1}' for j in v)})" for b, v in w.wiring.items())
        return (f"Mundo: {w.n} lâmpadas numeradas de 1 a {w.n}, cada uma {' / '.join(W(x) for x in w.states)}, e {w.m} botões. "
                f"Apertar um botão: {btn}.")
    caps = ", ".join(f"{x} (cabem {w.cap[x]} litros)" for x in w.names)
    return (f"Mundo: recipientes {caps} de {W(w.liq)}. 'encher X' enche X até a borda; 'esvaziar X' esvazia X; 'despejar X em Y' "
            f"passa {W(w.liq)} de X para Y até X ficar vazio ou Y ficar cheio, o que vier primeiro.")


def pt_state(w, s):
    if w.family == "machines":
        return "Dispositivos: " + ", ".join(f"{d} {W(w.cycle[v])}" for d, v in s["st"].items())
    if w.family == "toggles":
        return ", ".join(f"lâmpada {i + 1}: {W(w.states[x])}" for i, x in enumerate(s["st"]))
    return ", ".join(f"{x}: {s['v'][x]} de {w.cap[x]} litros" for x in w.names)


def pt_action(w, a):
    if w.family == "machines":
        return "avançar" if a["op"] == "tick" else (f"avançar {a['d']}" if a["op"] == "tick1" else f"zerar {a['d']}")
    if w.family == "toggles":
        return f"apertar {a['b']}"
    return {"fill": f"encher {a.get('x')}", "empty": f"esvaziar {a.get('x')}", "pour": f"despejar {a.get('x')} em {a.get('y')}"}[a["op"]]


def pt_question(w, q):
    t = q["instructions"]
    if q["type"] == "noul":
        rep = [("Are ", ""), (" and ", " e "), (" in the same state?", " estão no mesmo estado?"), ("Is ", ""), (" full?", " está cheio?"),
               (" empty?", " está vazio?"), ("lamp ", "a lâmpada "), ("light ", "a lâmpada "), ("bulb ", "a lâmpada "), ("LED ", "a lâmpada ")]
        for a, b in rep:
            t = t.replace(a, b)
        return qnoul(t[0].upper() + t[1:])
    crit = {k: W(v).replace(" liters", " litros") for k, v in q["criteria"].items()}
    if t.startswith("In which state is"):
        t = t.replace("In which state is", "Em qual estado está")
    elif t.startswith("How many devices are"):
        t = "Quantos dispositivos estão em " + W(t.split()[-1].rstrip("?")) + "?"
    elif t.startswith("What state is"):
        t = "Em que estado está a lâmpada " + t.split()[-2] + "?"
    elif t.startswith("How many") and "not off" in t:
        t = "Quantas lâmpadas não estão apagadas?"
    elif t.startswith("How many liters are in"):
        t = t.replace("How many liters are in", "Quantos litros há em")
    elif t.startswith("How many liters are there in all"):
        t = "Quantos litros há no total?"
    labels = {k: W(k) for k in crit} if all(k in WORD for k in crit) else {k: k for k in crit}
    return qchoice(t, [(labels[k], crit[k]) for k in crit]), labels


def post(items, adapter):
    req = urllib.request.Request("http://127.0.0.1:8400/batch", data=json.dumps({"items": items, "adapter": adapter}).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=900))["results"]


rng = random.Random(55)
items = []
for F in (Machines, Toggles, Jugs):
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
        en = (f"{w.rules}\n\nCurrent state:\n{w.render(s0)}\n\nActions, in order:\n" + "\n".join(f"{i + 1}. {w.render_action(a)}" for i, a in enumerate(acts))
              + f"\n\n{w.floor_note()}")
        pt = (f"{pt_rules(w)}\n\nEstado atual:\n{pt_state(w, s0)}\n\nAções, em ordem:\n" + "\n".join(f"{i + 1}. {pt_action(w, a)}" for i, a in enumerate(acts))
              + "\n\nAs perguntas são sobre o estado depois de todas essas ações.")
        if q["type"] == "noul":
            qpt, gpt = pt_question(w, q), label(gold)
        else:
            qpt, labels = pt_question(w, q)
            gpt = labels[label(gold)]
        items.append({"fam": F.family, "changed": changed, "en": en, "q": q, "gold": label(gold), "pt": pt, "qpt": qpt, "gpt": gpt})
print(f"{len(items)} items; example (pt):\n{items[1]['pt']}\nQ: {items[1]['qpt']['instructions']} -> {items[1]['gpt']}\n", flush=True)
res = {}
for adapter in ("base", "rules"):
    en = post([{"state": it["en"], "question": it["q"]} for it in items], adapter)
    pt = post([{"state": it["pt"], "question": it["qpt"]} for it in items], adapter)
    res[adapter] = ([e["answer"] == it["gold"] for e, it in zip(en, items)], [p["answer"] == it["gpt"] for p, it in zip(pt, items)])
print(f"{'world':9s} {'n chg':>5s} | {'base EN':>7s} {'base PT':>7s} | {'rules EN':>8s} {'rules PT':>8s}   (questions the actions change)")
for fam in ("machines", "toggles", "jugs", "all"):
    idx = [i for i, it in enumerate(items) if it["changed"] and (fam == "all" or it["fam"] == fam)]
    cell = lambda a, l: 100 * sum(res[a][l][i] for i in idx) / len(idx)
    print(f"{fam:9s} {len(idx):5d} | {cell('base', 0):7.1f} {cell('base', 1):7.1f} | {cell('rules', 0):8.1f} {cell('rules', 1):8.1f}")
