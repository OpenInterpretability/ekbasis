"""Migration guard probes: show the mechanism, in code, before the model reads the state.

A migration that passes on the base schema can still fail in production because of rows the scratch database does not
have. The probes run the migration on copies of the scratch (never on the replica) and report PostgreSQL's own error:

- key collision: an INSERT without ON CONFLICT into a table that already has a UNIQUE/PRIMARY KEY is run twice on a
  copy; the second run's error shows what happens when the key already exists. A collision with the base's own rows,
  or a file that inserts the same key twice, already fails the first run on the scratch: that is decided by the probe of
  the whole file (a real error), and this probe stays silent (it reports only a failure of the repeated statement);
- missing or present source: the tables the migration reads that hold rows inserted by earlier migrations are emptied
  on a copy, and the ones that are empty get one made-up row; a NOT NULL error shows what happens when those rows are
  missing, or when such a row exists;
- referenced rows: a DELETE (or an update of key columns) on a table that a foreign key with ON DELETE/UPDATE NO ACTION
  or RESTRICT references; a made-up row of the referencing table is added on a copy, and a foreign key error shows the
  mechanism. Without one, the foreign key itself is stated.

Made-up rows have fixed values (marked ekbasis_probe) chosen by the guard; nothing is read from production. They are
hypothetical, so a probe that needs them only adds a fact for the model, worded as a condition ("if ..."). A failure is
decided in code only from the replica's statistics (aggregates, never values): a DELETE of every row of a table whose
referencing table holds non-NULL references, and (from v4) SET NOT NULL on a column the replica shows NULLs in that
nothing earlier in the file fills.
"""
from __future__ import annotations

import re

QID = r'(?:"(?:[^"]|"")+"|[A-Za-z_][\w$]*)'
QNAME = rf"((?:{QID}\s*\.\s*)?{QID})"
INSERT = re.compile(rf"^\s*(?:WITH\b.*?\)\s*)?INSERT\s+INTO\s+{QNAME}", re.I | re.S)
DELETE = re.compile(rf"^\s*(?:WITH\b.*?\)\s*)?DELETE\s+FROM\s+(?:ONLY\s+)?{QNAME}", re.I | re.S)
UPDATE = re.compile(rf"^\s*(?:WITH\b.*?\)\s*)?UPDATE\s+(?:ONLY\s+)?{QNAME}(?:\s+(?:AS\s+)?{QID})?\s+SET\s+(.*?)"
                    r"(?:\bFROM\b|\bWHERE\b|\bRETURNING\b|$)", re.I | re.S)
TRUNCATE = re.compile(rf"^\s*TRUNCATE\s+(?:TABLE\s+)?(?:ONLY\s+)?{QNAME}", re.I | re.S)
ALTER_TABLE = re.compile(rf"^\s*ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?:ONLY\s+)?{QNAME}\s+(.*)$", re.I | re.S)
READS = re.compile(rf"\b(?:FROM|JOIN)\s+(?:ONLY\s+)?{QNAME}", re.I)
WHERE = re.compile(r"\bWHERE\b", re.I)
ON_CONFLICT = re.compile(r"\bON\s+CONFLICT\b", re.I)
MAX_PROBES = 8
ERR = re.compile(r"ERROR:\s*(?:([0-9A-Z]{5}):\s*)?(.*)")


def unq(name: str) -> str:
    last = re.findall(QID, name)[-1]
    return last[1:-1].replace('""', '"') if last.startswith('"') else last.lower()


def find(tables: list, name: str):
    n = unq(name)
    return next((t for t in tables if t["name"] == n), None) or next(
        (t for t in tables if t["name"].lower() == n.lower()), None)


def qt(t: dict) -> str:
    return '"' + t["schema"].replace('"', '""') + '"."' + t["name"].replace('"', '""') + '"'


def qc(c: str) -> str:
    return '"' + c.replace('"', '""') + '"'


def disp(t: dict) -> str:
    return t["name"] if t["schema"] == "public" else f"{t['schema']}.{t['name']}"


def _split_top(text: str) -> list:
    out, depth, buf = [], 0, []
    for ch in text:
        depth += ch == "("
        depth -= ch == ")"
        if ch == "," and depth == 0:
            out.append("".join(buf).strip())
            buf = []
            continue
        buf.append(ch)
    if "".join(buf).strip():
        out.append("".join(buf).strip())
    return out


