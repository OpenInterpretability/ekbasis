"""World factory 3: every action is a SCOPE times an EFFECT, so worlds have actions that change many objects at once.

Scopes: one object ('verb X'), every object, every object that has a flag, every object in a given cycle state, every
object whose quantity is at least t; plus row operations on a row of distinct items (swap two positions, move the first
item to the end or the last to the front, rotate by k, reverse the whole row, reverse a stretch, move one item to the
front or the end). Effects: add k, take k, set v, double, cycle forward, cycle reset, flip, flag on, flag off.

HELD scope x effect pairs never appear in training worlds; test worlds that use them check whether the model composes a
scope and an effect it only saw apart. They mirror the multi-object actions of the hand-made test families
(every device ticks / running timers count down / reverse cards i..j), in other words and other worlds.

FRESH: three hand-made families written before any training on this factory and not changed after, to test the factory
on worlds nobody tuned anything on (a line of people, savings accounts, a strip of lamps). Interface as worldgen.py."""
from __future__ import annotations

import collections

from envs import make_example, numeric_options, qchoice, qnoul
from worldgen import Base, pick

SKINS = [("tank", "level", "liters"), ("account", "balance", "coins"), ("plant", "height", "cm"),
         ("robot", "charge", "units"), ("shelf", "stock", "boxes"), ("jar", "count", "marbles"),
         ("player", "score", "points"), ("battery", "charge", "bars")]
NAMES = [["A", "B", "C", "D", "E"], ["north", "south", "east", "west", "center"], ["Ana", "Bo", "Cy", "Di", "Ed"],
         ["P1", "P2", "P3", "P4", "P5"], ["alpha", "beta", "gamma", "delta", "omega"]]
CYCLES = [["idle", "busy", "done"], ["low", "mid", "high"], ["new", "used", "worn", "broken"], ["seed", "sprout", "bloom"],
          ["cold", "warm", "hot", "boiling"]]
FLAGS = [("locked", "unlocked"), ("on", "off"), ("open", "closed"), ("armed", "disarmed"), ("active", "asleep")]
ROWS = [("books", "book", "on a shelf", list("PQRSTUV")), ("people", "person", "in a line", ["Ann", "Ben", "Cal", "Dee", "Eve", "Fay", "Gus"]),
        ("songs", "song", "in a playlist", ["S1", "S2", "S3", "S4", "S5", "S6", "S7"]),
        ("cars", "car", "in a train", ["coal", "mail", "grain", "oil", "wood", "milk", "salt"])]
VERBS = ["feed", "boost", "tap", "turn", "cut", "mix", "shift", "stamp", "pulse", "sweep", "fold", "kick", "spin",
         "nudge", "blend", "flash", "drift", "stir", "hop", "poke"]
VALUE_EFF = ["add", "take", "set", "double"]
CYC_EFF = ["cyc_next", "cyc_reset"]
FLAG_EFF = ["flip", "flag_on", "flag_off"]
ROW_OPS = ["swap", "shift", "shift_back", "rot_k", "reverse_all", "rev_range", "move_front", "move_back"]
HELD = {("all", "cyc_next"), ("flagged", "take"), ("row", "rev_range")}


