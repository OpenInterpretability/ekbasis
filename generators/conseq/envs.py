"""Text worlds with exact simulators, for consequence prediction ("what happens if I do X?").

Every world has its rules written in the state, a sampler of states and actions, an exact step function and typed
questions (System One: choice / noul) about the state AFTER the actions, with the gold answer from the simulator.

An example has two prompts with the same question:
- floor   = rules + current state + the actions -> the model must predict the outcome;
- ceiling = rules + the true resulting state (+ what happened at each action) -> the model only has to read it.

Training worlds: tetris, robot, stock, switches, files. Held-out worlds (never trained): columns, boxes, stack, bank.
Each training world also keeps one question type out of training (HELD_Q), to test questions never trained on.
"""
from __future__ import annotations

import random

COLS = "ABCDEF"


def cell_name(r, c):
    return f"{COLS[c]}{r + 1}"


def qchoice(text, options):
    """options: list of (label, description)."""
    return {"type": "choice", "instructions": text, "criteria": {k: v for k, v in options}}


def qnoul(text):
    return {"type": "noul", "instructions": text}


def numeric_options(gold, lo, hi, n=10, rng=None):
    """n candidate values around the gold one (always included), within [lo, hi], in increasing order."""
    vals = {gold}
    span = 1
    while len(vals) < n and span < 200:
        for v in (gold - span, gold + span):
            if lo <= v <= hi and len(vals) < n:
                vals.add(v)
        span += 1
    return [str(v) for v in sorted(vals)]


# ======================================================================================== tetris (train)
class Tetris:
    name = "tetris"
    W, H = 10, 14
    SHAPES = {"I": ["####"], "O": ["##", "##"], "T": ["###", ".#."], "L": ["..#", "###"], "J": ["#..", "###"],
              "S": [".##", "##."], "Z": ["##.", ".##"]}
    rules = ("World: Tetris. The board has 10 columns (1 to 10, left to right) and 14 rows (row 1 is the top, row 14 "
             "the bottom). A piece is dropped exactly as drawn (no rotation) with its leftmost cell in the given "
             "column; it falls straight down until one of its cells would enter a filled cell or go below row 14. "
             "When a row becomes completely filled it is removed before the next piece falls, and the rows above it "
             "move down one row.")
    QTYPES = ["land", "any_full", "top_row", "full_count"]
    HELD_Q = "full_count"

    def _cells(self, rows):
        return [(r, c) for r, row in enumerate(rows) for c, ch in enumerate(row) if ch == "#"]

    def _rot(self, cells):
        m = max(r for r, _ in cells)
        out = [(c, m - r) for r, c in cells]
        r0, c0 = min(r for r, _ in out), min(c for _, c in out)
        return sorted((r - r0, c - c0) for r, c in out)

    def rotations(self, name):
        cur, seen = sorted(self._cells(self.SHAPES[name])), []
        for _ in range(4):
            if cur not in seen:
                seen.append(cur)
            cur = self._rot(cur)
        return seen

    def sample_state(self, rng):
        W, H = self.W, self.H
        b = [[0] * W for _ in range(H)]
        h0 = rng.randint(3, 8)
        gap = rng.randrange(W)
        for r in range(H - h0, H):
            if rng.random() < 0.6:
                g = gap if rng.random() < 0.7 else rng.randrange(W)
                b[r] = [0 if c == g else 1 for c in range(W)]
            else:
                row = [1 if rng.random() < 0.7 else 0 for _ in range(W)]
                if all(row):
                    row[rng.randrange(W)] = 0
                b[r] = row
        return {"board": b}

    def sample_action(self, rng, s):
        name = rng.choice(list(self.SHAPES))
        cells = rng.choice(self.rotations(name))
        w = max(c for _, c in cells) + 1
        return {"name": name, "cells": cells, "col": rng.randrange(self.W - w + 1)}

    def _drop(self, b, cells, col):
        H = self.H
        h = max(r for r, _ in cells) + 1
        top = -h
        while all(r + top + 1 < H and (r + top + 1 < 0 or not b[r + top + 1][c + col]) for r, c in cells):
            top += 1
        if any(r + top < 0 for r, _ in cells):
            return None, None
        nb = [row[:] for row in b]
        landed = [(r + top, c + col) for r, c in cells]
        for r, c in landed:
            nb[r][c] = 1
        return nb, landed

    def step(self, s, a):
        """The board keeps the rows completed by THIS piece (they are removed only before the next piece falls)."""
        b = s["board"]
        if s.get("pending_clear"):
            keep = [row for row in b if not all(row)]
            b = [[0] * self.W for _ in range(self.H - len(keep))] + keep
        nb, landed = self._drop(b, a["cells"], a["col"])
        if nb is None:
            return None, None
        return {"board": nb, "pending_clear": True}, {"landed": landed}

    def render(self, s, events=None):
        b = s["board"]
        mark = set(events[-1]["landed"]) if events else set()
        lines, empty = [], []
        for r in range(self.H):
            cols = [f"{c + 1}{'*' if (r, c) in mark else ''}" for c in range(self.W) if b[r][c]]
            if cols:
                lines.append(f"row {r + 1}: columns {' '.join(cols)}")
            else:
                empty.append(r + 1)
        head = [f"rows {empty[0]} to {empty[-1]}: empty"] if empty and empty == list(range(empty[0], empty[-1] + 1)) else \
            [f"row {r}: empty" for r in empty]
        return "Filled cells, row by row:\n" + "\n".join(head + lines)

    def render_action(self, a):
        shape = "\n".join("".join("#" if (r, c) in a["cells"] else "." for c in range(max(c for _, c in a["cells"]) + 1))
                          for r in range(max(r for r, _ in a["cells"]) + 1))
        return f"drop this {a['name']} piece with its leftmost cell in column {a['col'] + 1}:\n{shape}"

    def ceiling_note(self):
        return ("This is the board right after the last piece landed; completely filled rows are still shown, and '*' "
                "marks the cells of the last piece.")

    def floor_note(self):
        return ("The questions are about the board right after the last piece lands, before any row it completes is "
                "removed.")

    def ask(self, rng, s, events, qtype):
        b = s["board"]
        if qtype == "land":
            gold = str(max(r for r, _ in events[-1]["landed"]) + 1)
            return qchoice("In which row is the lowest cell of the last piece?",
                           [(str(k), f"row {k}") for k in range(1, self.H + 1)]), gold
        if qtype == "any_full":
            return qnoul("Is at least one row completely filled (all 10 columns)?"), any(all(row) for row in b)
        if qtype == "top_row":
            c = rng.randrange(self.W)
            rows = [r for r in range(self.H) if b[r][c]]
            gold = str(rows[0] + 1) if rows else "none"
            return qchoice(f"Which is the highest row (smallest row number) with a filled cell in column {c + 1}?",
                           [(str(k), f"row {k}") for k in range(1, self.H + 1)] + [("none", "column empty")]), gold
        if qtype == "full_count":
            n = sum(all(row) for row in b)
            return qchoice("How many rows are completely filled (all 10 columns)?",
                           [(str(k), f"{k} rows") for k in range(5)]), str(min(n, 4))
        raise KeyError(qtype)


