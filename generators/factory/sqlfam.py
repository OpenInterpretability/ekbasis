"""WS-F SQL family: generated SQLite schemas (foreign keys, triggers, constraints, views), rows and statements, executed
for real (SQLite 3.45 in memory). New domains, layout and grammar (not sql_wild's)."""
from __future__ import annotations

import json
import random
import re
import sqlite3

from common import choice, row, stable_seed, world_ceiling, world_floor, yes_no

RULES = ("An SQLite 3.45 database used by a small service. Each numbered SQL statement is sent on its own, in order, over "
         "one connection (autocommit unless a BEGIN opened a transaction). If a statement raises an error it changes "
         "nothing, and the next statement is still sent.")
DOMAINS = [
    dict(P="greenhouses", C="seedlings", L="greenhouse_log", fk="greenhouse_id", qty="trays", tag="herb", n="sprouts",
         names=["Fern House", "Cactus Row", "Orchid Bay", "Moss Pit", "Palm Hall", "Ivy Nook"],
         tags=["basil", "thyme", "mint", "sage", "dill", "chive"]),
    dict(P="observatories", C="nights", L="obs_log", fk="observatory_id", qty="slots", tag="sky", n="frames",
         names=["Ridge", "Crater", "Summit", "Valley", "Dune", "Mesa"], tags=["clear", "cloudy", "windy", "misty", "calm"]),
    dict(P="depots", C="trucks", L="depot_log", fk="depot_id", qty="bays", tag="model", n="loads",
         names=["North Yard", "Harbor", "Airfield", "Quarry", "Mill Lane", "Ridgeway"],
         tags=["van", "rig", "flatbed", "tanker", "pickup"]),
    dict(P="kilns", C="batches", L="kiln_log", fk="kiln_id", qty="shelves", tag="ware", n="pieces",
         names=["Ember", "Forge", "Glow", "Cinder", "Blaze", "Flint"], tags=["bowl", "vase", "tile", "plate", "jar"]),
    dict(P="lighthouses", C="keepers", L="beacon_log", fk="lighthouse_id", qty="lamps", tag="shift", n="logs",
         names=["Gull Point", "Cape Mira", "Rock Haven", "Storm Isle", "Tern Head"], tags=["dawn", "dusk", "night", "noon"]),
]


def gen_db(rng):
    d = dict(rng.choice(DOMAINS))
    s = {"dom": d, "fk_mode": rng.choice(["cascade", "set null", "restrict", "no action", "none", "cascade"]),
         "fk_on": rng.random() < 0.7, "unique": rng.random() < 0.6, "check": rng.random() < 0.5,
         "notnull": rng.random() < 0.4, "default_n": rng.choice([0, 1]), "triggers": [], "view": rng.random() < 0.3,
         "lock_k": rng.randint(2, 4), "on_update": rng.random() < 0.25, "deferred": rng.random() < 0.15,
         "autoinc": rng.random() < 0.3}
    for t in ("log_delete", "dec_on_insert", "lock_delete", "purge_on_zero"):
        if rng.random() < 0.28:
            s["triggers"].append(t)
    names = rng.sample(d["names"], rng.randint(3, min(5, len(d["names"]))))
    s["P_rows"] = [[i + 1, n, rng.randint(0, 4), rng.randint(0, 6)] for i, n in enumerate(names)]
    ids = [r[0] for r in s["P_rows"]]
    s["C_rows"] = []
    for i in range(rng.randint(3, 7)):
        pid = rng.choice(ids) if rng.random() > 0.12 else None
        tag = rng.choice(d["tags"]) if (s["notnull"] or rng.random() > 0.12) else None
        s["C_rows"].append([i + 1, pid, tag, rng.randint(0, 5)])
    return s