class Mech3:
    family = "mech3"
    HELD_Q = None

    def __init__(self, rng, held_mode="exclude"):
        """held_mode: "exclude" (no held pair in the world), "require" (at least one), "any"."""
        for _ in range(500):
            self._sample(rng)
            used = self.used & HELD
            if held_mode == "any" or (held_mode == "exclude" and not used) or (held_mode == "require" and used):
                break
        else:
            raise RuntimeError("could not sample a world")
        self.name = "mech3"
        self.QTYPES = ["value", "compare", "count_zero", "count_atleast"] \
            + (["state", "count_state", "same_state"] if self.cyc else []) + (["flag"] if self.flag else []) \
            + (["row_at", "row_where", "row_left_of"] if self.row else []) + (["failed"] if self.can_fail else [])

    # ------------------------------------------------------------------ sampling a world
    def _sample(self, rng):
        self.obj, self.attr, self.unit = pick(rng, SKINS)
        self.names = pick(rng, NAMES)[:rng.randint(3, 5)]
        self.cap = pick(rng, [None, 10, 12, 15, 20])
        self.floor_fail = rng.random() < 0.5
        self.cyc = None
        if rng.random() < 0.5:
            self.cyc = pick(rng, CYCLES)[:]
            rng.shuffle(self.cyc)
        self.flag = pick(rng, FLAGS) if rng.random() < 0.5 else None
        self.row = None
        if rng.random() < 0.35:
            plural, single, where, pool = pick(rng, ROWS)
            n = rng.randint(4, 7)
            self.row = {"plural": plural, "single": single, "where": where, "items": pool[:n]}
        effects = VALUE_EFF + (CYC_EFF if self.cyc else []) + (FLAG_EFF if self.flag else [])
        scopes = ["all", "atleast"] + (["flagged"] if self.flag else []) + (["instate"] if self.cyc else [])
        self.actions, self.used, self.can_fail = [], set(), False
        for verb in rng.sample(VERBS, rng.randint(3, 5)):
            if self.row and rng.random() < 0.4:
                op = pick(rng, ROW_OPS)
                act = {"verb": verb, "scope": "row", "eff": op}
            else:
                eff = pick(rng, effects)
                scope = "one" if rng.random() < 0.35 else pick(rng, scopes)
                act = {"verb": verb, "scope": scope, "eff": eff, "k": rng.randint(1, 4), "v": rng.randint(0, 9), "guard": None}
                if scope == "flagged":
                    act["cond"] = self.flag[0]
                elif scope == "instate":
                    act["cond"] = pick(rng, self.cyc)
                elif scope == "atleast":
                    act["cond"] = rng.randint(2, 7)
                if scope == "one" and rng.random() < 0.2:
                    g = pick(rng, ["min"] + (["state"] if self.cyc else []) + (["flag"] if self.flag else []))
                    act["guard"] = (g, rng.randint(1, 5) if g == "min" else (pick(rng, self.cyc) if g == "state" else self.flag[0]))
                    self.can_fail = True
                if eff == "take" and self.floor_fail:
                    self.can_fail = True
            self.used.add((act["scope"], act["eff"]))
            self.actions.append(act)
        self.trig = None
        if rng.random() < 0.2:
            self.trig = (rng.randint(6, 12), pick(rng, ["reset", "half"] + (["cycle"] if self.cyc else [])))
        self.rules = self._write_rules()

    def _target(self, act):
        o, a = self.obj, self.attr
        cond = {"all": "", "flagged": f" that is {act.get('cond')}", "instate": f" whose state is {act.get('cond')}",
                "atleast": f" whose {a} is at least {act.get('cond')}"}.get(act["scope"], "")
        return cond

    def _write_rules(self):
        o, a, u = self.obj, self.attr, self.unit
        lines = [f"World: {o}s {', '.join(self.names)}. Each {o} has a {a} (a whole number of {u})"
                 + (f" and a state from the cycle {' -> '.join(self.cyc + [self.cyc[0]])}" if self.cyc else "")
                 + (f" and is either {self.flag[0]} or {self.flag[1]}" if self.flag else "") + "."]
        if self.row:
            r = self.row
            lines.append(f"There is also a row of {len(r['items'])} {r['plural']} {r['where']}, positions 1 to "
                         f"{len(r['items'])} from left to right.")
        if self.cap:
            lines.append(f"No {a} can go above {self.cap}: anything above {self.cap} is lost.")
        lines.append(f"An action that would take a {a} below 0 " + (
            f"fails and changes nothing (when it acts on several {o}s, nothing changes for any of them)."
            if self.floor_fail else "stops it at 0 instead."))
        if any(act["scope"] not in ("one", "row") for act in self.actions):
            lines.append(f"An action on several {o}s changes all of them at once, based on the state before the "
                         f"action; if no {o} matches, nothing happens.")
        for act in self.actions:
            v = act["verb"]
            if act["scope"] == "row":
                s, p = self.row["single"], self.row["plural"]
                body = {"swap": f"'{v} i j' exchanges the {p} at positions i and j",
                        "shift": f"'{v}' moves the first {s} to the end of the row",
                        "shift_back": f"'{v}' moves the last {s} to the front of the row",
                        "rot_k": f"'{v} k' moves the first k {p} to the end of the row, keeping their order",
                        "reverse_all": f"'{v}' reverses the order of the whole row",
                        "rev_range": f"'{v} i j' reverses the order of the {p} from position i to position j",
                        "move_front": f"'{v} i' takes the {s} at position i and puts that {s} at the front of the row",
                        "move_back": f"'{v} i' takes the {s} at position i and puts that {s} at the end of the row"}[act["eff"]]
                lines.append(body + ".")
                continue
            one = act["scope"] == "one"
            who = "X" if one else f"every {o}{self._target(act)}"
            whos = "X's" if one else f"the {{}} of every {o}{self._target(act)}"
            k, val = act["k"], min(act["v"], self.cap or 99)
            eff = act["eff"]
            if eff in VALUE_EFF:
                body = {"add": f"adds {k} to " + (f"X's {a}" if one else whos.format(a)),
                        "take": f"takes {k} from " + (f"X's {a}" if one else whos.format(a)),
                        "set": "sets " + (f"X's {a}" if one else whos.format(a)) + f" to {val}",
                        "double": "doubles " + (f"X's {a}" if one else whos.format(a))}[eff]
            elif eff in CYC_EFF:
                tgt = "X's state" if one else whos.format("state")
                body = f"moves {tgt} one step forward in the cycle" if eff == "cyc_next" else f"puts {tgt} back to {self.cyc[0]}"
            else:
                body = {"flip": f"switches {who} between {self.flag[0]} and {self.flag[1]}",
                        "flag_on": f"makes {who} {self.flag[0]}", "flag_off": f"makes {who} {self.flag[1]}"}[eff]
            g = act["guard"]
            cond = ""
            if g:
                cond = {"min": f", but only if X's {a} is at least {g[1]}", "state": f", but only if X's state is {g[1]}",
                        "flag": f", but only if X is {g[1]}"}[g[0]] + " (otherwise it fails and changes nothing)"
            lines.append(f"'{v}{' X' if one else ''}' {body}{cond}.")
        if self.trig:
            t, kind = self.trig
            what = {"reset": f"its {a} goes back to 0", "half": f"its {a} is halved (rounding down)",
                    "cycle": "its state moves one step forward in the cycle"}[kind]
            lines.append(f"After every action, each {o} whose {a} is {t} or more is changed: {what}.")
        return " ".join(lines)

    # ------------------------------------------------------------------ simulation
    def sample_state(self, rng):
        hi = min(9, self.cap or 9)
        st = {"v": {n: rng.randint(0, hi) for n in self.names}}
        if self.cyc:
            st["c"] = {n: rng.randrange(len(self.cyc)) for n in self.names}
        if self.flag:
            st["f"] = {n: rng.random() < 0.5 for n in self.names}
        if self.row:
            xs = self.row["items"][:]
            rng.shuffle(xs)
            st["r"] = xs
        return st

    def sample_action(self, rng, s):
        i = rng.randrange(len(self.actions))
        act = self.actions[i]
        a = {"i": i}
        if act["scope"] == "one":
            a["x"] = pick(rng, self.names)
        elif act["scope"] == "row":
            n = len(self.row["items"])
            if act["eff"] in ("swap", "rev_range"):
                a["p"], a["q"] = sorted(rng.sample(range(1, n + 1), 2))
            elif act["eff"] in ("move_front", "move_back"):
                a["p"] = rng.randint(1, n)
            elif act["eff"] == "rot_k":
                a["p"] = rng.randint(1, n - 1)
        return a

    def _clip(self, x):
        return min(x, self.cap) if self.cap else x

    def _has(self, s, n, act):
        sc = act["scope"]
        return (sc == "all" or (sc == "flagged" and s["f"][n]) or (sc == "instate" and self.cyc[s["c"][n]] == act["cond"])
                or (sc == "atleast" and s["v"][n] >= act["cond"]))

    def step(self, s, a):
        st = {k: (dict(v) if isinstance(v, dict) else list(v)) for k, v in s.items()}
        act = self.actions[a["i"]]
        fail = (s, {"failed": True, "note": "failed"})
        if act["scope"] == "row":
            xs, op = st["r"], act["eff"]
            if op == "swap":
                xs[a["p"] - 1], xs[a["q"] - 1] = xs[a["q"] - 1], xs[a["p"] - 1]
            elif op == "shift":
                xs.append(xs.pop(0))
            elif op == "shift_back":
                xs.insert(0, xs.pop())
            elif op == "rot_k":
                st["r"] = xs[a["p"]:] + xs[:a["p"]]
            elif op == "reverse_all":
                xs.reverse()
            elif op == "rev_range":
                xs[a["p"] - 1:a["q"]] = xs[a["p"] - 1:a["q"]][::-1]
            elif op == "move_front":
                xs.insert(0, xs.pop(a["p"] - 1))
            elif op == "move_back":
                xs.append(xs.pop(a["p"] - 1))
        else:
            if act["scope"] == "one":
                tg = [a["x"]]
                g = act["guard"]
                x = a["x"]
                if g and ((g[0] == "min" and s["v"][x] < g[1]) or (g[0] == "state" and self.cyc[s["c"][x]] != g[1])
                          or (g[0] == "flag" and not s["f"][x])):
                    return fail
            else:
                tg = [n for n in self.names if self._has(s, n, act)]
            eff, k = act["eff"], act["k"]
            if eff == "take":
                new = {n: s["v"][n] - k for n in tg}
                if any(v < 0 for v in new.values()):
                    if self.floor_fail:
                        return fail
                    new = {n: max(0, v) for n, v in new.items()}
                st["v"].update(new)
            for n in tg:
                if eff == "add":
                    st["v"][n] = self._clip(s["v"][n] + k)
                elif eff == "set":
                    st["v"][n] = self._clip(act["v"])
                elif eff == "double":
                    st["v"][n] = self._clip(s["v"][n] * 2)
                elif eff == "cyc_next":
                    st["c"][n] = (s["c"][n] + 1) % len(self.cyc)
                elif eff == "cyc_reset":
                    st["c"][n] = 0
                elif eff == "flip":
                    st["f"][n] = not s["f"][n]
                elif eff == "flag_on":
                    st["f"][n] = True
                elif eff == "flag_off":
                    st["f"][n] = False
        if self.trig:
            t, kind = self.trig
            for n in self.names:
                if st["v"][n] >= t:
                    if kind == "reset":
                        st["v"][n] = 0
                    elif kind == "half":
                        st["v"][n] //= 2
                    else:
                        st["c"][n] = (st["c"][n] + 1) % len(self.cyc)
        return st, {"failed": False, "note": "done"}

    # ------------------------------------------------------------------ text and questions
    def render(self, s, events=None):
        parts = []
        for n in self.names:
            t = f"{n}: {self.attr} {s['v'][n]}"
            if self.cyc:
                t += f", state {self.cyc[s['c'][n]]}"
            if self.flag:
                t += f", {self.flag[0] if s['f'][n] else self.flag[1]}"
            parts.append(t)
        out = "; ".join(parts)
        if self.row:
            out += f"\nRow of {self.row['plural']}, left to right: " + " ".join(s["r"])
        return out

    def render_action(self, a):
        act = self.actions[a["i"]]
        if act["scope"] == "one":
            return f"{act['verb']} {a['x']}"
        if act["scope"] == "row" and "q" in a:
            return f"{act['verb']} {a['p']} {a['q']}"
        if act["scope"] == "row" and "p" in a:
            return f"{act['verb']} {a['p']}"
        return act["verb"]

    def floor_note(self):
        return "The questions are about the state after all these actions."

    def ceiling_note(self):
        return "This is the state after all the actions."

    def event_log(self, acts, events):
        if not self.can_fail:
            return ""
        return "What happened: " + "; ".join(f"action {i + 1} ({self.render_action(a)}): {e['note']}"
                                             for i, (a, e) in enumerate(zip(acts, events))) + "."

    def ask(self, rng, s, events, qtype):
        o, a, N = self.obj, self.attr, self.names
        if qtype == "value":
            n = pick(rng, N)
            g = s["v"][n]
            return qchoice(f"What is {n}'s {a}?", [(x, x) for x in numeric_options(g, 0, max(40, g + 10), 10)]), str(g)
        if qtype == "compare":
            x, y = rng.sample(N, 2)
            return qnoul(f"Is {x}'s {a} greater than {y}'s?"), s["v"][x] > s["v"][y]
        if qtype == "total":
            g = sum(s["v"].values())
            return qchoice(f"What is the total {a} of all the {o}s?", [(x, x) for x in numeric_options(g, 0, max(120, g + 10), 10)]), str(g)
        if qtype == "count_zero":
            return qchoice(f"How many {o}s have {a} 0?", [(str(k), str(k)) for k in range(len(N) + 1)]), \
                str(sum(v == 0 for v in s["v"].values()))
        if qtype == "count_atleast":
            t = rng.randint(2, 8)
            return qchoice(f"How many {o}s have {a} {t} or more?", [(str(k), str(k)) for k in range(len(N) + 1)]), \
                str(sum(v >= t for v in s["v"].values()))
        if qtype == "state":
            n = pick(rng, N)
            return qchoice(f"In which state is {n}?", [(x, x) for x in self.cyc]), self.cyc[s["c"][n]]
        if qtype == "count_state":
            c = pick(rng, self.cyc)
            return qchoice(f"How many {o}s are in state {c}?", [(str(k), str(k)) for k in range(len(N) + 1)]), \
                str(sum(self.cyc[v] == c for v in s["c"].values()))
        if qtype == "same_state":
            x, y = rng.sample(N, 2)
            return qnoul(f"Are {x} and {y} in the same state?"), s["c"][x] == s["c"][y]
        if qtype == "flag":
            n = pick(rng, N)
            return qnoul(f"Is {n} {self.flag[0]}?"), s["f"][n]
        if qtype == "count_flag":
            return qchoice(f"How many {o}s are {self.flag[0]}?", [(str(k), str(k)) for k in range(len(N) + 1)]), \
                str(sum(s["f"].values()))
        if qtype == "row_at":
            k = rng.randrange(len(s["r"]))
            return qchoice(f"Which {self.row['single']} is at position {k + 1} of the row?",
                           [(x, x) for x in self.row["items"]]), s["r"][k]
        if qtype == "row_where":
            x = pick(rng, self.row["items"])
            return qchoice(f"At which position of the row is {x}?", [(str(k), f"position {k}") for k in range(1, len(s['r']) + 1)]), \
                str(s["r"].index(x) + 1)
        if qtype == "row_left_of":
            x, y = rng.sample(self.row["items"], 2)
            return qnoul(f"Is {x} somewhere to the left of {y} in the row?"), s["r"].index(x) < s["r"].index(y)
        if qtype == "failed":
            j = rng.randrange(len(events))
            return qnoul(f"Did action {j + 1} fail?"), events[j]["failed"]
        raise KeyError(qtype)


