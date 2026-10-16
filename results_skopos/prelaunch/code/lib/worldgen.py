"""World factory: every example is a NEW world. A family samples its parameters and conventions (names, numbering,
directions, which rules apply, limits) and writes its rules from them, so the only way to predict an outcome is to
read the rules. Exact simulators; typed questions about the state after the actions (with an event log in the
ceiling prompt, as in envs.py).

Families: TRAIN (7) for training, VAL (2) to choose checkpoints, TEST (3) never seen. Each training family keeps one
question type out of training (held). The interface matches envs.py, so make_example / the trainers work unchanged:
a world has rules, sample_state, sample_action, step, render, render_action, floor_note, ceiling_note, ask,
QTYPES, HELD_Q and, when actions can fail, event_log."""
from __future__ import annotations

import collections
import random

from envs import make_example, numeric_options, qchoice, qnoul

ALPHA = "ABCDEFGHIJ"


def pick(rng, pool, k=None):
    return rng.choice(pool) if k is None else rng.sample(pool, k)


def log_of(acts, events, render_action, ok_word="done"):
    return "What happened: " + "; ".join(
        f"action {i + 1} ({render_action(a)}): {e.get('note', ok_word)}" for i, (a, e) in enumerate(zip(acts, events))) + "."


class Base:
    HELD_Q = None

    def floor_note(self):
        return "The questions are about the state after all these actions."

    def ceiling_note(self):
        return "This is the state after all the actions."

    def event_log(self, acts, events):
        return log_of(acts, events, self.render_action)


# ============================================================================================== TRAIN families
class GridMove(Base):
    family = "grid"
    QTYPES = ["pos", "items_left", "item_at", "moved", "blocked"]
    HELD_Q = "moved"

    def __init__(self, rng):
        self.n = rng.randint(4, 7)
        self.letters = rng.random() < 0.5
        self.origin = pick(rng, ["top", "bottom"])
        self.vocab = pick(rng, [("north", "south", "east", "west"), ("up", "down", "right", "left")])
        self.wrap = rng.random() < 0.3
        self.ice = rng.random() < 0.3
        self.mover = pick(rng, ["robot", "rover", "drone", "cat", "bot"])
        self.item = pick(rng, ["coin", "gem", "star", "key"])
        n, up, down, right, left = self.n, *self.vocab
        cols = f"columns {ALPHA[0]} to {ALPHA[n - 1]}" if self.letters else f"columns 1 to {n}"
        name = f"like {ALPHA[1]}3" if self.letters else "like (2,3), column first"
        rows = f"rows 1 to {n}, row 1 at the {self.origin}"
        self.rules = (f"World: a {self.mover} on a {n}x{n} grid with {cols} (left to right) and {rows}; a cell is "
                      f"named {name}. '{up}' moves one cell toward the top edge, '{down}' toward the bottom edge, "
                      f"'{right}' toward the right edge, '{left}' toward the left edge. Walls cannot be entered. "
                      + ("Moving off an edge brings the " + self.mover + " to the opposite edge of the same row or "
                         "column, unless that cell is a wall (then the move is blocked). " if self.wrap else
                         "A move off the grid or into a wall is blocked and the " + self.mover + " stays. ")
                      + (f"Ice cells: after entering an ice cell the {self.mover} slides one more cell in the same "
                         "direction if that cell can be entered. " if self.ice else "")
                      + f"Entering a cell with a {self.item} picks it up.")

    def cell(self, r, c):
        """r is the internal row from the top (0-based)."""
        row = r + 1 if self.origin == "top" else self.n - r
        return f"{ALPHA[c]}{row}" if self.letters else f"({c + 1},{row})"

    def sample_state(self, rng):
        cells = [(r, c) for r in range(self.n) for c in range(self.n)]
        rng.shuffle(cells)
        k = rng.randint(2, max(2, self.n))
        walls = set(cells[:k])
        items = set(cells[k:k + rng.randint(2, 4)])
        ice = set(cells[k + 5:k + 5 + (rng.randint(2, 5) if self.ice else 0)])
        return {"walls": walls, "items": items, "ice": ice - items, "pos": cells[k + 4]}

    def sample_action(self, rng, s):
        return {"dir": rng.randrange(4)}

    def _next(self, s, r, c, d):
        dr, dc = [(-1, 0), (1, 0), (0, 1), (0, -1)][d]
        nr, nc = r + dr, c + dc
        if not (0 <= nr < self.n and 0 <= nc < self.n):
            if not self.wrap:
                return None
            nr, nc = nr % self.n, nc % self.n
        return None if (nr, nc) in s["walls"] else (nr, nc)

    def step(self, s, a):
        ns = {"walls": s["walls"], "items": set(s["items"]), "ice": s["ice"], "pos": s["pos"]}
        nxt = self._next(s, *s["pos"], a["dir"])
        if nxt is None:
            return ns, {"blocked": True, "moved": False, "note": "blocked"}
        got = []
        for _ in range(2):
            ns["pos"] = nxt
            if nxt in ns["items"]:
                ns["items"].discard(nxt)
                got.append(nxt)
            if not (self.ice and nxt in s["ice"]):
                break
            nxt = self._next(s, *nxt, a["dir"])
            if nxt is None:
                break
        note = "moved" + (f", picked up the {self.item} at " + ", ".join(self.cell(*g) for g in got) if got else "")
        return ns, {"blocked": False, "moved": True, "note": note}

    def render(self, s, events=None):
        lst = lambda xs: ", ".join(sorted(self.cell(*x) for x in xs)) or "none"
        return (f"Walls: {lst(s['walls'])}\n" + (f"Ice: {lst(s['ice'])}\n" if self.ice else "")
                + f"{self.item.capitalize()}s: {lst(s['items'])}\n{self.mover.capitalize()}: {self.cell(*s['pos'])}")

    def render_action(self, a):
        return f"move {self.vocab[a['dir']]}"

    def ask(self, rng, s, events, qtype):
        if qtype == "pos":
            return qchoice(f"In which cell is the {self.mover}?",
                           [(self.cell(r, c), "cell " + self.cell(r, c)) for r in range(self.n) for c in range(self.n)]), \
                self.cell(*s["pos"])
        if qtype == "items_left":
            return qchoice(f"How many {self.item}s are left?", [(str(k), f"{k}") for k in range(5)]), str(len(s["items"]))
        if qtype == "item_at":
            pool = list(s["items"]) or [(rng.randrange(self.n), rng.randrange(self.n))]
            if rng.random() < 0.5:
                pool = [(rng.randrange(self.n), rng.randrange(self.n))]
            x = rng.choice(pool)
            return qnoul(f"Is there a {self.item} at {self.cell(*x)}?"), x in s["items"]
        if qtype == "moved":
            n = sum(e["moved"] for e in events)
            return qchoice(f"In how many of the actions did the {self.mover} change cell?",
                           [(str(k), f"{k} actions") for k in range(len(events) + 1)]), str(n)
        if qtype == "blocked":
            return qnoul("Was at least one action blocked?"), any(e["blocked"] for e in events)
        raise KeyError(qtype)


