"""The migration guard's rule (0.1.22, the default policy): does a PostgreSQL migration fail or lose data, decided in
code from the facts the guard collects (the schema, the replica's statistics as the state shows them, the probes' facts,
the transaction mode) and the documented semantics of PostgreSQL 16. No model.

It is the frozen R_NOSEED of the pre-registered study `studies/migrations-rich-rule` (ekbasis-cookbook), unchanged
except for this module's packaging: a rule written from the PostgreSQL documentation over the same facts the model
reads matched or beat the model, and with realistic seed data it was more accurate (Rails v7: false alarms 4.4% vs
7.5%). Where the facts do not show the rows' values, it takes the conservative reading: what may happen counts.

    decide(facts_from(catalog, stmts, stats, transaction, schema_error, probe_facts)) -> ("fails" | "loses" | "ok", [why])

The migration is simulated statement by statement on a model of the reached tables:
- a table has rows unless the replica says 0 rows, or it was created (or emptied) by the file; with no replica it
  holds production data, so it has rows;
- a column may hold NULLs when the replica shows a NULL fraction, when it is nullable (no replica), or when it was added
  by the file without a default; it holds non-NULL values when the table has rows and it is not 100% NULL;
- a statement that fails changes nothing; in a transaction, a failure rolls back the whole file (nothing lost); in
  autocommit, the statements that do not fail keep their effect.

Failures (data-dependent; failures on the schema alone are the guard's schema error):
  ADD COLUMN ... NOT NULL without DEFAULT on a table with rows;
  SET NOT NULL / ADD PRIMARY KEY on a column that may hold NULLs;
  UNIQUE / PRIMARY KEY / CREATE UNIQUE INDEX on columns that hold repeated values (a constant DEFAULT on 2+ rows,
    fewer distinct values than rows);
  FOREIGN KEY (validated) on a column that holds non-NULL values the file did not copy from the referenced key;
  a cast of values that need not parse as the target type (text to json, uuid, numbers, booleans, dates, enums), to an
    enum without one of the labels the column holds, or to a shorter varchar;
  INSERT ... SELECT of NULLs into a NOT NULL column; a DELETE of rows still referenced through NO ACTION/RESTRICT;
  setting a foreign-key column to a literal the referenced table need not hold;
  the probes' failure facts whose condition the replica's statistics satisfy.
Losses: DROP TABLE / TRUNCATE / DELETE of rows, DROP COLUMN of non-NULL values not copied elsewhere first, UPDATE
overwriting non-NULL values, DROP TYPE ... CASCADE, and casts that change values.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .probes import QID, QNAME, unq, _split_top


# ---------------------------------------------------------------- the facts (what the state shows)

@dataclass
class ColStat:
    null_pct: float | None = None   # None: no NULL fact shown; else "about x% NULL" (0.1: "a few NULL")
    all_distinct: bool = False
    distinct: int | None = None     # shown only when <= 10


@dataclass
class TableStat:
    rows: int | None                # None: unknown (no replica, or never analyzed)
    cols: dict = field(default_factory=dict)


@dataclass
class Facts:
    tool: str
    transaction: bool
    stmts: list
    flat: list                      # statements with bodies and literals blanked (migrations.outside_bodies)
    schema_error: str | None
    catalog: dict
    regime: str                     # "R": replica statistics; "N": none
    stats: dict | None              # {(schema, table): TableStat}; None without a replica
    probe_facts: list
    probe_decided: str | None = None

    def table_stat(self, t: dict) -> TableStat:
        if self.stats is None:
            return TableStat(rows=None)
        return self.stats.get((t["schema"], t["name"])) or TableStat(rows=None)


def reduce_stats(stats: dict, catalog: dict) -> dict:
    """The replica's statistics reduced to exactly what the state prints (migrations.table_facts): row counts, "about
    x% NULL" / "a few NULL", "all values distinct", "about k distinct values" for k <= 10. Nothing else."""
    out = {}
    rows = stats.get("rows") or {}
    cols = stats.get("cols") or {}
    for t in catalog.get("tables") or []:
        key = f"{t['schema']}.{t['name']}"
        n = rows.get(key)
        ts = TableStat(rows=None if n is None or n < 0 else int(round(n)))
        for c in t["cols"] or []:
            s = cols.get(f"{key}.{c['name']}")
            if not s:
                continue
            nf, nd = s
            cs = ColStat()
            if nf and nf > 0:
                cs.null_pct = round(nf * 100) if nf >= 0.005 else 0.1
            if nd is not None and nd != 0 and n:
                dist = -nd * n if nd < 0 else nd
                if nd == -1:
                    cs.all_distinct = True
                elif dist <= 10:
                    cs.distinct = max(1, round(dist))
            if cs.null_pct is not None or cs.all_distinct or cs.distinct is not None:
                ts.cols[c["name"]] = cs
        out[(t["schema"], t["name"])] = ts
    return out


def facts_from(catalog: dict, stmts: list, stats: dict | None, transaction: bool, schema_error: str | None = None,
               probe_facts=(), tool: str = "generic") -> Facts:
    """The rule's facts from what the guard already has in _check_file: the scratch catalog, the statements, the
    replica's statistics (or None), the transaction mode, the schema error and the probes' facts."""
    from .migrations import outside_bodies      # here: migrations imports this module
    catalog = catalog or {}
    return Facts(tool=tool, transaction=bool(transaction), stmts=list(stmts),
                 flat=[outside_bodies(s) for s in stmts], schema_error=schema_error, catalog=catalog,
                 regime="R" if stats else "N", stats=reduce_stats(stats, catalog) if stats else None,
                 probe_facts=list(probe_facts or []))