def _verbs_used(ex):
    t = ex["floor"].split("Actions, in order:\n", 1)[1].split("\n\n", 1)[0]
    return [l.split(". ", 1)[1].split()[0] for l in t.splitlines()]


def m3balanced(steps, n, rng, held_mode="exclude", qtype=None, change_balance=False):
    """n examples, each from a NEW world. held_mode "require": the world has a held pair AND the example's actions
    use it. Answers spread out within each question type (yes/no about half each, no choice answer above 40%).
    Each example records held_used (held pairs among its actions) and wide (an action that changes many objects)."""
    out, counts, per_q, chg, tries = [], collections.Counter(), collections.Counter(), collections.Counter(), 0
    while len(out) < n and tries < n * 200:
        tries += 1
        w = Mech3(rng, held_mode)
        q = qtype if qtype else pick(rng, w.QTYPES)
        if q not in w.QTYPES:
            continue
        ex = make_example(w, steps, q, rng)
        by_verb = {act["verb"]: act for act in w.actions}
        acts = [by_verb[v] for v in _verbs_used(ex)]
        held = sorted({f"{x['scope']}:{x['eff']}" for x in acts if (x["scope"], x["eff"]) in HELD})
        if held_mode == "require" and not held:
            continue
        key = (q, str(ex["gold"]))
        limit = 0.55 if ex["question"]["type"] == "noul" else 0.4
        if counts[key] >= max(3, limit * (per_q[q] + 1)):
            continue
        if change_balance and ex.get("known0"):
            c = (q, ex["gold0"] != ex["gold"])
            if chg[c] >= max(3, 0.5 * (per_q[q] + 1)):
                continue
            chg[c] += 1
        counts[key] += 1
        per_q[q] += 1
        ex["held_used"] = held
        ex["wide"] = bool(w.trig) or any(x["scope"] != "one" and not (x["scope"] == "row" and x["eff"] == "swap") for x in acts)
        out.append(ex)
    return out