class Gravity(Base):
    family = "gravity"
    QTYPES = ["slot", "count", "full", "top_item"]
    HELD_Q = "top_item"

    def __init__(self, rng):
        self.k, self.h = rng.randint(4, 7), rng.randint(4, 7)
        self.dir = pick(rng, ["down", "up"])
        self.lost = rng.random() < 0.4
        self.tokens = pick(rng, [("X", "O"), ("red", "blue"), ("A", "B"), ("cat", "dog")])
        self.thing = pick(rng, ["disc", "ball", "block", "token"])
        settle = "bottom" if self.dir == "down" else "top"
        self.rules = (f"World: {self.k} vertical tubes numbered 1 to {self.k}, each with {self.h} slots. A {self.thing} "
                      f"put into a tube {'falls down' if self.dir == 'down' else 'floats up'} to the first free slot from "
                      f"the {settle}. Slots are numbered from the {settle}: slot 1 is the {settle} slot. "
                      + ("Putting a " + self.thing + " into a full tube loses the " + self.thing + " (the tube stays "
                         "full)." if self.lost else "Putting a " + self.thing + " into a full tube fails and nothing "
                         "changes."))

    def sample_state(self, rng):
        return {"tubes": [[rng.choice(self.tokens) for _ in range(rng.randint(0, self.h))] for _ in range(self.k)]}

    def sample_action(self, rng, s):
        return {"tube": rng.randrange(self.k), "tok": rng.choice(self.tokens)}

    def step(self, s, a):
        tubes = [t[:] for t in s["tubes"]]
        t = tubes[a["tube"]]
        if len(t) >= self.h:
            return {"tubes": tubes}, {"slot": None, "note": "lost" if self.lost else "failed, the tube was full"}
        t.append(a["tok"])
        return {"tubes": tubes}, {"slot": len(t), "note": f"settled in slot {len(t)}"}

    def render(self, s, events=None):
        return f"Tubes, from slot 1 onward:\n" + "\n".join(
            f"tube {i + 1}: {' '.join(t) if t else '(empty)'}" for i, t in enumerate(s["tubes"]))

    def render_action(self, a):
        return f"put a {a['tok']} {self.thing} into tube {a['tube'] + 1}"

    def ask(self, rng, s, events, qtype):
        if qtype == "slot":
            e = events[-1]
            return qchoice(f"In which slot did the last {self.thing} end up?",
                           [(str(k), f"slot {k}") for k in range(1, self.h + 1)] + [("none", "it did not enter the tube")]), \
                str(e["slot"]) if e["slot"] else "none"
        if qtype == "count":
            c = rng.randrange(self.k)
            return qchoice(f"How many {self.thing}s are in tube {c + 1}?", [(str(k), f"{k}") for k in range(self.h + 1)]), \
                str(len(s["tubes"][c]))
        if qtype == "full":
            c = rng.randrange(self.k)
            return qnoul(f"Is tube {c + 1} full?"), len(s["tubes"][c]) >= self.h
        if qtype == "top_item":
            c = rng.randrange(self.k)
            t = s["tubes"][c]
            return qchoice(f"Which {self.thing} is in the highest-numbered occupied slot of tube {c + 1}?",
                           [(x, f"a {x} {self.thing}") for x in self.tokens] + [("empty", "the tube is empty")]), \
                t[-1] if t else "empty"
        raise KeyError(qtype)