# ======================================================================================== robot (train)
class Robot:
    name = "robot"
    N = 6
    rules = ("World: a robot on a 6x6 grid. Columns are A to F (left to right) and rows 1 to 6 (top to bottom); a cell "
             "is named like C4. North means one row up (smaller row number), south one row down, east one column to the "
             "right, west one column to the left. Each move goes one cell. A move into a wall or off the grid is "
             "blocked and the robot stays where it is. When the robot enters a cell with a coin it picks the coin up.")
    QTYPES = ["pos", "coins_left", "coin_at", "blocked"]
    HELD_Q = "blocked"
    DIRS = {"north": (-1, 0), "south": (1, 0), "east": (0, 1), "west": (0, -1)}

    def sample_state(self, rng):
        cells = [(r, c) for r in range(self.N) for c in range(self.N)]
        rng.shuffle(cells)
        walls = set(cells[:rng.randint(4, 8)])
        coins = set(cells[8:8 + rng.randint(2, 4)])
        robot = cells[12]
        return {"walls": walls, "coins": coins, "robot": robot}

    def sample_action(self, rng, s):
        return {"dir": rng.choice(list(self.DIRS))}

    def step(self, s, a):
        dr, dc = self.DIRS[a["dir"]]
        r, c = s["robot"]
        nr, nc = r + dr, c + dc
        ns = {"walls": s["walls"], "coins": set(s["coins"]), "robot": s["robot"]}
        if not (0 <= nr < self.N and 0 <= nc < self.N) or (nr, nc) in s["walls"]:
            return ns, {"blocked": True, "coin": None}
        ns["robot"] = (nr, nc)
        got = (nr, nc) if (nr, nc) in ns["coins"] else None
        ns["coins"].discard((nr, nc))
        return ns, {"blocked": False, "coin": got}

    def render(self, s, events=None):
        walls = ", ".join(sorted(cell_name(*w) for w in s["walls"]))
        coins = ", ".join(sorted(cell_name(*x) for x in s["coins"])) or "none"
        return f"Walls: {walls}\nCoins: {coins}\nRobot: {cell_name(*s['robot'])}"

    def render_action(self, a):
        return f"move {a['dir']}"

    def ceiling_note(self):
        return "This is the grid after all the moves."

    def floor_note(self):
        return "The questions are about the grid after all these moves."

    def event_log(self, acts, events):
        out = []
        for i, (a, e) in enumerate(zip(acts, events)):
            what = "blocked, the robot stayed" if e["blocked"] else ("moved and picked up the coin at " + cell_name(*e["coin"])
                                                                      if e["coin"] else "moved")
            out.append(f"move {i + 1} ({a['dir']}): {what}")
        return "What happened: " + "; ".join(out) + "."

    def ask(self, rng, s, events, qtype):
        if qtype == "pos":
            return qchoice("In which cell is the robot?",
                           [(cell_name(r, c), f"cell {cell_name(r, c)}") for r in range(self.N) for c in range(self.N)]), \
                cell_name(*s["robot"])
        if qtype == "coins_left":
            return qchoice("How many coins are left on the grid?", [(str(k), f"{k} coins") for k in range(5)]), \
                str(len(s["coins"]))
        if qtype == "coin_at":
            pool = list(s["coins"]) + [e["coin"] for e in events if e["coin"]]
            if not pool or rng.random() < 0.3:
                pool = [(rng.randrange(self.N), rng.randrange(self.N))]
            x = rng.choice(pool)
            return qnoul(f"Is there a coin at {cell_name(*x)}?"), x in s["coins"]
        if qtype == "blocked":
            return qnoul("Was at least one of the moves blocked?"), any(e["blocked"] for e in events)
        raise KeyError(qtype)


