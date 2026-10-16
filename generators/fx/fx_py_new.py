"""WS-FX new Python families (SPEC.md): py_collections and py_classes (held out), py_iter_lazy, py_files_io.
Same layout as WS-F's Python family (state = what already ran + values, actions = statements, CPython 3.12 run by the
unprivileged user); the FX harness preloads a few standard-library names (no import statement is ever generated) and
records the files of the working folder, so file side effects can be asked about."""
from __future__ import annotations

import ast
import json
import os
import random

from common import choice, make_box, remove_box, row, run_unprivileged, stable_seed, world_ceiling, world_floor, \
    yes_no, chown_tree

RULES = ("Python 3.12 in a fresh interpreter, started in an empty working folder. The statements below run in order in "
         "one program. If a statement raises an exception that nothing catches, the program stops there and the later "
         "statements do not run. Already available without imports: collections (defaultdict, Counter, OrderedDict, "
         "deque, ChainMap), itertools (groupby, islice, chain), dataclass and field, os and Path.")
NAMES = ["crate", "bins", "tally", "queue", "stack", "ledger", "pins", "marks", "rows", "cells", "slots", "pegs", "notes",
         "tiles", "beads", "chips", "cards", "keys", "tags", "parts"]
FILES = ["log.txt", "notes.txt", "data.csv", "out.txt", "cache.json", "draft.md", "report.txt"]
EXCS = ["KeyError", "IndexError", "TypeError", "ValueError", "AttributeError", "FileExistsError", "FileNotFoundError",
        "NameError", "StopIteration", "UnboundLocalError"]
HARNESS = r'''
import io, json, sys, os, contextlib
from collections import defaultdict, Counter, OrderedDict, deque, ChainMap
import collections, itertools
from itertools import groupby, islice, chain
from dataclasses import dataclass, field
from pathlib import Path
spec = json.loads(sys.stdin.read())
ns = {"__name__": "__main__", "defaultdict": defaultdict, "Counter": Counter, "OrderedDict": OrderedDict,
      "deque": deque, "ChainMap": ChainMap, "collections": collections, "itertools": itertools, "groupby": groupby,
      "islice": islice, "chain": chain, "dataclass": dataclass, "field": field, "Path": Path, "os": os}
def snap():
    out = {}
    for v in spec["track"]:
        if v in ns:
            try:
                out[v] = repr(ns[v])
            except Exception:
                out[v] = "<unrepresentable>"
        else:
            out[v] = None
    files = {}
    for n in sorted(os.listdir(".")):
        try:
            if os.path.isdir(n):
                files[n] = "<folder>"
            else:
                with open(n, errors="replace") as fh:
                    files[n] = fh.read(300)
        except Exception:
            files[n] = "<unreadable>"
    return {"vars": out, "files": files}
for code in spec["setup"]:
    exec(compile(code, "<setup>", "exec"), ns)
before = snap()
log = []
for i, code in enumerate(spec["actions"]):
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            exec(compile(code, "<a%d>" % i, "exec"), ns)
        log.append(["ok", None, buf.getvalue()])
    except BaseException as e:
        log.append(["raise", type(e).__name__, buf.getvalue()])
        break
after = snap()
print(json.dumps({"before": before, "after": after, "log": log}))
'''
HARNESS_PATH = "/dev/shm/fx/py_harness_fx.py"
FORBIDDEN = {"__import__", "eval", "exec", "compile", "globals", "locals", "vars", "getattr", "setattr", "delattr",
             "input", "breakpoint", "exit", "quit", "help", "memoryview", "__builtins__"}


def safe(code):
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            return False
        if isinstance(node, ast.Name) and node.id in FORBIDDEN:
            return False
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            return False
        if isinstance(node, ast.Attribute) and node.attr in ("system", "popen", "spawnl", "execv", "fork", "kill",
                                                               "chdir", "rmdir", "removedirs"):
            return False
    return True


T = {}


def tpl(family, name):
    def deco(fn):
        T[name] = (family, fn)
        return fn
    return deco


def pick(rng, k=1):
    return rng.sample(NAMES, k) if k > 1 else rng.choice(NAMES)


# ------------------------------------------------------------------ py_collections (held out)