class Counters(Base):
    family = "counters"
    QTYPES = ["value", "rejected", "zero", "total"]
    HELD_Q = "total"

    def __init__(self, rng):
        self.items = pick(rng, ["apples", "coins", "tickets", "credits", "bolts", "crates", "points"], rng.randint(2, 3))
        self.overdraft = pick(rng, [0, 0, 5, 10])
        self.fee = pick(rng, [0, 0, 1, 2])
        self.cap = pick(rng, [None, None, 20, 25, 30])
        self.refill = pick(rng, [None, None, (3, 5), (5, 8)])
        parts = [f"World: counters for {', '.join(self.items)}. 'add n X' adds n to X; 'remove n X' takes n from X."]
        parts.append(f"A removal costs a fee of {self.fee} more from the same counter." if self.fee else "Removals have no fee.")
        parts.append(f"A removal (with its fee) is rejected, changing nothing, if it would take the counter below "
                     f"{-self.overdraft}." if self.overdraft else "A removal (with its fee) is rejected, changing "
                     "nothing, if the counter would go below 0.")
        if self.cap:
            parts.append(f"No counter can exceed {self.cap}: any amount above {self.cap} is discarded.")
        if self.refill:
            parts.append(f"After an accepted removal, if the counter is below {self.refill[0]}, it is refilled by "
                         f"{self.refill[1]} at once.")
        self.rules = " ".join(parts)

    def sample_state(self, rng):
        hi = self.cap or 25
        return {"v": {it: rng.randint(0, min(15, hi)) for it in self.items}}

    def sample_action(self, rng, s):
        return {"op": pick(rng, ["add", "remove", "remove"]), "n": rng.randint(1, 9), "it": pick(rng, self.items)}

    def step(self, s, a):
        v = dict(s["v"])
        x = v[a["it"]]
        if a["op"] == "add":
            x += a["n"]
            if self.cap:
                x = min(x, self.cap)
            v[a["it"]] = x
            return {"v": v}, {"rejected": False, "note": "done"}
        x -= a["n"] + self.fee
        if x < -self.overdraft:
            return {"v": v}, {"rejected": True, "note": "rejected"}
        note = "done"
        if self.refill and x < self.refill[0]:
            x += self.refill[1]
            note = "done, then refilled"
        if self.cap:
            x = min(x, self.cap)
        v[a["it"]] = x
        return {"v": v}, {"rejected": False, "note": note}

    def render(self, s, events=None):
        return "Counters: " + ", ".join(f"{it} {s['v'][it]}" for it in self.items)

    def render_action(self, a):
        return f"{a['op']} {a['n']} {a['it']}"

    def ask(self, rng, s, events, qtype):
        if qtype == "value":
            it = pick(rng, self.items)
            g = s["v"][it]
            return qchoice(f"What is the value of {it}?", [(v, v) for v in numeric_options(g, -15, 60, 10)]), str(g)
        if qtype == "rejected":
            k = rng.randrange(len(events))
            return qnoul(f"Was action {k + 1} rejected?"), events[k]["rejected"]
        if qtype == "zero":
            it = pick(rng, self.items)
            return qnoul(f"Is {it} at 0 or below?"), s["v"][it] <= 0
        if qtype == "total":
            g = sum(s["v"].values())
            return qchoice("What is the sum of all the counters?", [(v, v) for v in numeric_options(g, -30, 120, 10)]), str(g)
        raise KeyError(qtype)


