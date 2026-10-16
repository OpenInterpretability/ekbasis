"""Robustness of the consequence model (served by the System One API) to how the situation is written. The same items
(machines, lamps, containers; 1-3 actions; the question is about a variable the actions change) in five versions:
  orig     the training format
  para     reworded: other names for the things, rules and actions in other words, state lines shuffled, question rephrased
  facts    the training format plus irrelevant facts before and after
  past     the training format plus actions done BEFORE the state was recorded (they must not be applied again)
  big      bigger worlds than in training (9-10 devices, 10-12 lamps with 6 buttons, 5 containers), training format
argv: N items per world. env: CQ_URL."""
import json, os, random, sys, urllib.request
sys.path.insert(0, "/root/decis/conseq")
from envs import qchoice
from worldgen import Jugs, Machines, Toggles

N = int(sys.argv[1]) if len(sys.argv) > 1 else 40
CQ_URL = os.environ.get("CQ_URL", "http://127.0.0.1:8501/v1/systemone")
NOTE = "The questions are about the state after all these actions."
FACTS = ("Background, not part of the task: the workshop opened at 8 a.m., two cats live in the building, the coffee "
         "machine is broken and the next delivery is on Friday.")
FACTS2 = "(Unrelated: the delivery truck arrived at noon and the parking lot was full.)"
DEV = ["the pump", "the fan", "the valve", "the drill", "the press", "the mixer", "the heater", "the lift", "the saw", "the oven"]
SW = ["the red switch", "the green switch", "the blue switch", "the white switch", "the black switch", "the gray switch"]
CONT = ["the kettle", "the bucket", "the vase", "the pitcher", "the barrel"]


def grow(F, rng):
    """A world of family F, bigger than in training when F is in BIG."""
    w = F(rng)
    if BIG:
        if F is Machines:
            w.devs = [f"M{k}" for k in range(1, rng.randint(9, 10) + 1)]
            w.rules = ("World: devices " + ", ".join(w.devs) + ". Each is in one state of the cycle " + " -> ".join(w.cycle + [w.cycle[0]])
                       + ". 'tick' moves every device one step along the cycle; 'tick D' moves only D; 'reset D' puts D back to " + w.cycle[0] + ".")
        elif F is Toggles:
            w.n, w.m = rng.randint(10, 12), 6
            w.wiring = {f"B{i + 1}": sorted(rng.sample(range(w.n), rng.randint(1, 4))) for i in range(w.m)}
            w.kinds = {b: rng.choice(["advance", "advance", "on", "off"]) for b in w.wiring}
            cyc = "off -> dim -> bright -> off" if w.three else "off -> on -> off"
            kinds = {"advance": f"moves each of its {w.lamp}s one step along the cycle {cyc}",
                     "on": f"sets each of its {w.lamp}s to {w.states[-1]}", "off": f"sets each of its {w.lamp}s to off"}
            btn = "; ".join(f"{b} {kinds[w.kinds[b]]} ({', '.join(f'{w.lamp} {j + 1}' for j in v)})" for b, v in w.wiring.items())
            w.rules = f"World: {w.n} {w.lamp}s numbered 1 to {w.n}, each {' / '.join(w.states)}, and {w.m} buttons. Pressing a button: {btn}."
        else:
            w.names = ["A", "B", "C", "D", "E"]
            w.cap = {x: rng.randint(3, 10) for x in w.names}
            w.rules = (f"World: containers {', '.join(f'{x} (holds {w.cap[x]} liters)' for x in w.names)} of {w.liq}. 'fill X' fills X "
                       f"to the top; 'empty X' empties X; 'pour X into Y' moves {w.liq} from X to Y until X is empty or Y is full, whichever comes first.")
    return w


def var_q(w, s, key):
    """(question, answer) about one variable, in the training wording."""
    if w.family == "machines":
        return qchoice(f"In which state is {key}?", [(x, x) for x in w.cycle]), w.cycle[s["st"][key]]
    if w.family == "toggles":
        return qchoice(f"What state is {w.lamp} {key + 1} in?", [(x, x) for x in w.states]), w.states[s["st"][key]]
    return qchoice(f"How many liters are in {key}?", [(str(k), f"{k} liters") for k in range(w.cap[key] + 1)]), str(s["v"][key])


