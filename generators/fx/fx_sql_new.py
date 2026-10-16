"""WS-FX new SQLite families (SPEC.md + Addendum 2): sql_triggers (held out: INSTEAD OF triggers, RAISE(IGNORE / FAIL /
ROLLBACK), trigger chains, recursive triggers; none of WS-F's trigger kinds), sql_views_check_generated (generated
columns, STRICT tables, partial unique indexes, writes into views, CHECK), sql_collation_affinity (NOCASE, type affinity,
LIKE vs GLOB, integer division, text in arithmetic). Every template is a small schema, rows, statements and a flip twin;
the truth is SQLite 3.45 (in memory, one connection, autocommit unless BEGIN), as in WS-F's SQL family."""
from __future__ import annotations

import random
import re
import sqlite3

from common import choice, row, stable_seed, world_ceiling, world_floor, yes_no

RULES = ("An SQLite 3.45 database used by a small service. Each numbered SQL statement is sent on its own, in order, over "
         "one connection (autocommit unless a BEGIN opened a transaction). If a statement raises an error it changes "
         "nothing beyond what SQLite itself keeps, and the next statement is still sent.")
ITEMS = ["basil", "thyme", "mint", "sage", "dill", "chive", "fennel", "cumin", "anise", "sorrel"]
PLACES = ["Ridge", "Harbor", "Quarry", "Summit", "Dune", "Mesa", "Cove", "Glade"]
T = {}


def tpl(family, name):
    def deco(fn):
        T[name] = (family, fn)
        return fn
    return deco


def lit(v):
    return "NULL" if v is None else ("'" + v.replace("'", "''") + "'" if isinstance(v, str) else str(v))


def ins(table, cols, rows):
    return [f"INSERT INTO {table}({', '.join(cols)}) VALUES ({', '.join(lit(x) for x in r)});" for r in rows]


# ------------------------------------------------------------------ sql_triggers (held out)

@tpl("sql_triggers", "instead_of_view_insert")
def _(rng, flip):
    names = rng.sample(ITEMS, 3)
    schema = ["CREATE TABLE stock (id INTEGER PRIMARY KEY, name TEXT, qty INTEGER);",
              "CREATE VIEW stock_names AS SELECT id, name FROM stock;"]
    trig = [] if flip else ["CREATE TRIGGER stock_names_ins INSTEAD OF INSERT ON stock_names\nBEGIN\n  INSERT INTO stock(name, qty) "
                            "VALUES (upper(new.name), 1);\nEND;"]
    new = rng.choice([x for x in ITEMS if x not in names])
    return dict(schema=schema, rows=ins("stock", ["id", "name", "qty"], [[i + 1, n, rng.randint(2, 6)] for i, n in enumerate(names)]),
                late=trig, stmts=[f"INSERT INTO stock_names(name) VALUES ({lit(new)});"],
                qs=[("fails", 1), ("rows", "stock"), ("value", ("stock", 4, "name"))])


@tpl("sql_triggers", "raise_ignore_vs_abort")
def _(rng, flip):
    kind = "ABORT, 'negative'" if flip else "IGNORE"
    names = rng.sample(ITEMS, 4)
    return dict(schema=["CREATE TABLE stock (id INTEGER PRIMARY KEY, name TEXT, qty INTEGER);"],
                rows=ins("stock", ["id", "name", "qty"], [[i + 1, n, rng.randint(1, 5)] for i, n in enumerate(names[:2])]),
                late=[f"CREATE TRIGGER no_negative BEFORE INSERT ON stock WHEN new.qty < 0\nBEGIN\n  SELECT RAISE({kind});\nEND;"],
                stmts=[f"INSERT INTO stock(name, qty) VALUES ({lit(names[2])}, -{rng.randint(1, 4)});",
                       f"INSERT INTO stock(name, qty) VALUES ({lit(names[3])}, {rng.randint(1, 4)});"],
                qs=[("fails", 1), ("rows", "stock")])


@tpl("sql_triggers", "raise_rollback_txn")
def _(rng, flip):
    kind = "ABORT, 'blocked'" if flip else "ROLLBACK, 'blocked'"
    a, b = rng.sample(ITEMS, 2)
    return dict(schema=["CREATE TABLE orders (id INTEGER PRIMARY KEY, item TEXT, qty INTEGER);"],
                rows=ins("orders", ["id", "item", "qty"], [[1, rng.choice(ITEMS), 2]]),
                late=[f"CREATE TRIGGER cap_qty BEFORE INSERT ON orders WHEN new.qty > 9\nBEGIN\n  SELECT RAISE({kind});\nEND;"],
                stmts=["BEGIN;", f"INSERT INTO orders(item, qty) VALUES ({lit(a)}, {rng.randint(1, 5)});",
                       f"INSERT INTO orders(item, qty) VALUES ({lit(b)}, {rng.randint(10, 20)});", "COMMIT;"],
                qs=[("fails", 3), ("fails", 4), ("rows", "orders")])