class Toggles(Base):
    family = "toggles"
    QTYPES = ["state", "same", "count_on"]
    HELD_Q = "count_on"

    def __init__(self, rng):
        self.n, self.m = rng.randint(4, 7), rng.randint(3, 4)
        self.three = rng.random() < 0.35
        self.lamp = pick(rng, ["lamp", "light", "bulb", "LED"])
        self.states = ["off", "dim", "bright"] if self.three else ["off", "on"]
        self.wiring, self.kinds = {}, {}
        for i in range(self.m):
            self.wiring[f"B{i + 1}"] = sorted(rng.sample(range(self.n), rng.randint(1, 3)))
            self.kinds[f"B{i + 1}"] = pick(rng, ["advance", "advance", "on", "off"])
        cyc = "off -> dim -> bright -> off" if self.three else "off -> on -> off"
        top = self.states[-1]
        kinds = {"advance": f"moves each of its {self.lamp}s one step along the cycle {cyc}",
                 "on": f"sets each of its {self.lamp}s to {top}", "off": f"sets each of its {self.lamp}s to off"}
        btn = "; ".join(f"{b} {kinds[self.kinds[b]]} ({', '.join(f'{self.lamp} {j + 1}' for j in w)})"
                        for b, w in self.wiring.items())
        self.rules = (f"World: {self.n} {self.lamp}s numbered 1 to {self.n}, each {' / '.join(self.states)}, and "
                      f"{self.m} buttons. Pressing a button: {btn}.")

    def sample_state(self, rng):
        return {"st": [rng.randrange(len(self.states)) for _ in range(self.n)]}

    def sample_action(self, rng, s):
        return {"b": pick(rng, list(self.wiring))}

    def step(self, s, a):
        st = s["st"][:]
        for j in self.wiring[a["b"]]:
            k = self.kinds[a["b"]]
            st[j] = (st[j] + 1) % len(self.states) if k == "advance" else (len(self.states) - 1 if k == "on" else 0)
        return {"st": st}, {"note": "done"}

    def render(self, s, events=None):
        return ", ".join(f"{self.lamp} {i + 1}: {self.states[x]}" for i, x in enumerate(s["st"]))

    def render_action(self, a):
        return f"press {a['b']}"

    def event_log(self, acts, events):
        return ""

    def ask(self, rng, s, events, qtype):
        if qtype == "state":
            j = rng.randrange(self.n)
            return qchoice(f"What state is {self.lamp} {j + 1} in?", [(x, x) for x in self.states]), self.states[s["st"][j]]
        if qtype == "same":
            a, b = rng.sample(range(self.n), 2)
            return qnoul(f"Are {self.lamp} {a + 1} and {self.lamp} {b + 1} in the same state?"), s["st"][a] == s["st"][b]
        if qtype == "count_on":
            n = sum(x != 0 for x in s["st"])
            return qchoice(f"How many {self.lamp}s are not off?", [(str(k), str(k)) for k in range(self.n + 1)]), str(n)
        raise KeyError(qtype)


class SeqOps(Base):
    family = "seq"
    QTYPES = ["head", "size", "failed", "contains"]
    HELD_Q = "contains"

    def __init__(self, rng):
        self.queue = rng.random() < 0.5
        self.cap = pick(rng, [None, 4, 5, 6])
        self.vals = pick(rng, [[str(i) for i in range(10)], list("PQRSTUVW"), ["red", "green", "blue", "gold"]])
        self.name = pick(rng, ["line", "pile", "tray", "list"])
        end = "front" if self.queue else "top"
        self.end = end
        self.rules = (f"World: a {self.name} of items, written from {'front to back' if self.queue else 'bottom to top'}. "
                      f"'add x' puts x at the {'back' if self.queue else 'top'}; 'take' removes the item at the {end}; "
                      f"'copy' adds a copy of the {end} item at the {'back' if self.queue else 'top'}; 'turn' "
                      + ("moves the front item to the back." if self.queue else "exchanges the top two items.")
                      + (f" The {self.name} holds at most {self.cap} items: adding to a full one fails." if self.cap else "")
                      + " An action that needs more items than there are fails and changes nothing.")

    def sample_state(self, rng):
        return {"xs": [rng.choice(self.vals) for _ in range(rng.randint(0, min(4, self.cap or 4)))]}

    def sample_action(self, rng, s):
        op = pick(rng, ["add", "add", "take", "copy", "turn"])
        return {"op": op, "x": rng.choice(self.vals)} if op == "add" else {"op": op}

    def step(self, s, a):
        xs = s["xs"][:]
        op = a["op"]
        head = (lambda: xs[0]) if self.queue else (lambda: xs[-1])
        fail = ({"xs": xs}, {"failed": True, "note": "failed"})
        if op in ("add", "copy"):
            if self.cap and len(xs) >= self.cap or (op == "copy" and not xs):
                return fail
            xs.append(a["x"] if op == "add" else head())
        elif op == "take":
            if not xs:
                return fail
            xs.pop(0 if self.queue else -1)
        else:
            if len(xs) < (1 if self.queue else 2):
                return fail
            if self.queue:
                xs.append(xs.pop(0))
            else:
                xs[-1], xs[-2] = xs[-2], xs[-1]
        return {"xs": xs}, {"failed": False, "note": "done"}

    def render(self, s, events=None):
        return f"{self.name.capitalize()}: " + (" ".join(s["xs"]) if s["xs"] else "(empty)")

    def render_action(self, a):
        return f"add {a['x']}" if a["op"] == "add" else a["op"]

    def ask(self, rng, s, events, qtype):
        if qtype == "head":
            g = (s["xs"][0] if self.queue else s["xs"][-1]) if s["xs"] else "empty"
            return qchoice(f"Which item is at the {self.end}?", [(v, v) for v in self.vals] + [("empty", "nothing, it is empty")]), g
        if qtype == "size":
            return qchoice("How many items are there?", [(str(k), str(k)) for k in range(9)]), str(min(8, len(s["xs"])))
        if qtype == "failed":
            return qnoul("Did at least one action fail?"), any(e["failed"] for e in events)
        if qtype == "contains":
            x = rng.choice(s["xs"] if s["xs"] and rng.random() < 0.5 else self.vals)
            return qnoul(f"Is there at least one {x} in the {self.name}?"), x in s["xs"]
        raise KeyError(qtype)