@tpl("py_collections", "defaultdict_access_creates")
def _(rng, flip):
    d = pick(rng)
    k1, k2 = rng.sample(["red", "blue", "gold", "teal", "plum"], 2)
    look = f"x = {d}.get({k2!r})" if flip else f"x = {d}[{k2!r}]"
    return dict(setup=[f"{d} = defaultdict(list)", f"{d}[{k1!r}].append({rng.randint(1, 9)})"],
                actions=[look, f"n = len({d})"], track=[d, "n"], qs=[("value", "n", ["1"])])


@tpl("py_collections", "counter_minus_drops")
def _(rng, flip):
    a, b = rng.randint(2, 5), rng.randint(1, 3)
    c = rng.randint(b + 1, b + 3)
    act = f"c.subtract(Counter(b={c}))" if flip else f"c = c - Counter(b={c})"
    return dict(setup=[f"c = Counter(a={a}, b={b})"], actions=[act, "bv = c['b']", "keys = sorted(c)"],
                track=["bv", "keys"], qs=[("value", "bv", [repr(b - c), "0"]), ("value", "keys", [repr(['a', 'b'])])])


@tpl("py_collections", "setdefault_vs_get")
def _(rng, flip):
    d = pick(rng)
    k, z = rng.choice(["x", "y", "k"]), rng.randint(1, 9)
    act = f"{d}.get({k!r}, []).append({z})" if flip else f"{d}.setdefault({k!r}, []).append({z})"
    return dict(setup=[f"{d} = {{}}"], actions=[act], track=[d], qs=[("value", d, [repr({k: [z]}), "{}"])])


@tpl("py_collections", "dict_reinsert_order")
def _(rng, flip):
    ks = rng.sample(["a", "b", "c", "d"], 3)
    d = {k: i for i, k in enumerate(ks, 1)}
    act = [f"d[{ks[0]!r}] = 9"] if flip else [f"del d[{ks[0]!r}]", f"d[{ks[0]!r}] = 9"]
    return dict(setup=[f"d = {d!r}"], actions=act + ["order = list(d)"], track=["order"],
                qs=[("value", "order", [repr(ks), repr(ks[1:] + ks[:1])])])


@tpl("py_collections", "deque_maxlen")
def _(rng, flip):
    xs = [rng.randint(1, 9) for _ in range(3)]
    z = rng.randint(10, 20)
    ml = "None" if flip else str(len(xs))
    return dict(setup=[f"q = deque({xs}, maxlen={ml})"], actions=[f"q.append({z})", "out = list(q)"], track=["out"],
                qs=[("value", "out", [repr(xs + [z]), repr(xs[1:] + [z])])])


@tpl("py_collections", "chainmap_write_first")
def _(rng, flip):
    k, z = rng.choice(["mode", "level", "size"]), rng.randint(1, 9)
    tgt = "second" if flip else "cm"
    return dict(setup=["first = {}", f"second = {{{k!r}: 0}}", "cm = ChainMap(first, second)"],
                actions=[f"{tgt}[{k!r}] = {z}", f"seen = cm[{k!r}]"], track=["first", "second", "seen"],
                qs=[("value", "second", [repr({k: z})]), ("value", "first", ["{}"])])


@tpl("py_collections", "dict_pop_default")
def _(rng, flip):
    d = pick(rng)
    k = rng.choice(["x", "y", "z"])
    act = f"v = {d}.pop({k!r}, None)" if flip else f"v = {d}.pop({k!r})"
    return dict(setup=[f"{d} = {{'a': 1}}"], actions=[act, f"n = len({d})"], track=["v", "n"],
                qs=[("exc",), ("value", "n", ["1"])])


@tpl("py_collections", "counter_update_vs_assign")
def _(rng, flip):
    a, b = rng.randint(1, 4), rng.randint(1, 4)
    act = f"c['x'] = {b}" if flip else f"c.update(x={b})"
    return dict(setup=[f"c = Counter(x={a})"], actions=[act, "v = c['x']"], track=["v"],
                qs=[("value", "v", [repr(b), repr(a + b)])])


# ------------------------------------------------------------------ py_classes (held out)

@tpl("py_classes", "class_list_shared")
def _(rng, flip):
    z = rng.randint(1, 9)
    body = ("class Box:\n    def __init__(self):\n        self.items = []" if flip else "class Box:\n    items = []")
    return dict(setup=[body, "b1 = Box()", "b2 = Box()"], actions=[f"b1.items.append({z})", "seen = b2.items"],
                track=["seen"], qs=[("value", "seen", ["[]", repr([z])])])