# ---------------------------------------------------------------- the rule

TEXTY = {"text", "varchar", "character varying", "char", "character", "bpchar", "citext", "name"}
STRICT = ("json", "jsonb", "uuid", "integer", "int", "int2", "int4", "int8", "bigint", "smallint", "numeric", "decimal",
          "real", "double precision", "float", "float4", "float8", "boolean", "bool", "timestamp", "date", "time",
          "inet", "cidr", "interval")
INTS = ("integer", "int", "int2", "int4", "int8", "bigint", "smallint", "serial", "bigserial")
FRACT = ("numeric", "decimal", "real", "double precision", "float", "float4", "float8")


def base_type(t: str) -> str:
    t = (t or "").strip().strip('"').lower()
    t = re.sub(r"\s*\(.*?\)", "", t)
    t = t.replace("without time zone", "").replace("with time zone", "tz").strip()
    if t.startswith("public."):
        t = t[7:].strip('"')
    return t


def tparam(t: str) -> int | None:
    m = re.search(r"\(\s*(\d+)", t or "")
    return int(m.group(1)) if m else None


class Col:
    def __init__(self, name, type_, notnull, default, nulls, values, new=False, ndistinct=None, all_distinct=False):
        self.name, self.type, self.notnull, self.default = name, type_, notnull, default
        self.nulls, self.values, self.new = nulls, values, new
        self.ndistinct, self.all_distinct = ndistinct, all_distinct
        self.copied = False       # its values were copied elsewhere by the file
        self.filled = False       # an UPDATE of the file set it
        self.fk_ok = False        # rows not matching a key were deleted by the file
        self.labels = None        # enum labels its values can hold (None: those of its type)
        self.fk_ref = None        # the table its foreign key references


class Tab:
    def __init__(self, name, rows, created=False, oid=None, cat=None):
        self.name, self.rows, self.created, self.oid, self.cat = name, rows, created, oid, cat
        self.cols = {}
        self.copied = False


class Sim:
    def __init__(self, f):
        self.f = f
        self.cat = f.catalog
        self.tabs = {}
        self.dropped = set()
        self.renamed = {}         # enum renamed by the file: old name (lower) -> new name (lower)
        self.enums = {k: list(v) for k, v in (f.catalog.get("enums") or {}).items()}
        self.byoid = {str(t["oid"]): t for t in f.catalog.get("tables") or []}

    # ------------------------------------------------------------ the model of a table
    def tab(self, name: str) -> Tab | None:
        n = unq(name)
        if n in self.tabs:
            return self.tabs[n]
        low = {k.lower(): k for k in self.tabs}
        if n.lower() in low:
            return self.tabs[low[n.lower()]]
        if n.lower() in self.dropped:
            return None
        t = next((t for t in self.cat.get("tables") or [] if t["name"] == n), None) or next(
            (t for t in self.cat.get("tables") or [] if t["name"].lower() == n.lower()), None)
        if not t:
            return None
        ts = self.f.table_stat(t)
        rows = ts.rows if ts.rows is not None else -1          # -1: unknown, holds production data
        T = Tab(t["name"], rows, oid=str(t["oid"]), cat=t)
        for c in t["cols"] or []:
            cs = ts.cols.get(c["name"])
            if self.f.stats is not None and ts.rows is not None:
                nulls = bool(cs and cs.null_pct is not None)
                values = rows > 0 and not (cs and cs.null_pct is not None and cs.null_pct >= 100)
                nd = cs.distinct if cs else None
                alld = bool(cs and cs.all_distinct)
            else:
                nulls, values, nd, alld = not c["notnull"], True, None, False
            T.cols[c["name"]] = Col(c["name"], c["type"], c["notnull"], c["default"], nulls and rows != 0,
                                    values and rows != 0, ndistinct=nd, all_distinct=alld)
        for k in t.get("cons") or []:
            mm = re.match(r"FOREIGN KEY \((.*?)\) REFERENCES (\S+?)\(", k["def"] or "") if k["type"] == "f" else None
            if mm:
                for cn in cols_of(mm.group(1)):
                    if cn in T.cols:
                        T.cols[cn].fk_ref = unq(mm.group(2))
        self.tabs[t["name"]] = T
        return T

    def has_rows(self, T: Tab) -> bool:
        return T.rows != 0

    def col(self, T: Tab, name: str) -> Col | None:
        n = unq(name)
        return T.cols.get(n) or next((c for k, c in T.cols.items() if k.lower() == n.lower()), None)

    def enum_of(self, typ: str) -> list | None:
        b = base_type(typ)
        b = self.renamed.get(b, b)
        for k, v in self.enums.items():
            if k.lower() == b:
                return v
        return None


def cols_of(text: str) -> list:
    return [unq(m) for m in re.findall(QID, text or "")]


def cast_fails(sim: Sim, src: str, dst: str, col: Col) -> str | None:
    """Why a cast of col's values from src to dst may fail, or None."""
    if not col.values:
        return None
    s, d = base_type(src), base_type(dst)
    se, de = sim.enum_of(src), sim.enum_of(dst)
    if de is not None:
        if se is not None or col.labels is not None:
            have = col.labels if col.labels is not None else se
            gone = [x for x in have if x not in de]
            if gone:
                return f"enum labels {gone} not in {d}"
            return None
        if s in TEXTY or s.endswith("[]") is False and s not in ("",):
            if col.all_distinct and col.ndistinct is None:
                return f"values of {col.name} ({s}) need not be labels of {d}"
            return f"values of {col.name} ({s}) need not be labels of {d}"
        return None
    if s in TEXTY:
        if any(d == x or d.startswith(x) for x in STRICT):
            return f"text values of {col.name} need not parse as {d}"
        if d in ("varchar", "character varying", "char", "character", "bpchar"):
            n_old, n_new = tparam(src), tparam(dst)
            if n_new is not None and (n_old is None or n_new < n_old) :
                return f"values of {col.name} may be longer than {d}({n_new})"
    return None


