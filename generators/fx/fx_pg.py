"""WS-FX PostgreSQL 16 families (SPEC.md): pg_txn_abort and pg_ddl_cascade (held out), pg_conflict_sequences,
pg_types_strict. A private cluster (Unix socket only, /dev/shm/fx/pg) runs every scenario in a fresh schema over one
session: autocommit unless BEGIN opened a transaction; an unfinished transaction is rolled back when the session ends.
The truth is what PostgreSQL itself does; each template has a flip twin."""
from __future__ import annotations

import decimal
import os
import random
import re
import sys

sys.path.insert(0, "/root/decis/mission/FX/pylib")
import psycopg2  # noqa: E402
from psycopg2 import extensions  # noqa: E402

from common import choice, row, stable_seed, world_ceiling, world_floor, yes_no  # noqa: E402

RULES = ("A PostgreSQL 16 database used by a small service. Each numbered SQL statement is sent on its own, in order, in one "
         "session (autocommit unless a BEGIN opened a transaction). If a statement raises an error, the next statement is "
         "still sent. When the statements end, a transaction that is still open is rolled back (the session closes).")
ITEMS = ["basil", "thyme", "mint", "sage", "dill", "chive", "fennel", "cumin", "anise", "sorrel"]
T = {}
_CON = {}


def tpl(family, name):
    def deco(fn):
        T[name] = (family, fn)
        return fn
    return deco


def lit(v):
    return "NULL" if v is None else ("'" + v.replace("'", "''") + "'" if isinstance(v, str) else str(v))


def ins(table, cols, rows):
    return [f"INSERT INTO {table}({', '.join(cols)}) VALUES ({', '.join(lit(x) for x in r)});" for r in rows]


def items(rng, k):
    return rng.sample(ITEMS, k)


# ------------------------------------------------------------------ pg_txn_abort (held out)

@tpl("pg_txn_abort", "error_aborts_rest")
def _(rng, flip):
    a, b, c = items(rng, 3)
    dup = b if flip else a
    return dict(schema=["CREATE TABLE stock (id SERIAL PRIMARY KEY, name TEXT UNIQUE, qty INTEGER);"],
                rows=ins("stock", ["name", "qty"], [[a, 2]]),
                stmts=["BEGIN;", f"INSERT INTO stock(name, qty) VALUES ({lit(c)}, 1);",
                       f"INSERT INTO stock(name, qty) VALUES ({lit(dup)}, 3);",
                       f"INSERT INTO stock(name, qty) VALUES ({lit(rng.choice([x for x in ITEMS if x not in (a, b, c)]))}, 4);",
                       "COMMIT;"],
                qs=[("fails", 3), ("fails", 4), ("fails", 5), ("rows", "stock")])


@tpl("pg_txn_abort", "savepoint_recovers")
def _(rng, flip):
    a, b, c = items(rng, 3)
    body = [f"INSERT INTO stock(name, qty) VALUES ({lit(b)}, 1);"]
    if not flip:
        body += ["SAVEPOINT before_dup;", f"INSERT INTO stock(name, qty) VALUES ({lit(a)}, 5);", "ROLLBACK TO SAVEPOINT before_dup;"]
    else:
        body += [f"INSERT INTO stock(name, qty) VALUES ({lit(a)}, 5);"]
    body += [f"INSERT INTO stock(name, qty) VALUES ({lit(c)}, 2);", "COMMIT;"]
    return dict(schema=["CREATE TABLE stock (id SERIAL PRIMARY KEY, name TEXT UNIQUE, qty INTEGER);"],
                rows=ins("stock", ["name", "qty"], [[a, 2]]), stmts=["BEGIN;"] + body, qs=[("rows", "stock")])


@tpl("pg_txn_abort", "commit_after_error")
def _(rng, flip):
    q0, add = rng.randint(1, 5), rng.randint(1, 4)
    return dict(schema=["CREATE TABLE stock (id INTEGER PRIMARY KEY, name TEXT, qty INTEGER);"],
                rows=ins("stock", ["id", "name", "qty"], [[1, rng.choice(ITEMS), q0]]),
                stmts=["BEGIN;", f"UPDATE stock SET qty = qty + {add} WHERE id = 1;",
                       f"SELECT 1 / {1 if flip else 0};", "COMMIT;"],
                qs=[("fails", 3), ("fails", 4), ("value", ("stock", 1, "qty"))])