@tpl("py_classes", "class_counter_rebind")
def _(rng, flip):
    k = rng.randint(1, 4)
    act = "Tally.count += 1" if flip else "t1.count += 1"
    return dict(setup=[f"class Tally:\n    count = {k}", "t1 = Tally()", "t2 = Tally()"],
                actions=[act, "c2 = t2.count", "cc = Tally.count"], track=["c2", "cc"],
                qs=[("value", "c2", [repr(k + 1), repr(k)]), ("value", "cc", [repr(k + 1), repr(k)])])


@tpl("py_classes", "eq_without_hash")
def _(rng, flip):
    extra = "\n    def __hash__(self):\n        return hash(self.v)" if flip else ""
    cls = "class Pt:\n    def __init__(self, v):\n        self.v = v\n    def __eq__(self, o):\n        return self.v == o.v" + extra
    return dict(setup=[cls], actions=[f"s = {{Pt({rng.randint(1, 5)})}}", "n = len(s)"], track=["n"],
                qs=[("exc",), ("value", "n", ["1"])])


@tpl("py_classes", "property_no_setter")
def _(rng, flip):
    setter = "\n    @size.setter\n    def size(self, v):\n        self._s = v" if flip else ""
    cls = "class Shelf:\n    def __init__(self):\n        self._s = 1\n    @property\n    def size(self):\n        return self._s" + setter
    z = rng.randint(2, 9)
    return dict(setup=[cls, "sh = Shelf()"], actions=[f"sh.size = {z}", "v = sh.size"], track=["v"],
                qs=[("exc",), ("value", "v", [repr(z), "1"])])


@tpl("py_classes", "dataclass_mutable_default")
def _(rng, flip):
    dflt = "field(default_factory=list)" if flip else "[]"
    return dict(setup=[], actions=[f"@dataclass\nclass Bag:\n    items: list = {dflt}", "b = Bag()", "n = len(b.items)"],
                track=["n"], qs=[("exc",), ("value", "n", ["0"])])


@tpl("py_classes", "mro_super_chain")
def _(rng, flip):
    order = "(Left, Right)" if not flip else "(Right, Left)"
    src = ("class Base:\n    def tag(self, out):\n        out.append('base')\n"
           "class Left(Base):\n    def tag(self, out):\n        out.append('left')\n        super().tag(out)\n"
           "class Right(Base):\n    def tag(self, out):\n        out.append('right')\n        super().tag(out)\n"
           f"class Both{order}:\n    pass")
    return dict(setup=[src], actions=["out = []", "Both().tag(out)"], track=["out"],
                qs=[("value", "out", [repr(['left', 'base']), repr(['left', 'right', 'base']), repr(['right', 'base'])])])


@tpl("py_classes", "attribute_shadows_method")
def _(rng, flip):
    act = "r.note = 5" if not flip else "r.extra = 5"
    return dict(setup=["class Rec:\n    def note(self):\n        return 'ok'", "r = Rec()"],
                actions=[act, "v = r.note()"], track=["v"], qs=[("exc",), ("value", "v", ["'ok'"])])


@tpl("py_classes", "classmethod_counter")
def _(rng, flip):
    k = rng.randint(2, 4)
    meth = ("    @classmethod\n    def make(cls):\n        cls.made += 1\n        return cls()" if not flip else
            "    def make(self):\n        self.made += 1\n        return self")
    return dict(setup=[f"class Part:\n    made = 0\n{meth}"], actions=[f"ps = [Part.make() for _ in range({k})]" if not flip
                                                                      else f"p = Part()\nps = [p.make() for _ in range({k})]",
                                                                      "m = Part.made"],
                track=["m"], qs=[("value", "m", [repr(k), "0"]), ("exc",)])


# ------------------------------------------------------------------ py_iter_lazy

@tpl("py_iter_lazy", "map_exhausted")
def _(rng, flip):
    xs = [rng.randint(1, 9) for _ in range(3)]
    src = f"list(map(abs, {xs}))" if flip else f"map(abs, {xs})"
    return dict(setup=[], actions=[f"m = {src}", "a = list(m)", "b = list(m)"], track=["b"],
                qs=[("value", "b", [repr(xs)])])


@tpl("py_iter_lazy", "zip_same_iterator")
def _(rng, flip):
    xs = [rng.randint(1, 9) for _ in range(4)]
    act = "pairs = list(zip(it, it))" if not flip else "pairs = list(zip(xs, xs))"
    return dict(setup=[f"xs = {xs}", "it = iter(xs)"], actions=[act], track=["pairs"],
                qs=[("value", "pairs", [repr(list(zip(xs, xs)))])])