# ======================================================================================== stock (train)
class Stock:
    name = "stock"
    rules = ("World: a warehouse. An order for n units of an item is filled only if the stock of that item is at least "
             "n; otherwise the order is rejected and nothing changes. Right after a filled order, if the stock of that "
             "item is below its reorder point, a restock of that item arrives at once and adds its restock amount.")
    QTYPES = ["stock", "below", "rejected", "restocks"]
    HELD_Q = "restocks"
    ITEMS = ["bolts", "nuts", "gears"]

    def sample_state(self, rng):
        st = {}
        for it in self.ITEMS:
            st[it] = {"stock": rng.randint(0, 15), "reorder": rng.randint(3, 8), "restock": rng.choice([5, 8, 10])}
        return {"items": st}

    def sample_action(self, rng, s):
        return {"item": rng.choice(self.ITEMS), "n": rng.randint(1, 9)}

    def step(self, s, a):
        items = {k: dict(v) for k, v in s["items"].items()}
        x = items[a["item"]]
        if x["stock"] < a["n"]:
            return {"items": items}, {"rejected": True, "restock": False}
        x["stock"] -= a["n"]
        restock = x["stock"] < x["reorder"]
        if restock:
            x["stock"] += x["restock"]
        return {"items": items}, {"rejected": False, "restock": restock}

    def render(self, s, events=None):
        return "\n".join(f"{it}: stock {v['stock']}, reorder point {v['reorder']}, restock amount {v['restock']}"
                         for it, v in s["items"].items())

    def render_action(self, a):
        return f"order {a['n']} {a['item']}"

    def ceiling_note(self):
        return "This is the warehouse after all the orders."

    def floor_note(self):
        return "The questions are about the warehouse after all these orders."

    def event_log(self, acts, events):
        out = []
        for i, (a, e) in enumerate(zip(acts, events)):
            what = "rejected" if e["rejected"] else ("filled, then restocked" if e["restock"] else "filled")
            out.append(f"order {i + 1} ({a['n']} {a['item']}): {what}")
        return "What happened: " + "; ".join(out) + "."

    def ask(self, rng, s, events, qtype, acts=None):
        if qtype == "stock":
            it = rng.choice(self.ITEMS)
            g = s["items"][it]["stock"]
            opts = numeric_options(g, 0, 40, 10)
            return qchoice(f"How many {it} are in stock?", [(v, f"{v} units") for v in opts]), str(g)
        if qtype == "below":
            it = rng.choice(self.ITEMS)
            v = s["items"][it]
            return qnoul(f"Is the stock of {it} below its reorder point?"), v["stock"] < v["reorder"]
        if qtype == "rejected":
            k = rng.randrange(len(events))
            return qnoul(f"Was order number {k + 1} rejected?"), events[k]["rejected"]
        if qtype == "restocks":
            n = sum(e["restock"] for e in events)
            return qchoice("How many restocks arrived?", [(str(k), f"{k} restocks") for k in range(5)]), str(n)
        raise KeyError(qtype)