@tpl("pg_txn_abort", "autocommit_isolated")
def _(rng, flip):
    a, b, c = items(rng, 3)
    core = [f"INSERT INTO stock(name, qty) VALUES ({lit(b)}, 1);", f"INSERT INTO stock(name, qty) VALUES ({lit(a)}, 5);",
            f"INSERT INTO stock(name, qty) VALUES ({lit(c)}, 2);"]
    stmts = (["BEGIN;"] + core + ["COMMIT;"]) if flip else core
    return dict(schema=["CREATE TABLE stock (id SERIAL PRIMARY KEY, name TEXT UNIQUE, qty INTEGER);"],
                rows=ins("stock", ["name", "qty"], [[a, 2]]), stmts=stmts, qs=[("rows", "stock")])


@tpl("pg_txn_abort", "ddl_rolled_back")
def _(rng, flip):
    return dict(schema=["CREATE TABLE stock (id INTEGER PRIMARY KEY, name TEXT);"],
                rows=ins("stock", ["id", "name"], [[1, rng.choice(ITEMS)]]),
                stmts=["BEGIN;", "CREATE TABLE audit (id SERIAL PRIMARY KEY, note TEXT);", "INSERT INTO audit(note) VALUES ('start');",
                       f"SELECT 10 / {1 if flip else 0};", "COMMIT;"],
                qs=[("table_exists", "audit"), ("fails", 5)])


@tpl("pg_txn_abort", "rollback_then_continue")
def _(rng, flip):
    a, b = items(rng, 2)
    mid = ["SELECT 1;"] if flip else ["ROLLBACK;"]
    return dict(schema=["CREATE TABLE stock (id SERIAL PRIMARY KEY, name TEXT UNIQUE, qty INTEGER);"],
                rows=ins("stock", ["name", "qty"], [[a, 2]]),
                stmts=["BEGIN;", f"INSERT INTO stock(name, qty) VALUES ({lit(a)}, 9);"] + mid +
                      [f"INSERT INTO stock(name, qty) VALUES ({lit(b)}, 1);"],
                qs=[("fails", 3), ("fails", 4), ("rows", "stock")])


# ------------------------------------------------------------------ pg_ddl_cascade (held out)

@tpl("pg_ddl_cascade", "drop_table_with_view")
def _(rng, flip):
    return dict(schema=["CREATE TABLE stock (id INTEGER PRIMARY KEY, name TEXT, qty INTEGER);",
                        "CREATE VIEW low_stock AS SELECT id, name FROM stock WHERE qty < 3;"],
                rows=ins("stock", ["id", "name", "qty"], [[1, rng.choice(ITEMS), 1], [2, rng.choice(ITEMS), 5]]),
                stmts=[f"DROP TABLE stock{' CASCADE' if flip else ''};"],
                qs=[("fails", 1), ("view_exists", "low_stock"), ("table_exists", "stock")])


@tpl("pg_ddl_cascade", "truncate_parent")
def _(rng, flip):
    return dict(schema=["CREATE TABLE shelves (id INTEGER PRIMARY KEY, label TEXT);",
                        "CREATE TABLE jars (id INTEGER PRIMARY KEY, shelf_id INTEGER REFERENCES shelves(id), herb TEXT);"],
                rows=ins("shelves", ["id", "label"], [[1, "top"], [2, "low"]]) +
                     ins("jars", ["id", "shelf_id", "herb"], [[i + 1, rng.choice([1, 2]), h] for i, h in enumerate(items(rng, 3))]),
                stmts=[f"TRUNCATE shelves{' CASCADE' if flip else ''};"],
                qs=[("fails", 1), ("rows", "jars"), ("rows", "shelves")])


@tpl("pg_ddl_cascade", "drop_column_used_by_view")
def _(rng, flip):
    col = "qty" if not flip else "note"
    return dict(schema=["CREATE TABLE stock (id INTEGER PRIMARY KEY, name TEXT, qty INTEGER, note TEXT);",
                        "CREATE VIEW stock_qty AS SELECT id, qty FROM stock;"],
                rows=ins("stock", ["id", "name", "qty", "note"], [[1, rng.choice(ITEMS), 2, "x"]]),
                stmts=[f"ALTER TABLE stock DROP COLUMN {col};"], qs=[("fails", 1), ("view_exists", "stock_qty")])