def family(sim, t: str) -> str:
    b = base_type(t)
    if b.endswith("[]") or b.startswith("_"):
        return "array"
    if sim is not None and sim.enum_of(t) is not None:
        return "enum"
    for fam, names in (("text", TEXTY), ("int", INTS), ("fract", FRACT), ("bool", ("boolean", "bool")),
                       ("json", ("json", "jsonb")), ("uuid", ("uuid",)), ("bytea", ("bytea",)), ("date", ("date",))):
        if b in names:
            return fam
    if b.startswith("timestamp"):
        return "timestamp"
    return b


# casts that keep the value (the same text or number, in another type)
KEEP_FAM = {("int", "fract"), ("int", "text"), ("fract", "text"), ("enum", "text"), ("text", "enum"), ("uuid", "text"),
            ("text", "uuid"), ("text", "json"), ("json", "text"), ("enum", "enum"), ("timestamp", "text"),
            ("date", "timestamp"), ("text", "int"), ("text", "fract"), ("text", "timestamp"), ("text", "date"),
            ("bool", "text")}


def cast_loses(src: str, dst: str, sim=None) -> bool:
    s, d = base_type(src), base_type(dst)
    fs, fd = family(sim, src), family(sim, dst)
    if fs != fd and (fs, fd) not in KEEP_FAM and fs not in ("array",) and fd not in ("array",):
        return True
    if d in INTS and s in FRACT:
        return True
    if s.startswith("timestamp") and d.startswith("timestamp"):
        ps, pd = tparam(src), tparam(dst)
        ps = 6 if ps is None else ps
        pd = 6 if pd is None else pd
        return pd < ps
    if s.startswith("timestamp") and d == "date":
        return True
    if s in FRACT and d in FRACT:
        ps, pd = tparam(src), tparam(dst)
        return pd is not None and (ps is None or pd < ps)
    return False


ADD_CON = re.compile(r"^ADD\s+(?:CONSTRAINT\s+(" + QID + r")\s+)?(UNIQUE|PRIMARY\s+KEY|FOREIGN\s+KEY|CHECK|EXCLUDE)\b(.*)$",
                     re.I | re.S)
ADD_COL = re.compile(r"^ADD\s+(?:COLUMN\s+)?(?:IF\s+NOT\s+EXISTS\s+)?(" + QID + r")\s+(.*)$", re.I | re.S)
DROP_COL = re.compile(r"^DROP\s+(?:COLUMN\s+)?(?:IF\s+EXISTS\s+)?(" + QID + r")(\s+CASCADE|\s+RESTRICT)?\s*$", re.I | re.S)
ALT_TYPE = re.compile(r"^ALTER\s+(?:COLUMN\s+)?(" + QID + r")\s+(?:SET\s+DATA\s+)?TYPE\s+(.*?)(?:\s+USING\s+(.*))?$",
                      re.I | re.S)
SET_NN = re.compile(r"^ALTER\s+(?:COLUMN\s+)?(" + QID + r")\s+SET\s+NOT\s+NULL\s*$", re.I)
SET_DEF = re.compile(r"^ALTER\s+(?:COLUMN\s+)?(" + QID + r")\s+SET\s+DEFAULT\b", re.I)
RENAME_COL = re.compile(r"^RENAME\s+(?:COLUMN\s+)?(" + QID + r")\s+TO\s+(" + QID + r")\s*$", re.I)
RENAME_TAB = re.compile(r"^RENAME\s+TO\s+(" + QID + r")\s*$", re.I)
VALIDATE = re.compile(r"^VALIDATE\s+CONSTRAINT\b", re.I)

ALTER_TABLE = re.compile(rf"^\s*ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?:ONLY\s+)?{QNAME}\s+(.*)$", re.I | re.S)
CREATE_TABLE = re.compile(rf"^\s*CREATE\s+(?:UNLOGGED\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?{QNAME}\s*(\(.*)?$", re.I | re.S)
CREATE_TABLE_AS = re.compile(rf"^\s*CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?{QNAME}\s+AS\b(.*)$", re.I | re.S)
DROP_TABLE = re.compile(r"^\s*DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?(.*?)(\s+CASCADE|\s+RESTRICT)?\s*$", re.I | re.S)
UNIQUE_IDX = re.compile(rf"^\s*CREATE\s+UNIQUE\s+INDEX\s+(?:CONCURRENTLY\s+)?(?:IF\s+NOT\s+EXISTS\s+)?(?:{QID}\s+)?ON\s+"
                        rf"(?:ONLY\s+)?{QNAME}\s*(?:USING\s+\w+\s*)?\((.*)\)(.*)$", re.I | re.S)