# ======================================================================================== switches (train)
class Switches:
    name = "switches"
    rules = ("World: six lights L1 to L6, each on or off, and four switches S1 to S4. Pressing a switch flips every "
             "light it is wired to: lights that were on go off, lights that were off go on. Other lights do not change.")
    QTYPES = ["light", "same", "count_on"]
    HELD_Q = "count_on"
    LIGHTS = [f"L{i}" for i in range(1, 7)]

    def sample_state(self, rng):
        wiring = {f"S{i}": sorted(rng.sample(self.LIGHTS, rng.randint(1, 3)), key=lambda x: int(x[1:])) for i in range(1, 5)}
        on = {l: rng.random() < 0.5 for l in self.LIGHTS}
        return {"wiring": wiring, "on": on}

    def sample_action(self, rng, s):
        return {"switch": rng.choice(list(s["wiring"]))}

    def step(self, s, a):
        on = dict(s["on"])
        for l in s["wiring"][a["switch"]]:
            on[l] = not on[l]
        return {"wiring": s["wiring"], "on": on}, {}

    def render(self, s, events=None):
        w = "; ".join(f"{k} flips {', '.join(v)}" for k, v in s["wiring"].items())
        on = ", ".join(l for l in self.LIGHTS if s["on"][l]) or "none"
        off = ", ".join(l for l in self.LIGHTS if not s["on"][l]) or "none"
        return f"Wiring: {w}.\nLights on: {on}. Lights off: {off}."

    def render_action(self, a):
        return f"press {a['switch']}"

    def ceiling_note(self):
        return "This is the state after all the presses."

    def floor_note(self):
        return "The questions are about the lights after all these presses."

    def ask(self, rng, s, events, qtype):
        if qtype == "light":
            l = rng.choice(self.LIGHTS)
            return qnoul(f"Is light {l} on?"), s["on"][l]
        if qtype == "same":
            a, b = rng.sample(self.LIGHTS, 2)
            return qnoul(f"Are lights {a} and {b} in the same state (both on or both off)?"), s["on"][a] == s["on"][b]
        if qtype == "count_on":
            return qchoice("How many lights are on?", [(str(k), f"{k} lights") for k in range(7)]), \
                str(sum(s["on"].values()))
        raise KeyError(qtype)