@tpl("pg_ddl_cascade", "drop_column_cascade")
def _(rng, flip):
    cas = " CASCADE" if not flip else ""
    return dict(schema=["CREATE TABLE stock (id INTEGER PRIMARY KEY, name TEXT, qty INTEGER);",
                        "CREATE VIEW stock_qty AS SELECT id, qty FROM stock;"],
                rows=ins("stock", ["id", "name", "qty"], [[1, rng.choice(ITEMS), 2]]),
                stmts=[f"ALTER TABLE stock DROP COLUMN qty{cas};"], qs=[("fails", 1), ("view_exists", "stock_qty")])


@tpl("pg_ddl_cascade", "rename_column_keeps_view")
def _(rng, flip):
    stmt2 = "INSERT INTO stock(id, amount) VALUES (2, 4);" if flip else "INSERT INTO stock(id, qty) VALUES (2, 4);"
    return dict(schema=["CREATE TABLE stock (id INTEGER PRIMARY KEY, qty INTEGER);",
                        "CREATE VIEW stock_qty AS SELECT id, qty FROM stock;"],
                rows=ins("stock", ["id", "qty"], [[1, 3]]),
                stmts=["ALTER TABLE stock RENAME COLUMN qty TO amount;", stmt2],
                qs=[("fails", 2), ("view_exists", "stock_qty"), ("rows", "stock")])


@tpl("pg_ddl_cascade", "drop_owned_sequence")
def _(rng, flip):
    cas = " CASCADE" if flip else ""
    return dict(schema=["CREATE TABLE tickets (id SERIAL PRIMARY KEY, title TEXT);"],
                rows=ins("tickets", ["title"], [[rng.choice(ITEMS)]]),
                stmts=[f"DROP SEQUENCE tickets_id_seq{cas};", f"INSERT INTO tickets(title) VALUES ({lit(rng.choice(ITEMS))});"],
                qs=[("fails", 1), ("fails", 2), ("rows", "tickets")])


# ------------------------------------------------------------------ pg_conflict_sequences

@tpl("pg_conflict_sequences", "sequence_gap_after_rollback")
def _(rng, flip):
    a, b, c = items(rng, 3)
    mid = ["BEGIN;", f"INSERT INTO tickets(title) VALUES ({lit(b)});", "ROLLBACK;"] if not flip else []
    return dict(schema=["CREATE TABLE tickets (id SERIAL PRIMARY KEY, title TEXT);"],
                rows=ins("tickets", ["title"], [[a]]), stmts=mid + [f"INSERT INTO tickets(title) VALUES ({lit(c)});"],
                qs=[("new_id", ("tickets", "title", c))])


@tpl("pg_conflict_sequences", "do_nothing_vs_error")
def _(rng, flip):
    a = rng.choice(ITEMS)
    tail = "" if flip else " ON CONFLICT (name) DO NOTHING"
    return dict(schema=["CREATE TABLE stock (id SERIAL PRIMARY KEY, name TEXT UNIQUE, qty INTEGER);"],
                rows=ins("stock", ["name", "qty"], [[a, 2]]),
                stmts=[f"INSERT INTO stock(name, qty) VALUES ({lit(a)}, 7){tail};"], qs=[("fails", 1), ("value", ("stock", 1, "qty"))])


@tpl("pg_conflict_sequences", "do_update_excluded")
def _(rng, flip):
    a, q0, q1 = rng.choice(ITEMS), rng.randint(1, 5), rng.randint(6, 9)
    upd = "stock.qty + EXCLUDED.qty" if flip else "EXCLUDED.qty"
    return dict(schema=["CREATE TABLE stock (id SERIAL PRIMARY KEY, name TEXT UNIQUE, qty INTEGER);"],
                rows=ins("stock", ["name", "qty"], [[a, q0]]),
                stmts=[f"INSERT INTO stock(name, qty) VALUES ({lit(a)}, {q1}) ON CONFLICT (name) DO UPDATE SET qty = {upd};"],
                qs=[("value", ("stock", 1, "qty")), ("rows", "stock")])


@tpl("pg_conflict_sequences", "conflict_target_without_index")
def _(rng, flip):
    a = rng.choice(ITEMS)
    tgt = "name" if flip else "qty"
    return dict(schema=["CREATE TABLE stock (id SERIAL PRIMARY KEY, name TEXT UNIQUE, qty INTEGER);"],
                rows=ins("stock", ["name", "qty"], [[a, 2]]),
                stmts=[f"INSERT INTO stock(name, qty) VALUES ({lit(a)}, 2) ON CONFLICT ({tgt}) DO NOTHING;"],
                qs=[("fails", 1), ("rows", "stock")])