@tpl("sql_triggers", "raise_fail_multirow")
def _(rng, flip):
    kind = "ABORT, 'too high'" if flip else "FAIL, 'too high'"
    n = 4
    qtys = [rng.randint(1, 3) for _ in range(n)]
    lim = rng.randint(2, 3)
    qtys[2] = lim + 2  # only the third row (rowid order) trips the trigger once it gets +1
    return dict(schema=["CREATE TABLE bins (id INTEGER PRIMARY KEY, qty INTEGER);"],
                rows=ins("bins", ["id", "qty"], [[i + 1, q] for i, q in enumerate(qtys)]),
                late=[f"CREATE TRIGGER bin_cap BEFORE UPDATE ON bins WHEN new.qty > {lim + 2}\nBEGIN\n  SELECT RAISE({kind});\nEND;"],
                stmts=["UPDATE bins SET qty = qty + 1;"],
                qs=[("fails", 1), ("value", ("bins", 1, "qty")), ("value", ("bins", 4, "qty"))])


@tpl("sql_triggers", "trigger_chain")
def _(rng, flip):
    k = rng.randint(1, 4)
    late = ["CREATE TRIGGER a_to_b AFTER INSERT ON a\nBEGIN\n  INSERT INTO b(note) VALUES ('from a ' || new.id);\nEND;"]
    if not flip:
        late.append(f"CREATE TRIGGER b_to_c AFTER INSERT ON b\nBEGIN\n  UPDATE c SET total = total + {k};\nEND;")
    return dict(schema=["CREATE TABLE a (id INTEGER PRIMARY KEY, v INTEGER);", "CREATE TABLE b (id INTEGER PRIMARY KEY, note TEXT);",
                        "CREATE TABLE c (id INTEGER PRIMARY KEY, total INTEGER);"],
                rows=ins("c", ["id", "total"], [[1, rng.randint(0, 5)]]), late=late,
                stmts=[f"INSERT INTO a(v) VALUES ({rng.randint(1, 9)});", f"INSERT INTO a(v) VALUES ({rng.randint(1, 9)});"],
                qs=[("value", ("c", 1, "total")), ("rows", "b")])


@tpl("sql_triggers", "recursive_triggers")
def _(rng, flip):
    start, cap = rng.randint(0, 1), rng.randint(3, 5)
    pragma = "PRAGMA recursive_triggers = OFF;" if flip else "PRAGMA recursive_triggers = ON;"
    return dict(schema=["CREATE TABLE counter (id INTEGER PRIMARY KEY, n INTEGER);"],
                rows=ins("counter", ["id", "n"], [[1, start]]),
                late=[f"CREATE TRIGGER bump AFTER UPDATE OF n ON counter WHEN new.n < {cap}\nBEGIN\n  UPDATE counter SET n = n + 1 "
                      "WHERE id = new.id;\nEND;"],
                stmts=[pragma, "UPDATE counter SET n = n + 1 WHERE id = 1;"], qs=[("value", ("counter", 1, "n"))])


# ------------------------------------------------------------------ sql_views_check_generated

@tpl("sql_views_check_generated", "generated_stored")
def _(rng, flip):
    rows = [[i + 1, rng.randint(1, 5), rng.randint(2, 9)] for i in range(3)]
    tgt = 2 if flip else 1
    return dict(schema=["CREATE TABLE lines (id INTEGER PRIMARY KEY, qty INTEGER, price INTEGER,\n  total INTEGER GENERATED ALWAYS AS "
                        f"(qty * price) {rng.choice(['STORED', 'VIRTUAL'])});"],
                rows=ins("lines", ["id", "qty", "price"], rows), late=[],
                stmts=[f"UPDATE lines SET qty = qty + {rng.randint(1, 3)} WHERE id = {tgt};"],
                qs=[("value", ("lines", 1, "total"))])