# ======================================================================================== files (train)
class Files:
    name = "files"
    rules = ("World: a file system with folders directly under the root (like /docs) and files inside them (like "
             "/docs/a.txt). Commands: 'mkdir /x' creates a folder (fails if it already exists); 'touch /x/f' creates "
             "a file (fails if the folder does not exist; does nothing if the file already exists); 'rm /x/f' deletes "
             "a file (fails if it does not exist); 'mv /x/f /y' moves a file into folder /y (fails if the file or the "
             "folder does not exist, or if /y already has a file with that name). A failed command changes nothing.")
    QTYPES = ["exists", "failed", "count"]
    HELD_Q = "count"
    DIRS = ["docs", "img", "tmp", "src"]
    FILES = ["a.txt", "b.txt", "notes.md", "plan.md", "x.py"]

    def sample_state(self, rng):
        dirs = set(rng.sample(self.DIRS, rng.randint(2, 3)))
        files = set()
        for d in dirs:
            for f in rng.sample(self.FILES, rng.randint(0, 3)):
                files.add((d, f))
        return {"dirs": dirs, "files": files}

    def sample_action(self, rng, s):
        k = rng.random()
        if k < 0.2:
            return {"cmd": "mkdir", "d": rng.choice(self.DIRS)}
        if k < 0.5:
            return {"cmd": "touch", "d": rng.choice(self.DIRS), "f": rng.choice(self.FILES)}
        if k < 0.75:
            pool = list(s["files"]) or [(rng.choice(self.DIRS), rng.choice(self.FILES))]
            d, f = rng.choice(pool) if rng.random() < 0.7 else (rng.choice(self.DIRS), rng.choice(self.FILES))
            return {"cmd": "rm", "d": d, "f": f}
        pool = list(s["files"]) or [(rng.choice(self.DIRS), rng.choice(self.FILES))]
        d, f = rng.choice(pool)
        return {"cmd": "mv", "d": d, "f": f, "to": rng.choice(self.DIRS)}

    def step(self, s, a):
        dirs, files = set(s["dirs"]), set(s["files"])
        ok = True
        if a["cmd"] == "mkdir":
            ok = a["d"] not in dirs
            if ok:
                dirs.add(a["d"])
        elif a["cmd"] == "touch":
            ok = a["d"] in dirs
            if ok:
                files.add((a["d"], a["f"]))
        elif a["cmd"] == "rm":
            ok = (a["d"], a["f"]) in files
            if ok:
                files.discard((a["d"], a["f"]))
        else:
            ok = (a["d"], a["f"]) in files and a["to"] in dirs and (a["to"], a["f"]) not in files and a["to"] != a["d"]
            if ok:
                files.discard((a["d"], a["f"]))
                files.add((a["to"], a["f"]))
        return {"dirs": dirs, "files": files}, {"failed": not ok}

    def render(self, s, events=None):
        lines = []
        for d in sorted(s["dirs"]):
            fs = sorted(f for dd, f in s["files"] if dd == d)
            lines.append(f"/{d}: " + (", ".join(fs) if fs else "(empty)"))
        return "Folders and their files:\n" + "\n".join(lines)

    def render_action(self, a):
        if a["cmd"] == "mkdir":
            return f"mkdir /{a['d']}"
        if a["cmd"] in ("touch", "rm"):
            return f"{a['cmd']} /{a['d']}/{a['f']}"
        return f"mv /{a['d']}/{a['f']} /{a['to']}"

    def ceiling_note(self):
        return "This is the file system after all the commands."

    def floor_note(self):
        return "The questions are about the file system after all these commands."

    def event_log(self, acts, events):
        return "What happened: " + "; ".join(f"command {i + 1} ({self.render_action(a)}): {'failed' if e['failed'] else 'done'}"
                                             for i, (a, e) in enumerate(zip(acts, events))) + "."

    def ask(self, rng, s, events, qtype):
        if qtype == "exists":
            pool = list(s["files"]) if s["files"] and rng.random() < 0.5 else [(rng.choice(self.DIRS), rng.choice(self.FILES))]
            d, f = rng.choice(pool)
            return qnoul(f"Does the file /{d}/{f} exist?"), (d, f) in s["files"]
        if qtype == "failed":
            k = rng.randrange(len(events))
            return qnoul(f"Did command number {k + 1} fail?"), events[k]["failed"]
        if qtype == "count":
            d = rng.choice(sorted(s["dirs"]))
            return qchoice(f"How many files are in /{d}?", [(str(k), f"{k} files") for k in range(6)]), \
                str(min(5, sum(1 for dd, _ in s["files"] if dd == d)))
        raise KeyError(qtype)


# ======================================================================================== columns (held-out world)
class Columns:
    name = "columns"
    NC, NR = 7, 6
    rules = ("World: a vertical board with 7 columns (1 to 7) and 6 slots per column, filled from the bottom. A disc "
             "dropped into a column lands in the lowest empty slot of that column (slot 1 is the bottom, slot 6 the "
             "top). Dropping a disc into a full column fails and changes nothing.")
    QTYPES = ["slot", "count", "full"]

    def sample_state(self, rng):
        return {"cols": [[rng.choice("XO") for _ in range(rng.randint(0, 6))] for _ in range(self.NC)]}

    def sample_action(self, rng, s):
        return {"col": rng.randrange(self.NC), "disc": rng.choice("XO")}

    def step(self, s, a):
        cols = [c[:] for c in s["cols"]]
        if len(cols[a["col"]]) >= self.NR:
            return {"cols": cols}, {"slot": None}
        cols[a["col"]].append(a["disc"])
        return {"cols": cols}, {"slot": len(cols[a["col"]])}

    def render(self, s, events=None):
        return "Discs in each column, from the bottom slot up:\n" + "\n".join(
            f"column {i + 1}: {' '.join(c) if c else '(empty)'}" for i, c in enumerate(s["cols"]))

    def render_action(self, a):
        return f"drop an {a['disc']} disc into column {a['col'] + 1}"

    def ceiling_note(self):
        return "This is the board after all the drops."

    def floor_note(self):
        return "The questions are about the board after all these drops."

    def event_log(self, acts, events):
        return "What happened: " + "; ".join(
            f"drop {i + 1} (column {a['col'] + 1}): " + (f"landed in slot {e['slot']}" if e["slot"] else "failed, column full")
            for i, (a, e) in enumerate(zip(acts, events))) + "."

    def ask(self, rng, s, events, qtype, acts=None):
        if qtype == "slot":
            e = events[-1]
            gold = str(e["slot"]) if e["slot"] else "failed"
            return qchoice("In which slot did the last disc land?",
                           [(str(k), f"slot {k}") for k in range(1, self.NR + 1)] + [("failed", "it did not land: the column was full")]), gold
        if qtype == "count":
            c = rng.randrange(self.NC)
            return qchoice(f"How many discs are in column {c + 1}?", [(str(k), f"{k} discs") for k in range(self.NR + 1)]), \
                str(len(s["cols"][c]))
        if qtype == "full":
            c = rng.randrange(self.NC)
            return qnoul(f"Is column {c + 1} full?"), len(s["cols"][c]) >= self.NR
        raise KeyError(qtype)