@tpl("pg_conflict_sequences", "conflict_consumes_sequence")
def _(rng, flip):
    a, b, c = items(rng, 3)
    first = a if not flip else b
    return dict(schema=["CREATE TABLE stock (id SERIAL PRIMARY KEY, name TEXT UNIQUE, qty INTEGER);"],
                rows=ins("stock", ["name", "qty"], [[a, 2]]),
                stmts=[f"INSERT INTO stock(name, qty) VALUES ({lit(first)}, 1) ON CONFLICT (name) DO NOTHING;",
                       f"INSERT INTO stock(name, qty) VALUES ({lit(c)}, 1);"],
                qs=[("new_id", ("stock", "name", c))])


@tpl("pg_conflict_sequences", "identity_always")
def _(rng, flip):
    a = rng.choice(ITEMS)
    over = " OVERRIDING SYSTEM VALUE" if flip else ""
    return dict(schema=["CREATE TABLE tickets (id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY, title TEXT);"],
                rows=["INSERT INTO tickets(title) VALUES ('first');"],
                stmts=[f"INSERT INTO tickets(id, title){over} VALUES ({rng.randint(5, 9)}, {lit(a)});"],
                qs=[("fails", 1), ("rows", "tickets")])


# ------------------------------------------------------------------ pg_types_strict

@tpl("pg_types_strict", "text_into_integer")
def _(rng, flip):
    v = f"'{rng.randint(10, 99)}'" if flip else rng.choice(["'12a'", "'many'", "'4.5'"])
    return dict(schema=["CREATE TABLE crates (id SERIAL PRIMARY KEY, label TEXT, qty INTEGER);"],
                rows=ins("crates", ["label", "qty"], [["north", 3]]),
                stmts=[f"INSERT INTO crates(label, qty) VALUES ('south', {v});"], qs=[("fails", 1), ("rows", "crates")])


@tpl("pg_types_strict", "integer_division")
def _(rng, flip):
    tot, cnt = rng.randint(7, 20), rng.choice([2, 3, 4])
    if tot % cnt == 0:
        tot += 1
    expr = "total::numeric / cnt" if flip else "total / cnt"
    return dict(schema=["CREATE TABLE stats (id INTEGER PRIMARY KEY, total INTEGER, cnt INTEGER, avg_v NUMERIC(8,2));"],
                rows=ins("stats", ["id", "total", "cnt"], [[1, tot, cnt]]),
                stmts=[f"UPDATE stats SET avg_v = {expr};"], qs=[("value", ("stats", 1, "avg_v"))])


@tpl("pg_types_strict", "varchar_too_long")
def _(rng, flip):
    w = rng.choice(["fennel", "anise", "cumin", "sorrel"])
    val = w[:4] if flip else w + "seed"
    return dict(schema=["CREATE TABLE tags (id SERIAL PRIMARY KEY, code VARCHAR(5));"],
                rows=ins("tags", ["code"], [["mint"]]), stmts=[f"INSERT INTO tags(code) VALUES ({lit(val)});"],
                qs=[("fails", 1), ("rows", "tags")])


@tpl("pg_types_strict", "nulls_first_desc")
def _(rng, flip):
    scores = [rng.randint(1, 9), rng.randint(10, 20), None]
    rng.shuffle(scores)
    order = "score DESC NULLS LAST" if flip else "score DESC"
    null_id = scores.index(None) + 1
    return dict(schema=["CREATE TABLE players (id INTEGER PRIMARY KEY, score INTEGER, top BOOLEAN DEFAULT false);"],
                rows=ins("players", ["id", "score"], [[i + 1, s] for i, s in enumerate(scores)]),
                stmts=[f"UPDATE players SET top = true WHERE id = (SELECT id FROM players ORDER BY {order} LIMIT 1);"],
                qs=[("value", ("players", null_id, "top"))])


@tpl("pg_types_strict", "boolean_from_integer")
def _(rng, flip):
    val = "true" if flip else "1"
    return dict(schema=["CREATE TABLE users (id INTEGER PRIMARY KEY, active BOOLEAN);"],
                rows=["INSERT INTO users(id, active) VALUES (1, false);"],
                stmts=[f"UPDATE users SET active = {val} WHERE id = 1;"], qs=[("fails", 1), ("value", ("users", 1, "active"))])