def _cols(text: str) -> list:
    return [unq(m) for m in re.findall(QID, text or "")]


def has_unique(t: dict) -> bool:
    return any(k["type"] in ("u", "p") for k in t.get("cons") or []) or any(
        i.startswith("CREATE UNIQUE INDEX") for i in t.get("idx") or [])


def child_fks(tables: list, t: dict, on: str) -> list:
    """(child table, constraint name, child columns, parent columns) for foreign keys that reference t and block a
    DELETE (on="DELETE") or an UPDATE of the key (on="UPDATE"): NO ACTION or RESTRICT."""
    out = []
    for c in tables:
        for k in c.get("cons") or []:
            if k["type"] != "f" or k.get("ref") != t["oid"]:
                continue
            d = k["def"] or ""
            if re.search(rf"ON {on} (CASCADE|SET NULL|SET DEFAULT)", d, re.I):
                continue
            m = re.match(r"FOREIGN KEY \((.*?)\) REFERENCES .*?\((.*?)\)", d)
            if m:
                out.append((c, k["name"], _cols(m.group(1)), _cols(m.group(2))))
    return out


# ---------------------------------------------------------------- running a script on a copy

def run_script(pg, stmts: list, transaction: bool, pre: list = ()) -> tuple:
    """Run `pre` (setup on the copy) then `stmts`, stopping at the first error. (index of the failing statement in
    stmts, or -1 when a `pre` statement failed, or None; SQLSTATE; message)."""
    parts = [f"\\echo ekbasis_pre\n{s};" for s in pre]
    parts += [f"\\echo ekbasis_stmt_{i}\n{s};" for i, s in enumerate(stmts)]
    args = ["-v", "ON_ERROR_STOP=1", "-v", "VERBOSITY=verbose"] + (["--single-transaction"] if transaction else [])
    rc, out, err = pg.run(args + ["-f", "-"], stdin="\n".join(parts) + "\n")
    if rc == 0:
        return None, None, None
    marks = re.findall(r"ekbasis_(pre|stmt_(\d+))", out)
    m = ERR.search(err or "")
    code, msg = (m.group(1), m.group(2).strip()[:300]) if m else (None, (err or "").strip()[:300])
    if not marks or marks[-1][0] == "pre":
        return -1, code, msg
    return int(marks[-1][1]), code, msg


# ---------------------------------------------------------------- made-up rows

NOT_FOUND = "IF NOT FOUND THEN RAISE EXCEPTION 'ekbasis_probe: no row inserted'; END IF"   # plpgsql, inside DO
NUM = {"int2": "30001", "int4": "900000001", "int8": "900000001", "numeric": "900000001", "float4": "900000001",
       "float8": "900000001", "oid": "900000001"}


def value_expr(col: dict, enums: dict, n: int) -> str | None:
    """A fixed made-up value for a column (never read from anywhere), or None when the guard has none for its type."""
    tn = (col.get("typname") or "").lower()
    typ = col["type"]
    if tn.startswith("_"):
        return f"'{{}}'::{typ}"
    if tn in NUM:
        return f"{NUM[tn]}::{typ}"
    if tn in ("text", "varchar", "bpchar", "name", "citext"):
        return f"'ekbasis_probe_{n}'::{typ}"
    if tn == "uuid":
        return f"'00000000-0000-4000-8000-{n:012d}'::uuid"
    if tn == "bool":
        return "false"
    if tn in ("timestamp", "timestamptz", "date", "time", "timetz"):
        return f"now()::{typ}"
    if tn in ("json", "jsonb"):
        return f"'{{}}'::{typ}"
    if tn == "bytea":
        return "'\\x00'::bytea"
    if tn == "interval":
        return "'1 day'::interval"
    if tn in ("inet", "cidr"):
        return f"'10.0.0.1'::{typ}"
    if tn in enums and enums[tn]:
        return "'" + enums[tn][0].replace("'", "''") + f"'::{typ}"
    return None