# ======================================================================================== boxes (held-out world)
class Boxes:
    name = "boxes"
    N = 6
    rules = ("World: a 6x6 warehouse grid. Columns are A to F (left to right) and rows 1 to 6 (top to bottom); a cell "
             "is named like C4. North means one row up, south one row down, east one column right, west one column "
             "left. The worker moves one cell per move. Moving into a wall or off the grid is blocked. Moving into the "
             "box pushes the box one cell in the same direction, but only if the cell beyond the box is free (not a "
             "wall and not off the grid); otherwise the move is blocked and nothing moves.")
    QTYPES = ["box", "worker", "on_target"]

    def sample_state(self, rng):
        cells = [(r, c) for r in range(self.N) for c in range(self.N)]
        rng.shuffle(cells)
        walls = set(cells[:rng.randint(3, 6)])
        free = [x for x in cells if x not in walls]
        box = rng.choice([x for x in free if 0 < x[0] < self.N - 1 and 0 < x[1] < self.N - 1] or free)
        near = [(box[0] + dr, box[1] + dc) for dr, dc in ((-1, 0), (1, 0), (0, 1), (0, -1))]
        near = [x for x in near if x in free]
        worker = rng.choice(near) if near and rng.random() < 0.8 else rng.choice([x for x in free if x != box])
        target = rng.choice([x for x in free if x not in (box, worker)])
        return {"walls": walls, "box": box, "worker": worker, "target": target}

    DIRS = Robot.DIRS

    def sample_action(self, rng, s):
        r, c = s["worker"]
        br, bc = s["box"]
        toward = [d for d, (dr, dc) in self.DIRS.items() if (r + dr, c + dc) == (br, bc)]
        if toward and rng.random() < 0.6:
            return {"dir": toward[0]}
        return {"dir": rng.choice(list(self.DIRS))}

    def step(self, s, a):
        dr, dc = self.DIRS[a["dir"]]
        r, c = s["worker"]
        nr, nc = r + dr, c + dc
        inside = lambda x: 0 <= x[0] < self.N and 0 <= x[1] < self.N
        ns = dict(s)
        if not inside((nr, nc)) or (nr, nc) in s["walls"]:
            return ns, {"blocked": True}
        if (nr, nc) == s["box"]:
            b2 = (nr + dr, nc + dc)
            if not inside(b2) or b2 in s["walls"]:
                return ns, {"blocked": True}
            ns["box"] = b2
        ns["worker"] = (nr, nc)
        return ns, {"blocked": False}

    def render(self, s, events=None):
        return (f"Walls: {', '.join(sorted(cell_name(*w) for w in s['walls']))}\nBox: {cell_name(*s['box'])}\n"
                f"Target: {cell_name(*s['target'])}\nWorker: {cell_name(*s['worker'])}")

    def render_action(self, a):
        return f"move {a['dir']}"

    def ceiling_note(self):
        return "This is the grid after all the moves."

    def floor_note(self):
        return "The questions are about the grid after all these moves."

    def ask(self, rng, s, events, qtype):
        cells = [(cell_name(r, c), f"cell {cell_name(r, c)}") for r in range(self.N) for c in range(self.N)]
        if qtype == "box":
            return qchoice("In which cell is the box?", cells), cell_name(*s["box"])
        if qtype == "worker":
            return qchoice("In which cell is the worker?", cells), cell_name(*s["worker"])
        if qtype == "on_target":
            return qnoul("Is the box on the target cell?"), s["box"] == s["target"]
        raise KeyError(qtype)