INSERT = re.compile(rf"^\s*(?:WITH\b.*?\)\s*)?INSERT\s+INTO\s+{QNAME}\s*(\([^)]*\))?\s*(.*)$", re.I | re.S)
UPDATE = re.compile(rf"^\s*(?:WITH\b.*?\)\s*)?UPDATE\s+(?:ONLY\s+)?{QNAME}(?:\s+(?:AS\s+)?(?!SET\b){QID})?\s+SET\s+(.*?)"
                    r"(?:\s+FROM\s+(.*?))?(?:\s+WHERE\s+(.*))?$", re.I | re.S)
DELETE = re.compile(rf"^\s*(?:WITH\b.*?\)\s*)?DELETE\s+FROM\s+(?:ONLY\s+)?{QNAME}(.*)$", re.I | re.S)
TRUNCATE = re.compile(r"^\s*TRUNCATE\s+(?:TABLE\s+)?(?:ONLY\s+)?(.*?)(\s+CASCADE|\s+RESTRICT)?\s*$", re.I | re.S)
DROP_TYPE = re.compile(r"^\s*DROP\s+TYPE\s+(?:IF\s+EXISTS\s+)?(.*?)(\s+CASCADE)?\s*$", re.I | re.S)
CREATE_ENUM = re.compile(rf"^\s*CREATE\s+TYPE\s+{QNAME}\s+AS\s+ENUM\s*\((.*)\)\s*$", re.I | re.S)
ALTER_TYPE_RENAME = re.compile(rf"^\s*ALTER\s+TYPE\s+{QNAME}\s+RENAME\s+TO\s+({QID})\s*$", re.I)
ALTER_TYPE_ADD = re.compile(rf"^\s*ALTER\s+TYPE\s+{QNAME}\s+ADD\s+VALUE\s+(?:IF\s+NOT\s+EXISTS\s+)?'([^']*)'", re.I)
ALTER_TYPE_RENVAL = re.compile(rf"^\s*ALTER\s+TYPE\s+{QNAME}\s+RENAME\s+VALUE\s+'([^']*)'\s+TO\s+'([^']*)'", re.I)


def _set_literal(raw: str, col: str) -> str | None:
    m = re.search(rf"\bSET\b.*?{re.escape(col)}\s*=\s*'((?:[^']|'')*)'", raw, re.I | re.S)
    return m.group(1) if m else None


DEDUPE = re.compile(r"ROW_NUMBER\s*\(\s*\)\s*OVER|HAVING\s+count|NOT\s+IN\s*\(\s*SELECT\s+(?:MIN|MAX)\s*\("
                    r"|\bGROUP\s+BY\b.*\bHAVING\b", re.I | re.S)
JSONOP = re.compile(r"->|\?|@>|jsonb_|json_", re.I)


def closed(sim: "Sim", c: "Col") -> bool:
    """Its values come from a small closed set: an enum, a boolean, or a replica count of at most 10 distinct values."""
    return sim.enum_of(c.type) is not None or base_type(c.type) in ("boolean", "bool") or c.ndistinct is not None


def _balanced(x: str) -> bool:
    d = 0
    for ch in x:
        d += ch == "("
        d -= ch == ")"
        if d < 0:
            return False
    return d == 0


def where_matches(sim: "Sim", T: "Tab", where: str, literals_present: bool = False) -> bool:
    """Whether any row of T may satisfy the condition, from what the facts show. A specific literal on a free-valued
    column is not assumed present (the state shows no value); duplicates are not assumed where nothing shows them."""
    if not where or not where.strip():
        return True
    if re.search(r"\bNOT\s+(?:IN|EXISTS)\s*\(\s*SELECT\b", where, re.I):
        return True
    top = re.split(r"\bOR\b", where, flags=re.I) if not re.search(r"\(.*\bOR\b.*\)", where, re.I | re.S) else [where]

    def atom(a: str) -> bool:
        a = a.strip()
        while a.startswith("(") and a.endswith(")") and _balanced(a[1:-1]):
            a = a[1:-1].strip()
        m = re.match(rf"(?:{QID}\s*\.\s*)?({QID})\s+IS\s+(NOT\s+)?NULL\b", a, re.I)
        if m:
            c = sim.col(T, m.group(1))
            return True if c is None else (c.values if m.group(2) else c.nulls)
        m = re.match(rf"(?:{QID}\s*\.\s*)?({QID})\s*(=|<>|!=|LIKE|ILIKE|IN)\s*(\(\s*''.*\)|''|-?\d+(?:\.\d+)?|TRUE|FALSE)"
                     rf"(?:\s*::\s*{QNAME})?\s*$", a, re.I | re.S)
        if m:
            c = sim.col(T, m.group(1))
            if m.group(2) in ("<>", "!="):
                return True
            if c is None:
                return True
            if m.group(3).upper() in ("TRUE", "FALSE"):
                return c.values
            return c.values
        return True

    for alt in top:
        parts = re.split(r"\bAND\b", alt, flags=re.I)
        if all(atom(p) for p in parts):
            return True
    return False


def decide(f) -> tuple:
    sim = Sim(f)
    why_fail, why_lost = [], []
    pending_lost = []              # (statement index, why): losses of statements that did not fail
    for i, (raw, s) in enumerate(zip(f.stmts, f.flat)):
        fails, lost = [], []
        _statement(sim, i, raw, s, fails, lost)
        if fails:
            why_fail += [f"action {i + 1}: {w}" for w in fails]
            if f.transaction:
                break
            continue               # autocommit: a failed statement changes nothing
        pending_lost += [f"action {i + 1}: {w}" for w in lost]
    # the probes' failure facts that the replica's statistics satisfy
    pf = _probe_fails(sim, f)
    why_fail += pf
    if why_fail:
        if f.transaction:
            return "fails", why_fail
        return "fails", why_fail + (["also loses: " + "; ".join(pending_lost)] if pending_lost else [])
    if pending_lost:
        return "loses", pending_lost
    return "ok", []