class Jugs(Base):
    family = "jugs"
    QTYPES = ["amount", "full", "empty", "total"]
    HELD_Q = "total"

    def __init__(self, rng):
        self.names = pick(rng, ["A", "B", "C"] if rng.random() < 0.5 else ["red", "green", "blue"], rng.randint(2, 3))
        self.cap = {x: rng.randint(3, 10) for x in self.names}
        self.liq = pick(rng, ["water", "oil", "juice", "sand"])
        self.rules = (f"World: containers {', '.join(f'{x} (holds {self.cap[x]} liters)' for x in self.names)} of "
                      f"{self.liq}. 'fill X' fills X to the top; 'empty X' empties X; 'pour X into Y' moves {self.liq} "
                      "from X to Y until X is empty or Y is full, whichever comes first.")

    def sample_state(self, rng):
        return {"v": {x: rng.randint(0, self.cap[x]) for x in self.names}}

    def sample_action(self, rng, s):
        k = rng.random()
        if k < 0.25:
            return {"op": "fill", "x": pick(rng, self.names)}
        if k < 0.45:
            return {"op": "empty", "x": pick(rng, self.names)}
        x, y = rng.sample(self.names, 2)
        return {"op": "pour", "x": x, "y": y}

    def step(self, s, a):
        v = dict(s["v"])
        if a["op"] == "fill":
            v[a["x"]] = self.cap[a["x"]]
        elif a["op"] == "empty":
            v[a["x"]] = 0
        else:
            m = min(v[a["x"]], self.cap[a["y"]] - v[a["y"]])
            v[a["x"]] -= m
            v[a["y"]] += m
        return {"v": v}, {"note": "done"}

    def render(self, s, events=None):
        return ", ".join(f"{x}: {s['v'][x]} of {self.cap[x]} liters" for x in self.names)

    def render_action(self, a):
        return f"pour {a['x']} into {a['y']}" if a["op"] == "pour" else f"{a['op']} {a['x']}"

    def event_log(self, acts, events):
        return ""

    def ask(self, rng, s, events, qtype):
        if qtype == "amount":
            x = pick(rng, self.names)
            return qchoice(f"How many liters are in {x}?", [(str(k), f"{k} liters") for k in range(self.cap[x] + 1)]), str(s["v"][x])
        if qtype == "full":
            x = pick(rng, self.names)
            return qnoul(f"Is {x} full?"), s["v"][x] == self.cap[x]
        if qtype == "empty":
            x = pick(rng, self.names)
            return qnoul(f"Is {x} empty?"), s["v"][x] == 0
        if qtype == "total":
            g = sum(s["v"].values())
            return qchoice(f"How many liters are there in all?", [(v, f"{v} liters") for v in numeric_options(g, 0, 40, 10)]), str(g)
        raise KeyError(qtype)


class Crafting(Base):
    family = "craft"
    QTYPES = ["count", "failed", "can_make"]
    HELD_Q = "can_make"

    def __init__(self, rng):
        self.mats = pick(rng, ["wood", "stone", "iron", "cloth", "nails", "glass", "rope"], 3)
        self.prods = pick(rng, ["chair", "table", "shelf", "lamp", "boat", "box"], 2)
        self.rec = {}
        for p in self.prods:
            need = pick(rng, self.mats, 2)
            self.rec[p] = {need[0]: rng.randint(1, 3), need[1]: rng.randint(1, 3)}
        r = "; ".join(f"a {p} needs " + " and ".join(f"{n} {m}" for m, n in need.items()) for p, need in self.rec.items())
        self.rules = (f"World: an inventory of {', '.join(self.mats + self.prods)}. 'gather n M' adds n of material M. "
                      f"'make P' uses up the materials of the recipe and adds one P; if any material is short, it fails "
                      f"and nothing changes. Recipes: {r}.")

    def sample_state(self, rng):
        inv = {m: rng.randint(0, 5) for m in self.mats}
        inv.update({p: rng.randint(0, 2) for p in self.prods})
        return {"inv": inv}

    def sample_action(self, rng, s):
        return {"op": "make", "p": pick(rng, self.prods)} if rng.random() < 0.55 else \
            {"op": "gather", "m": pick(rng, self.mats), "n": rng.randint(1, 3)}

    def step(self, s, a):
        inv = dict(s["inv"])
        if a["op"] == "gather":
            inv[a["m"]] += a["n"]
            return {"inv": inv}, {"failed": False, "note": "done"}
        need = self.rec[a["p"]]
        if any(inv[m] < n for m, n in need.items()):
            return {"inv": inv}, {"failed": True, "note": "failed"}
        for m, n in need.items():
            inv[m] -= n
        inv[a["p"]] += 1
        return {"inv": inv}, {"failed": False, "note": "done"}

    def render(self, s, events=None):
        return "Inventory: " + ", ".join(f"{k} {v}" for k, v in s["inv"].items())

    def render_action(self, a):
        return f"make {a['p']}" if a["op"] == "make" else f"gather {a['n']} {a['m']}"

    def ask(self, rng, s, events, qtype):
        if qtype == "count":
            k = pick(rng, self.mats + self.prods)
            return qchoice(f"How many {k} are in the inventory?", [(str(i), str(i)) for i in range(16)]), str(min(15, s["inv"][k]))
        if qtype == "failed":
            j = rng.randrange(len(events))
            return qnoul(f"Did action {j + 1} fail?"), events[j]["failed"]
        if qtype == "can_make":
            p = pick(rng, self.prods)
            return qnoul(f"Are there enough materials right now to make a {p}?"), \
                all(s["inv"][m] >= n for m, n in self.rec[p].items())
        raise KeyError(qtype)