@tpl("pg_types_strict", "numeric_rounding")
def _(rng, flip):
    v = rng.choice(["2.675", "1.005", "3.145", "0.125"])
    col = "REAL" if flip else "NUMERIC(6,2)"
    return dict(schema=[f"CREATE TABLE prices (id INTEGER PRIMARY KEY, amount {col});"],
                rows=["INSERT INTO prices(id, amount) VALUES (1, 0);"],
                stmts=[f"UPDATE prices SET amount = {v} WHERE id = 1;"], qs=[("value", ("prices", 1, "amount"))])


FAMILIES = sorted({f for f, _ in T.values()})
FAMILY_TEMPLATES = {fam: sorted(n for n, (f, _) in T.items() if f == fam) for fam in FAMILIES}


# ------------------------------------------------------------------ session, run, render

def con():
    c = _CON.get(os.getpid())
    if c is None or c.closed:
        c = psycopg2.connect(host="/dev/shm/fx/pg/sock", port=54329, user="fx", dbname="postgres")
        c.autocommit = True
        _CON[os.getpid()] = c
    return c


def fmt(x):
    if x is None:
        return "NULL"
    if isinstance(x, bool):
        return "true" if x else "false"
    if isinstance(x, decimal.Decimal):
        return str(x)
    if isinstance(x, float):
        return repr(x)
    return str(x)


def dump(cur, schema):
    cur.execute("SELECT table_name, table_type FROM information_schema.tables WHERE table_schema = %s ORDER BY table_name",
                (schema,))
    objs = cur.fetchall()
    tables, views = {}, []
    for name, typ in objs:
        if typ == "VIEW":
            views.append(name)
            continue
        cur.execute(f'SELECT * FROM "{schema}"."{name}" ORDER BY 1')
        cols = [d[0] for d in cur.description]
        tables[name] = {"cols": cols, "rows": [[fmt(x) for x in r] for r in cur.fetchall()]}
    return {"tables": tables, "views": sorted(views)}


def run(sp, tag):
    c = con()
    schema = f"fx_{tag}"
    cur = c.cursor()
    try:
        cur.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        cur.execute(f'CREATE SCHEMA "{schema}"')
        cur.execute(f'SET search_path TO "{schema}"')
        for x in sp["schema"] + sp["rows"]:
            cur.execute(x)
        before = dump(cur, schema)
        res = []
        for st in sp["stmts"]:
            try:
                cur.execute(st)
                res.append(["ok", ""])
            except psycopg2.Error as e:
                msg = (e.pgerror or str(e)).strip().splitlines()[0].replace("ERROR:  ", "")
                res.append(["error", re.sub(r'"?fx_[a-z0-9_]+"?\.', "", msg)[:120]])
        if c.get_transaction_status() != extensions.TRANSACTION_STATUS_IDLE:
            c.rollback() if not c.autocommit else cur.execute("ROLLBACK")
        cur.execute(f'SET search_path TO "{schema}"')
        after = dump(cur, schema)
        return {"before": before, "after": after, "res": res}
    finally:
        try:
            if c.get_transaction_status() != extensions.TRANSACTION_STATUS_IDLE:
                cur.execute("ROLLBACK")
            cur.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            cur.execute("RESET search_path")
        except Exception:  # noqa: BLE001
            try:
                c.close()
            except Exception:  # noqa: BLE001
                pass
            _CON.pop(os.getpid(), None)


def render(sp, db):
    lines = ["Database schema:", *sp["schema"], "", "Table contents:"]
    for t, v in db["tables"].items():
        lines.append(f"{t}: {' | '.join(v['cols'])} ({len(v['rows'])} rows)")
        for r in v["rows"]:
            lines.append("  " + " | ".join(r))
    lines.append("Views: " + (", ".join(db["views"]) or "none") + ".")
    return "\n".join(lines)


def render_after(db):
    lines = ["Tables and contents:"]
    for t, v in db["tables"].items():
        lines.append(f"{t}: {' | '.join(v['cols'])} ({len(v['rows'])} rows)")
        for r in v["rows"]:
            lines.append("  " + " | ".join(r))
    lines.append("Views: " + (", ".join(db["views"]) or "none") + ".")
    return "\n".join(lines)


def cell(db, t, rid, col):
    tab = db["tables"].get(t)
    if not tab:
        return "(the table no longer exists)"
    if col not in tab["cols"]:
        return "(no such column)"
    for r in tab["rows"]:
        if r[0] == str(rid):
            return r[tab["cols"].index(col)]
    return "(the row does not exist)"


