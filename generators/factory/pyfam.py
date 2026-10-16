"""WS-F Python family: generated short programs where the usual reading and the real semantics can differ (aliasing,
mutable defaults, late binding, floor division, banker's rounding, exhausted generators, ...), executed for real by
CPython 3.12 as the unprivileged user. Statement-level world layout: state = values and definitions, actions = statements.
No benchmark code: every program is assembled from the templates below with random names and values."""
from __future__ import annotations

import ast
import json
import os
import random
import re

from common import BOX_ROOT, choice, make_box, remove_box, row, run_unprivileged, stable_seed, world_ceiling, \
    world_floor, yes_no, chown_tree

RULES = ("Python 3.12 in a fresh interpreter. The statements below run in order in one program. If a statement raises an "
         "exception that nothing catches, the program stops there and the later statements do not run.")
NAMES = ["crate", "bins", "tally", "queue", "stack", "ledger", "pins", "marks", "rows", "cells", "slots", "pegs", "notes",
         "tiles", "beads", "chips", "cards", "keys", "tags", "parts"]
EXCS = ["KeyError", "IndexError", "TypeError", "ValueError", "ZeroDivisionError", "RuntimeError", "UnboundLocalError",
        "AttributeError", "NameError", "StopIteration"]
HARNESS = r'''
import io, json, sys, contextlib
spec = json.loads(sys.stdin.read())
ns = {"__name__": "__main__"}
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
    return out
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
print(json.dumps({"before": before, "after": snap(), "log": log}))
'''
FORBIDDEN = {"__import__", "eval", "exec", "compile", "globals", "locals", "vars", "getattr", "setattr", "delattr",
             "input", "breakpoint", "exit", "quit", "help", "memoryview", "__builtins__"}


def safe(code: str) -> bool:
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
    return True


def vals(rng, k, lo=1, hi=9):
    return [rng.randint(lo, hi) for _ in range(k)]


# Each template: fn(rng, flip) -> dict(setup, actions, track, qs) where qs are ("value", var, [naive alts]),
# ("raises",), ("exc",), ("printed", k, [naive alts]). flip=True gives the minimal twin where the trap does not apply.
T = {}


def tpl(name):
    def deco(fn):
        T[name] = fn
        return fn
    return deco


@tpl("alias_append")
def _(rng, flip):
    a, b = rng.sample(NAMES, 2)
    xs, z = vals(rng, 2), rng.randint(10, 20)
    cp = rng.choice([f"{a}[:]", f"list({a})", f"{a}.copy()"])
    return dict(setup=[f"{a} = {xs}"], actions=[f"{b} = {cp if flip else a}", f"{b}.append({z})"], track=[a, b],
                qs=[("value", a, [repr(xs)])])


@tpl("iadd_vs_add")
def _(rng, flip):
    a, b = rng.sample(NAMES, 2)
    xs, z = vals(rng, 2), rng.randint(10, 20)
    op = f"{b} = {b} + [{z}]" if flip else f"{b} += [{z}]"
    return dict(setup=[f"{a} = {xs}", f"{b} = {a}"], actions=[op], track=[a, b], qs=[("value", a, [repr(xs)])])


@tpl("shallow_nested")
def _(rng, flip):
    a, b = rng.sample(NAMES, 2)
    x, y, z = vals(rng, 3)
    cp = "[list(r) for r in " + a + "]" if flip else f"{a}.copy()"
    return dict(setup=[f"{a} = [[{x}], [{y}]]"], actions=[f"{b} = {cp}", f"{b}[0].append({z})"], track=[a],
                qs=[("value", a, [repr([[x], [y]])])])