# ============================================================================================== VAL families
class Track(Base):
    family = "track"
    QTYPES = ["pos", "at_end", "blocked"]

    def __init__(self, rng):
        self.n = rng.randint(6, 12)
        self.closed = set(rng.sample(range(2, self.n), rng.randint(0, 2)))
        self.bounce = rng.random() < 0.4
        self.car = pick(rng, ["elevator", "train", "cart"])
        self.unit = "floor" if self.car == "elevator" else "stop"
        art = "an" if self.car[0] in "aeiou" else "a"
        self.rules = (f"World: {art} {self.car} on {self.unit}s 1 to {self.n}. 'up k' and 'down k' move it k {self.unit}s. "
                      + (f"Closed {self.unit}s ({', '.join(str(c) for c in sorted(self.closed))}) are skipped: they do not "
                         "count as steps. " if self.closed else "")
                      + ("At an end it turns around and keeps moving the remaining steps the other way." if self.bounce
                         else "It stops at an end even if steps remain."))

    def sample_state(self, rng):
        return {"p": rng.choice([x for x in range(1, self.n + 1) if x not in self.closed])}

    def sample_action(self, rng, s):
        return {"d": pick(rng, ["up", "down"]), "k": rng.randint(1, 4)}

    def step(self, s, a):
        p, d, left, hit = s["p"], 1 if a["d"] == "up" else -1, a["k"], False
        while left > 0:
            q = p + d
            while 1 <= q <= self.n and q in self.closed:
                q += d
            if not 1 <= q <= self.n:
                hit = True
                if self.bounce:
                    d = -d
                    continue
                break
            p, left = q, left - 1
        return {"p": p}, {"blocked": hit and not self.bounce, "note": "stopped at an end" if hit and not self.bounce else "done"}

    def render(self, s, events=None):
        return f"The {self.car} is at {self.unit} {s['p']}."

    def render_action(self, a):
        return f"{a['d']} {a['k']}"

    def ask(self, rng, s, events, qtype):
        if qtype == "pos":
            return qchoice(f"At which {self.unit} is the {self.car}?", [(str(k), f"{self.unit} {k}") for k in range(1, self.n + 1)]), str(s["p"])
        if qtype == "at_end":
            return qnoul(f"Is the {self.car} at {self.unit} 1 or {self.unit} {self.n}?"), s["p"] in (1, self.n)
        if qtype == "blocked":
            return qnoul(f"Did the {self.car} stop early at an end in any action?"), any(e["blocked"] for e in events)
        raise KeyError(qtype)