@tpl("sql_views_check_generated", "insert_generated_value")
def _(rng, flip):
    q, p = rng.randint(1, 5), rng.randint(2, 9)
    stmt = (f"INSERT INTO lines(qty, price) VALUES ({q}, {p});" if flip else
            f"INSERT INTO lines(qty, price, total) VALUES ({q}, {p}, {q * p});")
    return dict(schema=["CREATE TABLE lines (id INTEGER PRIMARY KEY, qty INTEGER, price INTEGER,\n  total INTEGER GENERATED ALWAYS AS "
                        "(qty * price) STORED);"],
                rows=ins("lines", ["id", "qty", "price"], [[1, 2, 3]]), late=[], stmts=[stmt],
                qs=[("fails", 1), ("rows", "lines")])


@tpl("sql_views_check_generated", "strict_types")
def _(rng, flip):
    strict = "" if flip else " STRICT"
    bad = rng.choice(["'12a'", "'many'", "4.5"])
    return dict(schema=[f"CREATE TABLE crates (id INTEGER PRIMARY KEY, label TEXT, qty INTEGER){strict};"],
                rows=ins("crates", ["id", "label", "qty"], [[1, "north", 3]]), late=[],
                stmts=[f"INSERT INTO crates(label, qty) VALUES ('south', {bad});"],
                qs=[("fails", 1), ("rows", "crates")])


@tpl("sql_views_check_generated", "partial_unique")
def _(rng, flip):
    name = rng.choice(ITEMS)
    active = 0 if flip else 1
    return dict(schema=["CREATE TABLE tags (id INTEGER PRIMARY KEY, name TEXT, active INTEGER);",
                        "CREATE UNIQUE INDEX one_active_name ON tags(name) WHERE active = 1;"],
                rows=ins("tags", ["id", "name", "active"], [[1, name, 1], [2, rng.choice(ITEMS), 0]]), late=[],
                stmts=[f"INSERT INTO tags(name, active) VALUES ({lit(name)}, {active});"],
                qs=[("fails", 1), ("rows", "tags")])


@tpl("sql_views_check_generated", "write_into_view")
def _(rng, flip):
    tgt = "stock" if flip else "stock_view"
    return dict(schema=["CREATE TABLE stock (id INTEGER PRIMARY KEY, name TEXT, qty INTEGER);",
                        "CREATE VIEW stock_view AS SELECT id, name, qty FROM stock WHERE qty > 0;"],
                rows=ins("stock", ["id", "name", "qty"], [[1, rng.choice(ITEMS), 2], [2, rng.choice(ITEMS), 0]]), late=[],
                stmts=[f"UPDATE {tgt} SET qty = qty + 1 WHERE id = 1;"],
                qs=[("fails", 1), ("value", ("stock", 1, "qty"))])


@tpl("sql_views_check_generated", "check_range")
def _(rng, flip):
    s, e = rng.randint(1, 5), rng.randint(6, 9)
    new_end = s + 1 if flip else s - 1
    return dict(schema=["CREATE TABLE shifts (id INTEGER PRIMARY KEY, start_h INTEGER, end_h INTEGER,\n  CHECK (end_h >= start_h));"],
                rows=ins("shifts", ["id", "start_h", "end_h"], [[1, s, e], [2, s, e + 1]]), late=[],
                stmts=[f"UPDATE shifts SET end_h = {new_end};"],
                qs=[("fails", 1), ("value", ("shifts", 2, "end_h"))])


# ------------------------------------------------------------------ sql_collation_affinity

@tpl("sql_collation_affinity", "nocase_unique")
def _(rng, flip):
    n = rng.choice(ITEMS)
    coll = "" if flip else " COLLATE NOCASE"
    return dict(schema=[f"CREATE TABLE herbs (id INTEGER PRIMARY KEY, name TEXT UNIQUE{coll});"],
                rows=ins("herbs", ["id", "name"], [[1, n], [2, rng.choice([x for x in ITEMS if x != n])]]), late=[],
                stmts=[f"INSERT INTO herbs(name) VALUES ({lit(n.capitalize())});"], qs=[("fails", 1), ("rows", "herbs")])


@tpl("sql_collation_affinity", "text_number_compare")
def _(rng, flip):
    col = "INTEGER" if flip else "TEXT"
    vals = rng.sample([3, 7, 9, 10, 12, 25, 40], 4)
    k = rng.choice([5, 8])
    return dict(schema=[f"CREATE TABLE marks (id INTEGER PRIMARY KEY, score {col});"],
                rows=ins("marks", ["id", "score"], [[i + 1, v] for i, v in enumerate(vals)]), late=[],
                stmts=[f"DELETE FROM marks WHERE score > '{k}';"], qs=[("rows", "marks")])