def insert_made_up(catalog: dict, t: dict, n: int, refs: set | None = None, depth: int = 0,
                   fill_all: bool = False, fill_cols: frozenset = frozenset()) -> list | None:
    """Statements that insert one made-up row into t. A NOT NULL foreign key points at the first row of its parent; a
    parent with no row gets a made-up one first (up to depth 2). refs: names of foreign keys to fill even when the column
    is nullable. None when a NOT NULL column has no value the guard can make up."""
    tables = catalog.get("tables") or []
    enums = catalog.get("enums") or {}
    byoid = {x["oid"]: x for x in tables}
    fkcol = {}
    for k in t.get("cons") or []:
        m = re.match(r"FOREIGN KEY \((.*?)\) REFERENCES .*?\((.*?)\)", k["def"] or "") if k["type"] == "f" else None
        parent = byoid.get(k.get("ref"))
        if m and parent:
            for c, p in zip(_cols(m.group(1)), _cols(m.group(2))):
                fkcol[c] = (k["name"], parent, p)
    names, exprs, joins, pre = [], [], {}, []
    for c in t.get("cols") or []:
        if c.get("generated"):
            continue
        name = c["name"]
        if name in fkcol:
            kname, parent, pcol = fkcol[name]
            if not c["notnull"] and kname not in (refs or {}) and name not in fill_cols:
                continue                                   # a nullable reference stays NULL
            alias = joins.setdefault(kname, (f"p{len(joins)}", parent))[0]
            names.append(name)
            exprs.append(f"{alias}.{qc(pcol)}")
            continue
        if c.get("default") or (not c["notnull"] and not fill_all and name not in fill_cols):
            continue
        e = value_expr(c, enums, n)
        if e is None:
            if c["notnull"]:
                return None
            continue
        names.append(name)
        exprs.append(e)
    for alias, parent in joins.values():
        if parent["oid"] == t["oid"] or depth >= 3:
            continue
        sub = made_up_row(catalog, parent, n + 1, depth=depth + 1)
        if sub is None:
            return None
        tag = f"$ekb{depth}$"
        pre.append(f"DO {tag} BEGIN IF NOT EXISTS (SELECT 1 FROM {qt(parent)}) THEN {sub}; END IF; END {tag}")
    if not names:
        return pre + [f"INSERT INTO {qt(t)} DEFAULT VALUES"]
    frm = (" FROM " + ", ".join(f"(SELECT * FROM {qt(p)} LIMIT 1) AS {a}" for a, p in joins.values())) if joins else ""
    return pre + [f"INSERT INTO {qt(t)} ({', '.join(qc(x) for x in names)}) OVERRIDING SYSTEM VALUE "
                  f"SELECT {', '.join(exprs)}{frm}", NOT_FOUND]


def nullable_fks(t: dict) -> list:
    names = {c["name"]: c for c in t.get("cols") or []}
    out = []
    for k in t.get("cons") or []:
        m = re.match(r"FOREIGN KEY \((.*?)\)", k["def"] or "") if k["type"] == "f" else None
        if m and all(not names.get(c, {}).get("notnull", True) for c in _cols(m.group(1))):
            out.append(k["name"])
    return out


def made_up_row(catalog: dict, t: dict, n: int, refs: set | None = None, depth: int = 0) -> str | None:
    """One statement that inserts a made-up row into t, trying variants until one satisfies t's CHECK constraints: the
    NOT NULL columns only, then with one nullable foreign key filled (up to 3), then with one nullable column a CHECK
    names filled (up to 4), then every nullable column filled. A failure of the last variant is raised (the probe is
    then dropped)."""
    variants = []
    checked = [c["name"] for c in t.get("cols") or [] if not c["notnull"] and any(
        k["type"] == "c" and re.search(r"(?<![\w$])\"?" + re.escape(c["name"]) + r"\"?(?![\w$])", k["def"] or "")
        for k in t.get("cons") or [])]
    tries = ([(set(), False, frozenset())] + [({k}, False, frozenset()) for k in nullable_fks(t)[:3]]
             + [(set(), False, frozenset([c])) for c in checked[:4]] + [(set(), True, frozenset())])
    for extra, fill_all, cols in tries:
        v = insert_made_up(catalog, t, n, (refs or set()) | extra, depth, fill_all, cols)
        if v is not None and v not in variants:
            variants.append(v)
    if not variants:
        return None
    body = "; ".join(variants[-1])
    for v in reversed(variants[:-1]):
        body = "BEGIN " + "; ".join(v) + "; EXCEPTION WHEN others THEN " + body + "; END"
    tag = f"$ekr{depth}{n}$"
    return f"DO {tag} BEGIN {body}; END {tag}"