@tpl("py_iter_lazy", "groupby_unsorted")
def _(rng, flip):
    s = rng.choice(["aabba", "xyyxx", "ppqpp", "mmnmn"])
    arg = f"sorted({s!r})" if flip else repr(s)
    return dict(setup=[], actions=[f"keys = [k for k, _ in groupby({arg})]"], track=["keys"],
                qs=[("value", "keys", [repr(sorted(set(s)))])])


@tpl("py_iter_lazy", "generator_not_run")
def _(rng, flip):
    z = rng.randint(1, 9)
    use = "list(g)" if flip else "g"
    return dict(setup=["log = []", f"def gen():\n    log.append({z})\n    yield 1"], actions=["g = gen()", f"h = {use}"],
                track=["log"], qs=[("value", "log", [repr([z])])])


@tpl("py_iter_lazy", "filter_none_falsy")
def _(rng, flip):
    xs = rng.choice([[0, 1, "", "a", None, 2], [3, 0, [], "b", 0.0], ["", "x", 0, 5]])
    act = "out = list(filter(None, xs))" if not flip else "out = [x for x in xs if x is not None]"
    return dict(setup=[f"xs = {xs!r}"], actions=[act], track=["out"],
                qs=[("value", "out", [repr([x for x in xs if x is not None]), repr([x for x in xs if x])])])


@tpl("py_iter_lazy", "dictcomp_duplicate_keys")
def _(rng, flip):
    pairs = [("a", 1), ("b", 2), ("a", 3)] if not flip else [("a", 1), ("b", 2), ("c", 3)]
    return dict(setup=[f"pairs = {pairs!r}"], actions=["d = {k: v for k, v in pairs}", "n = len(d)"],
                track=["d", "n"], qs=[("value", "n", ["3"]), ("value", "d", [repr(dict(pairs))])])


@tpl("py_iter_lazy", "islice_consumes")
def _(rng, flip):
    xs = list(range(1, 7))
    act = "first = list(islice(it, 2))" if not flip else "first = xs[:2]"
    return dict(setup=[f"xs = {xs}", "it = iter(xs)"], actions=[act, "rest = list(it)"], track=["rest"],
                qs=[("value", "rest", [repr(xs[2:]), repr(xs)])])


@tpl("py_iter_lazy", "sorted_key_stable")
def _(rng, flip):
    ws = rng.sample(["bb", "a", "cc", "d", "ee", "f"], 4)
    key = "len" if not flip else "None"
    return dict(setup=[f"ws = {ws!r}"], actions=[f"out = sorted(ws, key={key})"], track=["out"],
                qs=[("value", "out", [repr(sorted(ws)), repr(sorted(ws, key=len))])])


# ------------------------------------------------------------------ py_files_io

@tpl("py_files_io", "read_before_close")
def _(rng, flip):
    fn, w = rng.choice(FILES), rng.choice(["alpha", "beta", "gamma"])
    acts = [f"f = open({fn!r}, 'w')", f"f.write({w!r})"] + (["f.close()"] if flip else []) + [f"seen = open({fn!r}).read()"]
    return dict(setup=[], actions=acts, track=["seen"], qs=[("value", "seen", [repr(w), "''"])], files=True)


@tpl("py_files_io", "append_vs_write")
def _(rng, flip):
    fn, a, b = rng.choice(FILES), rng.choice(["one", "two"]), rng.choice(["three", "four"])
    mode = "'a'" if flip else "'w'"
    return dict(setup=[f"with open({fn!r}, 'w') as f:\n    f.write({a + chr(10)!r})"],
                actions=[f"with open({fn!r}, {mode}) as f:\n    f.write({b + chr(10)!r})"], track=[],
                qs=[("file", fn, [repr(a + chr(10) + b + chr(10)), repr(b + chr(10))])], files=True)


@tpl("py_files_io", "wplus_no_seek")
def _(rng, flip):
    fn, w = rng.choice(FILES), rng.choice(["delta", "omega"])
    acts = [f"f = open({fn!r}, 'w+')", f"f.write({w!r})"] + (["f.seek(0)"] if flip else []) + ["got = f.read()", "f.close()"]
    return dict(setup=[], actions=acts, track=["got"], qs=[("value", "got", [repr(w), "''"])], files=True)