class Tally(Base):
    family = "tally"
    QTYPES = ["count", "leader", "changed"]

    def __init__(self, rng):
        self.opts = pick(rng, ["pizza", "tacos", "sushi", "salad", "curry"], rng.randint(2, 4))
        self.voters = pick(rng, ["Ana", "Bo", "Cy", "Di", "Ed", "Flo", "Gus"], rng.randint(3, 6))
        self.rules = (f"World: a vote among {', '.join(self.opts)} by {', '.join(self.voters)}. Each person has at most "
                      "one vote: voting again replaces their previous vote; 'withdraw' removes their vote.")

    def sample_state(self, rng):
        return {"v": {p: rng.choice(self.opts + [None]) for p in self.voters}}

    def sample_action(self, rng, s):
        p = pick(rng, self.voters)
        return {"p": p, "o": None} if rng.random() < 0.2 else {"p": p, "o": pick(rng, self.opts)}

    def step(self, s, a):
        v = dict(s["v"])
        changed = v[a["p"]] != a["o"]
        v[a["p"]] = a["o"]
        return {"v": v}, {"changed": changed, "note": "done"}

    def render(self, s, events=None):
        return "Votes: " + ", ".join(f"{p} {o or 'none'}" for p, o in s["v"].items())

    def render_action(self, a):
        return f"{a['p']} withdraws" if a["o"] is None else f"{a['p']} votes {a['o']}"

    def event_log(self, acts, events):
        return ""

    def ask(self, rng, s, events, qtype):
        cnt = collections.Counter(o for o in s["v"].values() if o)
        if qtype == "count":
            o = pick(rng, self.opts)
            return qchoice(f"How many votes does {o} have?", [(str(k), str(k)) for k in range(len(self.voters) + 1)]), str(cnt[o])
        if qtype == "leader":
            best = max(cnt.values(), default=0)
            tops = [o for o in self.opts if cnt[o] == best and best > 0]
            g = tops[0] if len(tops) == 1 else "tie"
            return qchoice("Which option has the most votes?", [(o, o) for o in self.opts] + [("tie", "a tie, or no votes")]), g
        if qtype == "changed":
            p = pick(rng, self.voters)
            return qnoul(f"Does {p} currently have a vote?"), s["v"][p] is not None
        raise KeyError(qtype)


# ============================================================================================== TEST families
class Cards(Base):
    family = "cards"
    QTYPES = ["at", "where", "left_of"]

    def __init__(self, rng):
        self.n = rng.randint(4, 7)
        self.labels = pick(rng, [list("PQRSTUV"), ["ace", "king", "queen", "jack", "ten", "nine", "eight"]])[:self.n]
        self.rules = (f"World: {self.n} cards in a row, positions 1 to {self.n} from left to right. 'swap i j' exchanges "
                      "the cards at positions i and j; 'reverse i j' reverses the order of the cards from position i to "
                      "position j; 'shift' moves the leftmost card to the right end.")

    def sample_state(self, rng):
        xs = self.labels[:]
        rng.shuffle(xs)
        return {"xs": xs}

    def sample_action(self, rng, s):
        k = rng.random()
        i, j = sorted(rng.sample(range(1, self.n + 1), 2))
        return {"op": "swap", "i": i, "j": j} if k < 0.45 else ({"op": "reverse", "i": i, "j": j} if k < 0.8 else {"op": "shift"})

    def step(self, s, a):
        xs = s["xs"][:]
        if a["op"] == "swap":
            xs[a["i"] - 1], xs[a["j"] - 1] = xs[a["j"] - 1], xs[a["i"] - 1]
        elif a["op"] == "reverse":
            xs[a["i"] - 1:a["j"]] = xs[a["i"] - 1:a["j"]][::-1]
        else:
            xs.append(xs.pop(0))
        return {"xs": xs}, {"note": "done"}

    def render(self, s, events=None):
        return "Row, left to right: " + " ".join(s["xs"])

    def render_action(self, a):
        return a["op"] if a["op"] == "shift" else f"{a['op']} {a['i']} {a['j']}"

    def event_log(self, acts, events):
        return ""

    def ask(self, rng, s, events, qtype):
        if qtype == "at":
            k = rng.randrange(self.n)
            return qchoice(f"Which card is at position {k + 1}?", [(x, x) for x in self.labels]), s["xs"][k]
        if qtype == "where":
            x = pick(rng, self.labels)
            return qchoice(f"At which position is the {x}?", [(str(k), f"position {k}") for k in range(1, self.n + 1)]), str(s["xs"].index(x) + 1)
        if qtype == "left_of":
            a, b = rng.sample(self.labels, 2)
            return qnoul(f"Is the {a} somewhere to the left of the {b}?"), s["xs"].index(a) < s["xs"].index(b)
        raise KeyError(qtype)


class Timers(Base):
    family = "timers"
    QTYPES = ["done", "left", "n_done"]

    def __init__(self, rng):
        self.tasks = pick(rng, ["bread", "rice", "tea", "eggs", "soup", "cake"], rng.randint(2, 4))
        self.rules = ("World: kitchen timers. A running timer counts down one per minute; when it reaches 0 the dish is "
                      "done and stays done. 'wait k' lets k minutes pass; 'pause X' stops X's timer; 'start X' makes X's "
                      "timer run again. Paused timers do not count down.")

    def sample_state(self, rng):
        return {"left": {t: rng.randint(1, 9) for t in self.tasks}, "run": {t: rng.random() < 0.7 for t in self.tasks}}

    def sample_action(self, rng, s):
        k = rng.random()
        if k < 0.55:
            return {"op": "wait", "k": rng.randint(1, 5)}
        return {"op": "pause" if k < 0.78 else "start", "x": pick(rng, self.tasks)}

    def step(self, s, a):
        left, run = dict(s["left"]), dict(s["run"])
        if a["op"] == "wait":
            for t in self.tasks:
                if run[t]:
                    left[t] = max(0, left[t] - a["k"])
        else:
            run[a["x"]] = a["op"] == "start"
        return {"left": left, "run": run}, {"note": "done"}

    def render(self, s, events=None):
        return "Timers: " + ", ".join(f"{t} {s['left'][t]} min left ({'running' if s['run'][t] else 'paused'})" if s["left"][t]
                                      else f"{t} done" for t in self.tasks)

    def render_action(self, a):
        return f"wait {a['k']}" if a["op"] == "wait" else f"{a['op']} {a['x']}"

    def event_log(self, acts, events):
        return ""

    def ask(self, rng, s, events, qtype):
        if qtype == "done":
            t = pick(rng, self.tasks)
            return qnoul(f"Is the {t} done?"), s["left"][t] == 0
        if qtype == "left":
            t = pick(rng, self.tasks)
            return qchoice(f"How many minutes are left for the {t}?", [(str(k), f"{k} minutes") for k in range(10)]), str(s["left"][t])
        if qtype == "n_done":
            return qchoice("How many dishes are done?", [(str(k), str(k)) for k in range(len(self.tasks) + 1)]), \
                str(sum(v == 0 for v in s["left"].values()))
        raise KeyError(qtype)