# ---------------------------------------------------------------- the probes

def probe_facts(scratch, catalog: dict, stmts: list, stats: dict | None, transaction: bool, outside_bodies) -> tuple:
    """(facts, decided failure or None). scratch: the Scratch (clone/drop); catalog: the base schema before the file."""
    tables = catalog.get("tables") or []
    created = set()
    facts, decided, probes = [], None, 0
    flat = [outside_bodies(s) for s in stmts]
    for s in flat:
        m = re.match(rf"^\s*CREATE\s+(?:UNLOGGED\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?{QNAME}", s, re.I)
        if m:
            created.add(unq(m.group(1)))

    def existing(name):
        t = find(tables, name)
        return t if t and t["name"] not in created else None

    def on_copy(stmts_, pre=()):
        nonlocal probes
        probes += 1
        pg = scratch.clone()
        try:
            return run_script(pg, stmts_, transaction, pre)
        finally:
            scratch.drop(pg)

    def rows_in(_, t) -> int:
        try:
            return int(scratch.db.json(f"SELECT count(*) FROM (SELECT 1 FROM {qt(t)} LIMIT 1000) AS x") or 0)
        except Exception:
            return 0

    # decided in code from the replica (aggregates only)
    if stats:
        decided = _replica_decisions(tables, flat, stats, existing)

    # 1. key collision
    for i, s in enumerate(flat):
        if probes >= MAX_PROBES:
            break
        m = INSERT.match(s)
        if not m or ON_CONFLICT.search(s):
            continue
        t = existing(m.group(1))
        if not t or not has_unique(t):
            continue
        idx, code, msg = on_copy(stmts[:i + 1] + [stmts[i]])
        if idx == i + 1 and code == "23505":
            facts.append(f"Checked on a copy of the base schema: if {disp(t)} already holds a row with the key that "
                         f"action {i + 1} inserts, action {i + 1} fails with: {msg}.")

    # 2. missing source rows
    read = {}
    for i, s in enumerate(flat):
        if INSERT.match(s) or UPDATE.match(s):
            for name in READS.findall(s):
                t = existing(name)
                if t:
                    read.setdefault(t["oid"], t)
    full = [t for t in read.values() if rows_in(None, t)]
    if full and probes < MAX_PROBES:
        pre = ["TRUNCATE " + ", ".join(qt(t) for t in full) + " CASCADE"]
        idx, code, msg = on_copy(stmts, pre)
        if idx is not None and idx >= 0 and code == "23502":
            facts.append(f"Checked on a copy of the base schema: if {', '.join(disp(t) for t in full)} do not hold the "
                         f"rows that earlier migrations inserted, action {idx + 1} fails with: {msg}.")

    # 2b. source rows present: the tables read that are empty in the scratch get one made-up row each
    empty = [t for t in read.values() if not rows_in(None, t)]
    rows = [r for r in (made_up_row(catalog, t, 3 + k) for k, t in enumerate(empty)) if r]
    if rows and probes < MAX_PROBES:
        idx, code, msg = on_copy(stmts, rows)
        if idx is not None and idx >= 0 and code == "23502":
            facts.append(f"Checked on a copy of the base schema: if {', '.join(disp(t) for t in empty)} hold rows (one "
                         f"made-up row each, its optional columns NULL), action {idx + 1} fails with: {msg}.")

    # 3. rows still referenced
    for i, s in enumerate(flat):
        if probes >= MAX_PROBES:
            break
        md, mu, mt = DELETE.match(s), UPDATE.match(s), TRUNCATE.match(s)
        if md or mt:
            t, on = existing((md or mt).group(1)), "DELETE"
        elif mu:
            t, on = existing(mu.group(1)), "UPDATE"
        else:
            continue
        if not t:
            continue
        fks = child_fks(tables, t, on)
        if on == "UPDATE":
            setcols = {unq(c) for c in re.findall(rf"({QID})\s*=", mu.group(2))}
            fks = [f for f in fks if set(f[3]) & setcols]
        hit = False
        for c, kname, ccols, pcols in fks:
            if c["name"] in created or probes >= MAX_PROBES:
                continue
            pre = []
            if not rows_in(None, t):
                parent_row = made_up_row(catalog, t, 1)
                if parent_row is None:
                    continue
                pre.append(parent_row)
            child = _child_rows(catalog, c, t, kname, ccols, pcols)
            if child is None:
                continue
            idx, code, msg = on_copy(stmts, pre + child)
            if idx is not None and idx >= 0 and code == "23503":
                facts.append(f"Checked on a copy of the base schema: if a row of {disp(c)} still references a row that "
                             f"action {idx + 1} {'deletes' if on == 'DELETE' else 'changes'}, action {idx + 1} fails "
                             f"with: {msg}.")
                hit = True
                break
        if not hit and fks and on == "DELETE" and not mt:
            c, kname = fks[0][0], fks[0][1]
            facts.append(f"Foreign key {kname} on {disp(c)} references {disp(t)} with ON DELETE NO ACTION: action "
                         f"{i + 1} fails if any row it deletes is still referenced.")
    return facts, decided