# ============================================================================================== FRESH test families
class Line(Base):
    family = "line"
    QTYPES = ["first", "where", "size"]

    def __init__(self, rng):
        self.pool = pick(rng, [["Ann", "Ben", "Cal", "Dee", "Eve", "Fay", "Gus", "Hal"],
                               ["Ivo", "Jun", "Kai", "Lea", "Max", "Nia", "Oto", "Pia"]])
        self.rules = ("World: people waiting in a line at a counter; position 1 is the front of the line. 'serve' removes "
                      "the person at the front (if the line is empty nothing happens); 'arrive P' puts P at the back; "
                      "'let P first' moves P to the front and everyone else keeps their order; 'turn' makes the whole "
                      "line turn around, so the back becomes the front.")

    def sample_state(self, rng):
        return {"q": rng.sample(self.pool, rng.randint(3, 6))}

    def sample_action(self, rng, s):
        out = [p for p in self.pool if p not in s["q"]]
        k = rng.random()
        if k < 0.25:
            return {"op": "serve"}
        if k < 0.45 and out:
            return {"op": "arrive", "p": pick(rng, out)}
        if k < 0.75 and s["q"]:
            return {"op": "first", "p": pick(rng, s["q"])}
        return {"op": "turn"}

    def step(self, s, a):
        q = s["q"][:]
        if a["op"] == "serve":
            q = q[1:]
        elif a["op"] == "arrive":
            q.append(a["p"])
        elif a["op"] == "first":
            q.remove(a["p"])
            q.insert(0, a["p"])
        else:
            q.reverse()
        return {"q": q}, {"note": "done"}

    def render(self, s, events=None):
        return "Line, front to back: " + (" ".join(s["q"]) if s["q"] else "(empty)")

    def render_action(self, a):
        return {"serve": "serve", "turn": "turn", "arrive": f"arrive {a.get('p')}", "first": f"let {a.get('p')} first"}[a["op"]]

    def event_log(self, acts, events):
        return ""

    def ask(self, rng, s, events, qtype):
        if qtype == "first":
            return qchoice("Who is at the front of the line?", [(p, p) for p in self.pool] + [("nobody", "nobody, the line is empty")]), \
                (s["q"][0] if s["q"] else "nobody")
        if qtype == "where":
            p = pick(rng, s["q"]) if s["q"] and rng.random() < 0.85 else pick(rng, self.pool)
            return qchoice(f"At which position of the line is {p}?",
                           [(str(k), f"position {k}") for k in range(1, 9)] + [("none", "not in the line")]), \
                (str(s["q"].index(p) + 1) if p in s["q"] else "none")
        if qtype == "size":
            return qchoice("How many people are in the line?", [(str(k), str(k)) for k in range(9)]), str(len(s["q"]))
        raise KeyError(qtype)