class Machines(Base):
    family = "machines"
    QTYPES = ["state", "n_in", "same"]

    def __init__(self, rng):
        pool = pick(rng, [["green", "yellow", "red"], ["idle", "warming", "running", "cooling"], ["low", "mid", "high"],
                          ["closed", "opening", "open", "closing"]])
        self.cycle = pool[:]
        rng.shuffle(self.cycle)
        self.devs = pick(rng, ["M1", "M2", "M3", "M4", "M5"], rng.randint(3, 5))
        self.rules = ("World: devices " + ", ".join(self.devs) + ". Each is in one state of the cycle "
                      + " -> ".join(self.cycle + [self.cycle[0]]) + ". 'tick' moves every device one step along the "
                      "cycle; 'tick D' moves only D; 'reset D' puts D back to " + self.cycle[0] + ".")

    def sample_state(self, rng):
        return {"st": {d: rng.randrange(len(self.cycle)) for d in self.devs}}

    def sample_action(self, rng, s):
        k = rng.random()
        return {"op": "tick"} if k < 0.35 else {"op": "tick1" if k < 0.75 else "reset", "d": pick(rng, self.devs)}

    def step(self, s, a):
        st = dict(s["st"])
        if a["op"] == "tick":
            st = {d: (v + 1) % len(self.cycle) for d, v in st.items()}
        elif a["op"] == "tick1":
            st[a["d"]] = (st[a["d"]] + 1) % len(self.cycle)
        else:
            st[a["d"]] = 0
        return {"st": st}, {"note": "done"}

    def render(self, s, events=None):
        return "Devices: " + ", ".join(f"{d} {self.cycle[v]}" for d, v in s["st"].items())

    def render_action(self, a):
        return "tick" if a["op"] == "tick" else (f"tick {a['d']}" if a["op"] == "tick1" else f"reset {a['d']}")

    def event_log(self, acts, events):
        return ""

    def ask(self, rng, s, events, qtype):
        if qtype == "state":
            d = pick(rng, self.devs)
            return qchoice(f"In which state is {d}?", [(x, x) for x in self.cycle]), self.cycle[s["st"][d]]
        if qtype == "n_in":
            x = pick(rng, self.cycle)
            return qchoice(f"How many devices are {x}?", [(str(k), str(k)) for k in range(len(self.devs) + 1)]), \
                str(sum(self.cycle[v] == x for v in s["st"].values()))
        if qtype == "same":
            a, b = rng.sample(self.devs, 2)
            return qnoul(f"Are {a} and {b} in the same state?"), s["st"][a] == s["st"][b]
        raise KeyError(qtype)


TRAIN = [GridMove, Gravity, Counters, Toggles, SeqOps, Jugs, Crafting]
VAL = [Track, Tally]
TEST = [Cards, Timers, Machines]


def fbalanced(fam, steps, qtype, rng, n, change_balance=False):
    """n examples of a family, each from a NEW world, with the answers spread out (yes/no about half each, no choice
    answer above 40%). change_balance: at most half of the examples whose initial-state answer is defined keep that
    answer and at most half change it, so "nothing changes" is not a winning shortcut."""
    out, counts, chg, tries = [], collections.Counter(), collections.Counter(), 0
    while len(out) < n and tries < n * (400 if change_balance else 80):
        tries += 1
        w = fam(rng)
        w.name = fam.family
        ex = make_example(w, steps, qtype, rng)
        g = ex["gold"]
        cap = (n + 1) // 2 if ex["question"]["type"] == "noul" else max(2, int(0.4 * n))
        if counts[g] >= cap:
            continue
        if change_balance and ex.get("known0"):
            c = ex["gold0"] != g
            if chg[c] >= (n + 1) // 2:
                continue
            chg[c] += 1
        counts[g] += 1
        out.append(ex)
    return out