def schema_sql(s):
    d = s["dom"]
    out = [f"PRAGMA foreign_keys = {'ON' if s['fk_on'] else 'OFF'};"]
    cols = [f"  id INTEGER PRIMARY KEY{' AUTOINCREMENT' if s.get('autoinc') else ''}", f"  name TEXT{' UNIQUE' if s['unique'] else ''}",
            f"  {d['qty']} INTEGER{' CHECK (' + d['qty'] + ' >= 0)' if s['check'] else ''}", "  reserve INTEGER DEFAULT 0"]
    out.append(f"CREATE TABLE {d['P']} (\n" + ",\n".join(cols) + "\n);")
    fk = "" if s["fk_mode"] == "none" else (f" REFERENCES {d['P']}(id) ON DELETE {s['fk_mode'].upper()}" +
                                            (" ON UPDATE CASCADE" if s.get("on_update") else "") +
                                            (" DEFERRABLE INITIALLY DEFERRED" if s.get("deferred") else ""))
    ccols = ["  id INTEGER PRIMARY KEY", f"  {d['fk']} INTEGER{fk}", f"  {d['tag']} TEXT{' NOT NULL' if s['notnull'] else ''}",
             f"  {d['n']} INTEGER DEFAULT {s['default_n']}"]
    out.append(f"CREATE TABLE {d['C']} (\n" + ",\n".join(ccols) + "\n);")
    out.append(f"CREATE TABLE {d['L']} (\n  id INTEGER PRIMARY KEY,\n  note TEXT\n);")
    T = s["triggers"]
    if "log_delete" in T:
        out.append(f"CREATE TRIGGER log_{d['P']}_delete AFTER DELETE ON {d['P']}\nBEGIN\n  INSERT INTO {d['L']}(note) "
                   f"VALUES ('removed ' || old.name);\nEND;")
    if "dec_on_insert" in T:
        out.append(f"CREATE TRIGGER take_{d['qty']} AFTER INSERT ON {d['C']}\nBEGIN\n  UPDATE {d['P']} SET {d['qty']} = "
                   f"{d['qty']} - 1 WHERE id = new.{d['fk']};\nEND;")
    if "lock_delete" in T:
        out.append(f"CREATE TRIGGER lock_{d['C']} BEFORE DELETE ON {d['C']} WHEN old.{d['n']} >= {s['lock_k']}\nBEGIN\n"
                   f"  SELECT RAISE(ABORT, 'locked');\nEND;")
    if "purge_on_zero" in T:
        out.append(f"CREATE TRIGGER purge_{d['C']} AFTER UPDATE OF {d['qty']} ON {d['P']} WHEN new.{d['qty']} = 0\nBEGIN\n"
                   f"  DELETE FROM {d['C']} WHERE {d['fk']} = new.id;\nEND;")
    if s["view"]:
        out.append(f"CREATE VIEW {d['C']}_summary AS SELECT {d['tag']}, {d['n']} FROM {d['C']};")
    return "\n".join(out)


def sql_lit(v):
    if v is None:
        return "NULL"
    if isinstance(v, str):
        return "'" + v.replace("'", "''") + "'"
    return str(v)


def build(s):
    """Tables first, then the rows, then triggers and views, then the PRAGMA: loading the rows fires no trigger."""
    con = sqlite3.connect(":memory:", isolation_level=None)
    parts = schema_sql(s).split("\n")
    text = "\n".join(parts[1:])
    stmts = [x.strip() + ";" for x in re.split(r";\s*\n(?=CREATE )", text + "\n") if x.strip()]
    stmts = [x[:-1] if x.endswith(";;") else x for x in stmts]
    tables = [x for x in stmts if x.startswith("CREATE TABLE")]
    extras = [x for x in stmts if not x.startswith("CREATE TABLE")]
    for x in tables:
        con.execute(x.rstrip(";"))
    d = s["dom"]
    for r in s["P_rows"]:
        con.execute(f"INSERT INTO {d['P']}(id, name, {d['qty']}, reserve) VALUES (?, ?, ?, ?)", r)
    for r in s["C_rows"]:
        con.execute(f"INSERT INTO {d['C']}(id, {d['fk']}, {d['tag']}, {d['n']}) VALUES (?, ?, ?, ?)", r)
    for x in extras:
        con.executescript(x if x.endswith(";") else x + ";")
    con.execute(f"PRAGMA foreign_keys = {'ON' if s['fk_on'] else 'OFF'}")
    return con


def dump(con):
    out = {}
    tabs = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    for t in tabs:
        cols = [r[1] for r in con.execute(f"PRAGMA table_info({t})")]
        rows = [list(r) for r in con.execute(f"SELECT * FROM {t} ORDER BY rowid")]
        out[t] = {"cols": cols, "rows": rows}
    views = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='view' ORDER BY name")]
    trig = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='trigger' ORDER BY name")]
    fk = con.execute("PRAGMA foreign_keys").fetchone()[0]
    return {"tables": out, "views": views, "triggers": trig, "fk_on": bool(fk)}