# ======================================================================================== stack (held-out world)
class Stack:
    name = "stack"
    rules = ("World: a stack of numbers, written from bottom to top. 'push n' puts n on top; 'pop' removes the top "
             "number; 'dup' pushes a copy of the top number; 'swap' exchanges the top two numbers; 'add' removes the "
             "top two numbers and pushes their sum. An operation that needs more numbers than the stack has fails "
             "and changes nothing.")
    QTYPES = ["top", "size", "failed"]

    def sample_state(self, rng):
        return {"st": [rng.randint(0, 9) for _ in range(rng.randint(0, 4))]}

    def sample_action(self, rng, s):
        op = rng.choice(["push", "push", "pop", "dup", "swap", "add", "add"])
        return {"op": op, "n": rng.randint(0, 9)} if op == "push" else {"op": op}

    def step(self, s, a):
        st = s["st"][:]
        need = {"push": 0, "pop": 1, "dup": 1, "swap": 2, "add": 2}[a["op"]]
        if len(st) < need:
            return {"st": st}, {"failed": True}
        if a["op"] == "push":
            st.append(a["n"])
        elif a["op"] == "pop":
            st.pop()
        elif a["op"] == "dup":
            st.append(st[-1])
        elif a["op"] == "swap":
            st[-1], st[-2] = st[-2], st[-1]
        else:
            x, y = st.pop(), st.pop()
            st.append(x + y)
        return {"st": st}, {"failed": False}

    def render(self, s, events=None):
        return "Stack (bottom to top): " + (" ".join(map(str, s["st"])) if s["st"] else "(empty)")

    def render_action(self, a):
        return f"push {a['n']}" if a["op"] == "push" else a["op"]

    def ceiling_note(self):
        return "This is the stack after all the operations."

    def floor_note(self):
        return "The questions are about the stack after all these operations."

    def event_log(self, acts, events):
        return "What happened: " + "; ".join(f"operation {i + 1} ({self.render_action(a)}): {'failed' if e['failed'] else 'done'}"
                                             for i, (a, e) in enumerate(zip(acts, events))) + "."

    def ask(self, rng, s, events, qtype):
        if qtype == "top":
            gold = str(s["st"][-1]) if s["st"] else "empty"
            g = s["st"][-1] if s["st"] else 0
            opts = numeric_options(g, 0, 40, 9)
            return qchoice("What number is on top of the stack?", [(v, f"the number {v}") for v in opts] + [("empty", "the stack is empty")]), gold
        if qtype == "size":
            return qchoice("How many numbers are on the stack?", [(str(k), f"{k} numbers") for k in range(10)]), \
                str(min(9, len(s["st"])))
        if qtype == "failed":
            return qnoul("Did at least one operation fail?"), any(e["failed"] for e in events)
        raise KeyError(qtype)


# ======================================================================================== bank (held-out world)
class Bank:
    name = "bank"
    rules = ("World: a bank account. A deposit adds its amount. A withdrawal takes its amount plus a fee of 2 dollars, "
             "but it is declined (nothing changes) if it would leave the balance below -20 dollars. Balances are in "
             "whole dollars.")
    QTYPES = ["balance", "declined", "negative"]

    def sample_state(self, rng):
        return {"bal": rng.randint(-10, 40)}

    def sample_action(self, rng, s):
        return {"op": "deposit" if rng.random() < 0.35 else "withdraw", "n": rng.choice([5, 10, 15, 20, 25])}

    def step(self, s, a):
        b = s["bal"]
        if a["op"] == "deposit":
            return {"bal": b + a["n"]}, {"declined": False}
        if b - a["n"] - 2 < -20:
            return {"bal": b}, {"declined": True}
        return {"bal": b - a["n"] - 2}, {"declined": False}

    def render(self, s, events=None):
        return f"Balance: {s['bal']} dollars"

    def render_action(self, a):
        return f"{a['op']} {a['n']} dollars"

    def ceiling_note(self):
        return "This is the account after all the operations."

    def floor_note(self):
        return "The questions are about the account after all these operations."

    def event_log(self, acts, events):
        return "What happened: " + "; ".join(f"operation {i + 1} ({self.render_action(a)}): {'declined' if e['declined'] else 'done'}"
                                             for i, (a, e) in enumerate(zip(acts, events))) + "."

    def ask(self, rng, s, events, qtype):
        if qtype == "balance":
            g = s["bal"]
            opts = numeric_options(g, -40, 200, 10)
            return qchoice("What is the balance, in dollars?", [(v, f"{v} dollars") for v in opts]), str(g)
        if qtype == "declined":
            k = rng.randrange(len(events))
            return qnoul(f"Was operation number {k + 1} declined?"), events[k]["declined"]
        if qtype == "negative":
            return qnoul("Is the balance below zero?"), s["bal"] < 0
        raise KeyError(qtype)


TRAIN_WORLDS = [Tetris(), Robot(), Stock(), Switches(), Files()]
HELDOUT_WORLDS = [Columns(), Boxes(), Stack(), Bank()]
WORLDS = {w.name: w for w in TRAIN_WORLDS + HELDOUT_WORLDS}