def new_id(db, t, col, val):
    tab = db["tables"].get(t)
    if not tab or col not in tab["cols"]:
        return "(no such row)"
    for r in tab["rows"]:
        if r[tab["cols"].index(col)] == val:
            return r[0]
    return "(no such row)"


def golds(qs, res):
    g = {}
    for q in qs:
        k, a = q[0], q[1]
        if k == "fails":
            g[q] = res["res"][a - 1][0] == "error"
        elif k == "rows":
            tab = res["after"]["tables"].get(a)
            g[q] = str(len(tab["rows"])) if tab else "(the table no longer exists)"
        elif k == "value":
            g[q] = cell(res["after"], *a)
        elif k == "new_id":
            g[q] = new_id(res["after"], *a)
        elif k == "view_exists":
            g[q] = a in res["after"]["views"]
        elif k == "table_exists":
            g[q] = a in res["after"]["tables"]
    return g


def question(q, gold, allv):
    k, a = q[0], q[1]
    if k == "fails":
        return yes_no(f"Does statement {a} fail (raise an error)?")
    if k == "view_exists":
        return yes_no(f"After these statements, does the view {a} exist?")
    if k == "table_exists":
        return yes_no(f"After these statements, does the table {a} exist?")
    if k == "rows":
        vals = [r_[s]["tables"][a]["rows"] for r_ in allv for s in ("before", "after") if a in r_[s]["tables"]]
        hi = max([len(v) for v in vals] + [3]) + 1
        opts = [str(i) for i in range(0, min(hi, 9) + 1)] + ["(the table no longer exists)"]
        qd = choice(f"After these statements, how many rows does {a} have?", opts)
    elif k == "value":
        t, rid, col = a
        opts = [cell(r_[s], t, rid, col) for r_ in allv for s in ("after", "before")] + ["NULL", "(the row does not exist)"]
        qd = choice(f"After these statements, what is {col} of the {t} row whose id is {rid}?", list(dict.fromkeys(opts))[:6])
    else:
        t, col, val = a
        ids = [new_id(r_["after"], t, col, val) for r_ in allv]
        mx = max([int(r[0]) for r_ in allv for r in r_["before"]["tables"].get(t, {"rows": []})["rows"]] + [0])
        opts = list(dict.fromkeys(ids + [str(x) for x in range(max(1, mx), mx + 4)] + ["(no such row)"]))[:7]
        qd = choice(f"After these statements, what id does the {t} row with {col} = '{val}' have?", opts)
    if gold not in qd["criteria"]:
        qd["criteria"][gold] = gold
    return qd


def make_items(seed, allowed=None):
    names = sorted(n for n in T if allowed is None or n in allowed)
    if not names:
        return [], {"skipped": 1}
    rng = random.Random(stable_seed("fx_pg", T[names[0]][0], seed))
    name = rng.choice(names)
    flip_first = rng.random() < 0.5
    st = rng.getstate()
    sp_a = T[name][1](rng, flip_first)
    rng.setstate(st)
    sp_b = T[name][1](rng, not flip_first)
    try:
        ra, rb = run(sp_a, f"{os.getpid()}_{seed}a"), run(sp_b, f"{os.getpid()}_{seed}b")
    except Exception as e:  # noqa: BLE001
        _CON.pop(os.getpid(), None)
        return [], {"run_fail": 1, "last_error": str(e)[:150]}
    qs = [tuple(q) if not isinstance(q[1], list) else (q[0], tuple(q[1])) for q in sp_a["qs"]]
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
        for q in qs:
            gold = g[q]
            qd = question(q, gold, [ra, rb])
            known0 = q[0] not in ("fails",)
            gold0 = g0[q] if known0 else None
            if known0 and qd["type"] == "choice" and gold0 not in qd["criteria"]:
                known0, gold0 = False, None
            arg = re.sub(r"[^A-Za-z0-9]", "_", str(q[1]))
            rows.append(row(world="rx_pg", family="pg", template=name, qtype=q[0], steps=len(sp["stmts"]), question=qd,
                            gold=gold if qd["type"] == "choice" else bool(gold), gold0=gold0, known0=known0, floor=floor,
                            ceiling=ceiling, rid=f"fxpg-{seed}-{side}-{q[0]}-{arg}",
                            twin=(f"fxpg-{seed}-{'b' if side == 'a' else 'a'}" if twin else None),
                            struct={"schema": sp["schema"], "rows": sp["rows"], "stmts": sp["stmts"], "res": res["res"]}))
    return rows, {"scenarios": 1, "twins": int(twin)}