def _probe_fails(sim: Sim, f) -> list:
    out = []
    for fact in f.probe_facts:
        m = re.search(r"if (.*?) do not hold the rows that earlier migrations inserted", fact)
        if m:
            names = [x.strip() for x in m.group(1).split(",")]
            if f.stats is not None and all((sim.tab(n) is not None and sim.tab(n).rows == 0) for n in names):
                out.append("probe: " + fact)
            continue
        m = re.search(r"if (.*?) hold rows \(one made-up row each", fact)
        if m:
            names = [x.strip() for x in m.group(1).split(",")]
            if any((sim.tab(n) is not None and sim.tab(n).rows != 0) for n in names):
                out.append("probe: " + fact)
            continue
    return out


def _statement(sim: Sim, i: int, raw: str, s: str, fails: list, lost: list):
    m = CREATE_TABLE_AS.match(s)
    if m:
        T = Tab(unq(m.group(1)), -1, created=True)
        sim.tabs[T.name] = T
        for name in re.findall(rf"\bFROM\s+(?:ONLY\s+)?{QNAME}", m.group(2), re.I):
            src = sim.tab(name)
            if src:
                src.copied = True
                for c in src.cols.values():
                    c.copied = True
        return
    m = CREATE_TABLE.match(s)
    if m:
        n = unq(m.group(1))
        if sim.tab(n) and re.search(r"IF\s+NOT\s+EXISTS", s, re.I):
            return
        sim.dropped.discard(n.lower())
        T = Tab(n, 0, created=True)
        body = m.group(2) or ""
        body = body[body.find("(") + 1: body.rfind(")")] if "(" in body else ""
        for part in _split_top(body):
            mm = re.match(rf"({QID})\s+(.*)$", part.strip(), re.S)
            if mm and mm.group(1).upper() not in ("CONSTRAINT", "PRIMARY", "UNIQUE", "FOREIGN", "CHECK", "EXCLUDE"):
                typ = mm.group(2)
                T.cols[unq(mm.group(1))] = Col(unq(mm.group(1)), typ.split()[0] if typ.split() else "",
                                               bool(re.search(r"NOT\s+NULL|PRIMARY\s+KEY", typ, re.I)),
                                               None, False, False, new=True)
        sim.tabs[n] = T
        return
    m = ALTER_TABLE.match(s)
    if m:
        T = sim.tab(m.group(1))
        if T is None:
            return
        for sub in _split_top(m.group(2)):
            _alter(sim, T, sub.strip(), raw, fails, lost)
        return
    m = UNIQUE_IDX.match(s)
    if m:
        T = sim.tab(m.group(1))
        if T is None:
            return
        w = _unique_fails(sim, T, m.group(2), partial=bool(re.search(r"\bWHERE\b", m.group(3) or "", re.I)))
        if w:
            fails.append(w)
        return
    m = DROP_TABLE.match(s)
    if m:
        for name in _split_top(m.group(1)):
            T = sim.tab(name.strip())
            if T is None:
                continue
            if sim.has_rows(T) and not T.copied and any(c.values and not c.copied for c in T.cols.values()):
                lost.append(f"drops {T.name}, which holds rows not copied elsewhere")
            # rows of tables referencing it through the dropped foreign key stay; nothing else lost
            sim.tabs.pop(T.name, None)
            sim.dropped.add(T.name.lower())
            T.rows = 0
        return
    m = TRUNCATE.match(s)
    if m:
        for name in _split_top(m.group(1)):
            T = sim.tab(name.strip())
            if T and sim.has_rows(T) and not T.copied:
                lost.append(f"truncates {T.name}")
            if T:
                T.rows = 0
                for c in T.cols.values():
                    c.values = c.nulls = False
        return
    m = DELETE.match(s)
    if m:
        T = sim.tab(m.group(1))
        if T is None or not sim.has_rows(T):
            return
        rest = m.group(2) or ""
        wm = re.search(r"\bWHERE\b(.*)$", rest, re.I | re.S)
        where = wm.group(1) if wm else None
        using = re.match(r"\s*(?:AS\s+)?(?:" + QID + r"\s+)?USING\b", rest, re.I)
        if where is not None or using:
            if not where_matches(sim, T, (where or "") + (" " + rest if using else ""), literals_present=True):
                return
        blocked = _referenced(sim, T)
        if blocked:
            fails.append(f"deletes rows of {T.name} that {blocked} still references (ON DELETE NO ACTION)")
            return
        if not T.copied:
            lost.append(f"deletes rows of {T.name}" + (" (WHERE)" if where else ""))
        if where is None and not using:
            T.rows = 0
            for c in T.cols.values():
                c.values = c.nulls = False
        else:
            for name in re.findall(rf"({QID})\s+IS\s+NULL", where or "", re.I):
                c = sim.col(T, name)
                if c:
                    c.nulls = False
            orphan = re.search(rf"({QID})\s+NOT\s+IN\s*\(\s*SELECT\b", where or "", re.I)
            if orphan and sim.col(T, orphan.group(1)):
                sim.col(T, orphan.group(1)).fk_ok = True
            if re.search(r"\bNOT\s+EXISTS\b", where or "", re.I):
                for c in T.cols.values():
                    c.fk_ok = True
        return
    m = UPDATE.match(s)
    if m:
        T = sim.tab(m.group(1))
        if T is None or not sim.has_rows(T):
            return
        sets, frm, where = m.group(2), m.group(3), m.group(4)
        if where is not None and not where_matches(sim, T, where):
            return
        rw = UPDATE.match(raw)
        raw_where = (rw.group(4) or "") if rw else ""
        partial = where is not None and bool(re.search(r"\bIS\s+(NOT\s+)?NULL\b|''|\b\d+\b|\bTRUE\b|\bFALSE\b", where,
                                                        re.I))
        for part in _split_top(sets):
            mm = re.match(rf"({QID})\s*=\s*(.*)$", part.strip(), re.S)
            if not mm:
                continue
            c = sim.col(T, mm.group(1))
            expr = mm.group(2).strip()
            for src, dst in re.findall(rf"({QID})\s*::\s*(?:text\s*::\s*)?({QID}(?:\s*\.\s*{QID})?)", expr):
                sc = sim.col(T, src)
                if sc and dst.lower().strip('"') != "text":
                    w = cast_fails(sim, sc.type, dst, sc)
                    if w:
                        fails.append(w)
            if c is None:
                continue
            bare = re.fullmatch(rf"\(?\s*(?:{QID}\s*\.\s*)?({QID})\s*(?:::\s*{QNAME})?\s*\)?", expr)
            if not partial:
                for ref in re.findall(rf"(?<!CASE )(?:{QID}\s*\.\s*)?({QID})(?!\s*(?:->|#>|\(|=|<>|!=|<|>|\bIS\b|\bWHEN\b))",
                                      re.sub(r"\bWHEN\b.*?\bTHEN\b", " ", expr, flags=re.I | re.S)):
                    sc = sim.col(T, ref)
                    if sc and sc is not c:
                        sc.copied = True
            same = bare and sim.col(T, bare.group(1)) is c
            only_null = re.search(rf"(?<![\w]){re.escape(mm.group(1))}\s+IS\s+NULL", where or "", re.I) and not \
                re.search(r"\bOR\b", where or "", re.I)
            keeps = re.match(rf"\s*COALESCE\s*\(\s*(?:{QID}\s*\.\s*)?{re.escape(mm.group(1))}\s*,", expr, re.I)
            if c.values and not c.new and not only_null and not keeps and not same and not c.copied:
                lost.append(f"overwrites {T.name}.{c.name}")
            em = re.fullmatch(rf"\(?\s*(?:{QID}\s*\.\s*)?({QID})\s*::\s*(?:text|varchar|character varying)\s*\)?", expr, re.I)
            if em and sim.col(T, em.group(1)) is not None:
                sc = sim.col(T, em.group(1))
                if sc.labels is not None or sim.enum_of(sc.type) is not None:
                    c.labels = list(sc.labels if sc.labels is not None else sim.enum_of(sc.type))
            if c.fk_ref and re.fullmatch(r"''(?:\s*::\s*\S+)?", expr) and not closed(sim, c):
                fails.append(f"sets {T.name}.{c.name} to a literal that {c.fk_ref} need not hold (foreign key)")
            c.filled = True
            # an enum-like column's present labels: SET c = 'X' WHERE c = 'Y' / IN ('Y', ...)
            if c.labels is not None or sim.enum_of(c.type) is not None:
                if c.labels is None:
                    c.labels = list(sim.enum_of(c.type) or [])
                olds = re.findall(r"'([^']*)'", re.search(rf"{re.escape(mm.group(1))}\s*(?:=|IN)\s*(\(.*?\)|'[^']*')",
                                                          raw_where, re.I).group(1)) \
                    if re.search(rf"{re.escape(mm.group(1))}\s*(?:=|IN)\s*(\(.*?\)|'[^']*')", raw_where, re.I) else []
                if where is None:
                    c.labels = []
                c.labels = [x for x in c.labels if x not in olds]
                lit = _set_literal(raw, mm.group(1))
                if lit is not None and lit not in c.labels:
                    c.labels.append(lit)
            if where is None or only_null:
                nulls_src = bare and sim.col(T, bare.group(1)) is not None and sim.col(T, bare.group(1)).nulls
                c.nulls = bool(re.fullmatch(r"NULL", expr, re.I)) or bool(nulls_src and not frm)
                c.values = not re.fullmatch(r"NULL", expr, re.I)
                c.ndistinct = None
                c.all_distinct = False
        return
    m = INSERT.match(s)
    if not m and re.match(r"\s*WITH\b", s, re.I):
        k = re.search(r"\bINSERT\s+INTO\b", s, re.I)
        m = INSERT.match(s[k.start():]) if k else None
    if m:
        T = sim.tab(m.group(1))
        tcols = cols_of(m.group(2)[1:-1]) if m.group(2) else None
        rest = m.group(3) or ""
        sel = re.match(r"\s*SELECT\s+(?:DISTINCT\s+(?:ON\s*\([^)]*\)\s*)?)?(.*?)\bFROM\s+(?:ONLY\s+)?" + QNAME + r"(.*)$",
                       rest, re.I | re.S)
        if sel:
            src = sim.tab(sel.group(2))
            items = _split_top(sel.group(1))
            src_where = sel.group(3) or ""
            if src is not None and sim.has_rows(src):
                if src_where and re.search(r"\bWHERE\b", src_where, re.I) and not where_matches(
                        sim, src, re.split(r"\bWHERE\b", src_where, flags=re.I)[1]):
                    return
                partial = bool(re.search(r"\bWHERE\b", src_where, re.I))
                for k, it in enumerate(items):
                    b = re.fullmatch(rf"\(?\s*(?:{QID}\s*\.\s*)?({QID})\s*(?:::\s*{QNAME})?\s*\)?(?:\s+(?:AS\s+)?{QID})?",
                                     it.strip(), re.S)
                    sc = sim.col(src, b.group(1)) if b else None
                    if sc is None:
                        continue
                    if not partial:
                        sc.copied = True
                    # a NOT NULL target column fed by a source column that holds NULLs
                    if T is not None and tcols and k < len(tcols):
                        tc = sim.col(T, tcols[k])
                        nn_filter = re.search(rf"{re.escape(b.group(1))}\s+IS\s+NOT\s+NULL", src_where, re.I)
                        if tc and tc.notnull and sc.nulls and not nn_filter:
                            fails.append(f"inserts NULLs of {src.name}.{sc.name} into {T.name}.{tc.name} (NOT NULL)")
                if not partial and all(sim.col(src, c.name) is None or c.copied for c in src.cols.values()):
                    src.copied = True
                if T is not None:
                    T.rows = -1
        if T and re.match(r"\s*VALUES\b", rest, re.I) and T.rows == 0:
            T.rows = -1
        return
    m = CREATE_ENUM.match(s)
    if m:
        sim.enums[unq(m.group(1))] = re.findall(r"'((?:[^']|'')*)'", raw[raw.find("("):])
        return
    m = ALTER_TYPE_RENAME.match(s)
    if m:
        old = unq(m.group(1))
        if old in sim.enums:
            sim.enums[unq(m.group(2))] = sim.enums.pop(old)
            sim.renamed[old.lower()] = unq(m.group(2)).lower()
            for T in sim.tabs.values():
                for c in T.cols.values():
                    if base_type(c.type) == old.lower():
                        c.type = unq(m.group(2))
        return
    m = ALTER_TYPE_ADD.match(raw)
    if m and unq(m.group(1)) in sim.enums:
        sim.enums[unq(m.group(1))].append(m.group(2))
        return
    m = ALTER_TYPE_RENVAL.match(raw)
    if m and unq(m.group(1)) in sim.enums:
        e = sim.enums[unq(m.group(1))]
        sim.enums[unq(m.group(1))] = [m.group(3) if x == m.group(2) else x for x in e]
        return
    m = DROP_TYPE.match(s)
    if m and m.group(2):
        for name in _split_top(m.group(1)):
            tn = unq(name.strip()).lower()
            for T in list(sim.tabs.values()):
                for c in list(T.cols.values()):
                    if base_type(c.type) == tn and c.values and not c.copied:
                        lost.append(f"DROP TYPE CASCADE drops {T.name}.{c.name}")
        return