def reworded(w, s0, acts, key, rng):
    """The same item in other words (and other names)."""
    if w.family == "machines":
        nm = dict(zip(w.devs, rng.sample(DEV, len(w.devs))))
        cyc = ", then ".join(w.cycle)
        rules = (f"A workshop has {len(w.devs)} machines: {', '.join(nm[d] for d in w.devs)}. Each machine is always in one of these modes, "
                 f"visited in this order and wrapping around: {cyc}, then back to {w.cycle[0]}. A general 'tick' pushes every machine to its "
                 f"next mode. Ticking a single machine pushes only that machine. Resetting a machine sends it back to {w.cycle[0]}.")
        order = rng.sample(w.devs, len(w.devs))
        state = "Right now: " + "; ".join(f"{nm[d]} is {w.cycle[s0['st'][d]]}" for d in order) + "."
        say = lambda a: ("a general tick happens" if a["op"] == "tick" else
                         f"{nm[a['d']]} alone is ticked" if a["op"] == "tick1" else f"{nm[a['d']]} is reset")
        q = qchoice(f"Once all of this is done, what mode is {nm[key]} in?", [(x, x) for x in w.cycle])
    elif w.family == "toggles":
        sw = dict(zip(w.wiring, rng.sample(SW, len(w.wiring))))
        lv = " and ".join(w.states) if len(w.states) == 2 else ", ".join(w.states[:-1]) + " and " + w.states[-1]
        what = {"advance": f"bumps each of them to the next level ({' -> '.join(w.states + ['off'])})",
                "on": f"turns all of them to {w.states[-1]}", "off": "turns all of them off"}
        wires = " ".join(f"{sw[b][0].upper() + sw[b][1:]} is wired to {w.lamp}{'s' if len(v) > 1 else ''} {', '.join(str(j + 1) for j in v)} and {what[w.kinds[b]]}."
                         for b, v in w.wiring.items())
        rules = f"A control panel drives {w.n} {w.lamp}s, numbered from 1 to {w.n}; each one can be {lv}. {wires}"
        order = rng.sample(range(w.n), w.n)
        state = "At the moment, " + ", ".join(f"{w.lamp} {j + 1} is {w.states[s0['st'][j]]}" for j in order) + "."
        say = lambda a: f"someone flips {sw[a['b']]}"
        q = qchoice(f"When everything is over, how is {w.lamp} {key + 1}?", [(x, x) for x in w.states])
    else:
        nm = dict(zip(w.names, rng.sample(CONT, len(w.names))))
        rules = (f"There are {len(w.names)} containers of {w.liq}: " + ", ".join(f"{nm[x]}, which takes at most {w.cap[x]} liters" for x in w.names)
                 + f". Filling a container tops it up to its capacity; emptying it throws everything out; pouring one container into another "
                 "transfers as much as fits, stopping when the first runs dry or the second is full.")
        order = rng.sample(w.names, len(w.names))
        state = "Right now " + ", ".join(f"{nm[x]} has {s0['v'][x]} liters" for x in order) + "."
        say = lambda a: (f"{nm[a['x']]} is poured into {nm[a['y']]}" if a["op"] == "pour" else
                         f"{nm[a['x']]} is filled up" if a["op"] == "fill" else f"{nm[a['x']]} is emptied")
        q = qchoice(f"How much {w.liq} is in {nm[key]} at the end, in liters?", [(str(k), f"{k} liters") for k in range(w.cap[key] + 1)])
    steps = "Then, in this order: " + "; ".join(f"({i + 1}) {say(a)}" for i, a in enumerate(acts)) + "."
    return f"{rules}\n\n{state}\n\n{steps}\n\nAnswer about how things stand once every step above has been carried out.", q


def post(text, q):
    req = urllib.request.Request(CQ_URL, data=json.dumps({"state": text, "questions": {"q": q}}).encode(),
                                 headers={"Content-Type": "application/json"})
    a = json.load(urllib.request.urlopen(req, timeout=600))["answers"]["q"]
    return a["choice"], a["confidence"]


def items(F, rng, n):
    out = []
    while len(out) < n:
        w = grow(F, rng)
        w.name = F.family
        s0 = s = w.sample_state(rng)
        acts = []
        for _ in range(rng.randint(1, 3)):
            a = w.sample_action(rng, s)
            s, _ = w.step(s, a)
            acts.append(a)
        keys = list(w.devs) if F is Machines else list(range(w.n)) if F is Toggles else list(w.names)
        moved = [k for k in keys if var_q(w, s0, k)[1] != var_q(w, s, k)[1]]
        if not moved:
            continue
        key = rng.choice(moved)
        q, gold = var_q(w, s, key)
        listing = "\n".join(f"{i + 1}. {w.render_action(a)}" for i, a in enumerate(acts))
        base = f"{w.rules}\n\nCurrent state:\n{w.render(s0)}\n\nActions, in order:\n{listing}\n\n{NOTE}"
        v = {"orig" if not BIG else "big": (base, q)}
        if not BIG:
            v["para"] = reworded(w, s0, acts, key, rng)
            v["facts"] = (f"{FACTS}\n\n{base}\n\n{FACTS2}", q)
            past = "; ".join(w.render_action(w.sample_action(rng, s0)) for _ in range(2))
            v["past"] = (f"{w.rules}\n\nEarlier today, before the state below was recorded, these actions were done: {past}.\n\nCurrent state:\n"
                         f"{w.render(s0)}\n\nActions, in order:\n{listing}\n\n{NOTE}", q)
        out.append((F.family, gold, v))
    return out


if __name__ == "__main__":
    rng = random.Random(77)
    BIG = False
    for name, (text, q) in items(Toggles, random.Random(3), 1)[0][2].items():
        print(f"--- example, {name}:\n{text}\nQ: {q['instructions']}\n")
    res = {}
    for BIG in (False, True):
        for F in (Machines, Toggles, Jugs):
            for fam, gold, v in items(F, rng, N):
                for name, (text, q) in v.items():
                    ans, conf = post(text, q)
                    res.setdefault(name, {}).setdefault(fam, []).append((ans == gold, conf))
    print(f"accuracy on questions the actions change ({N} items per world; 'big' = bigger worlds than in training)")
    print(f"{'version':8s} {'machines':>9s} {'lamps':>9s} {'containers':>11s} {'all':>7s} {'mean conf':>10s}")
    for name in ("orig", "para", "facts", "past", "big"):
        r = res[name]
        allr = [x for f in r for x in r[f]]
        cell = lambda xs: f"{100 * sum(o for o, _ in xs) / len(xs):.1f}"
        print(f"{name:8s} {cell(r['machines']):>9s} {cell(r['toggles']):>9s} {cell(r['jugs']):>11s} {cell(allr):>7s} "
              f"{100 * sum(c for _, c in allr) / len(allr):9.1f}%")