@tpl("mutable_default")
def _(rng, flip):
    f, acc = rng.choice(["add", "push", "keep", "note"]), rng.choice(["acc", "bag", "box"])
    x, y = vals(rng, 2)
    head = f"def {f}(v, {acc}=None):\n    if {acc} is None:\n        {acc} = []\n" if flip else f"def {f}(v, {acc}=[]):\n"
    body = f"    {acc}.append(v)\n    return {acc}"
    return dict(setup=[head + body], actions=[f"r1 = {f}({x})", f"r2 = {f}({y})"], track=["r1", "r2"],
                qs=[("value", "r2", [repr([y])]), ("value", "r1", [repr([x])])])


@tpl("late_binding")
def _(rng, flip):
    k = rng.randint(2, 5)
    n = rng.randint(3, 4)
    lam = f"lambda i=i: i * {k}" if flip else f"lambda: i * {k}"
    return dict(setup=[], actions=[f"fs = [{lam} for i in range({n})]", "out = [g() for g in fs]"], track=["out"],
                qs=[("value", "out", [repr([i * k for i in range(n)]), repr([(n - 1) * k] * n)])])


@tpl("floordiv_neg")
def _(rng, flip):
    a, b = rng.randint(5, 19), rng.randint(2, 4)
    if a % b == 0:
        a += 1
    sign = "" if flip else "-"
    q_naive = (a // b) if flip else -(a // b)
    r_naive = (a % b) if flip else -(a % b)
    return dict(setup=[], actions=[f"q = {sign}{a} // {b}", f"r = {sign}{a} % {b}"], track=["q", "r"],
                qs=[("value", "q", [repr(q_naive)]), ("value", "r", [repr(r_naive)])])


@tpl("round_half")
def _(rng, flip):
    n = rng.choice([0, 2, 4, 6]) + (1 if flip else 0)
    return dict(setup=[], actions=[f"v = round({n}.5)", f"w = round({n + 1}.5)"], track=["v", "w"],
                qs=[("value", "v", [repr(n + 1)]), ("value", "w", [repr(n + 2)])])


@tpl("int_trunc")
def _(rng, flip):
    x = rng.randint(1, 8) + rng.choice([0.3, 0.7])
    sign = "" if flip else "-"
    naive = round(x) if flip else -round(x)
    return dict(setup=[], actions=[f"t = int({sign}{x})"], track=["t"], qs=[("value", "t", [repr(naive)])])


@tpl("float_eq")
def _(rng, flip):
    a, b = rng.choice([(0.1, 0.2), (0.1, 0.7), (0.3, 0.6)]) if not flip else rng.choice([(0.5, 0.25), (0.25, 0.25), (1.5, 0.5)])
    return dict(setup=[], actions=[f"same = {a} + {b} == {round(a + b, 10)}"], track=["same"],
                qs=[("value", "same", ["True", "False"])])


@tpl("strip_chars")
def _(rng, flip):
    w = rng.choice(["banana", "abacab", "cabbage", "baobab"])
    arg = rng.choice(["ab", "ba", "abc"])
    s = f"{arg}{w}{arg}" if not flip else f"xy{w}yx"
    naive = s[len(arg):-len(arg)] if not flip else s
    return dict(setup=[f"s = {s!r}"], actions=[f"t = s.strip({arg!r})"], track=["t"], qs=[("value", "t", [repr(naive)])])


@tpl("split_spaces")
def _(rng, flip):
    words = rng.sample(["alpha", "beta", "gamma", "delta", "eps"], 3)
    s = "  ".join(words) if not flip else " ".join(words)
    return dict(setup=[f"s = {s!r}"], actions=["parts = s.split(' ')", "n = len(parts)"], track=["n", "parts"],
                qs=[("value", "n", ["3", "5"])])


@tpl("list_mult_alias")
def _(rng, flip):
    r, c = rng.randint(2, 3), rng.randint(2, 3)
    mk = f"[[0] * {c} for _ in range({r})]" if flip else f"[[0] * {c}] * {r}"
    good = [[1] + [0] * (c - 1)] + [[0] * c for _ in range(r - 1)]
    bad = [[1] + [0] * (c - 1) for _ in range(r)]
    return dict(setup=[], actions=[f"grid = {mk}", "grid[0][0] = 1"], track=["grid"],
                qs=[("value", "grid", [repr(good), repr(bad)])])


@tpl("sort_returns_none")
def _(rng, flip):
    a = rng.choice(NAMES)
    xs = vals(rng, 4)
    act = f"res = sorted({a})" if flip else f"res = {a}.sort()"
    return dict(setup=[f"{a} = {xs}"], actions=[act], track=["res", a],
                qs=[("value", "res", [repr(sorted(xs)), "None"]),
                    ("value", a, [repr(xs) if flip else repr(sorted(xs)), repr(sorted(xs)) if flip else repr(xs)])])


@tpl("tuple_iadd")
def _(rng, flip):
    x, y = vals(rng, 2)
    act = f"t[0].extend([{y}])" if flip else f"t[0] += [{y}]"
    return dict(setup=[f"t = ([{x}],)"], actions=[act, "done = True"], track=["t", "done"],
                qs=[("raises",), ("value", "t", [repr(([x, y],)), repr(([x],))])])


@tpl("gen_exhaust")
def _(rng, flip):
    a = rng.choice(NAMES)
    xs = vals(rng, 3)
    mk = f"g = [x * 2 for x in {a}]" if flip else f"g = (x * 2 for x in {a})"
    return dict(setup=[f"{a} = {xs}"], actions=[mk, "first = list(g)", "second = list(g)"], track=["second"],
                qs=[("value", "second", [repr([x * 2 for x in xs]), "[]"])])


@tpl("dict_iter_mutate")
def _(rng, flip):
    ks = rng.sample(["ash", "elm", "oak", "fir", "yew"], 3)
    d = {k: i for i, k in enumerate(ks)}
    loop = "for k in list(d):\n    d[k + '2'] = 0" if flip else "for k in d:\n    d[k + '2'] = 0"
    return dict(setup=[f"d = {d!r}"], actions=[loop, "n = len(d)"], track=["n"],
                qs=[("raises",), ("exc",), ("value", "n", [repr(2 * len(ks)), repr(len(ks) + 1)])])


@tpl("remove_while_iter")
def _(rng, flip):
    tgt = rng.randint(1, 5)
    other = [rng.randint(6, 9) for _ in range(2)]
    xs = [other[0], tgt, tgt, other[1]] if not flip else [other[0], tgt, other[1], tgt]
    loop = f"for x in xs:\n    if x == {tgt}:\n        xs.remove(x)"
    return dict(setup=[f"xs = {xs}"], actions=[loop], track=["xs"], qs=[("value", "xs", [repr([x for x in xs if x != tgt])])])


@tpl("finally_return")
def _(rng, flip):
    a, b = vals(rng, 2)
    if a == b:
        b = a + 1
    fin = f"    finally:\n        print('done')" if flip else f"    finally:\n        return {b}"
    return dict(setup=[f"def f():\n    try:\n        return {a}\n{fin}"], actions=["v = f()"], track=["v"],
                qs=[("value", "v", [repr(a), repr(b)])])


@tpl("unbound_local")
def _(rng, flip):
    a = rng.randint(1, 9)
    body = "    global c\n    c += 1\n    return c" if flip else "    c += 1\n    return c"
    return dict(setup=[f"c = {a}", "def bump():\n" + body], actions=["r = bump()"], track=["r", "c"],
                qs=[("raises",), ("exc",), ("value", "r", [repr(a + 1)])])


@tpl("and_or_value")
def _(rng, flip):
    a = rng.choice(["''", "0", "[]", "None"]) if not flip else rng.choice(["'x'", "3", "[1]"])
    b = rng.choice(["'fallback'", "7", "[9]"])
    return dict(setup=[], actions=[f"v = {a} or {b}", f"w = {a} and {b}"], track=["v", "w"],
                qs=[("value", "v", ["True", "False"]), ("value", "w", ["False", "True"])])


@tpl("key_error")
def _(rng, flip):
    ks = rng.sample(["ash", "elm", "oak", "fir"], 2)
    miss = rng.choice(["yew", "pine"]) if not flip else ks[0]
    return dict(setup=[f"d = {{'{ks[0]}': 1, '{ks[1]}': 2}}"], actions=[f"x = d.get('{ks[1]}')", f"x = d['{miss}']", "y = 1"],
                track=["x", "y"], qs=[("raises",), ("exc",), ("value", "x", ["None", "2"])])


@tpl("slice_vs_index")
def _(rng, flip):
    xs = vals(rng, 3)
    act = "v = xs[5]" if not flip else "v = xs[5:]"
    return dict(setup=[f"xs = {xs}"], actions=[act], track=["v"], qs=[("raises",), ("exc",), ("value", "v", ["None", "[]"])])


@tpl("int_parse")
def _(rng, flip):
    s = rng.choice(["'3.5'", "'4,0'", "' 7x'"]) if not flip else rng.choice(["' 12 '", "'0042'", "'-8'"])
    return dict(setup=[], actions=[f"n = int({s})"], track=["n"], qs=[("raises",), ("exc",)])


@tpl("str_int_concat")
def _(rng, flip):
    n = rng.randint(2, 9)
    act = f"label = 'item' + {n}" if not flip else f"label = 'item' * {n}"
    return dict(setup=[], actions=[act], track=["label"], qs=[("raises",), ("exc",)])


@tpl("remove_first_only")
def _(rng, flip):
    x = rng.randint(1, 5)
    xs = [x, rng.randint(6, 9), x] if not flip else [x, rng.randint(6, 9), rng.randint(10, 12)]
    return dict(setup=[f"xs = {xs}"], actions=[f"xs.remove({x})"], track=["xs"],
                qs=[("value", "xs", [repr([v for v in xs if v != x])])])


@tpl("dict_merge_order")
def _(rng, flip):
    k = rng.choice(["ash", "elm", "oak"])
    a = rng.randint(1, 5)
    b = a + rng.randint(1, 5)
    expr = "d1 | d2" if not flip else "d2 | d1"
    return dict(setup=[f"d1 = {{'{k}': {a}}}", f"d2 = {{'{k}': {b}}}"], actions=[f"m = {expr}"], track=["m"],
                qs=[("value", "m", [repr({k: a}), repr({k: b})])])


@tpl("range_stop")
def _(rng, flip):
    a, b, s = rng.randint(0, 3), rng.randint(6, 10), rng.choice([2, 3])
    expr = f"list(range({a}, {b}, {s}))" if not flip else f"list(range({a}, {b} + 1, {s}))"
    return dict(setup=[], actions=[f"r = {expr}"], track=["r"], qs=[("value", "r", [repr(list(range(a, b + 1, s))),
                                                                                    repr(list(range(a, b, s)))])])


@tpl("str_compare_numbers")
def _(rng, flip):
    a, b = rng.choice([("'10'", "'9'"), ("'100'", "'25'"), ("'7'", "'30'")])
    num = str(max(int(a.strip("'")), int(b.strip("'"))))
    if flip:
        a, b = a.strip("'"), b.strip("'")
    naive = repr(num) if not flip else num
    return dict(setup=[], actions=[f"m = max([{a}, {b}])"], track=["m"], qs=[("value", "m", [naive])])


@tpl("keys_view_live")
def _(rng, flip):
    ks = rng.sample(["ash", "elm", "oak", "fir"], 2)
    mk = "k = d.keys()" if not flip else "k = list(d.keys())"
    return dict(setup=[f"d = {{'{ks[0]}': 1, '{ks[1]}': 2}}"], actions=[mk, "d['new'] = 3", "n = len(k)"], track=["n"],
                qs=[("value", "n", ["2", "3"])])


@tpl("file_mode_w")
def _(rng, flip):
    a, b = rng.choice(["north", "cedar", "flint"]), rng.choice(["gale", "jade", "inlet"])
    mode = "a" if flip else "w"
    acts = [f"with open('log.txt', 'w') as fh:\n    fh.write('{a}')", f"with open('log.txt', '{mode}') as fh:\n    fh.write('{b}')",
            "with open('log.txt') as fh:\n    text = fh.read()"]
    return dict(setup=[], actions=acts, track=["text"], qs=[("value", "text", [repr(a + b), repr(b)])])


@tpl("print_sep")
def _(rng, flip):
    a, b = rng.choice(["x", "y"]), rng.choice(["p", "q"])
    act = f"print('{a}', '{b}', sep='')" if not flip else f"print('{a}', '{b}')"
    return dict(setup=[], actions=[act], track=[], qs=[("printed", 1, [repr(f"{a} {b}\n"), repr(f"{a}{b}\n")])])


@tpl("zip_truncate")
def _(rng, flip):
    xs, ys = vals(rng, 3), vals(rng, 2 if not flip else 3)
    return dict(setup=[f"xs = {xs}", f"ys = {ys}"], actions=["pairs = list(zip(xs, ys))", "n = len(pairs)"], track=["n"],
                qs=[("value", "n", ["3", "2"])])


@tpl("chained_compare")
def _(rng, flip):
    x = rng.randint(1, 9)
    lo, hi = (x + 1, x + 5) if not flip else (x - 1, x + 3)
    return dict(setup=[f"x = {x}"], actions=[f"ok = {lo} < x < {hi}"], track=["ok"], qs=[("value", "ok", ["True", "False"])])


@tpl("string_immutable_method")
def _(rng, flip):
    w = rng.choice(["cedar", "flint", "jade"])
    act = "s.upper()" if not flip else "s = s.upper()"
    return dict(setup=[f"s = {w!r}"], actions=[act], track=["s"], qs=[("value", "s", [repr(w.upper()), repr(w)])])


@tpl("default_arg_eval_time")
def _(rng, flip):
    a, b = rng.randint(1, 5), rng.randint(6, 9)
    head = f"def get(v=None):\n    if v is None:\n        v = base\n    return v" if flip else "def get(v=base):\n    return v"
    return dict(setup=[f"base = {a}", head], actions=[f"base = {b}", "r = get()"], track=["r"],
                qs=[("value", "r", [repr(b), repr(a)])])


HARNESS_PATH = "/tmp/rxF/py_harness.py"


def ensure_harness():
    os.makedirs("/tmp/rxF", exist_ok=True)
    os.chmod("/tmp/rxF", 0o711)
    if not os.path.exists(HARNESS_PATH) or open(HARNESS_PATH).read() != HARNESS:
        with open(HARNESS_PATH, "w") as f:
            f.write(HARNESS)
        os.chmod(HARNESS_PATH, 0o644)


def execute(spec, tag):
    ensure_harness()
    for code in spec["setup"] + spec["actions"]:
        if not safe(code):
            return None
    box = make_box(tag)
    try:
        chown_tree(box)
        rc, out, err = run_unprivileged(["/usr/bin/python3", "-I", "-S", HARNESS_PATH], cwd=box, timeout=4,
                                        stdin_text=json.dumps(spec))
        if rc != 0 or not out.strip():
            return None
        return json.loads(out.strip().splitlines()[-1])
    finally:
        remove_box(box)


def render_vals(snap, track):
    parts = [f"{v} = {snap[v]}" for v in track if snap.get(v) is not None]
    return "; ".join(parts) if parts else "(none of the names below is defined yet)"


def golds(qs, res):
    out = {}
    raised = next((l[1] for l in res["log"] if l[0] == "raise"), None)
    for qq in qs:
        if qq[0] == "value":
            v = res["after"].get(qq[1])
            out[("value", qq[1])] = v if v is not None else "(not defined)"
        elif qq[0] == "raises":
            out[("raises", None)] = raised is not None
        elif qq[0] == "exc":
            out[("exc", None)] = raised or "none"
        elif qq[0] == "printed":
            k = qq[1]
            out[("printed", k)] = repr(res["log"][k - 1][2]) if len(res["log"]) >= k else "(the statement did not run)"
    return out


def make_items(seed):
    rng = random.Random(stable_seed("rx_py", seed))
    name = rng.choice(sorted(T))
    flip_first = rng.random() < 0.5
    st = rng.getstate()
    spec_a = T[name](rng, flip_first)
    rng.setstate(st)
    spec_b = T[name](rng, not flip_first)
    tag = f"p{os.getpid()}_{seed}"
    ra = execute(spec_a, tag)
    rb = execute(spec_b, tag + "t")
    if ra is None:
        return [], {"exec_fail": 1}
    qs = spec_a["qs"]
    ga = golds(qs, ra)
    twin = rb is not None and golds(qs, rb) != ga
    inst = [("a", spec_a, ra)] + ([("b", spec_b, rb)] if twin else [])
    rows = []
    for side, sp, res in inst:
        g = golds(qs, res)
        state = ("Already run:\n" + "\n".join(sp["setup"]) + "\n" if sp["setup"] else "Nothing has run yet.\n")
        state += "Values now: " + render_vals(res["before"], sp["track"])
        floor = world_floor(RULES, state, sp["actions"])
        what = "; ".join(f"statement {i + 1}: " + ("ok" if l[0] == "ok" else f"raised {l[1]}") +
                         (f", printed {l[2]!r}" if l[2] else "") for i, l in enumerate(res["log"]))
        if len(res["log"]) < len(sp["actions"]):
            what += "; the later statements did not run"
        ceiling = world_ceiling(RULES, "Values: " + render_vals(res["after"], sp["track"]), what + ".")
        for qq in qs:
            key = (qq[0], qq[1] if len(qq) > 1 else None)
            gold = g[key]
            if qq[0] == "value":
                alts = list(qq[2]) if len(qq) > 2 else []
                other = rb if side == "a" and rb else ra
                o = golds(qs, other)[key] if other else None
                opts = list(dict.fromkeys([gold] + alts + ([o] if o else []) + ["(not defined)"]))[:6]
                qd = choice(f"After these statements, what is the value of {qq[1]}?", opts)
                fv = alts[0] if alts else None
            elif qq[0] == "raises":
                qd = yes_no("Does any statement raise an exception that is not caught?")
                fv = False
            elif qq[0] == "exc":
                pool_ = [e for e in EXCS if e != gold]
                opts = ["none"] + sorted(set([gold] + rng.sample(pool_, 3)) - {"none"})
                qd = choice("Which exception stops the program (none if the program runs to the end)?", opts)
                fv = "none"
            else:
                alts = list(qq[2])
                opts = list(dict.fromkeys([gold] + alts + ["''"]))[:5]
                qd = choice(f"What does statement {qq[1]} print?", opts)
                fv = alts[0]
            known0 = qq[0] == "value" and res["before"].get(qq[1]) is not None
            g0 = res["before"].get(qq[1]) if known0 else None
            if known0 and g0 not in qd["criteria"]:
                known0, g0 = False, None
            rows.append(row(world="rx_py", family="python", template=name, qtype=qq[0], steps=len(sp["actions"]),
                            question=qd, gold=gold if qd["type"] == "choice" else bool(gold), gold0=g0, known0=known0,
                            floor=floor, ceiling=ceiling, rid=f"rxpy-{seed}-{side}-{qq[0]}-{qq[1] if len(qq) > 1 else ''}",
                            twin=(f"rxpy-{seed}-{'b' if side == 'a' else 'a'}" if twin else None), face=fv,
                            struct={"setup": sp["setup"], "actions": sp["actions"], "track": sp["track"], "log": res["log"]}))
    return rows, {"scenarios": 1, "twins": int(twin)}