def _referenced(sim: Sim, T: Tab) -> str | None:
    """A table with rows that references T through a NO ACTION/RESTRICT key on non-NULL columns."""
    if T.cat is None:
        return None
    for t in sim.cat.get("tables") or []:
        for k in t.get("cons") or []:
            if k["type"] != "f" or str(k.get("ref")) != T.oid:
                continue
            if re.search(r"ON DELETE (CASCADE|SET NULL|SET DEFAULT)", k["def"] or "", re.I):
                continue
            C = sim.tab(t["name"])
            if C is None or not sim.has_rows(C):
                continue
            mm = re.match(r"FOREIGN KEY \((.*?)\)", k["def"] or "")
            cs = [sim.col(C, x) for x in cols_of(mm.group(1))] if mm else []
            if cs and all(c is not None and c.values for c in cs):
                return C.name
    return None


def _unique_fails(sim: Sim, T: Tab, colspec: str, partial: bool = False, pk: bool = False) -> str | None:
    if not sim.has_rows(T) or partial:
        return None
    names = cols_of(colspec)
    names = [n for n in names if n.upper() not in ("ASC", "DESC", "NULLS", "FIRST", "LAST", "COLLATE")]
    cs = [sim.col(T, n) for n in names]
    if not cs or any(c is None for c in cs):
        return None                # an expression index: not judged
    if pk and any(c.nulls for c in cs):
        return f"PRIMARY KEY on {T.name}({', '.join(names)}), which holds NULLs"
    if any(c.all_distinct for c in cs):
        return None
    if any(not c.values for c in cs):
        return None                # all NULL in some column: NULLs are distinct
    if T.rows > 0:
        nn = [c.ndistinct for c in cs]
        if all(x is not None for x in nn):
            prod = 1
            for x in nn:
                prod *= x
            if prod < T.rows:
                return f"{T.name}({', '.join(names)}) holds at most {prod} distinct values in {T.rows} rows"
        if len(cs) == 1 and cs[0].new and cs[0].default and T.rows >= 2:
            return f"{T.name}.{names[0]} was added with one DEFAULT for every row"
        return None
    # rows unknown (regime N): a constant default on an existing table repeats
    if len(cs) == 1 and cs[0].new and cs[0].default:
        return f"{T.name}.{names[0]} was added with one DEFAULT for every row"
    return None