@tpl("py_files_io", "x_mode_existing")
def _(rng, flip):
    fn = rng.choice(FILES)
    setup = [f"with open({fn!r}, 'w') as f:\n    f.write('old')"] if not flip else []
    return dict(setup=setup, actions=[f"with open({fn!r}, 'x') as f:\n    f.write('new')"], track=[],
                qs=[("exc",), ("file", fn, ["'new'", "'old'"])], files=True)


@tpl("py_files_io", "replace_overwrites")
def _(rng, flip):
    a, b = rng.sample(FILES, 2)
    setup = [f"with open({a!r}, 'w') as f:\n    f.write('A')"] + ([f"with open({b!r}, 'w') as f:\n    f.write('B')"] if not flip else [])
    return dict(setup=setup, actions=[f"os.replace({a!r}, {b!r})"], track=[],
                qs=[("file", b, ["'B'", "'A'"]), ("file_exists", a)], files=True)


@tpl("py_files_io", "mkdir_parents")
def _(rng, flip):
    d = rng.choice(["build/out", "cache/v1", "data/raw"])
    arg = "parents=True" if flip else ""
    return dict(setup=[], actions=[f"Path({d!r}).mkdir({arg})", f"open({d + '/' + rng.choice(FILES)!r}, 'w').close()"],
                track=[], qs=[("exc",), ("file_exists", d.split('/')[0])], files=True)


@tpl("py_files_io", "with_exception_partial")
def _(rng, flip):
    fn = rng.choice(FILES)
    bad = "1 / 0" if not flip else "1 / 1"
    return dict(setup=[], actions=[f"with open({fn!r}, 'w') as f:\n    f.write('head\\n')\n    {bad}\n    f.write('tail\\n')"],
                track=[], qs=[("exc",), ("file", fn, [repr('head\ntail\n'), "''"])], files=True)


@tpl("py_files_io", "remove_missing")
def _(rng, flip):
    fn = rng.choice(FILES)
    setup = [f"open({fn!r}, 'w').close()"] if flip else []
    return dict(setup=setup, actions=[f"os.remove({fn!r})", "done = True"], track=["done"],
                qs=[("exc",), ("file_exists", fn)], files=True)


FAMILIES = sorted({f for f, _ in T.values()})
FAMILY_TEMPLATES = {fam: sorted(n for n, (f, _) in T.items() if f == fam) for fam in FAMILIES}


# ------------------------------------------------------------------ execution, questions, rows

def ensure_harness():
    os.makedirs("/dev/shm/fx", exist_ok=True)
    os.chmod("/dev/shm/fx", 0o711)
    if not os.path.exists(HARNESS_PATH) or open(HARNESS_PATH).read() != HARNESS:
        tmp = HARNESS_PATH + f".{os.getpid()}"
        with open(tmp, "w") as f:
            f.write(HARNESS)
        os.chmod(tmp, 0o644)
        os.replace(tmp, HARNESS_PATH)


def execute(spec, tag):
    ensure_harness()
    for code in spec["setup"] + spec["actions"]:
        if not safe(code):
            return None
    box = make_box(tag)
    try:
        chown_tree(box)
        rc, out, err = run_unprivileged(["/usr/bin/python3", "-I", "-S", HARNESS_PATH], cwd=box, timeout=4,
                                        stdin_text=json.dumps({k: spec[k] for k in ("setup", "actions", "track")}))
        if rc != 0 or not out.strip():
            return None
        return json.loads(out.strip().splitlines()[-1])
    finally:
        remove_box(box)


def render_state(spec, snap):
    s = ("Already run:\n" + "\n".join(spec["setup"]) + "\n" if spec["setup"] else "Nothing has run yet.\n")
    vs = [f"{v} = {snap['vars'][v]}" for v in spec["track"] if snap["vars"].get(v) is not None]
    s += "Values now: " + ("; ".join(vs) if vs else "(none of the names below is defined yet)")
    if spec.get("files"):
        fs = snap["files"]
        s += "\nFiles in the working folder: " + ("; ".join(f"{n}: {c!r}" if c != "<folder>" else f"{n}/ (folder)"
                                                           for n, c in fs.items()) if fs else "(none)")
    return s


def golds(qs, res):
    out = {}
    raised = next((l[1] for l in res["log"] if l[0] == "raise"), None)
    for qq in qs:
        if qq[0] == "value":
            v = res["after"]["vars"].get(qq[1])
            out[("value", qq[1])] = v if v is not None else "(not defined)"
        elif qq[0] == "raises":
            out[("raises", None)] = raised is not None
        elif qq[0] == "exc":
            out[("exc", None)] = raised or "none"
        elif qq[0] == "file":
            c = res["after"]["files"].get(qq[1])
            out[("file", qq[1])] = repr(c) if c is not None and c != "<folder>" else "(no such file)"
        elif qq[0] == "file_exists":
            out[("file_exists", qq[1])] = qq[1] in res["after"]["files"]
    return out