def render(s, db, schema_text=None):
    lines = [f"Database schema:\n{schema_text or schema_sql(s)}", "", "Table contents:"]
    for t, v in db["tables"].items():
        lines.append(f"{t}: {' | '.join(v['cols'])} ({len(v['rows'])} rows)")
        for r in v["rows"]:
            lines.append("  " + " | ".join("NULL" if x is None else str(x) for x in r))
    return "\n".join(lines)


def render_after(db):
    lines = [f"PRAGMA foreign_keys is {'ON' if db['fk_on'] else 'OFF'}.", "Tables and contents:"]
    for t, v in db["tables"].items():
        lines.append(f"{t}: {' | '.join(v['cols'])} ({len(v['rows'])} rows)")
        for r in v["rows"]:
            lines.append("  " + " | ".join("NULL" if x is None else str(x) for x in r))
    lines.append("Views: " + (", ".join(db["views"]) or "none") + ". Triggers: " + (", ".join(db["triggers"]) or "none") + ".")
    return "\n".join(lines)


def run(s, stmts):
    con = build(s)
    before = dump(con)
    res = []
    for st in stmts:
        try:
            con.execute(st)
            res.append(["ok", ""])
        except sqlite3.Error as e:
            res.append(["error", str(e)[:120]])
    after = dump(con)
    con.close()
    return {"before": before, "after": after, "res": res}


# ------------------------------------------------------------------ statement forms

def forms(s, rng):
    d = s["dom"]
    P, C, L, fk, qty, tag, n = d["P"], d["C"], d["L"], d["fk"], d["qty"], d["tag"], d["n"]
    pids = [r[0] for r in s["P_rows"]]
    names = [r[1] for r in s["P_rows"]]
    R = []
    k = rng.choice(pids)
    nm = rng.choice(names)
    R.append(("del_p_id", [f"DELETE FROM {P} WHERE id = {k};"], [P, C, L]))
    pref = nm[:2].lower()
    R.append(("del_p_like", [f"DELETE FROM {P} WHERE name LIKE '{pref}%';"], [P, C]))
    R.append(("del_c_eq_null", [f"DELETE FROM {C} WHERE {fk} = NULL;"], [C]))
    R.append(("del_c_is_null", [f"DELETE FROM {C} WHERE {fk} IS NULL;"], [C]))
    tg = rng.choice(d["tags"])
    R.append(("del_c_ne", [f"DELETE FROM {C} WHERE {tag} != '{tg}';"], [C]))
    R.append(("del_c_ge", [f"DELETE FROM {C} WHERE {n} >= {rng.randint(1, 4)};"], [C]))
    R.append(("del_all", [f"DELETE FROM {rng.choice([P, C])};"], [P, C, L]))
    R.append(("del_p_in", [f"DELETE FROM {P} WHERE id IN (SELECT {fk} FROM {C} WHERE {n} > {rng.randint(1, 4)});"], [P, C]))
    R.append(("upd_qty", [f"UPDATE {P} SET {qty} = {qty} - {rng.randint(1, 3)}" +
                          rng.choice(["", f" WHERE id = {k}"]) + ";"], [P, C]))
    other = rng.choice([x for x in names if x != nm] or [nm])
    R.append(("upd_or_ignore", [f"UPDATE OR IGNORE {P} SET name = {sql_lit(other)} WHERE id = {k};"], [P]))
    R.append(("upd_or_replace", [f"UPDATE OR REPLACE {P} SET name = {sql_lit(other)} WHERE id = {k};"], [P, C]))
    R.append(("upd_fk", [f"UPDATE {C} SET {fk} = {max(pids) + 7} WHERE id = {rng.randint(1, len(s['C_rows']))};"], [C]))
    R.append(("ins_dup_name", [f"INSERT INTO {P}(name, {qty}) VALUES ({sql_lit(nm)}, 2);"], [P]))
    R.append(("ins_ignore", [f"INSERT OR IGNORE INTO {P}(name, {qty}) VALUES ({sql_lit(nm)}, 2);"], [P]))
    R.append(("ins_replace", [f"INSERT OR REPLACE INTO {P}(id, name, {qty}) VALUES ({k}, {sql_lit(nm + ' II')}, 2);"], [P, C]))
    R.append(("replace_into", [f"REPLACE INTO {P}(id, name) VALUES ({k}, {sql_lit(nm)});"], [P, C]))
    R.append(("upsert", [f"INSERT INTO {P}(name, {qty}) VALUES ({sql_lit(nm)}, 2) ON CONFLICT(name) DO UPDATE SET "
                         f"{qty} = {qty} + excluded.{qty};"], [P]))
    R.append(("ins_c_missing_parent", [f"INSERT INTO {C}({fk}, {tag}) VALUES ({max(pids) + 5}, {sql_lit(tg)});"], [C, P]))
    R.append(("ins_c_parent", [f"INSERT INTO {C}({fk}, {tag}) VALUES ({k}, {sql_lit(tg)});"], [C, P]))
    R.append(("ins_c_null_tag", [f"INSERT INTO {C}({fk}) VALUES ({k});"], [C, P]))
    R.append(("ins_c_text_in_int", [f"INSERT INTO {C}({fk}, {tag}, {n}) VALUES ({k}, {sql_lit(tg)}, 'several');"], [C]))
    inner = rng.choice([f"DELETE FROM {C};", f"DELETE FROM {P} WHERE id = {k};", f"UPDATE {P} SET {qty} = 0;"])
    R.append(("txn_rollback", ["BEGIN;", inner, "ROLLBACK;"], [P, C]))
    R.append(("txn_commit", ["BEGIN;", inner, f"INSERT INTO {P}(name, {qty}) VALUES ({sql_lit(nm)}, -1);", "COMMIT;"], [P, C]))
    R.append(("rollback_no_begin", [inner, "ROLLBACK;"], [P, C]))
    R.append(("alter_add", [f"ALTER TABLE {C} ADD COLUMN extra INTEGER DEFAULT 7;"], [C]))
    R.append(("alter_drop", [f"ALTER TABLE {C} DROP COLUMN {rng.choice([n, tag, fk])};"], [C]))
    R.append(("alter_rename", [f"ALTER TABLE {P} RENAME TO {P}_old;"], [P, C]))
    R.append(("drop_parent", [f"DROP TABLE {P};"], [P, C, L]))
    R.append(("fk_off_then_delete", ["PRAGMA foreign_keys = OFF;", f"DELETE FROM {P} WHERE id = {k};"], [C, P]))
    R.append(("fk_on_then_delete", ["PRAGMA foreign_keys = ON;", f"DELETE FROM {P} WHERE id = {k};"], [C, P]))
    return R