@tpl("sql_collation_affinity", "like_vs_glob")
def _(rng, flip):
    names = ["Basil", "beet", "Borage", "mint", "bay"]
    rng.shuffle(names)
    cond = "name GLOB 'b*'" if flip else "name LIKE 'b%'"
    return dict(schema=["CREATE TABLE plants (id INTEGER PRIMARY KEY, name TEXT);"],
                rows=ins("plants", ["id", "name"], [[i + 1, n] for i, n in enumerate(names)]), late=[],
                stmts=[f"DELETE FROM plants WHERE {cond};"], qs=[("rows", "plants")])


@tpl("sql_collation_affinity", "integer_division")
def _(rng, flip):
    tot, cnt = rng.randint(7, 20), rng.choice([2, 3, 4])
    if tot % cnt == 0:
        tot += 1
    expr = "total * 1.0 / cnt" if flip else "total / cnt"
    return dict(schema=["CREATE TABLE stats (id INTEGER PRIMARY KEY, total INTEGER, cnt INTEGER, avg_v);"],
                rows=ins("stats", ["id", "total", "cnt"], [[1, tot, cnt]]), late=[],
                stmts=[f"UPDATE stats SET avg_v = {expr};"], qs=[("value", ("stats", 1, "avg_v"))])


@tpl("sql_collation_affinity", "text_in_arithmetic")
def _(rng, flip):
    a, b = rng.randint(2, 9), rng.randint(2, 9)
    expr = f"'{a}' || {b}" if flip else f"'{a}' + {b}"
    return dict(schema=["CREATE TABLE memo (id INTEGER PRIMARY KEY, v);"], rows=ins("memo", ["id", "v"], [[1, 0]]), late=[],
                stmts=[f"UPDATE memo SET v = {expr};"], qs=[("value", ("memo", 1, "v"))])


@tpl("sql_collation_affinity", "eq_case_in_where")
def _(rng, flip):
    n = rng.choice(ITEMS)
    coll = " COLLATE NOCASE" if flip else ""
    return dict(schema=[f"CREATE TABLE herbs (id INTEGER PRIMARY KEY, name TEXT{coll}, qty INTEGER);"],
                rows=ins("herbs", ["id", "name", "qty"], [[1, n.capitalize(), 2], [2, rng.choice(ITEMS), 3]]), late=[],
                stmts=[f"UPDATE herbs SET qty = qty + 10 WHERE name = {lit(n)};"], qs=[("value", ("herbs", 1, "qty"))])


FAMILIES = sorted({f for f, _ in T.values()})
FAMILY_TEMPLATES = {fam: sorted(n for n, (f, _) in T.items() if f == fam) for fam in FAMILIES}


# ------------------------------------------------------------------ run, render, questions

def build(sp):
    con = sqlite3.connect(":memory:", isolation_level=None)
    for x in sp["schema"]:
        con.executescript(x)
    for x in sp["rows"]:
        con.execute(x.rstrip(";"))
    for x in sp["late"]:
        con.executescript(x)
    return con


def dump(con):
    out = {}
    for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
        cols = [r[1] for r in con.execute(f"PRAGMA table_xinfo({t})")]
        rows = [list(r) for r in con.execute(f"SELECT {', '.join(cols)} FROM {t} ORDER BY rowid")]
        out[t] = {"cols": cols, "rows": rows}
    return {"tables": out}


def run(sp):
    con = build(sp)
    before = dump(con)
    res = []
    for st in sp["stmts"]:
        try:
            con.execute(st.rstrip(";"))
            res.append(["ok", ""])
        except sqlite3.Error as e:
            res.append(["error", str(e)[:120]])
    after = dump(con)
    con.close()
    return {"before": before, "after": after, "res": res}


def fmt(x):
    if x is None:
        return "NULL"
    if isinstance(x, float):
        return repr(x)
    return str(x)


def render(sp, db):
    lines = ["Database schema:", *sp["schema"], *sp["late"], "", "Table contents:"]
    for t, v in db["tables"].items():
        lines.append(f"{t}: {' | '.join(v['cols'])} ({len(v['rows'])} rows)")
        for r in v["rows"]:
            lines.append("  " + " | ".join(fmt(x) for x in r))
    return "\n".join(lines)