def _alter(sim: Sim, T: Tab, sub: str, raw: str, fails: list, lost: list):
    rows = sim.has_rows(T)
    m = ADD_CON.match(sub)
    if m:
        kind, rest = m.group(2).upper(), m.group(3)
        not_valid = bool(re.search(r"\bNOT\s+VALID\b", rest, re.I))
        if kind.startswith("UNIQUE") or kind.startswith("PRIMARY"):
            mm = re.match(r"\s*\((.*?)\)", rest, re.S)
            if mm:
                w = _unique_fails(sim, T, mm.group(1), pk=kind.startswith("PRIMARY"))
                if w:
                    fails.append(w)
            return
        if kind.startswith("FOREIGN"):
            mm = re.match(r"\s*\((.*?)\)\s*REFERENCES\s+" + QNAME, rest, re.S | re.I)
            for cn in cols_of(mm.group(1)) if mm else []:
                if sim.col(T, cn):
                    sim.col(T, cn).fk_ref = unq(mm.group(2))
        if kind.startswith("FOREIGN") and not not_valid and rows:
            mm = re.match(r"\s*\((.*?)\)\s*REFERENCES\s+" + QNAME, rest, re.S | re.I)
            if mm:
                cs = [sim.col(T, x) for x in cols_of(mm.group(1))]
                ref = sim.tab(mm.group(2))
                if cs and all(c is not None for c in cs) and all(c.values for c in cs) \
                        and not any(c.new and not c.filled for c in cs) and not any(c.filled or c.fk_ok for c in cs):
                    if ref is not None and ref.rows == 0:
                        fails.append(f"foreign key on {T.name} references {ref.name}, which is empty")
                    elif not any(_had_fk(T, c.name) for c in cs):
                        fails.append(f"foreign key on {T.name}({', '.join(c.name for c in cs)}): existing values "
                                     "need not match a key of " + (ref.name if ref else "the referenced table"))
            return
        return
    m = ADD_COL.match(sub)
    if m and m.group(1).upper() not in ("CONSTRAINT",):
        name, spec = unq(m.group(1)), m.group(2)
        if re.search(r"IF\s+NOT\s+EXISTS", sub, re.I) and sim.col(T, name):
            return
        typ = spec.split()[0] if spec.split() else ""
        notnull = bool(re.search(r"NOT\s+NULL|PRIMARY\s+KEY", spec, re.I))
        default = bool(re.search(r"\bDEFAULT\b|\bGENERATED\b|\bSERIAL\b|\bBIGSERIAL\b|\bSMALLSERIAL\b", spec, re.I)) \
            or base_type(typ) in ("serial", "bigserial", "smallserial")
        if notnull and not default and rows:
            fails.append(f"adds {T.name}.{name} NOT NULL without a DEFAULT, and {T.name} holds rows")
            return
        c = Col(name, typ, notnull, default or None, nulls=rows and not default, values=rows and default, new=True)
        if default and rows:
            c.ndistinct = None if re.search(r"\bSERIAL|GENERATED|gen_random_uuid|uuid_generate|nextval|now\(\)",
                                            spec, re.I) else 1
        if re.search(r"\bUNIQUE\b|PRIMARY\s+KEY", spec, re.I) and c.ndistinct == 1 and T.rows != 0 and T.rows != 1:
            fails.append(f"adds {T.name}.{name} UNIQUE with one DEFAULT for every row")
        T.cols[name] = c
        return
    m = DROP_COL.match(sub)
    if m:
        c = sim.col(T, m.group(1))
        if c is None:
            return
        if c.values and not c.copied and not c.new:
            lost.append(f"drops {T.name}.{c.name}, which holds values not copied elsewhere")
        T.cols.pop(c.name, None)
        return
    m = ALT_TYPE.match(sub)
    if m:
        c = sim.col(T, m.group(1))
        if c is None:
            return
        dst, using = m.group(2).strip(), (m.group(3) or "").strip()
        simple = not using or re.fullmatch(rf"\(?\s*{QID}\s*(::\s*\w+\s*)?::\s*{QNAME}\s*(\([^)]*\))?\s*\)?", using, re.S) \
            or re.fullmatch(rf"\(?\s*{QID}\s*\)?", using)
        if simple:
            w = cast_fails(sim, c.type, dst, c)
            if w:
                fails.append(w)
                return
            if c.values and cast_loses(c.type, dst, sim):
                lost.append(f"casting {T.name}.{c.name} from {c.type} to {dst} changes values")
        elif c.values and family(sim, c.type) != family(sim, dst) and (family(sim, c.type), family(sim, dst)) \
                not in KEEP_FAM and "array" not in (family(sim, c.type), family(sim, dst)):
            lost.append(f"converting {T.name}.{c.name} from {c.type} to {dst} changes values")
        if sim.enum_of(c.type) is not None and family(sim, dst) == "text" and c.labels is None:
            c.labels = list(sim.enum_of(c.type))
        c.type = dst
        return
    m = SET_NN.match(sub)
    if m:
        c = sim.col(T, m.group(1))
        if c is None:
            return
        if c.nulls and rows:
            fails.append(f"{T.name}.{c.name} holds NULLs and is made NOT NULL")
            return
        c.notnull = True
        return
    m = RENAME_COL.match(sub)
    if m:
        c = sim.col(T, m.group(1))
        if c is not None:
            T.cols.pop(c.name, None)
            c.name = unq(m.group(2))
            T.cols[c.name] = c
        return
    m = RENAME_TAB.match(sub)
    if m:
        sim.tabs.pop(T.name, None)
        sim.dropped.add(T.name.lower())
        T.name = unq(m.group(1))
        sim.tabs[T.name] = T
        return


def _had_fk(T: Tab, col: str) -> bool:
    """The column already had a foreign key in the base (its values already match a key)."""
    for k in (T.cat or {}).get("cons") or []:
        if k["type"] == "f":
            mm = re.match(r"FOREIGN KEY \((.*?)\)", k["def"] or "")
            if mm and col in cols_of(mm.group(1)):
                return True
    return False