TRAPS = ["t_swap", "t_int_div", "t_not_in_null_list", "t_in_null_list", "t_not_in_subquery_null", "t_null_arith",
         "t_concat_null", "t_multirow_dup", "t_or_fail_partial", "t_on_update_cascade", "t_deferred_fk", "t_rowid_reuse",
         "t_upsert_where"]


def require(name, s, rng):
    """Schema flags a trap needs (its flip twin may undo them)."""
    if name == "t_on_update_cascade":
        s["fk_mode"] = rng.choice(["cascade", "set null", "no action"]); s["on_update"] = True; s["fk_on"] = True
    elif name == "t_deferred_fk":
        s["fk_mode"] = "no action"; s["deferred"] = True; s["fk_on"] = True
    elif name in ("t_multirow_dup", "t_or_fail_partial", "t_upsert_where"):
        s["unique"] = rng.random() < 0.8


def trap_form(name, s, rng):
    """(name, statements, tables, naive): naive = the face-value reading {(qtype, arg): answer} and the questions to ask."""
    d = s["dom"]
    P, C, qty, fk, tag, n = d["P"], d["C"], d["qty"], d["fk"], d["tag"], d["n"]
    prows, crows = s["P_rows"], s["C_rows"]
    pids = [r[0] for r in prows]
    with_kids = [r[0] for r in prows if any(c[1] == r[0] for c in crows)] or pids
    k = rng.choice(with_kids)
    pk = next(r for r in prows if r[0] == k)
    ex = rng.choice(prows)
    new1, new2 = f"{rng.choice(['Annex', 'Spur', 'Outpost', 'Ledge'])} {rng.randint(2, 9)}", f"{rng.choice(['Nook', 'Wing', 'Bay'])} {rng.randint(10, 19)}"
    nv = {}
    if name == "t_swap":
        st = [f"UPDATE {P} SET {qty} = reserve, reserve = {qty} WHERE id = {k};"]
        nv = {("value", (P, k, qty)): str(pk[3]), ("value", (P, k, "reserve")): str(pk[3])}
        return name, st, [P], nv
    if name == "t_int_div":
        odd = [r for r in prows if r[2] % 2 == 1] or prows
        r = rng.choice(odd)
        st = [f"UPDATE {P} SET {qty} = {qty} / 2 WHERE id = {r[0]};"]
        return name, st, [P], {("value", (P, r[0], qty)): (str(r[2] / 2) if r[2] % 2 else str(r[2] // 2))}
    if name == "t_not_in_null_list":
        t1 = rng.choice([c[2] for c in crows if c[2]] or d["tags"])
        st = [f"DELETE FROM {C} WHERE {tag} NOT IN ({sql_lit(t1)}, NULL);"]
        keep = sum(1 for c in crows if c[2] == t1 or c[2] is None)
        return name, st, [C], {("rows", C): str(keep)}
    if name == "t_in_null_list":
        st = [f"DELETE FROM {C} WHERE {fk} IN ({k}, NULL);"]
        keep = sum(1 for c in crows if c[1] not in (k, None))
        return name, st, [C], {("rows", C): str(keep)}
    if name == "t_not_in_subquery_null":
        st = [f"DELETE FROM {P} WHERE id NOT IN (SELECT {fk} FROM {C});"]
        keep = sum(1 for r in prows if any(c[1] == r[0] for c in crows))
        return name, st, [P], {("rows", P): str(keep)}
    if name == "t_null_arith":
        j = rng.choice(crows)
        st = [f"UPDATE {C} SET {n} = {n} + NULL WHERE id = {j[0]};"]
        return name, st, [C], {("value", (C, j[0], n)): str(j[3])}
    if name == "t_concat_null":
        st = [f"UPDATE {P} SET name = name || NULL WHERE id = {k};"]
        return name, st, [P], {("value", (P, k, "name")): pk[1]}
    if name == "t_multirow_dup":
        st = [f"INSERT INTO {P}(name, {qty}) VALUES ({sql_lit(new1)}, 1), ({sql_lit(ex[1])}, 2), ({sql_lit(new2)}, 3);"]
        return name, st, [P], {("rows", P): str(len(prows) + (2 if s["unique"] else 3)), ("fails", 1): False}
    if name == "t_or_fail_partial":
        st = [f"INSERT OR FAIL INTO {P}(name, {qty}) VALUES ({sql_lit(new1)}, 1), ({sql_lit(ex[1])}, 2), ({sql_lit(new2)}, 3);"]
        return name, st, [P], {("rows", P): str(len(prows) + (2 if s["unique"] else 3)), ("fails", 1): False}
    if name == "t_on_update_cascade":
        st = [f"UPDATE {P} SET id = {max(pids) + 40} WHERE id = {k};"]
        return name, st, [P, C], {("other", C): False, ("fails", 1): False}
    if name == "t_deferred_fk":
        st = ["BEGIN;", f"DELETE FROM {P} WHERE id = {k};", "COMMIT;"]
        return name, st, [P, C], {("fails", 2): True, ("fails", 3): False}
    if name == "t_rowid_reuse":
        m = max(pids)
        fresh = f"{rng.choice(['Fresh', 'New', 'Late'])} {rng.choice(['Row', 'Site', 'Entry'])}"
        st = [f"DELETE FROM {P} WHERE id = {m};", f"INSERT INTO {P}(name, {qty}) VALUES ({sql_lit(fresh)}, 1);"]
        return name, st, [P], {("new_id", (P, fresh)): str(m + 1)}
    if name == "t_upsert_where":
        v = rng.randint(0, 6)
        st = [f"INSERT INTO {P}(name, {qty}) VALUES ({sql_lit(ex[1])}, {v}) ON CONFLICT(name) DO UPDATE SET {qty} = "
              f"excluded.{qty} WHERE excluded.{qty} > {qty};"]
        return name, st, [P], {("value", (P, ex[0], qty)): str(v)}
    raise KeyError(name)


def questions(s, stmts, tables, res, rng):
    d = s["dom"]
    qs = []
    for k in range(1, len(stmts) + 1):
        qs.append((f"fails{k}", k, yes_no(f"Does statement {k} fail (raise an error)?")))
    named = {t for t in (d["P"], d["C"], d["L"]) if any(re.search(rf"\b{t}\b", x) for x in stmts)}
    for t in tables[:2]:
        if rng.random() < 0.8:
            qs.append(("rows", t, None))
    others = [t for t in (d["P"], d["C"], d["L"]) if t not in named]
    if others:
        t = rng.choice(others)
        qs.append(("other", t, yes_no(f"After these statements, has any row of {t} been changed, added or deleted?")))
    t = rng.choice([d["P"], d["C"]])
    before_rows = res["before"]["tables"].get(t, {}).get("rows", [])
    if before_rows:
        rid = rng.choice(before_rows)[0]
        cols = res["before"]["tables"][t]["cols"][1:]
        qs.append(("value", (t, rid, rng.choice(cols)), None))
    if any(x.startswith(("ALTER", "DROP")) for x in stmts):
        if rng.random() < 0.5:
            tt = rng.choice([d["P"], d["C"]])
            qs.append(("table_exists", tt, yes_no(f"After these statements, does the table {tt} still exist?")))
        else:
            col = rng.choice([d["n"], d["tag"], "extra"])
            qs.append(("col_exists", (d["C"], col), yes_no(f"After these statements, does the table {d['C']} have a column "
                                                           f"named {col}?")))
    return qs


def cell(db, t, rid, col):
    tab = db["tables"].get(t)
    if not tab or col not in tab["cols"]:
        return "(no such column or table)"
    for r in tab["rows"]:
        if r[0] == rid:
            v = r[tab["cols"].index(col)]
            return "NULL" if v is None else str(v)
    return "(the row no longer exists)"


def golds(qs, res):
    out = {}
    for qt, arg, _ in qs:
        if qt.startswith("fails"):
            out[(qt, arg)] = res["res"][arg - 1][0] == "error"
        elif qt == "rows":
            tab = res["after"]["tables"].get(arg)
            out[(qt, arg)] = None if tab is None else len(tab["rows"])
        elif qt == "other":
            out[(qt, arg)] = res["before"]["tables"].get(arg) != res["after"]["tables"].get(arg)
        elif qt == "value":
            out[(qt, arg)] = cell(res["after"], *arg)
        elif qt == "table_exists":
            out[(qt, arg)] = arg in res["after"]["tables"]
        elif qt == "col_exists":
            t, c = arg
            out[(qt, arg)] = t in res["after"]["tables"] and c in res["after"]["tables"][t]["cols"]
        elif qt == "new_id":
            t, nm = arg
            tab = res["after"]["tables"].get(t)
            hit = [r[0] for r in (tab["rows"] if tab else []) if len(r) > 1 and r[1] == nm]
            out[(qt, arg)] = str(hit[0]) if hit else "(no such row)"
    return out


def face(s, stmts, qt, arg, before):
    """The face value of the statements: rows go only where a statement names them, nothing fails, NULL compares
    like a value, LIKE is case-sensitive."""
    d = s["dom"]
    tabs = json.loads(json.dumps(before["tables"]))
    for st in stmts:
        m = re.match(r"DELETE FROM (\w+)(?: WHERE (.*))?;", st)
        if m and m.group(1) in tabs:
            t, cond = m.group(1), m.group(2)
            cols = tabs[t]["cols"]
            keep = []
            for r in tabs[t]["rows"]:
                rr = dict(zip(cols, r))
                hit = True
                if cond:
                    m2 = re.match(r"(\w+) (=|!=|>=|>|LIKE|IS) (.+)", cond)
                    if m2 and m2.group(1) in rr:
                        a, op, b = rr[m2.group(1)], m2.group(2), m2.group(3)
                        bv = None if b in ("NULL",) else (b.strip("'").rstrip("%") if b.startswith("'") else
                                                          (int(b) if b.lstrip("-").isdigit() else b))
                        if op in ("=", "IS"):
                            hit = a == bv
                        elif op == "!=":
                            hit = a != bv
                        elif op == ">=":
                            hit = a is not None and isinstance(bv, int) and a >= bv
                        elif op == ">":
                            hit = a is not None and isinstance(bv, int) and a > bv
                        elif op == "LIKE":
                            hit = isinstance(a, str) and a.startswith(str(bv))
                    else:
                        hit = False
                if not hit:
                    keep.append(r)
            tabs[t]["rows"] = keep
        m = re.match(r"INSERT INTO (\w+)", st)
        if m and m.group(1) in tabs and "ON CONFLICT" not in st:
            tabs[m.group(1)]["rows"].append([None] * len(tabs[m.group(1)]["cols"]))
        m = re.match(r"DROP TABLE (\w+);", st)
        if m:
            tabs.pop(m.group(1), None)
    if qt.startswith("fails"):
        return False
    if qt == "rows":
        return None if arg not in tabs else len(tabs[arg]["rows"])
    if qt == "other":
        return False
    if qt == "value":
        t, rid, col = arg
        for st in stmts:
            m = re.match(rf"UPDATE {t} SET {col} = (.+?)(?: WHERE id = (\d+))?;", st)
            if m and (m.group(2) is None or int(m.group(2)) == rid):
                expr = m.group(1)
                v = cell({"tables": tabs}, t, rid, col)
                m3 = re.match(rf"{col} - (\d+)", expr)
                if m3 and v.lstrip("-").isdigit():
                    return str(int(v) - int(m3.group(1)))
                return expr.strip("'")
        return cell({"tables": tabs}, t, rid, col)
    if qt == "table_exists":
        return arg in tabs
    if qt == "col_exists":
        t, c = arg
        return t in tabs and (c in tabs[t]["cols"] or (c == "extra" and any("ADD COLUMN extra" in x for x in stmts))) and \
            not any(f"DROP COLUMN {c};" in x for x in stmts)
    return None


def perturb(s, rng):
    s2 = json.loads(json.dumps(s))
    op = rng.choice(["fk_on", "fk_mode", "trigger", "unique", "check", "row"])
    if op == "fk_on":
        s2["fk_on"] = not s2["fk_on"]
    elif op == "fk_mode":
        s2["fk_mode"] = rng.choice([m for m in ["cascade", "set null", "restrict", "no action", "none"] if m != s["fk_mode"]])
    elif op == "trigger":
        allt = ["log_delete", "dec_on_insert", "lock_delete", "purge_on_zero"]
        t = rng.choice(allt)
        s2["triggers"] = [x for x in s2["triggers"] if x != t] if t in s2["triggers"] else s2["triggers"] + [t]
    elif op == "unique":
        s2["unique"] = not s2["unique"]
    elif op == "check":
        s2["check"] = not s2["check"]
    else:
        r = rng.choice(s2["C_rows"])
        r[3] = rng.randint(0, 5)
        r[1] = rng.choice([x[0] for x in s2["P_rows"]] + [None])
    return s2, op


def make_items(seed):
    rng = random.Random(stable_seed("rx_sql", seed))
    s = gen_db(rng)
    naive = {}
    if rng.random() < 0.8:
        name = rng.choice(TRAPS)
        require(name, s, rng)
        name, stmts, tables, naive = trap_form(name, s, rng)
        R = []
    else:
        R = forms(s, rng)
        name, stmts, tables = rng.choice(R)
    if R and rng.random() < 0.3 and len(stmts) == 1:
        n2, st2, t2 = rng.choice(R)
        if len(st2) == 1 and st2 != stmts:
            stmts = stmts + st2
            tables = list(dict.fromkeys(tables + t2))
            name = name + "+" + n2
    try:
        res = run(s, stmts)
    except Exception as e:  # noqa: BLE001
        return [], {"build_fail": 1, "last_error": str(e)[:150]}
    qs = questions(s, stmts, tables, res, rng)
    if naive:  # a trap: its target questions, one other-table control, and statement failures only for the traps whose
        # mechanism is a failure (decided per template, before any answer is seen); no random extras
        keep_other = [q_ for q_ in qs if q_[0] == "other"][:1]
        fail_traps = {"t_multirow_dup", "t_or_fail_partial", "t_on_update_cascade", "t_deferred_fk", "t_upsert_where",
                      "t_rowid_reuse", "t_not_in_subquery_null"}
        qs = ([q_ for q_ in qs if q_[0].startswith("fails")] if name in fail_traps else []) + keep_other
    have = {(q_[0], json.dumps(q_[1])) for q_ in qs}
    for (qt_, arg_) in naive:
        if (qt_, json.dumps(arg_)) in have:
            continue
        if qt_ == "fails":
            qs.append((f"fails{arg_}", arg_, yes_no(f"Does statement {arg_} fail (raise an error)?")))
        elif qt_ == "other":
            qs.append(("other", arg_, yes_no(f"After these statements, has any row of {arg_} been changed, added or deleted?")))
        else:
            qs.append((qt_, arg_, None))
    qs = [q_ for i_, q_ in enumerate(qs) if (q_[0], json.dumps(q_[1])) not in {(x[0], json.dumps(x[1])) for x in qs[:i_]}]
    twin = None
    for _ in range(6):
        s2, op = perturb(s, rng)
        try:
            r2 = run(s2, stmts)
        except Exception:  # noqa: BLE001
            continue
        if golds(qs, r2) != golds(qs, res):
            twin = (s2, r2, op)
            break
    inst = [("a", s, res)] + ([("b", twin[0], twin[1])] if twin else [])
    rows = []
    for side, s_, res_ in inst:
        g = golds(qs, res_)
        g0 = golds(qs, {"before": res_["before"], "after": res_["before"], "res": [["ok", ""]] * len(stmts)})
        floor = world_floor(RULES, render(s_, res_["before"]), stmts)
        what = "; ".join(f"statement {k}: {'ok' if r[0] == 'ok' else 'error (' + r[1] + ')'}"
                         for k, r in enumerate(res_["res"], 1)) + "."
        ceiling = world_ceiling(RULES, render_after(res_["after"]), what)
        allv = [res["after"], res["before"]] + ([twin[1]["after"]] if twin else [])
        for qt, arg, qd in qs:
            gold = g[(qt, arg)]
            if gold is None:
                continue
            if qt == "rows":
                hi = max([len(db["tables"].get(arg, {"rows": []})["rows"]) for db in allv] + [3]) + 1
                qd = choice(f"After these statements, how many rows does {arg} have?", [str(i) for i in range(0, min(hi, 9) + 1)])
                if str(gold) not in qd["criteria"]:
                    qd["criteria"][str(gold)] = str(gold)
            elif qt == "value":
                t, rid, col = arg
                opts = [cell(db, t, rid, col) for db in allv]
                for st in stmts:
                    opts += [x.strip("'") for x in re.findall(r"'[^']*'|\b-?\d+\b", st)][:3]
                opts += ["NULL", "(the row no longer exists)"]
                opts = list(dict.fromkeys(str(o) for o in opts if str(o)))[:7]
                if str(gold) not in opts:
                    opts.append(str(gold))
                qd = choice(f"After these statements, what is {col} of the {t} row whose id was {rid}?", opts)
            if qt == "new_id":
                t, nm = arg
                m = max([r[0] for r in res["before"]["tables"][t]["rows"]] + [0])
                qd = choice(f"After these statements, what id does the {t} row named {nm!r} have?",
                            [str(x) for x in range(max(1, m - 1), m + 3)] + ["(no such row)"])
                if str(gold) not in qd["criteria"]:
                    qd["criteria"][str(gold)] = str(gold)
            known0 = qt in ("rows", "value", "table_exists", "col_exists")
            nkey = ("fails", int(qt[5:])) if qt.startswith("fails") else (qt, arg)
            fv = naive[nkey] if nkey in naive else face(s_, stmts, qt, arg, res_["before"])
            if qt == "value" and fv is not None and str(fv) not in qd["criteria"]:
                qd["criteria"][str(fv)] = str(fv)
            rid_ = f"rxsql-{seed}-{side}-{qt}-{re.sub(r'[^A-Za-z0-9]', '_', json.dumps(arg))}"
            rows.append(row(world="rx_sql", family="sql", template=name, qtype="fails" if qt.startswith("fails") else qt,
                            steps=len(stmts), question=qd, gold=str(gold) if qd["type"] == "choice" else gold,
                            gold0=(str(g0[(qt, arg)]) if known0 and qd["type"] == "choice" else (g0[(qt, arg)] if known0 else None)),
                            known0=known0, floor=floor, ceiling=ceiling, rid=rid_,
                            twin=(f"rxsql-{seed}-{'b' if side == 'a' else 'a'}" if twin else None),
                            face=(str(fv) if fv is not None and qd["type"] == "choice" else fv),
                            struct={"db": s_, "stmts": stmts, "res": res_["res"], "op": twin[2] if twin else None}))
    return rows, {"scenarios": 1, "twins": int(bool(twin))}