def render_after(db):
    lines = ["Tables and contents:"]
    for t, v in db["tables"].items():
        lines.append(f"{t}: {' | '.join(v['cols'])} ({len(v['rows'])} rows)")
        for r in v["rows"]:
            lines.append("  " + " | ".join(fmt(x) for x in r))
    return "\n".join(lines)


def cell(db, t, rid, col):
    tab = db["tables"].get(t)
    if not tab or col not in tab["cols"]:
        return "(no such column)"
    for r in tab["rows"]:
        if r[0] == rid:
            return fmt(r[tab["cols"].index(col)])
    return "(the row does not exist)"


def golds(qs, res):
    g = {}
    for q in qs:
        if q[0] == "fails":
            k = q[1]
            g[q] = res["res"][k - 1][0] == "error"
        elif q[0] == "rows":
            g[q] = str(len(res["after"]["tables"].get(q[1], {"rows": []})["rows"]))
        elif q[0] == "value":
            t, rid, col = q[1]
            g[q] = cell(res["after"], t, rid, col)
    return g


def make_items(seed, allowed=None):
    names = sorted(n for n in T if allowed is None or n in allowed)
    if not names:
        return [], {"skipped": 1}
    rng = random.Random(stable_seed("fx_sql", T[names[0]][0], seed))
    name = rng.choice(names)
    flip_first = rng.random() < 0.5
    st = rng.getstate()
    sp_a = T[name][1](rng, flip_first)
    rng.setstate(st)
    sp_b = T[name][1](rng, not flip_first)
    try:
        ra, rb = run(sp_a), run(sp_b)
    except Exception as e:  # noqa: BLE001
        return [], {"build_fail": 1, "last_error": str(e)[:150]}
    qs = [tuple(q) for q in sp_a["qs"]]
    ga, gb = golds(qs, ra), golds(qs, rb)
    twin = ga != gb
    inst = [("a", sp_a, ra)] + ([("b", sp_b, rb)] if twin else [])
    rows = []
    for side, sp, res in inst:
        g = golds(qs, res)
        g0 = golds(qs, {"before": res["before"], "after": res["before"], "res": [["ok", ""]] * len(sp["stmts"])})
        floor = world_floor(RULES, render(sp, res["before"]), sp["stmts"])
        what = "; ".join(f"statement {k}: {'ok' if r[0] == 'ok' else 'error (' + r[1] + ')'}"
                         for k, r in enumerate(res["res"], 1)) + "."
        ceiling = world_ceiling(RULES, render_after(res["after"]), what)
        allv = [ra, rb]
        for q in qs:
            gold = g[q]
            if q[0] == "fails":
                qd = yes_no(f"Does statement {q[1]} fail (raise an error)?")
                known0, gold0 = False, None
            elif q[0] == "rows":
                vals = [str(len(r_[k]["tables"].get(q[1], {"rows": []})["rows"])) for r_ in allv for k in ("before", "after")]
                hi = max([int(v) for v in vals] + [3]) + 1
                qd = choice(f"After these statements, how many rows does {q[1]} have?", [str(i) for i in range(0, min(hi, 9) + 1)])
                if gold not in qd["criteria"]:
                    qd["criteria"][gold] = gold
                known0, gold0 = True, g0[q]
            else:
                t, rid, col = q[1]
                opts = [cell(r_[k], t, rid, col) for r_ in allv for k in ("after", "before")]
                opts += ["NULL", "(the row does not exist)"]
                opts = list(dict.fromkeys(opts))[:6]
                if gold not in opts:
                    opts.append(gold)
                qd = choice(f"After these statements, what is {col} of the {t} row whose id is {rid}?", opts)
                known0, gold0 = True, g0[q]
            if known0 and gold0 not in qd.get("criteria", {}):
                known0, gold0 = False, None
            arg = re.sub(r"[^A-Za-z0-9]", "_", str(q[1]))
            rows.append(row(world="rx_sql", family="sql", template=name, qtype=q[0], steps=len(sp["stmts"]), question=qd,
                            gold=gold if qd["type"] == "choice" else bool(gold), gold0=gold0, known0=known0, floor=floor,
                            ceiling=ceiling, rid=f"fxsql-{seed}-{side}-{q[0]}-{arg}",
                            twin=(f"fxsql-{seed}-{'b' if side == 'a' else 'a'}" if twin else None),
                            struct={"schema": sp["schema"], "late": sp["late"], "rows": sp["rows"], "stmts": sp["stmts"],
                                    "res": res["res"]}))
    return rows, {"scenarios": 1, "twins": int(twin)}