def _child_rows(catalog, c, t, kname, ccols, pcols) -> list | None:
    """A made-up row of c whose foreign key kname points at a row of t (one per row of t, up to 50, when the made-up
    values allow it; else one)."""
    one = made_up_row(catalog, c, 7, refs={kname})
    if one is None:
        return None
    many = one.replace(f"(SELECT * FROM {qt(t)} LIMIT 1)", f"(SELECT * FROM {qt(t)} LIMIT 50)")
    if many == one:
        return [one]
    return [f"DO $ekbc$ BEGIN BEGIN EXECUTE {_dq(many)}; EXCEPTION WHEN others THEN EXECUTE {_dq(one)}; END; END $ekbc$"]


def _dq(sql: str) -> str:
    return "'" + sql.replace("'", "''") + "'"


def _replica_decisions(tables, flat, stats, existing) -> str | None:
    rows = stats.get("rows") or {}
    cols = stats.get("cols") or {}
    writes, deletes = {}, set()
    for i, s in enumerate(flat):
        md, mt, mu = DELETE.match(s), TRUNCATE.match(s), UPDATE.match(s)
        if mu:
            t = existing(mu.group(1))
            if t:
                writes.setdefault(t["name"], set()).update(unq(c) for c in re.findall(rf"({QID})\s*=", mu.group(2)))
        if md or mt:
            t = existing((md or mt).group(1))
            if not t:
                continue
            deletes.add(t["name"])
            if (md and WHERE.search(s)) or (mt and re.search(r"\bCASCADE\b", s, re.I)):
                continue
            for c, kname, ccols, _ in child_fks(tables, t, "DELETE"):
                n = rows.get(f"{c['schema']}.{c['name']}") or 0
                nf = [((cols.get(f"{c['schema']}.{c['name']}.{x}") or [1, 0])[0] or 0) for x in ccols]
                if n > 0 and all(f < 1 for f in nf):
                    return (f"action {i + 1} deletes every row of {disp(t)}, and the replica's statistics show "
                            f"{disp(c)} holding about {int(n):,} rows whose foreign key {kname} references it "
                            "(not all NULL)")
        m = ALTER_TABLE.match(s)
        if m:
            t = existing(m.group(1))
            if not t:
                continue
            for sub in _split_top(m.group(2)):
                w = re.match(rf"ALTER\s+(?:COLUMN\s+)?({QID})\s+(?:SET\s+DATA\s+)?TYPE\b.*\bUSING\b", sub, re.I | re.S)
                if w:
                    writes.setdefault(t["name"], set()).add(unq(w.group(1)))
                    continue
                nn = re.match(rf"ALTER\s+(?:COLUMN\s+)?({QID})\s+SET\s+NOT\s+NULL\b", sub, re.I)
                if not nn:
                    continue
                col = unq(nn.group(1))
                st = cols.get(f"{t['schema']}.{t['name']}.{col}")
                if st and (st[0] or 0) >= 0.005 and col not in writes.get(t["name"], set()) \
                        and t["name"] not in deletes:
                    return (f"action {i + 1} makes {disp(t)}.{col} NOT NULL, and the replica's statistics show about "
                            f"{st[0] * 100:.0f}% of its rows NULL with no earlier statement of the file filling them")
    return None