def make_items(seed, allowed=None):
    names = sorted(n for n in T if allowed is None or n in allowed)
    if not names:
        return [], {"skipped": 1}
    rng = random.Random(stable_seed("fx_py", T[names[0]][0], seed))
    name = rng.choice(names)
    flip_first = rng.random() < 0.5
    st = rng.getstate()
    spec_a = T[name][1](rng, flip_first)
    rng.setstate(st)
    spec_b = T[name][1](rng, not flip_first)
    tag = f"fxp{os.getpid()}_{seed}"
    ra, rb = execute(spec_a, tag), execute(spec_b, tag + "t")
    if ra is None:
        return [], {"exec_fail": 1}
    qs = spec_a["qs"]
    ga = golds(qs, ra)
    twin = rb is not None and golds(qs, rb) != ga
    inst = [("a", spec_a, ra)] + ([("b", spec_b, rb)] if twin else [])
    rows = []
    for side, sp, res in inst:
        g = golds(qs, res)
        g_other = golds(qs, rb if side == "a" and twin else ra)
        floor = world_floor(RULES, render_state(sp, res["before"]), sp["actions"])
        what = "; ".join(f"statement {i + 1}: " + ("ok" if l[0] == "ok" else f"raised {l[1]}") +
                         (f", printed {l[2]!r}" if l[2] else "") for i, l in enumerate(res["log"]))
        if len(res["log"]) < len(sp["actions"]):
            what += "; the later statements did not run"
        ceiling = world_ceiling(RULES, render_state(sp, res["after"]), what + ".")
        for qq in qs:
            key = (qq[0], qq[1] if len(qq) > 1 else None)
            gold = g[key]
            if qq[0] == "value":
                alts = list(qq[2]) if len(qq) > 2 else []
                opts = list(dict.fromkeys([gold] + alts + [g_other[key], "(not defined)"]))[:6]
                qd = choice(f"After these statements, what is the value of {qq[1]}?", opts)
                fv = alts[0] if alts else None
            elif qq[0] == "exc":
                pool_ = [e for e in EXCS if e != gold]
                opts = ["none"] + sorted(set([gold] + rng.sample(pool_, 3)) - {"none"})
                qd = choice("Which exception stops the program (none if the program runs to the end)?", opts)
                fv = "none"
            elif qq[0] == "file":
                alts = list(qq[2]) if len(qq) > 2 else []
                opts = list(dict.fromkeys([gold] + alts + [g_other[key], "(no such file)"]))[:6]
                qd = choice(f"After these statements, what does the file {qq[1]} contain?", opts)
                fv = alts[0] if alts else None
            elif qq[0] == "file_exists":
                qd = yes_no(f"After these statements, does {qq[1]} exist in the working folder?")
                fv = None
            else:
                continue
            known0 = qq[0] == "value" and res["before"]["vars"].get(qq[1]) is not None
            g0 = res["before"]["vars"].get(qq[1]) if known0 else None
            if qq[0] == "file":
                c0 = res["before"]["files"].get(qq[1])
                known0, g0 = True, (repr(c0) if c0 is not None and c0 != "<folder>" else "(no such file)")
            if qq[0] == "file_exists":
                known0, g0 = True, qq[1] in res["before"]["files"]
            if known0 and qd["type"] == "choice" and g0 not in qd["criteria"]:
                known0, g0 = False, None
            rows.append(row(world="rx_py", family="python", template=name, qtype=qq[0], steps=len(sp["actions"]),
                            question=qd, gold=gold if qd["type"] == "choice" else bool(gold), gold0=g0, known0=known0,
                            floor=floor, ceiling=ceiling,
                            rid=f"fxpy-{seed}-{side}-{qq[0]}-{qq[1] if len(qq) > 1 else ''}",
                            twin=(f"fxpy-{seed}-{'b' if side == 'a' else 'a'}" if twin else None), face=fv,
                            struct={"setup": sp["setup"], "actions": sp["actions"], "track": sp["track"],
                                    "log": res["log"]}))
    return rows, {"scenarios": 1, "twins": int(twin)}