def make_example(world, steps, qtype, rng, max_tries=200):
    """One example: rules + state + `steps` actions, one typed question about the outcome, gold from the simulator."""
    for _ in range(max_tries):
        s0 = world.sample_state(rng)
        s, acts, events, ok = s0, [], [], True
        for _ in range(steps):
            a = world.sample_action(rng, s)
            ns, ev = world.step(s, a)
            if ns is None:
                ok = False
                break
            acts.append(a)
            events.append(ev)
            s = ns
        if not ok:
            continue
        st = rng.getstate()
        q, gold = world.ask(rng, s, events, qtype)
        r0 = random.Random()
        r0.setstate(st)
        try:  # the same question about the initial state (same random draws), for change balance and the honest metric
            q0, gold0 = world.ask(r0, s0, [], qtype)
            known0 = q0["instructions"] == q["instructions"]
        except Exception:
            gold0, known0 = None, False
        act_text = "\n".join(f"{i + 1}. {world.render_action(a)}" for i, a in enumerate(acts))
        floor = (f"{world.rules}\n\nCurrent state:\n{world.render(s0)}\n\nActions, in order:\n{act_text}\n\n"
                 f"{world.floor_note()}")
        log = world.event_log(acts, events) if hasattr(world, "event_log") else ""
        ceiling = (f"{world.rules}\n\nState after the actions:\n{world.render(s, events)}\n\n{world.ceiling_note()}"
                   + (f"\n{log}" if log else ""))
        return {"world": world.name, "steps": steps, "qtype": qtype, "question": q, "gold": gold,
                "floor": floor, "ceiling": ceiling, "gold0": gold0 if known0 else None, "known0": known0}
    raise RuntimeError(f"could not build an example for {world.name}")


def balanced(world, steps, qtype, rng, n):
    """n examples with the answers spread out: yes/no about half each, and no choice answer above 40%."""
    out, counts = [], {}
    tries = 0
    while len(out) < n and tries < n * 60:
        tries += 1
        ex = make_example(world, steps, qtype, rng)
        g = ex["gold"]
        if ex["question"]["type"] == "noul":
            if counts.get(g, 0) >= (n + 1) // 2:
                continue
        elif counts.get(g, 0) >= max(2, int(0.4 * n)):
            continue
        counts[g] = counts.get(g, 0) + 1
        out.append(ex)
    return out


# ======================================================================================== trajectories (latent model)
# Questions about a STATE (no question about what happened during an action), per world; HELD_Q stays out of training.
STATE_Q = {"tetris": ["land", "any_full", "top_row", "full_count"], "robot": ["pos", "coins_left", "coin_at"],
           "stock": ["stock", "below"], "switches": ["light", "same", "count_on"], "files": ["exists", "count"],
           "columns": ["count", "full"], "boxes": ["box", "worker", "on_target"], "stack": ["top", "size"],
           "bank": ["balance", "negative"]}


def make_trajectory(world, steps, final_qtype, rng, train_qtypes=None, max_tries=200):
    """s0, the actions, the text of every intermediate state, one state question per state (the last one of type
    final_qtype), and the floor / ceiling prompts of the last question exactly as make_example builds them."""
    pool = train_qtypes or STATE_Q[world.name]
    for _ in range(max_tries):
        s0 = world.sample_state(rng)
        s, acts, events, states, ok = s0, [], [], [s0], True
        for _ in range(steps):
            a = world.sample_action(rng, s)
            ns, ev = world.step(s, a)
            if ns is None:
                ok = False
                break
            acts.append(a)
            events.append(ev)
            states.append(ns)
            s = ns
        if not ok:
            continue
        renders = [world.render(states[0])] + [world.render(states[t], events[:t]) for t in range(1, steps + 1)]
        qs = []
        for t in range(steps + 1):
            qt = final_qtype if t == steps else rng.choice([q for q in pool if not (q == "land" and t == 0)])
            q, gold = world.ask(rng, states[t], events[:t], qt)
            qs.append({"t": t, "qtype": qt, "question": q, "gold": gold})
        act_text = "\n".join(f"{i + 1}. {world.render_action(a)}" for i, a in enumerate(acts))
        floor = (f"{world.rules}\n\nCurrent state:\n{renders[0]}\n\nActions, in order:\n{act_text}\n\n"
                 f"{world.floor_note()}")
        ceiling = f"{world.rules}\n\nState after the actions:\n{renders[-1]}\n\n{world.ceiling_note()}"
        return {"world": world.name, "steps": steps, "qtype": final_qtype, "rules": world.rules, "states": renders,
                "actions": [world.render_action(a) for a in acts], "questions": qs,
                "question": qs[-1]["question"], "gold": qs[-1]["gold"], "floor": floor, "ceiling": ceiling}
    raise RuntimeError(world.name)