class Savings(Base):
    family = "savings"
    QTYPES = ["balance", "n_empty", "more"]

    def __init__(self, rng):
        self.names = pick(rng, [["Ana", "Bia", "Caio", "Davi"], ["Eli", "Fab", "Gil", "Hugo"]])[:rng.randint(3, 4)]
        self.rules = ("World: savings accounts of " + ", ".join(self.names) + ", each with a balance in whole coins. "
                      "'month' pays interest: every account with at least 10 coins gains 1 coin for every full 10 coins "
                      "it has. 'fee' takes 2 coins from every account, but a balance never goes below 0. 'deposit k X' "
                      "adds k coins to X's account. 'withdraw k X' takes k coins from X's account if it has at least k "
                      "coins; otherwise nothing happens.")

    def sample_state(self, rng):
        return {"b": {n: pick(rng, [0, 1, 2, rng.randint(3, 30), rng.randint(8, 40)]) for n in self.names}}

    def sample_action(self, rng, s):
        k = rng.random()
        if k < 0.3:
            return {"op": "month"}
        if k < 0.55:
            return {"op": "fee"}
        return {"op": "deposit" if k < 0.78 else "withdraw", "k": rng.randint(1, 12), "x": pick(rng, self.names)}

    def step(self, s, a):
        b = dict(s["b"])
        if a["op"] == "month":
            b = {n: v + (v // 10 if v >= 10 else 0) for n, v in b.items()}
        elif a["op"] == "fee":
            b = {n: max(0, v - 2) for n, v in b.items()}
        elif a["op"] == "deposit":
            b[a["x"]] += a["k"]
        elif b[a["x"]] >= a["k"]:
            b[a["x"]] -= a["k"]
        return {"b": b}, {"note": "done"}

    def render(self, s, events=None):
        return "Balances: " + ", ".join(f"{n} {v} coins" for n, v in s["b"].items())

    def render_action(self, a):
        return a["op"] if a["op"] in ("month", "fee") else f"{a['op']} {a['k']} {a['x']}"

    def event_log(self, acts, events):
        return ""

    def ask(self, rng, s, events, qtype):
        if qtype == "balance":
            n = pick(rng, self.names)
            g = s["b"][n]
            return qchoice(f"How many coins does {n} have?", [(x, x) for x in numeric_options(g, 0, max(80, g + 10), 10)]), str(g)
        if qtype == "n_empty":
            return qchoice("How many accounts have 0 coins?", [(str(k), str(k)) for k in range(len(self.names) + 1)]), \
                str(sum(v == 0 for v in s["b"].values()))
        if qtype == "more":
            x, y = rng.sample(self.names, 2)
            return qnoul(f"Does {x} have more coins than {y}?"), s["b"][x] > s["b"][y]
        raise KeyError(qtype)


class Strip(Base):
    family = "strip"
    QTYPES = ["is_on", "n_on", "both"]

    def __init__(self, rng):
        self.n = rng.randint(5, 8)
        self.rules = (f"World: a strip of {self.n} lamps numbered 1 to {self.n} from left to right, each on or off. "
                      "'flip i j' switches every lamp from i to j (on becomes off and off becomes on); 'press i' switches "
                      "lamp i only; 'light i j' turns on every lamp from i to j; 'clear' turns every lamp off.")

    def sample_state(self, rng):
        return {"on": [rng.random() < 0.5 for _ in range(self.n)]}

    def sample_action(self, rng, s):
        k = rng.random()
        i, j = sorted(rng.sample(range(1, self.n + 1), 2))
        if k < 0.4:
            return {"op": "flip", "i": i, "j": j}
        if k < 0.65:
            return {"op": "press", "i": rng.randint(1, self.n)}
        if k < 0.9:
            return {"op": "light", "i": i, "j": j}
        return {"op": "clear"}

    def step(self, s, a):
        on = s["on"][:]
        if a["op"] == "flip":
            for t in range(a["i"] - 1, a["j"]):
                on[t] = not on[t]
        elif a["op"] == "press":
            on[a["i"] - 1] = not on[a["i"] - 1]
        elif a["op"] == "light":
            for t in range(a["i"] - 1, a["j"]):
                on[t] = True
        else:
            on = [False] * self.n
        return {"on": on}, {"note": "done"}

    def render(self, s, events=None):
        return "Lamps: " + ", ".join(f"{t + 1} {'on' if v else 'off'}" for t, v in enumerate(s["on"]))

    def render_action(self, a):
        return {"flip": f"flip {a.get('i')} {a.get('j')}", "press": f"press {a.get('i')}",
                "light": f"light {a.get('i')} {a.get('j')}", "clear": "clear"}[a["op"]]

    def event_log(self, acts, events):
        return ""

    def ask(self, rng, s, events, qtype):
        if qtype == "is_on":
            k = rng.randint(1, self.n)
            return qnoul(f"Is lamp {k} on?"), s["on"][k - 1]
        if qtype == "n_on":
            return qchoice("How many lamps are on?", [(str(k), str(k)) for k in range(self.n + 1)]), str(sum(s["on"]))
        if qtype == "both":
            x, y = sorted(rng.sample(range(1, self.n + 1), 2))
            return qnoul(f"Are lamps {x} and {y} both on?"), s["on"][x - 1] and s["on"][y - 1]
        raise KeyError(qtype)


FRESH = [Line, Savings, Strip]
