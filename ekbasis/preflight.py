"""Preflight (since 0.1.6, v2): before a multi-step change runs, which step fails first, and whether the failure would
leave the change half applied.

A migration file, a maintenance script or a chain of commands is a plan whose steps run one after another. When step k
fails, steps 1..k-1 have already changed things, and in the sqlite3 shell (without -bail), a script without `set -e`
or a `;` chain, the steps after it still run: a table rebuild whose copy fails still drops the old table; a move that
fails is still followed by the `rm` that cleans up.

How a plan is judged, in this order:
1. **On a copy, when it can be** (local files and local SQLite databases; `copy=True`, the default). The folder (or the
   database) is cloned (APFS clonefile on macOS, a reflink or a size-capped copy elsewhere), the steps run there one by
   one under a timeout, and the first step that really fails is known, with its error. This is exact, and nothing
   touches the real files. It is used only when every step is a local file or SQLite command from an allowlist (and so
   is any program it would start: xargs, find -exec, awk's system()), every path it writes is inside the folder or in
   the temporary folder, and no step reaches the network or another machine.
   Shell steps run on a copy only inside a sandbox (macOS sandbox-exec: no network, no writes outside the copy); where
   there is none (Linux, or a sandbox that does not start), or when it refuses a step's write outside the copy, shell
   plans are judged by Ekbasis (2). SQL plans run on a copy wherever the sqlite3 command-line tool is installed; SQL
   that reaches other files (ATTACH, VACUUM INTO, readfile/writefile, extensions) never does.
2. **Otherwise, by Ekbasis** (remote or side-effectful targets: a deploy script that pushes or calls a service, a
   command outside the allowlist). One request asks whether each step fails on the current state (WS-B1's whole-plan
   question); for scripts and chains each step is also asked with only the steps before it (a step walk, in parallel),
   because asked about a whole coherent script the model tends to assume every step works. Facts that code can state
   are stated and decide their step: a `mkdir` onto a path that is a file, a destination written with a trailing slash
   that is not a folder, several sources onto something that is not a folder, a source that does not exist, a `cd`
   into a missing folder, writing into a folder you cannot write. Paths you cannot write are listed in the state.
   Numbers kept within a CHECK bound are decided in code (as in 0.1.4.dev0). SQL run by sqlite3 inside a chain is
   judged as SQL, with the database's state.

Then code works out what the first failure would leave. It warns only when the change would be left half applied: the
failing step changes something (a check that only reads, such as `git status` or `ls` after the change, is not a
half-done change), and a step that modifies or removes existing data has already run or would still run. Steps that only
add something new (a backup copy, a new folder, CREATE TABLE) do not count as half-done changes on their own.

What preflight follows on one line: sqlite3 with a file (`<`, `.read`, a pipe from `cat`), a here-document, SQL
arguments, `{ echo "BEGIN;"; cat f.sql; echo "COMMIT;"; } | sqlite3 db` (and the same with `( )`), a file written
earlier on the same line by echo/printf/cat, `cd DIR` and simple `NAME=value` assignments; a script run with bash, sh,
zsh or ./script; chains joined by &&, ||, ; or new lines. Where the sqlite3 command-line tool is not installed, a
`sqlite3` command fails before any statement runs: for a line made only of sqlite3 calls preflight says so, by code,
without a warning (nothing changes), and in a longer line that step fails like any command that is not installed.
`check_sql` (the Python API, for SQL you run some other way) asks Ekbasis when there is no sqlite3 shell to run a copy
with. What it cannot follow (loops, conditionals, functions, other dot-commands, variables it cannot resolve) is "cannot
judge": by default preflight then says nothing, since it is an extra check (`fail_closed=True` turns it into a
warning).

What the model reads, when it is asked: for SQL, the schema, foreign keys, CHECK constraints and the rows of the tables
the statements name (up to `row_cap` per table; bigger tables: a count, the first rows and per-column facts); rows go
to your Ekbasis server, or pass rows=False. For shell, the shell guard's listing (never file contents), the paths you
cannot write and the facts above.
"""
from __future__ import annotations

import concurrent.futures as cf
import math
import os
import platform
import re
import shlex
import shutil
import sqlite3
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass, field

from . import git as G
from . import prompts as P
from . import shell as S
from .client import CannotJudge, Ekbasis

FAIL_THRESHOLD = 0.5      # a plan is flagged when P(some step fails) reaches this (WS-B1's decision rule)
ROW_CAP = 60
SAMPLE_ROWS = 10
MAX_TABLES = 8
MAX_STEPS = 60
MAX_OPTIONS = 160
COPY_TIMEOUT = 20.0       # seconds for a run on a copy
COPY_MAX_BYTES = 512 << 20  # without clonefile or reflinks, folders bigger than this are not copied

READ, ADD, MODIFY, DESTROY = "read", "add", "modify", "destroy"

# ---------------------------------------------------------------- questions

def sql_fails(k: int) -> dict:
    return P.yes_no(f"Does statement {k} fail (an error or a constraint violation, so it changes nothing)?")


SQL_WHY = {
    "unique": "a UNIQUE or PRIMARY KEY constraint: a value would be repeated",
    "not null": "a NOT NULL constraint: a value would be missing",
    "check": "a CHECK constraint: a value would be out of its allowed range",
    "foreign key": "a FOREIGN KEY constraint: a row would point to a row that does not exist (or is still pointed to)",
    "missing": "a table, column or index it uses does not exist",
    "already exists": "a table, column or index it creates already exists",
    "syntax": "a syntax error, or something this SQLite does not support",
    "other": "another reason",
}
SHELL_WHY = {
    "missing source": "a file or folder it reads, moves or copies does not exist",
    "missing folder": "a folder in the destination path does not exist",
    "file vs folder": "a path that must be a folder is a file, or one that must be a file is a folder",
    "target exists": "the destination already exists and the command will not replace it",
    "not empty": "a folder it must remove or replace is not empty",
    "permission": "permission denied",
    "usage": "a wrong option or a wrong number of arguments",
    "other": "another reason",
}


def sql_why(k: int) -> dict:
    return P.choice(f"Why does statement {k} fail?", SQL_WHY)


def shell_why(k: int) -> dict:
    return P.choice(f"Why does command {k} fail?", SHELL_WHY)


# ---------------------------------------------------------------- the plan

@dataclass
class Step:
    text: str
    effect: str = READ           # read | add | modify | destroy
    joined_by: str = ""          # chains: the operator before it ("", "&&", "||", ";", "\n")
    ctx: bool = False            # cd / pushd / popd: changes where the next steps run
    cwd: str = ""                # where this step runs
    sql: list | None = None      # a sqlite3 call: its statements (Step objects)
    db: str | None = None        # a sqlite3 call: its database
    bail: bool = False           # a sqlite3 call with -bail / .bail on

    @property
    def writes(self) -> bool:
        return self.effect != READ

    @property
    def destructive(self) -> bool:
        return self.effect == DESTROY


@dataclass
class Plan:
    kind: str                    # "sql" (statements of one database) | "shell" (a script or a chain)
    steps: list
    cwd: str
    source: str
    db: str | None = None
    stop_on_error: bool = False  # sqlite3 -bail / .bail on, or a script with set -e
    shell: str = "bash"
    unread: list = field(default_factory=list)
    fk_from: int | None = None
    script: bool = False         # the steps are a script's lines
    sqlite3_line: bool = False   # SQL that a sqlite3 command on the line runs (not SQL given to check_sql)

    @property
    def writes(self) -> int:
        return sum(1 for s in self.steps if s.writes)


@dataclass
class PreflightVerdict:
    plan: Plan
    p_fail: list
    p_any: float
    first: int | None
    risky: bool = False
    cannot_judge: bool = False
    applied_before: list = field(default_factory=list)
    runs_after: list = field(default_factory=list)
    atomic: bool = False
    reason: str | None = None
    reason_p: float | None = None
    error: str | None = None     # the real error, when the plan ran on a copy
    by: str = "model"            # copy | model | code (sqlite3 not installed: the line fails before any statement)
    by_code: list = field(default_factory=list)      # steps decided by code (numbers, shell facts)
    by_numbers: list = field(default_factory=list)   # steps whose number the model carried
    p_lost: float | None = None
    reasons: list = field(default_factory=list)
    state: str = ""
    ms: float = 0.0
    requests: int = 0
    copy_note: str = ""          # why the plan did not run on a copy

    def message(self) -> str:
        pl = self.plan
        if self.cannot_judge:
            return ("Ekbasis preflight could not check this multi-step change (" + "; ".join(pl.unread) + "). If a "
                    "step fails midway, the steps before it stay applied.")
        k, n = self.first, len(pl.steps)
        step = pl.steps[k - 1].text.replace("\n", " ")
        short = step if len(step) <= 160 else step[:157] + "..."
        if self.by == "copy":
            out = [f"Ekbasis preflight ran this on a copy first: step {k} of {n} failed: `{short}`"
                   + (f" ({self.error.strip()[:240]})" if self.error else "") + "."]
        else:
            how = "checked in code" if k in self.by_code else f"{100 * self.p_fail[k - 1]:.0f}%"
            out = [f"Ekbasis preflight: step {k} of {n} is likely to fail ({how}): `{short}`"]
            if self.reason and (self.reason_p or 0) >= 0.5:
                table = SQL_WHY if pl.kind == "sql" else SHELL_WHY
                out[-1] += f", most likely because of {table.get(self.reason, self.reason)} ({100 * self.reason_p:.0f}%)"
            out[-1] += "."
        if self.applied_before:
            out.append(f"Step{'s' if len(self.applied_before) > 1 else ''} {_spans(self.applied_before)} would already "
                       "have run.")
        if self.runs_after:
            what = "the sqlite3 shell goes on after an error" if pl.kind == "sql" else (
                "the script has no `set -e`" if pl.script else "of how the commands are joined")
            dest = [pl.steps[j - 1].text for j in self.runs_after if pl.steps[j - 1].destructive]
            tail = ", including " + ", ".join(f"`{d if len(d) <= 80 else d[:77] + '...'}`" for d in dest[:2]) if dest else ""
            out.append(f"Step{'s' if len(self.runs_after) > 1 else ''} {_spans(self.runs_after)} would still run "
                       f"(because {what}){tail}.")
        out.append("The change would be left half applied.")
        return " ".join(out)

    def summary(self) -> str:
        pl = self.plan
        status = "CANNOT JUDGE" if self.cannot_judge else ("RISKY" if self.risky else ("fails, nothing half done" if
                 self.first or self.by == "code" else "ok"))
        out = [f"Ekbasis preflight: {status}  ({pl.source}; by {self.by}"
               + (f"; not on a copy: {self.copy_note}" if self.by == "model" and self.copy_note else "")
               + (f"; {self.copy_note}" if self.by == "code" and self.copy_note else "")
               + f"; P(some step fails) {100 * self.p_any:.0f}%)"]
        for i, (s, p) in enumerate(zip(pl.steps, self.p_fail), 1):
            mark = " <- first failure" if i == self.first else ""
            tag = " (code)" if i in self.by_code else (" (number followed)" if i in self.by_numbers else "")
            t = s.text.replace("\n", " ")
            out.append(f"  {100 * p:3.0f}% fails  {i:2d}. [{s.effect}] {t if len(t) <= 100 else t[:97] + '...'}{tag}{mark}")
        if self.error:
            out.append(f"  error on the copy: {self.error.strip()[:300]}")
        if self.risky and not self.cannot_judge:
            out.append("  " + self.message())
        if pl.unread:
            out.append("  ! not followed: " + "; ".join(pl.unread))
        return "\n".join(out)


def _spans(ks: list) -> str:
    ks = sorted(ks)
    runs, start, prev = [], ks[0], ks[0]
    for k in ks[1:]:
        if k == prev + 1:
            prev = k
            continue
        runs.append((start, prev))
        start = prev = k
    runs.append((start, prev))
    parts = [str(a) if a == b else f"{a}-{b}" for a, b in runs]
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


# ---------------------------------------------------------------- SQL: splitting and classifying

READ_DOTS = {".headers", ".header", ".mode", ".timer", ".echo", ".changes", ".print", ".nullvalue", ".separator",
             ".width", ".show", ".stats", ".eqp", ".explain", ".schema", ".fullschema", ".tables", ".indexes",
             ".indices", ".databases", ".dump", ".dbinfo", ".lint", ".quit", ".exit", ".bail", ".once"}
SIDE_DOTS = {".shell", ".system", ".output", ".import", ".load", ".save", ".backup", ".restore", ".clone", ".open",
             ".cd", ".excel", ".log", ".trace", ".archive", ".ar"}
SQL_BEGIN = re.compile(r"^\s*BEGIN\b", re.I)
SQL_END = re.compile(r"^\s*(COMMIT|END|ROLLBACK)\b", re.I)
FK_ON = re.compile(r"^\s*PRAGMA\s+(?:\w+\.)?foreign_keys\s*=\s*(ON|1|TRUE|YES)\s*;?\s*$", re.I)
FK_OFF = re.compile(r"^\s*PRAGMA\s+(?:\w+\.)?foreign_keys\s*=\s*(OFF|0|FALSE|NO)\s*;?\s*$", re.I)
SQL_SIDE = re.compile(r"\b(ATTACH|DETACH|load_extension|readfile|writefile|edit|fts3_tokenizer|zipfile)\b", re.I)
SQL_OUT = re.compile(r"\bVACUUM\b[^;]*?\bINTO\b", re.I)   # writes another file: never on a copy


def _end_of_statement(buf: str) -> int | None:
    i = buf.find(";")
    while i != -1:
        if sqlite3.complete_statement(buf[:i + 1]):
            return i + 1
        i = buf.find(";", i + 1)
    return None


def split_sql(text: str) -> tuple[list, list]:
    """(statements, [(index before which it comes, dot-command)]) in the order the sqlite3 shell reads them."""
    steps, dots, buf = [], [], ""
    for line in text.splitlines(keepends=True):
        if not buf.strip() and line.lstrip().startswith("."):
            dots.append((len(steps), line.strip()))
            continue
        buf += line
        while True:
            end = _end_of_statement(buf)
            if end is None:
                break
            stmt, buf = buf[:end].strip(), buf[end:]
            stmt = re.sub(r"\A(?:\s*--[^\n]*\n)+", "", stmt).strip()
            body = re.sub(r"--[^\n]*", "", stmt).strip()
            if body and body != ";":
                steps.append(stmt)
    rest = re.sub(r"--[^\n]*", "", buf).strip()
    if rest:
        steps.append(buf.strip())
    return steps, dots


def sql_effect(body: str, created: set) -> str:
    b = re.sub(r"--[^\n]*", "", body).strip()
    u = b.upper()
    w = re.match(r"(?:WITH\b.*?\b)?(INSERT|UPDATE|DELETE|REPLACE|CREATE|DROP|ALTER|REINDEX|VACUUM|SELECT|PRAGMA|BEGIN|"
                 r"COMMIT|END|ROLLBACK|SAVEPOINT|RELEASE|EXPLAIN|ANALYZE)\b", u, re.S)
    head = w.group(1) if w else ""
    if head in ("SELECT", "EXPLAIN", "BEGIN", "COMMIT", "END", "ROLLBACK", "SAVEPOINT", "RELEASE", "ANALYZE", "PRAGMA",
                "REINDEX", "VACUUM", ""):
        return READ
    if head == "CREATE":
        m = re.match(r"CREATE\s+(?:TEMP\w*\s+|UNIQUE\s+)?(?:TABLE|INDEX|VIEW|TRIGGER|VIRTUAL\s+TABLE)\s+"
                     r"(?:IF\s+NOT\s+EXISTS\s+)?[\"`\[]?(\w+)", u)
        if m:
            created.add(m.group(1).lower())
        return ADD
    if head in ("DROP", "DELETE"):
        return DESTROY
    if head == "ALTER":
        if re.search(r"\bDROP\b", u):
            return DESTROY
        m = re.match(r"ALTER\s+TABLE\s+[\"`\[]?(\w+)[\"`\]]?\s+RENAME\s+TO\s+[\"`\[]?(\w+)", u)
        if m:
            created.add(m.group(2).lower())
        return MODIFY
    if head == "INSERT":
        m = re.match(r"(?:WITH\b.*?\b)?INSERT\s+(?:OR\s+\w+\s+)?INTO\s+[\"`\[]?(\w+)", u, re.S)
        return ADD if m and m.group(1).lower() in created else MODIFY
    return MODIFY


def sql_steps(stmts: list) -> list:
    created, out = set(), []
    for s in stmts:
        body = re.sub(r"--[^\n]*", "", s).strip()
        out.append(Step(text=body, effect=sql_effect(body, created)))
    return out


# ---------------------------------------------------------------- SQL: the state (as in 0.1.4.dev0)

def _sql_literal(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, (int, float)):
        return repr(v) if isinstance(v, float) else str(v)
    if isinstance(v, bytes):
        return f"X'{v[:16].hex()}{'...' if len(v) > 16 else ''}'"
    return "'" + str(v).replace("'", "''") + "'"


_VERSION = {}


def sqlite_cli() -> str | None:
    return shutil.which("sqlite3")


def sqlite_version() -> str:
    if "v" not in _VERSION:
        v = None
        try:
            out = subprocess.run(["sqlite3", "--version"], capture_output=True, text=True, timeout=5).stdout
            m = re.match(r"(\d+\.\d+)", out or "")
            v = m.group(1) if m else None
        except (OSError, subprocess.SubprocessError):
            pass
        _VERSION["v"] = v or ".".join(sqlite3.sqlite_version.split(".")[:2])
    return _VERSION["v"]


def _connect_ro(db: str) -> sqlite3.Connection:
    from urllib.parse import quote
    con = sqlite3.connect(f"file:{quote(os.path.abspath(db))}?mode=ro", uri=True, timeout=2)
    con.execute("SELECT count(*) FROM sqlite_master").fetchone()
    return con


def _named_tables(steps: list, tables: list) -> list:
    text = "\n".join(s.text for s in steps)
    return [t for t in tables if re.search(r"(?<![\w$])[\"'`\[]?" + re.escape(t) + r"[\"'`\]]?(?![\w$])", text, re.I)]


def _facts(con, table: str, cols: list) -> list:
    out = []
    qt = '"' + table.replace('"', '""') + '"'
    for c in cols:
        qc = '"' + c.replace('"', '""') + '"'
        n, nn, nd = con.execute(f"SELECT count(*), count({qc}), count(DISTINCT {qc}) FROM {qt}").fetchone()
        f = []
        if n - nn:
            f.append(f"{n - nn} missing (NULL)")
        if nn and nd < nn:
            f.append(f"{nn - nd} repeated values")
        try:
            ndi = con.execute(f"SELECT count(DISTINCT lower(trim({qc}))) FROM {qt} WHERE typeof({qc}) = 'text'").fetchone()[0]
            ntext = con.execute(f"SELECT count(DISTINCT {qc}) FROM {qt} WHERE typeof({qc}) = 'text'").fetchone()[0]
            if ntext and ndi < ntext:
                f.append(f"{ntext - ndi} more repeat if case and spaces are ignored")
        except sqlite3.Error:
            pass
        lo, hi = con.execute(f"SELECT min({qc}), max({qc}) FROM {qt} WHERE typeof({qc}) IN ('integer', 'real')").fetchone()
        if lo is not None:
            f.append(f"numbers from {lo} to {hi}")
        if f:
            out.append(f"{c}: " + ", ".join(f))
    return out


def sql_state(db: str, steps: list, row_cap: int = ROW_CAP, rows: bool = True) -> tuple[str, dict]:
    if not os.path.exists(db):
        return "The database file does not exist yet: the sqlite3 shell creates an empty database.", {"tables": {},
                                                                                                    "rows": {}}
    try:
        con = _connect_ro(db)
    except sqlite3.Error as e:
        raise CannotJudge(f"cannot read the database {db}: {e}") from None
    try:
        objs = con.execute("SELECT type, name, tbl_name, sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE "
                           "'sqlite_%' ORDER BY CASE type WHEN 'table' THEN 0 WHEN 'index' THEN 1 ELSE 2 END, rowid"
                           ).fetchall()
        tables = [o[1] for o in objs if o[0] == "table"]
        cols = {t: [r[1] for r in con.execute(f"PRAGMA table_info(\"{t}\")")] for t in tables}
        named = _named_tables(steps, tables)
        fks, partners = [], []
        for t in tables:
            for r in con.execute(f"PRAGMA foreign_key_list(\"{t}\")"):
                parent, frm, to, on_delete = r[2], r[3], r[4], r[6]
                fks.append(f"{t}.{frm} REFERENCES {parent}({to or 'its primary key'}) ON DELETE {on_delete}")
                if t in named and parent in tables:
                    partners.append(parent)
                if parent in named:
                    partners.append(t)
        shown = list(dict.fromkeys(named + partners))[:MAX_TABLES]
        if not named and len(tables) <= MAX_TABLES:
            shown = list(tables)
        checks = []
        for o in objs:
            if o[0] == "table":
                for m in re.finditer(r"CHECK\s*\(", o[3], re.I):
                    depth, j = 1, m.end()
                    while j < len(o[3]) and depth:
                        depth += {"(": 1, ")": -1}.get(o[3][j], 0)
                        j += 1
                    checks.append((o[1], o[3][m.end():j - 1].strip()))
        lines = ["Schema:"] + [o[3].strip() + ";" for o in objs] + ["", "Rows:"]
        got_rows = {}
        for t in shown:
            n = con.execute(f"SELECT count(*) FROM \"{t}\"").fetchone()[0]
            head = f"{t} ({', '.join(cols[t])})"
            if not rows:
                f = _facts(con, t, cols[t])
                lines.append(f"{head}: {n} row{'s' if n != 1 else ''}" + (f"; facts: {'; '.join(f)}" if f else ""))
                continue
            if n <= row_cap:
                rs = con.execute(f"SELECT * FROM \"{t}\" ORDER BY rowid").fetchall()
                got_rows[t] = rs
                body = "; ".join("(" + ", ".join(_sql_literal(v) for v in r) + ")" for r in rs) or "none"
                lines.append(f"{head}: {body}")
            else:
                rs = con.execute(f"SELECT * FROM \"{t}\" ORDER BY rowid LIMIT {SAMPLE_ROWS}").fetchall()
                body = "; ".join("(" + ", ".join(_sql_literal(v) for v in r) + ")" for r in rs)
                f = _facts(con, t, cols[t])
                lines.append(f"{head}: {n} rows; the first {len(rs)}: {body}" + (f"; facts: {'; '.join(f)}" if f else ""))
        other = [t for t in tables if t not in shown]
        if other:
            counts = []
            for t in other[:20]:
                nrows = con.execute('SELECT count(*) FROM "' + t.replace('"', '""') + '"').fetchone()[0]
                counts.append(f"{t} ({nrows} rows)")
            lines.append("Other tables (rows not shown): " + ", ".join(counts) + ("" if len(other) <= 20 else ", ..."))
        return "\n".join(lines), {"tables": cols, "rows": got_rows, "checks": checks, "fks": fks}
    except sqlite3.Error as e:
        raise CannotJudge(f"cannot read the database {db}: {e}") from None
    finally:
        con.close()


def sql_rules(plan: Plan, facts: dict) -> str:
    v = sqlite_version()
    if plan.fk_from == 1:
        fk = "with foreign keys enforced (PRAGMA foreign_keys = ON)"
    elif plan.fk_from:
        fk = (f"with foreign keys not enforced until statement {plan.fk_from} turns them on (PRAGMA foreign_keys = ON; "
              "the sqlite3 shell starts with them off)")
    else:
        fk = "with foreign keys not enforced (the sqlite3 shell starts with PRAGMA foreign_keys = OFF, so REFERENCES clauses are not checked)"
    txn = any(SQL_BEGIN.match(s.text) for s in plan.steps)
    mode = "in order (BEGIN opens a transaction that COMMIT ends)" if txn else "in order in autocommit mode"
    out = (f"A SQLite {v} database {fk}. The statements run {mode}; a statement that fails (constraint violation or "
           "error) changes nothing and the next one still runs.")
    cons = list(facts.get("fks") or []) + [f"{t} has CHECK ({c})" for t, c in facts.get("checks") or []]
    if cons:
        out += " " + "; ".join(cons) + "."
    return out


# ---------------------------------------------------------------- SQL: numbers kept within a CHECK bound

NUM_UPDATE = re.compile(r"^\s*UPDATE\s+[\"`]?(\w+)[\"`]?\s+SET\s+[\"`]?(\w+)[\"`]?\s*=\s*[\"`]?\2[\"`]?\s*([+-])\s*"
                        r"(\d+(?:\.\d+)?)\s+WHERE\s+[\"`]?(\w+)[\"`]?\s*=\s*('(?:[^']|'')*'|-?\d+)\s*;?\s*$", re.I)
CHECK_BOUND = re.compile(r"^[\"`]?(\w+)[\"`]?\s*(>=|>|<=|<)\s*(-?\d+(?:\.\d+)?)$")
CMP = {">=": lambda a, b: a >= b, ">": lambda a, b: a > b, "<=": lambda a, b: a <= b, "<": lambda a, b: a < b}


def _numbers_plan(plan: Plan, facts: dict):
    out = []
    for i, s in enumerate(plan.steps):
        m = NUM_UPDATE.match(s.text)
        if not m:
            continue
        table, col, sign, amount, key, val = m.groups()
        bound = None
        for t, c in facts.get("checks") or []:
            cm = CHECK_BOUND.match(c)
            if t.lower() == table.lower() and cm and cm.group(1).lower() == col.lower():
                bound = (cm.group(2), float(cm.group(3)))
        if bound is None:
            continue
        delta = float(amount) * (1 if sign == "+" else -1)
        val = val[1:-1].replace("''", "'") if val.startswith("'") else int(val)
        out.append((i, table, col, key, val, delta, bound))
    return out or None


def _start_values(facts: dict, nums: list) -> dict | None:
    rows, start = facts.get("rows") or {}, {}
    for t, c, k in {(t, c, k) for _, t, c, k, _, _, _ in nums}:
        real = next((x for x in rows if x.lower() == t.lower()), None)
        if real is None:
            return None
        cols = [x.lower() for x in facts["tables"][real]]
        if c.lower() not in cols or k.lower() not in cols:
            return None
        ci, ki = cols.index(c.lower()), cols.index(k.lower())
        for r in rows[real]:
            if any(v == r[ki] for _, tt, cc, kk, v, _, _ in nums if (tt, cc, kk) == (t, c, k)):
                if not isinstance(r[ci], (int, float)):
                    return None
                start[(t, c, k, r[ki])] = float(r[ci])
    if len({(t, c, k, v) for _, t, c, k, v, _, _ in nums}) != len(start):
        return None
    return start


def _exact_numbers(plan: Plan, nums: list, start: dict) -> dict | None:
    tables = {t.lower() for _, t, _, _, _, _, _ in nums}
    numeric = {i for i, *_ in nums}
    for i, s in enumerate(plan.steps):
        if s.writes and i not in numeric and any(re.search(r"(?<![\w$])" + re.escape(t) + r"(?![\w$])", s.text, re.I)
                                                 for t in tables):
            return None
    vals, out = dict(start), {}
    for i, t, c, k, v, d, (op, bound) in sorted(nums):
        new = vals[(t, c, k, v)] + d
        fails = not CMP[op](new, bound)
        if not fails:
            vals[(t, c, k, v)] = new
        out[i] = fails
    return out


def _track_numbers(plan: Plan, nums: list, start: dict, rules: str, state_text: str, client: Ekbasis) -> dict | None:
    vals = list(start.values()) + [d for *_, d, _ in nums]
    if any(not float(x).is_integer() for x in vals):
        return None
    g = 0
    for x in vals:
        g = math.gcd(g, int(abs(x)))
    g = g or 1
    lo = min(0, min(start.values()) - sum(abs(d) for *_, d, _ in nums))
    hi = max(start.values()) + sum(abs(d) for *_, d, _ in nums)
    grid = list(range(int(lo // g) * g, int(hi) + g, g))
    if len(grid) > MAX_OPTIONS:
        return None
    keys = {kv: f"v{j}" for j, kv in enumerate(sorted(start, key=str))}
    names = {keys[kv]: kv for kv in keys}
    qs = {keys[kv]: P.number(f"After all these statements, what is {kv[1]} of the {kv[0]} row whose {kv[2]} is "
                             f"{_sql_literal(kv[3])}?", grid) for kv in keys}
    cur = {keys[kv]: P.number_label(start[kv]) for kv in keys}
    dist = {k: {cur[k]: 1.0} for k in cur}

    def render(st):
        return state_text + "\nTracked values now: " + "; ".join(
            f"{names[k][0]}.{names[k][1]} where {names[k][2]} = {_sql_literal(names[k][3])}: {st[k]}" for k in sorted(st))

    out = {}
    by_step = {i: (t, c, k, v, d, b) for i, t, c, k, v, d, b in nums}
    for i, s in enumerate(plan.steps):
        if i in by_step:
            t, c, k, v, d, (op, bound) = by_step[i]
            out[i] = sum(p for x, p in dist[keys[(t, c, k, v)]].items() if not CMP[op](float(x) + d, bound))
        ans = client.ask(P.world_state(rules, render(cur), [s.text]), qs)
        cur = {k: str(ans[k].value) for k in qs}
        dist = {k: dict(ans[k].probabilities) for k in qs}
    return out


# ---------------------------------------------------------------- shell steps: effects

QUIET = {"echo", "printf", "true", "false", ":", "set", "export", "local", "readonly", "shopt", "trap", "exit", "return",
         "unset", "alias", "sleep", "wait", "pwd", "type", "which", "hash", "command", "builtin", "date", "env",
         "printenv", "whoami", "id", "uname", "hostname", "test", "[", "[[", "basename", "dirname", "realpath",
         "readlink", "seq", "yes", "tput", "clear"}
READ_CMDS = set(S.READS) - {"sed", "perl", "awk", "sort"} | {"ls", "find", "stat", "file", "du", "df", "tree", "md5",
                                                              "shasum", "sha1sum", "sha256sum", "md5sum", "cksum",
                                                              "xxd", "hexdump", "od", "strings", "column", "jq",
                                                              "zipinfo", "lsof", "ps", "top", "tail", "head", "less"}
CTX = {"cd", "pushd", "popd"}
DESTROY_CMDS = {"rm", "rmdir", "unlink", "shred", "truncate"}
NETWORK = {"curl", "wget", "ssh", "scp", "sftp", "rsync", "nc", "ncat", "telnet", "ftp", "aws", "gcloud", "az",
           "kubectl", "helm", "docker", "podman", "psql", "mysql", "mongo", "mongosh", "redis-cli", "http", "httpie",
           "gh", "heroku", "flyctl", "vercel", "netlify", "terraform", "ansible", "open", "osascript", "say", "mail",
           "sendmail", "npm", "npx", "pnpm", "yarn", "pip", "pip3", "brew", "apt", "apt-get", "yum", "cargo", "go"}
COPY_OK = {"mkdir", "rmdir", "mv", "cp", "rm", "ln", "touch", "cat", "echo", "printf", "tee", "sed", "sort", "uniq",
           "head", "tail", "cut", "tr", "wc", "grep", "egrep", "fgrep", "find", "tar", "gzip", "gunzip", "zcat", "zip",
           "unzip", "chmod", "cd", "pushd", "popd", "ls", "stat", "test", "[", "true", "false", ":", "date", "basename",
           "dirname", "realpath", "readlink", "diff", "cmp", "md5", "shasum", "sha256sum", "install", "split", "jq",
           "awk", "paste", "nl", "rev", "column", "sqlite3", "pwd", "file", "du", "xargs", "sleep", "export", "set",
           "unlink", "truncate", "bzip2", "bunzip2", "xz", "unxz", "seq", "comm", "join", "fold", "expand", "iconv"}


def _git_effect(args: list) -> str:
    cmd = shlex.join(["git"] + args)
    if G.read_only(cmd):
        return READ
    sub = args[0] if args else ""
    if sub in ("clean", "reset", "rm", "restore", "checkout", "switch", "stash", "branch", "tag", "rebase", "merge",
               "pull", "worktree"):
        return DESTROY if sub in ("clean", "rm") or (sub == "reset" and "--hard" in args) else MODIFY
    return MODIFY


def _exists(cwd: str, p: str) -> bool:
    return os.path.lexists(os.path.join(cwd, os.path.expanduser(p)))


def shell_effect(sc, cwd: str) -> tuple[str, bool]:
    """(effect, changes the folder the next steps run in) of one simple command."""
    name, at, _ = S.command_name(list(sc.words))
    args = [w.text for w in sc.words[at + 1:]]
    effect = READ
    for r in sc.redirects:
        if r.target is None or r.target.text in S.NOT_FILES or r.op in ("<", "<<", "<<<", "<&", ">&"):
            continue
        if r.op in S.TRUNCATING:
            effect = _max(effect, DESTROY if _exists(cwd, r.target.text) else ADD)
        elif r.op in (">>", "&>>"):
            effect = _max(effect, MODIFY if _exists(cwd, r.target.text) else ADD)
    if not name or name in QUIET:
        return effect, False
    if name in CTX:
        return effect, True
    if name in ("curl", "http", "httpie"):
        # a request changes nothing here unless it saves a file (-o, -O); what it does elsewhere is not a local change
        writes_file = any(a in ("-o", "--output", "-O", "--remote-name", "--remote-name-all") or
                          (a.startswith("-") and not a.startswith("--") and ("o" in a[1:] or "O" in a[1:]))
                          for a in args)
        return (_max(effect, ADD) if writes_file else effect), False
    if name == "git":
        return _max(effect, _git_effect(args)), False
    if name == "sqlite3":
        return _max(effect, MODIFY), False     # refined by its statements when it is read
    if name == "find":
        if "-delete" in args:
            return DESTROY, False
        if any(a in ("-exec", "-execdir", "-ok", "-okdir") for a in args):
            j = next(i for i, a in enumerate(args) if a in ("-exec", "-execdir", "-ok", "-okdir"))
            inner = args[j + 1] if j + 1 < len(args) else ""
            if inner not in READ_CMDS and inner not in QUIET:
                return _max(effect, DESTROY if inner in DESTROY_CMDS else MODIFY), False
        return effect, False
    if name == "tar":
        flags = "".join(a.lstrip("-") for a in args[:1] if not a.startswith("--")) + "".join(
            a[1:] for a in args if a.startswith("-") and not a.startswith("--"))
        if "t" in flags and "c" not in flags and "x" not in flags:
            return effect, False
        if "c" in flags:
            return _max(effect, ADD), False
        return _max(effect, MODIFY), False
    if name in ("unzip",) and "-l" in args:
        return effect, False
    if name == "sed":
        return (_max(effect, MODIFY) if any(a.startswith("-i") or a == "--in-place" for a in args) else effect), False
    if name in ("sort",):
        return (_max(effect, MODIFY) if any(a.startswith("-o") for a in args) else effect), False
    if name in READ_CMDS:
        return effect, False
    if name in DESTROY_CMDS:
        return DESTROY, False
    if name in ("mkdir", "touch", "ln"):
        return _max(effect, ADD), False
    if name in ("cp", "install", "tee"):
        pos = [a for a in args if not a.startswith("-")]
        dest = pos[-1] if pos else ""
        if name == "tee":
            return _max(effect, MODIFY if any(_exists(cwd, p) for p in pos) else ADD), False
        if dest and _exists(cwd, dest) and not os.path.isdir(os.path.join(cwd, dest)):
            return _max(effect, DESTROY), False    # replaces a file
        if dest and os.path.isdir(os.path.join(cwd, dest)):
            srcs = pos[:-1]
            if any(_exists(cwd, os.path.join(dest, os.path.basename(s.rstrip("/")))) for s in srcs):
                return _max(effect, DESTROY), False
        return _max(effect, ADD), False
    if name == "mv":
        pos = [a for a in args if not a.startswith("-")]
        dest = pos[-1] if pos else ""
        if dest and _exists(cwd, dest) and not os.path.isdir(os.path.join(cwd, dest)):
            return DESTROY, False
        return _max(effect, MODIFY), False
    if name in ("gzip", "bzip2", "xz", "gunzip", "bunzip2", "unxz"):
        return _max(effect, MODIFY if "-k" not in args and "--keep" not in args else ADD), False
    return _max(effect, MODIFY), False


ORDER = {READ: 0, ADD: 1, MODIFY: 2, DESTROY: 3}


def _max(a: str, b: str) -> str:
    return a if ORDER[a] >= ORDER[b] else b


# ---------------------------------------------------------------- reading a command line

SQLITE_VALUE_OPTS = {"-cmd", "-init", "-separator", "-nullvalue", "-newline", "-mmap", "-vfs", "-maxsize", "-heap",
                     "-escape"}
SQLITE_TWO_VALUES = {"-lookaside", "-pagecache"}
ASSIGN_WORD = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")
GROUP = re.compile(r"(?P<open>\{\s+|\(\s*)(?P<body>(?:[^{}()]|\$\([^()]*\))*?)\s*;?\s*(?P<close>[})])"
                   r"(?P<after>\s*(?:\||>>?\s*\S+))")


def _virtual_text(cmds_text: str, cwd: str, virtual: dict) -> str | None:
    """The output of a group made only of echo / printf / cat (None if it has anything else)."""
    out = []
    ps = S.parse(cmds_text.strip())
    if ps.problems:
        return None
    for sc in ps.commands:
        if sc.joined_by not in ("", ";", "&&", "\n") or sc.redirects or any(w.dynamic for w in sc.words):
            return None
        words = [w.text for w in sc.words]
        if not words:
            continue
        name, args = words[0], words[1:]
        if name == "echo":
            nl = "-n" not in args
            out.append(" ".join(a for a in args if a not in ("-n", "-e", "-E")) + ("\n" if nl else ""))
        elif name == "printf" and args:
            fmt = args[0].replace("\\n", "\n").replace("\\t", "\t")
            try:
                out.append(fmt % tuple(args[1:]) if "%" in fmt and len(args) > 1 else fmt)
            except (TypeError, ValueError):
                return None
        elif name == "cat" and args:
            for a in args:
                p = os.path.normpath(os.path.join(cwd, os.path.expanduser(a)))
                if p in virtual:
                    out.append(virtual[p])
                    continue
                try:
                    with open(p, errors="replace") as fh:
                        out.append(fh.read())
                except OSError:
                    return None
        else:
            return None
    return "".join(out)


READ_ONLY_GROUP = {"echo", "printf", "cat", "head", "tail", "grep", "egrep", "fgrep", "sort", "uniq", "cut", "tr",
                   "paste", "nl", "rev", "column", "comm", "join", "sed", "awk", "jq", "true", ":"}


def _group_output(body: str, cwd: str) -> str | None:
    """The output of a group of commands that only read (sed -n, head, grep, ...), by running them here: they cannot
    change anything. None when a command could write or the group fails."""
    ps = S.parse(body.strip())
    if ps.problems:
        return None
    for sc in ps.commands:
        name, at, _ = S.command_name(list(sc.words))
        args = [w.text for w in sc.words[at + 1:]]
        if name not in READ_ONLY_GROUP or sc.redirects or sc.joined_by not in ("", ";", "&&", "\n", "|"):
            return None
        if name == "sed" and any(a.startswith(("-i", "-I", "--in-place")) or re.search(r"(^|;)\s*w\s", a) for a in args):
            return None
        if name == "sort" and any(a.startswith("-o") for a in args):
            return None
        if name == "awk" and any("system" in a or ">" in a for a in args):
            return None
    try:
        p = subprocess.run(["/bin/bash", "-c", body], cwd=cwd, capture_output=True, text=True, timeout=5,
                           env={"PATH": "/usr/bin:/bin:/opt/homebrew/bin", "LANG": "C"})
    except (OSError, subprocess.SubprocessError):
        return None
    return p.stdout if p.returncode == 0 else None


def _rewrite_groups(line: str, cwd: str, virtual: dict) -> tuple[str, list]:
    """Groups whose output is known are replaced by `cat <virtual file>`: echo / printf / cat read here, or other
    commands that only read (sed -n, head, grep, ...) run here."""
    notes = []
    while True:
        m = GROUP.search(line)
        if not m:
            return line, notes
        text = _virtual_text(m.group("body"), cwd, virtual)
        if text is None:
            text = _group_output(m.group("body"), cwd)
        if text is None:
            return line, notes
        key = os.path.join(cwd, f".ekbasis-virtual-{len(virtual)}")
        virtual[key] = text
        line = line[:m.start()] + f"cat {shlex.quote(key)}" + m.group("after") + line[m.end():]
        notes.append("group")


def _pipelines(ps) -> list:
    out = []
    for sc in ps.commands:
        if sc.joined_by in ("|", "|&") and out:
            out[-1][1].append(sc)
        else:
            out.append((sc.joined_by, [sc]))
    return out


def _step_text(line: str, simples: list) -> str:
    starts = [w.start for sc in simples for w in sc.words if w.start >= 0]
    ends = [w.end for sc in simples for w in sc.words if w.end >= 0]
    ends += [r.target.end for sc in simples for r in sc.redirects if r.target is not None and r.target.end >= 0]
    if not starts:
        return ""
    return line[min(starts):max(ends)].strip()


def _heredoc_bodies(line: str) -> dict:
    out = {}
    for m in re.finditer(r"<<(-?)\s*(['\"]?)([A-Za-z_][\w.-]*)\2", line):
        nl = line.find("\n", m.end())
        if nl == -1:
            continue
        rest = line[nl + 1:].split("\n")
        body = []
        for x in rest:
            if (x.strip() if m.group(1) else x) == m.group(3):
                break
            body.append(x.lstrip("\t") if m.group(1) else x)
        else:
            continue
        out[m.start()] = "\n".join(body)
    return out


def _read_text(path: str, virtual: dict) -> str:
    if path in virtual:
        return virtual[path]
    try:
        with open(path, errors="replace") as fh:
            return fh.read()
    except OSError as e:
        raise CannotJudge(f"cannot read {path}: {e.strerror}") from None


def _sqlite_call(sc, cwd: str, bodies: dict, piped: str | None, virtual: dict):
    """A sqlite3 invocation -> (db, SQL text, bail, unread) or None if it is not one."""
    name, at, _ = S.command_name(list(sc.words))
    if name != "sqlite3":
        return None
    args, i, bail, unread, cmds, pos = sc.words[at + 1:], 0, False, [], [], []
    while i < len(args):
        t = args[i].text
        if t in ("-bail", "--bail"):
            bail = True
        elif t in SQLITE_VALUE_OPTS:
            if t == "-cmd" and i + 1 < len(args):
                cmds.append(args[i + 1].text)
            elif t == "-init":
                unread.append("sqlite3 -init runs another file first")
            i += 1
        elif t in SQLITE_TWO_VALUES:
            i += 2
        elif t in ("-readonly", "--readonly", "-safe"):
            unread.append(f"sqlite3 {t}")
        elif t.startswith("-") and not pos:
            pass
        else:
            pos.append(args[i])
        i += 1
    if any(w.dynamic for w in pos):
        unread.append("a database or SQL that comes from a variable or command substitution")
    db = os.path.normpath(os.path.join(cwd, os.path.expanduser(pos[0].text))) if pos else None
    # each argument after the database is one whole command: SQL ends there even without ';'
    texts = [w.text if w.text.strip().startswith(".") or w.text.rstrip().endswith(";") else w.text.rstrip() + ";"
             for w in pos[1:]]
    for r in sc.redirects:
        if r.op == "<" and r.target is not None:
            texts.append(_read_text(os.path.normpath(os.path.join(cwd, os.path.expanduser(r.target.text))), virtual))
        elif r.op == "<<":
            body = next((b for at_, b in sorted(bodies.items()) if at_ >= (sc.words[0].start if sc.words else 0)), None)
            if body is None:
                unread.append("a here-document preflight could not read")
            else:
                texts.append(body)
        elif r.op == "<<<":
            unread.append("a here-string")
    if piped is not None:
        texts.append(piped)
    sql = "\n".join(cmds + texts)
    for m in re.finditer(r"^\s*\.read\s+(\S+)", sql, re.M):
        p = os.path.normpath(os.path.join(cwd, os.path.expanduser(m.group(1).strip("'\""))))
        sql = sql.replace(m.group(0), _read_text(p, virtual), 1)
    return db, sql, bail, unread


def _sql_plan(db, sql, bail, unread, cwd, source) -> Plan:
    stmts, dots = split_sql(sql)
    unread = list(unread)
    for _, d in dots:
        word = d.split()[0].lower()
        if word == ".bail":
            bail = bail or (len(d.split()) > 1 and d.split()[1].lower() in ("on", "1", "yes", "true"))
        elif word not in READ_DOTS:
            unread.append(f"the sqlite3 dot-command {word}")
    steps = sql_steps(stmts)
    for s in steps:
        if SQL_SIDE.search(s.text):
            unread.append("SQL that reaches other files (ATTACH, load_extension, readfile/writefile)")
            break
    plan = Plan("sql", steps, cwd, source, db=db, stop_on_error=bail, shell="sqlite3", unread=list(dict.fromkeys(unread)))
    for k, s in enumerate(steps, 1):
        if FK_ON.match(s.text) and plan.fk_from is None:
            plan.fk_from = k + 1 if k < len(steps) else None
            if all(not x.writes for x in steps[:k]):
                plan.fk_from = 1
        elif FK_OFF.match(s.text):
            plan.fk_from = None
    return plan


def _substitute(text: str, env: dict) -> str:
    for name, val in env.items():
        text = re.sub(r"\$\{" + name + r"\}|\$" + name + r"(?![A-Za-z0-9_])", lambda m: val, text)
    return text


CONTROL_FLOW = re.compile(r"^\s*(if|then|elif|else|fi|for|while|until|do|done|case|esac|select|function)\b|"
                          r"^\s*[A-Za-z_][\w-]*\s*\(\)\s*\{?|^\s*[{}]\s*$")
ERREXIT = re.compile(r"^\s*set\s+(-[a-zA-Z]*e[a-zA-Z]*|-o\s+errexit)(\s|$)")
ASSIGN_LINE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)=(?:\"([^\"$`]*)\"|'([^']*)'|([^\s$`;&|'\"]*))\s*$")


def script_lines(text: str) -> tuple[list, list, bool]:
    lines, unread, errexit, buf, env = [], [], False, "", {}
    for raw in text.splitlines():
        if buf:
            raw = buf + raw
            buf = ""
        if raw.rstrip().endswith("\\") and not raw.rstrip().endswith("\\\\"):
            buf = raw.rstrip()[:-1] + " "
            continue
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        if ERREXIT.match(s):
            errexit = True
            continue
        if CONTROL_FLOW.match(s):
            unread.append("control flow or functions in the script (if, for, while, case, function)")
            continue
        if "<<" in s:
            unread.append("a here-document in the script")
        m = ASSIGN_LINE.match(s)
        if m:
            env[m.group(1)] = next(x for x in m.groups()[1:] if x is not None)
            continue
        lines.append(_substitute(s, env))
    return lines, list(dict.fromkeys(unread)), errexit


def _shell_steps(lines_or_pipes, line: str, cwd0: str, bodies: dict, virtual: dict, from_script: bool):
    """Steps of a chain (pipelines of one line) or of a script (its lines), each with its effect and folder; sqlite3
    calls carry their statements."""
    steps, unread, cwd = [], [], cwd0
    items = []
    if from_script:
        for text in lines_or_pipes:
            ps = S.parse(text)
            items.append(("\n", ps.commands, text, ps.problems))
    else:
        for joined, simples in lines_or_pipes:
            items.append((joined, simples, _step_text(line, simples), []))
    for joined, simples, text, problems in items:
        effect, ctx = READ, False
        piped = None
        sql_call = None
        if len(simples) == 2:
            n0, a0, _ = S.command_name(list(simples[0].words))
            files = [w.text for w in simples[0].words[a0 + 1:] if not w.text.startswith("-")]
            if n0 == "cat" and files:
                try:
                    piped = "".join(_read_text(os.path.normpath(os.path.join(cwd, os.path.expanduser(f))), virtual)
                                    for f in files)
                except CannotJudge:
                    piped = None
        for sc in simples:
            call = _sqlite_call(sc, cwd, bodies, piped if sc is simples[-1] else None, virtual) \
                if S.command_name(list(sc.words))[0] == "sqlite3" else None
            if call is not None:
                sql_call = call
                continue
            e, c = shell_effect(sc, cwd)
            effect, ctx = _max(effect, e), ctx or c
        step = Step(text=text, effect=effect, joined_by=joined, ctx=ctx, cwd=cwd)
        if sql_call is not None:
            db, sql, bail, un = sql_call
            sub = _sql_plan(db, sql, bail, un, cwd, "sqlite3")
            unread += sub.unread
            step.sql, step.db, step.bail = sub.steps, db, sub.stop_on_error
            step.effect = _max(effect, max((s.effect for s in sub.steps), key=lambda e: ORDER[e], default=READ))
        if ctx:
            sc = simples[0]
            name, at, _ = S.command_name(list(sc.words))
            targets = [w for w in sc.words[at + 1:] if not w.text.startswith("-")]
            if name == "cd" and len(targets) == 1 and not targets[0].dynamic:
                nxt = os.path.normpath(os.path.join(cwd, os.path.expanduser(targets[0].text)))
                cwd = nxt if os.path.isdir(nxt) else cwd
            elif name == "cd" and not targets:
                cwd = os.path.expanduser("~")
            elif name in ("pushd", "popd") or any(t.dynamic for t in targets):
                unread.append("pushd / popd or a cd preflight does not follow")
        steps.append(step)
        unread += [p for p in problems if p in (S.P_SUBST, S.P_HEREDOC_OPEN, S.P_QUOTE, S.P_GROUP, S.P_PROCSUB,
                                                S.P_NESTED)]
    return steps, list(dict.fromkeys(unread))


def plan_line(line: str, cwd: str = ".") -> Plan | None:
    """The plan of a command line, or None when it is not a multi-step change: SQL with fewer than two statements that
    change something; a script with fewer than two steps or none that changes something; a chain with fewer than two
    steps that change something and no step that removes data after a `;` or a new line."""
    cwd = os.path.realpath(cwd)
    virtual: dict = {}
    # line-level NAME=value assignments (R=/repo; sqlite3 $R/x.db ...) and groups of echo/printf/cat
    env = {}
    for m in re.finditer(r"(?:^|[;&|\n]\s*)([A-Za-z_][A-Za-z0-9_]*)=(\"[^\"`]*\"|'[^']*'|[^\s`;&|'\"()]+)(?=\s*(?:[;&\n]|$))",
                         line):
        val = _substitute(m.group(2).strip("'\""), env)
        if "$" not in val:
            env[m.group(1)] = val
    if env:
        line = _substitute(line, env)
    line, _ = _rewrite_groups(line, cwd, virtual)
    ps = S.parse(line)
    pipes = _pipelines(ps)
    pipes = [(j, s) for j, s in pipes if not (len(s) == 1 and not s[0].redirects and len(s[0].words) == 1 and
                                              ASSIGN_WORD.match(s[0].words[0].text))]
    bodies = _heredoc_bodies(line)
    if not pipes:
        return None
    # virtual files written on this line: `cat <virtual> > FILE` or `echo ... > FILE`
    for _, simples in pipes:
        sc = simples[-1]
        name, at, _ = S.command_name(list(sc.words))
        outs = [r for r in sc.redirects if r.op in (">", ">|") and r.target is not None]
        if outs and name in ("cat", "echo", "printf") and len(simples) == 1:
            text = _virtual_text(" ".join(shlex.quote(w.text) for w in sc.words), cwd, virtual)
            if text is not None:
                virtual[os.path.normpath(os.path.join(cwd, os.path.expanduser(outs[0].target.text)))] = text
    # one pipeline: a sqlite3 run or a script
    if len(pipes) == 1:
        simples = pipes[0][1]
        piped = None
        if len(simples) == 2:
            n0, a0, _ = S.command_name(list(simples[0].words))
            files = [w.text for w in simples[0].words[a0 + 1:] if not w.text.startswith("-")]
            if n0 == "cat" and files:
                piped = "".join(_read_text(os.path.normpath(os.path.join(cwd, os.path.expanduser(f))), virtual)
                                for f in files)
                simples = simples[1:]
        if len(simples) == 1:
            call = _sqlite_call(simples[0], cwd, bodies, piped, virtual)
            if call is not None:
                db, sql, bail, unread = call
                if db is None:
                    return None
                plan = _sql_plan(db, sql, bail, unread, cwd, f"sqlite3 on {os.path.relpath(db, cwd)}")
                plan.sqlite3_line = True
                return plan if plan.writes >= 2 else None
            name, at, _ = S.command_name(list(simples[0].words))
            args = list(simples[0].words[at + 1:])
            script = None
            if name in ("bash", "sh", "zsh", "dash", "source", ".") and args and not args[0].text.startswith("-"):
                script = args[0].text
            elif os.sep in simples[0].words[at].text and os.path.isfile(os.path.join(cwd, simples[0].words[at].text)):
                script, name = simples[0].words[at].text, "bash"
            if script is not None:
                p = os.path.join(cwd, os.path.expanduser(script))
                if not os.path.isfile(p):
                    return None
                try:
                    with open(p, errors="replace") as fh:
                        text = fh.read()
                except OSError as e:
                    raise CannotJudge(f"cannot read the script {script}: {e.strerror}") from None
                if text.startswith("#!") and not re.match(r"#!\s*/(usr/)?(local/)?bin/(env\s+)?(ba|z|da)?sh\b", text):
                    return None
                lines, unread, errexit = script_lines(text)
                if any(w.dynamic for w in args[1:]):
                    unread.append("script arguments from variables")
                if any(re.search(r"\$[0-9@*#]", x) for x in lines):
                    unread.append("the script's positional parameters ($1, $@)")
                steps, un2 = _shell_steps(lines[:MAX_STEPS], line, cwd, {}, virtual, from_script=True)
                plan = Plan("shell", steps, cwd, f"the script {script}", stop_on_error=errexit,
                            shell="zsh" if name == "zsh" else "bash", unread=list(dict.fromkeys(unread + un2)),
                            script=True)
                return plan if len(plan.steps) >= 2 and plan.writes >= 1 else None
        return None
    # a chain of sqlite3 calls on one database only -> one SQL plan
    calls = [None]
    if all(len(sm) == 1 and S.command_name(list(sm[0].words))[0] == "sqlite3" for _, sm in pipes):
        try:
            calls = [_sqlite_call(sm[0], cwd, bodies, None, virtual) for _, sm in pipes]
        except CannotJudge:
            calls = [None]
    if all(c is not None for c in calls) and len({c[0] for c in calls}) == 1 and calls[0][0]:
        sql = "\n".join(c[1].rstrip().rstrip(";") + ";" for c in calls)
        unread = [u for c in calls for u in c[3]]
        if any(j in ("||", "&") for j, _ in pipes[1:]):
            unread.append("sqlite3 calls joined by || or &")
        plan = _sql_plan(calls[0][0], sql, any(c[2] for c in calls), unread, cwd,
                         f"sqlite3 calls on {os.path.relpath(calls[0][0], cwd)}")
        plan.sqlite3_line = True
        if any(j == "&&" for j, _ in pipes[1:]):
            plan.stop_on_error = all(j in ("&&", "") for j, _ in pipes)
        return plan if plan.writes >= 2 else None
    # a chain: shell steps, sqlite3 calls among them carry their statements
    steps, unread = _shell_steps(pipes, line, cwd, bodies, virtual, from_script=False)
    changing = [i for i, st in enumerate(steps) if st.effect in (MODIFY, DESTROY)]
    if len(changing) == 1 and not unread and (steps[changing[0]].sql is not None or
                                               all(st.effect == READ for k, st in enumerate(steps) if k != changing[0])):
        # one change among checks that only read or steps that only add (`bash x.sh && git status`,
        # `cp app.db /tmp/app.bak && sqlite3 app.db < m.sql`): the change is the plan
        i = changing[0]
        j, simples = pipes[i]
        inner = _step_text(line, simples)
        if steps[i].sql is not None and steps[i].db:
            sub = _sql_plan(steps[i].db, "\n".join(x.text for x in steps[i].sql), steps[i].bail, [], steps[i].cwd,
                            f"sqlite3 on {os.path.relpath(steps[i].db, steps[i].cwd)}")
            sub.sqlite3_line = True
            return sub if sub.writes >= 2 else None
        name, at, _ = S.command_name(list(simples[0].words))
        if len(simples) == 1 and (name in ("bash", "sh", "zsh", "dash") or os.sep in simples[0].words[at].text):
            sub = plan_line(inner, steps[i].cwd)
            if sub is not None and sub.script:
                sub.source += " (inside a longer line)"
                return sub
    if any(j == "&" for j, _ in pipes[1:]):
        unread.append("commands run in the background (&)")
    plan = Plan("shell", steps[:MAX_STEPS], cwd, "the command line", shell=S.default_shell(),
                unread=list(dict.fromkeys(unread)))
    plan._virtual = virtual  # noqa: SLF001 — used by the run on a copy
    unguarded = any(s.destructive and any(x.joined_by in (";", "\n") for x in plan.steps[1:j + 1])
                    for j, s in enumerate(plan.steps) if j > 0)
    return plan if plan.writes >= 2 or unguarded else None


# ---------------------------------------------------------------- what a failure at step k leaves

def consequences(plan: Plan, k: int) -> tuple[list, list, bool]:
    """(changing steps already applied, steps that still run, atomic) if step k (1-based) is the first to fail."""
    steps = plan.steps
    if plan.kind == "sql":
        opened = None
        for i in range(k - 1):
            if SQL_BEGIN.match(steps[i].text):
                opened = i
            elif SQL_END.match(steps[i].text):
                opened = None
        applied = [i + 1 for i in range(k - 1) if steps[i].writes]
        if plan.stop_on_error:
            if opened is not None:
                applied = [i + 1 for i in range(opened) if steps[i].writes]
            return applied, [], not applied
        return applied, list(range(k + 1, len(steps) + 1)), False
    applied = [i + 1 for i in range(k - 1) if steps[i].writes]
    if plan.script:
        after = [] if plan.stop_on_error else list(range(k + 1, len(steps) + 1))
        return applied, after, not applied and not any(steps[j - 1].writes for j in after)
    ok, after = False, []
    for j in range(k + 1, len(steps) + 1):
        op = steps[j - 1].joined_by
        run = op in (";", "\n", "") or (op == "&&" and ok) or (op == "||" and not ok)
        if run:
            after.append(j)
            ok = True
    return applied, after, not applied and not any(steps[j - 1].writes for j in after)


def half_applied(plan: Plan, k: int) -> tuple[bool, list, list, bool]:
    """Whether a first failure at step k leaves the change half applied: the failing step changes something (or is a
    cd with changes after it), and a step that modifies or removes existing data has already run or would still run.
    Returns (half, applied, after, atomic)."""
    applied, after, atomic = consequences(plan, k)
    st = plan.steps[k - 1]
    if atomic:
        return False, applied, after, atomic
    failing_counts = st.writes or (st.ctx and any(plan.steps[j - 1].writes for j in after))
    heavy = [j for j in applied + after if plan.steps[j - 1].effect in (MODIFY, DESTROY)]
    return bool(failing_counts and heavy), applied, after, atomic


# ---------------------------------------------------------------- run on a copy

SANDBOX = """(version 1)
(allow default)
(deny network*)
(deny file-write*)
(allow file-write* (subpath "{root}") (subpath "/dev") (subpath "/private/tmp/{tag}"))
"""


def _copy_tree(src: str, dst: str) -> None:
    if platform.system() == "Darwin":
        try:
            import ctypes
            if ctypes.CDLL("libc.dylib", use_errno=True).clonefile(src.encode(), dst.encode(), 0) == 0:
                return
        except OSError:
            pass
        subprocess.run(["cp", "-c", "-R", "-p", src, dst], check=True, capture_output=True, timeout=COPY_TIMEOUT)
        return
    r = subprocess.run(["cp", "-a", "--reflink=always", src, dst], capture_output=True, timeout=COPY_TIMEOUT)
    if r.returncode == 0:
        return
    size = 0
    for d, _, fs in os.walk(src):
        for f in fs:
            try:
                size += os.lstat(os.path.join(d, f)).st_size
            except OSError:
                pass
            if size > COPY_MAX_BYTES:
                raise CannotJudge("the folder is too big to copy without reflinks")
    shutil.rmtree(dst, ignore_errors=True)
    subprocess.run(["cp", "-a", src, dst], check=True, capture_output=True, timeout=COPY_TIMEOUT)


def _words(text: str) -> list:
    try:
        return shlex.split(text, comments=False)
    except ValueError:
        return text.split()


def _tmp_roots() -> set:
    """Temporary folders: paths under them are mapped into the copy's own temporary folder."""
    return {os.path.realpath(tempfile.gettempdir()), "/tmp", "/private/tmp"}


def sandbox_here() -> bool:
    """True where the steps of a copy can run inside a sandbox (macOS sandbox-exec: no network, no writes outside the
    copy). Shell plans run on a copy only there: without one, a step that writes outside the folder (a path to an
    existing file elsewhere, `..`, a symbolic link, xargs over a list of paths) would write the real file during the
    check. SQL plans do not need it: SQL that reaches other files never runs on a copy."""
    return platform.system() == "Darwin" and shutil.which("sandbox-exec") is not None


def copy_eligible(plan: Plan) -> str | None:
    """None when the plan can run on a copy; otherwise why not."""
    if plan.unread:
        return "parts preflight does not follow"
    root = plan.cwd
    if plan.kind == "sql":
        if not plan.db or not sqlite_cli():
            return "no sqlite3 shell here" if plan.db else "no database"
        if any(SQL_SIDE.search(s.text) or SQL_OUT.search(s.text) for s in plan.steps):
            return "SQL that writes another file"
        if not os.path.exists(plan.db) or os.path.getsize(plan.db) > COPY_MAX_BYTES and platform.system() != "Darwin":
            return "the database is too big to copy" if os.path.exists(plan.db) else None
        return None
    tmps = _tmp_roots()
    for s in plan.steps:
        why = _copy_ok_text(s.text, s.cwd or root, root, tmps, depth=0)
        if why:
            return why
        if s.sql is not None and any(SQL_SIDE.search(x.text) or SQL_OUT.search(x.text) for x in s.sql):
            return "SQL that reaches other files"
    if not sandbox_here():
        return "no sandbox here to run the steps in"
    return None


XARGS_VALUE = {"-I", "-n", "-L", "-l", "-P", "-s", "-E", "-e", "-d", "-a", "-R", "-S", "-J", "--arg-file",
               "--delimiter", "--max-args", "--max-lines", "--max-procs", "--max-chars", "--eof", "--replace"}
RUNS_PROGRAMS = {
    "tar": re.compile(r"^--(use-compress-program|to-command|checkpoint-action|info-script|new-volume-script|rsh-command)"),
    "zip": re.compile(r"^(-TT|--unzip-command)"),
    "sort": re.compile(r"^--compress-program"),
    "git": re.compile(r"^(-c$|-c\S|--config-env|--exec-path|--ext-diff)"),
}
AWK_RUNS = re.compile(r"\bsystem\s*\(|\|\s*getline|\|&|\bprint[f]?\b[^;}]*\|")


def _runs_other_programs(name: str, args: list) -> str | None:
    """A command the allowlist takes that would run a program of its own choosing: the program, or why."""
    if name == "xargs":
        i = 0
        while i < len(args) and args[i].startswith("-"):
            i += 2 if args[i] in XARGS_VALUE else 1
        return args[i] if i < len(args) else None
    if name == "find":
        progs = [args[i + 1] for i, a in enumerate(args[:-1]) if a in ("-exec", "-execdir", "-ok", "-okdir")]
        return next((p for p in progs if os.path.basename(p) not in COPY_OK or p in NETWORK), None)
    if name == "awk" and any(AWK_RUNS.search(a) for a in args):
        return "a program inside awk"
    rx = RUNS_PROGRAMS.get(name)
    if rx is not None and any(rx.search(a) for a in args):
        return f"a program named by {name}'s options"
    return None


def _copy_ok_text(text: str, cwd: str, root: str, tmps: set, depth: int) -> str | None:
    """Why the commands of this text cannot run on a copy (None: they can)."""
    for sc in S.parse(text).commands:
        name, at, _ = S.command_name(list(sc.words))
        if not name:
            continue
        word0 = sc.words[at].text if at < len(sc.words) else ""
        if os.sep in word0 and os.path.isfile(os.path.join(cwd, word0)) and name not in COPY_OK:
            name = "bash"                       # a script run by its path: judged like `bash script`
            sc = S.parse("bash " + shlex.quote(word0)).commands[0]
            at = 0
        if name in NETWORK or name not in COPY_OK and name not in ("bash", "sh", "zsh") and name != "git":
            return f"`{name}` is not a local file command"
        prog = _runs_other_programs(name, [w.text for w in sc.words[at + 1:]])
        if prog is not None and (name != "xargs" or os.path.basename(prog) not in COPY_OK or prog in NETWORK
                                 or prog in ("xargs", "find")):
            return f"`{name}` running {prog if ' ' in prog else '`' + prog + '`'}"
        if name == "git":
            args = [w.text for w in sc.words[at + 1:]]
            if not G.read_only(shlex.join(["git"] + args)):
                return "git commands that change the repository"
        if name in ("bash", "sh", "zsh"):
            args = [w.text for w in sc.words[at + 1:]]
            script = os.path.normpath(os.path.join(cwd, args[0])) if args and not args[0].startswith("-") else None
            if depth > 0 or not script or not os.path.isfile(script) or not (
                    script == root or script.startswith(root + os.sep)):
                return "a nested shell"
            try:
                with open(script, errors="replace") as fh:
                    lines, unread, _ = script_lines(fh.read())
            except OSError:
                return "a script it cannot read"
            if unread:
                return "a script with parts preflight does not follow"
            for x in lines:
                why = _copy_ok_text(x, cwd, root, tmps, depth + 1)
                if why:
                    return why
            continue
        for w in sc.words[at + 1:] + [r.target for r in sc.redirects if r.target is not None]:
            t = w.text
            if w.dynamic and name not in QUIET:
                return "a path from a variable"
            if t.startswith(("/", "~")):
                full = os.path.realpath(os.path.expanduser(t)) if os.path.exists(os.path.expanduser(t)) \
                    else os.path.normpath(os.path.expanduser(t))
                inside = full == root or full.startswith(root + os.sep)
                in_tmp = any(full == x or full.startswith(x + os.sep) for x in tmps)
                if not inside and not in_tmp and not os.path.isfile(full) and name not in ("cd",):
                    return "a path outside the folder"
                if not inside and not in_tmp and name == "cd":
                    return "a cd outside the folder"
    return None


def _sandboxed(cmd: list, base: str, tag: str, meta: str, required: bool) -> list:
    """cmd inside sandbox-exec (no network, writes only in the copy). Where it cannot start: CannotJudge when it is
    required (shell steps), cmd as it is otherwise (SQL, kept in the copy by the checks in copy_eligible)."""
    if sandbox_here():
        prof = os.path.join(meta, "box.sb")
        with open(prof, "w") as fh:
            fh.write(SANDBOX.format(root=os.path.realpath(base), tag=tag))
        probe = subprocess.run(["sandbox-exec", "-f", prof, "/usr/bin/true"], capture_output=True)
        if probe.returncode == 0:
            return ["sandbox-exec", "-f", prof] + cmd
    if required:
        raise CannotJudge("the sandbox did not start, so the steps were not run on a copy")
    return cmd


def _clean_err(err: str, meta: str, clone: str, root: str, tmpdir: str) -> str:
    err = re.sub(re.escape(os.path.join(meta, "run.sh")) + r": line \d+: ", "", err)
    return err.replace(clone, root).replace(tmpdir, "/tmp").strip()[-400:]


def run_on_copy(plan: Plan, work: str | None = None) -> dict:
    """Run the plan on a copy: {"first": k or None, "error": text, "ms"}. Raises CannotJudge if the copy fails."""
    t0 = time.monotonic()
    if work:
        os.makedirs(work, exist_ok=True)
    base = tempfile.mkdtemp(prefix="ekbasis-copy-", dir=work)
    tag = os.path.basename(base)
    try:
        if plan.kind == "sql":
            dbc = os.path.join(base, os.path.basename(plan.db))
            for ext in ("", "-wal", "-shm", "-journal"):
                if os.path.exists(plan.db + ext):
                    _copy_tree(plan.db + ext, dbc + ext)
            meta, tmpdir = os.path.join(base, "m"), os.path.join(base, "tmp")
            os.makedirs(meta)
            os.makedirs(tmpdir)
            text = "".join(f".print __EKBASIS_STEP_{k}__\n{s.text}\n" for k, s in enumerate(plan.steps, 1))
            cmd = _sandboxed([sqlite_cli(), "-bail", "-batch", dbc], base, tag, meta, required=False)
            env = dict(os.environ, TMPDIR=tmpdir + "/", SQLITE_TMPDIR=tmpdir)
            p = subprocess.run(cmd, input=text, capture_output=True, text=True, timeout=COPY_TIMEOUT, cwd=base, env=env)
            marks = re.findall(r"__EKBASIS_STEP_(\d+)__", p.stdout)
            first = int(marks[-1]) if p.returncode != 0 and marks else None
            return {"first": first, "error": p.stderr.strip()[-400:] if first else "",
                    "ms": round(1000 * (time.monotonic() - t0), 1)}
        root = plan.cwd
        clone = os.path.join(base, "root")
        _copy_tree(root, clone)
        tmpdir = os.path.join(base, "tmp")
        os.makedirs(tmpdir)
        tmps = sorted(_tmp_roots(), key=len, reverse=True)

        def remap(text):
            text = text.replace(root, "\x00ROOT\x00")       # the folder first: it may itself be under /tmp
            for t in tmps:
                text = re.sub(r"(?<![\w/])" + re.escape(t) + r"(?=/)", lambda m: tmpdir, text)
            return text.replace("\x00ROOT\x00", clone)
        virtual = getattr(plan, "_virtual", {})
        for path, content in virtual.items():
            vp = remap(path)
            os.makedirs(os.path.dirname(vp), exist_ok=True)
            with open(vp, "w") as fh:
                fh.write(content)
        meta = os.path.join(base, "m")
        os.makedirs(meta)
        lines = [f'cd "{remap(plan.steps[0].cwd or root)}" || exit 99']
        sql_lines = {}
        for k, s in enumerate(plan.steps, 1):
            text = remap(s.text)
            if s.sql is not None and s.db:
                body, starts = [], []
                for x in s.sql:
                    starts.append(len(body) + 1)
                    body += x.text.split("\n")
                sql_lines[k] = starts
                text = (f"{shlex.quote(sqlite_cli() or 'sqlite3')} {'-bail ' if s.bail else ''}-batch "
                        f"{shlex.quote(remap(s.db))} <<'__EKBASIS_SQL__'\n" + "\n".join(body) + "\n__EKBASIS_SQL__")
            lines += ["{ " + text, f'}} >/dev/null 2>"{meta}/{k}.err" </dev/null; rc=$?; echo $rc > "{meta}/{k}.rc"; '
                      f'[ $rc -ne 0 ] && exit 0']
        with open(os.path.join(meta, "run.sh"), "w") as fh:
            fh.write("\n".join(lines) + "\n")
        sh = "/bin/zsh" if plan.shell == "zsh" else "/bin/bash"
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": base, "LANG": "C", "TMPDIR": tmpdir + "/",
               "TMPPREFIX": os.path.join(tmpdir, "zsh")}
        cmd = _sandboxed([sh, os.path.join(meta, "run.sh")], base, tag, meta, required=True)
        subprocess.run(cmd, cwd=clone, capture_output=True, text=True, timeout=COPY_TIMEOUT, env=env)
        out = {"first": None, "error": ""}
        for k in range(1, len(plan.steps) + 1):
            rc_path = os.path.join(meta, f"{k}.rc")
            if not os.path.exists(rc_path):
                break
            if int(open(rc_path).read().strip() or "0") != 0:
                out["first"] = k
                err = open(os.path.join(meta, f"{k}.err"), errors="replace").read()
                if "operation not permitted" in err.lower():
                    # the sandbox refused a write outside the copy: the real run may well succeed there
                    raise CannotJudge("a step writes outside the folder, which a copy cannot reproduce")
                if k in sql_lines:
                    m = re.search(r"near line (\d+)", err)
                    if m:
                        n_line = int(m.group(1))
                        starts = sql_lines[k]
                        out["inner"] = max(i for i, st in enumerate(starts, 1) if st <= n_line)
                out["error"] = _clean_err(err, meta, clone, root, tmpdir)
                break
            if k in sql_lines:   # rc 0 but an error inside (no -bail): the shell went on after it
                err = open(os.path.join(meta, f"{k}.err"), errors="replace").read()
                m = re.search(r"near line (\d+)", err)
                if m:
                    starts = sql_lines[k]
                    out["first"], out["inner"] = k, max(i for i, st in enumerate(starts, 1) if st <= int(m.group(1)))
                    out["error"] = _clean_err(err, meta, clone, root, tmpdir)
                    break
        out["ms"] = round(1000 * (time.monotonic() - t0), 1)
        return out
    except (OSError, subprocess.SubprocessError) as e:
        raise CannotJudge(f"could not run it on a copy: {type(e).__name__}: {e}") from None
    finally:
        subprocess.run(["chmod", "-R", "u+rwx", base], capture_output=True)
        shutil.rmtree(base, ignore_errors=True)


# ---------------------------------------------------------------- shell facts code can state

SHELL_BUILTINS = {"cd", "pushd", "popd", "echo", "printf", "test", "[", "[[", "true", "false", ":", "set", "export",
                  "unset", "local", "readonly", "shift", "return", "exit", "eval", "source", ".", "exec", "type",
                  "command", "builtin", "alias", "unalias", "read", "wait", "trap", "umask", "ulimit", "hash", "let",
                  "declare", "typeset", "times", "jobs", "fg", "bg", "kill", "pwd", "shopt", "getopts", "break",
                  "continue", "dirs", "history", "fc", "enable", "help", "logout", "mapfile", "readarray", "caller",
                  "complete", "compgen", "disown", "suspend", "time", "{", "}"}
NOTE_MKDIR_FILE = ("mkdir -p fails when the path, or a folder in it, already exists as a file; a destination written "
                   "with a trailing slash (cp a b/, mv a b/) must be an existing folder, or the command fails.")


def shell_facts(plan: Plan) -> tuple[dict, list]:
    """({step index (1-based): the fact that makes it fail}, [fact lines for the state]). Only for paths no earlier
    step of the plan names (an earlier step could change them)."""
    import glob as _glob
    fails, lines, named = {}, [], set()
    for k, s in enumerate(plan.steps, 1):
        cwd = s.cwd or plan.cwd
        for sc in S.parse(s.text).commands:
            name, at, _ = S.command_name(list(sc.words))
            args = [w for w in sc.words[at + 1:]]
            pos = [w for w in args if not w.text.startswith("-")]
            fact = None

            def full(t):
                return os.path.normpath(os.path.join(cwd, os.path.expanduser(t)))

            def fresh(t):
                return full(t) not in named

            if name == "cd" and len(pos) == 1 and not pos[0].dynamic and fresh(pos[0].text):
                p = full(pos[0].text)
                if not os.path.isdir(p):
                    fact = f"{pos[0].text} {'is a file' if os.path.exists(p) else 'does not exist'}, so `cd {pos[0].text}` fails"
            elif name == "mkdir" and pos:
                for w in pos:
                    if w.dynamic or not fresh(w.text):
                        continue
                    p = full(w.text)
                    parts, cur = [], p
                    while cur and cur != os.path.dirname(cur):
                        parts.append(cur)
                        cur = os.path.dirname(cur)
                    blocker = next((x for x in reversed(parts) if os.path.exists(x) and not os.path.isdir(x)), None)
                    if blocker:
                        fact = f"{os.path.relpath(blocker, cwd)} is a file, so `mkdir {w.text}` fails"
                    elif os.path.isdir(p) and "-p" not in [a.text for a in args]:
                        fact = f"{w.text} already exists, so `mkdir {w.text}` (without -p) fails"
            elif name in ("cp", "mv", "ln", "install") and len(pos) >= 2 and not any(w.dynamic for w in pos):
                dest, srcs = pos[-1].text, [w for w in pos[:-1]]
                d = full(dest)
                if fresh(dest):
                    if dest.endswith("/") and not os.path.isdir(d):
                        fact = (f"{dest.rstrip('/')} {'is a file' if os.path.exists(d.rstrip('/')) else 'does not exist'}, "
                                f"so `{name} ... {dest}` fails")
                    elif len(srcs) > 1 and not os.path.isdir(d) and name != "ln":
                        fact = f"{dest} is not a folder, so `{name}` with several sources fails"
                    elif name == "ln" and os.path.lexists(d) and not os.path.isdir(d) and not any(
                            a.text.startswith("-") and "f" in a.text for a in args):
                        fact = f"{dest} already exists, so `ln` without -f fails"
                    else:
                        parent = d if os.path.isdir(d) else os.path.dirname(d)
                        if os.path.isdir(parent) and not os.access(parent, os.W_OK):
                            fact = f"{os.path.relpath(parent, cwd)}/ is read-only for you, so `{name}` into it fails"
                for w in srcs:
                    if not fresh(w.text) or fact or name == "ln":
                        continue
                    if w.glob:
                        if not _glob.glob(full(w.text)):
                            fact = f"{w.text} matches nothing here, so `{name}` fails"
                    elif not os.path.lexists(full(w.text)):
                        fact = f"{w.text} does not exist, so `{name}` fails"
            elif name in ("tar", "zip") and args:
                # the archive a step creates: its folder must exist and be writable
                arc = None
                if name == "zip":
                    arc = next((w for w in args if not w.text.startswith("-")), None)
                else:
                    flags = args[0].text if not args[0].text.startswith("--") else ""
                    for i, w in enumerate(args):
                        if w.text.startswith("-") and not w.text.startswith("--") and "f" in w.text and i + 1 < len(args):
                            arc = args[i + 1]
                            break
                    if arc is None and flags and "f" in flags.lstrip("-") and len(args) > 1:
                        arc = args[1]
                    if not any("c" in w.text.lstrip("-") for w in args[:1] + [a for a in args if a.text.startswith("-")
                                                                                and not a.text.startswith("--")]):
                        arc = None
                if arc is not None and not arc.dynamic and fresh(arc.text):
                    parent = os.path.dirname(full(arc.text))
                    if not os.path.isdir(parent):
                        what = "is a file" if os.path.exists(parent) else "does not exist"
                        fact = f"{os.path.relpath(parent, cwd)} {what}, so `{name}` cannot write {arc.text}"
                    elif not os.access(parent, os.W_OK):
                        fact = f"{os.path.relpath(parent, cwd)}/ is read-only for you, so `{name}` cannot write {arc.text}"
            elif name in ("rm", "touch") and pos:
                flags = "".join(a.text for a in args if a.text.startswith("-"))
                for w in pos:
                    if w.dynamic or not fresh(w.text):
                        continue
                    p = full(w.text)
                    if name == "rm" and "f" not in flags and not w.glob and not os.path.lexists(p):
                        fact = f"{w.text} does not exist, so `rm {w.text}` (without -f) fails"
                    parent = os.path.dirname(p)
                    if not fact and os.path.isdir(parent) and not os.access(parent, os.W_OK):
                        fact = f"{os.path.relpath(parent, cwd)}/ is read-only for you, so `{name} {w.text}` fails"
            for r in sc.redirects:
                if fact or r.target is None or r.op not in (">", ">>", ">|", "&>") or r.target.text in S.NOT_FILES:
                    continue
                p = full(r.target.text)
                parent = os.path.dirname(p)
                if fresh(r.target.text):
                    if not os.path.isdir(parent):
                        fact = f"{os.path.relpath(parent, cwd)} is not a folder, so writing {r.target.text} fails"
                    elif not os.access(parent, os.W_OK) and not (os.path.exists(p) and os.access(p, os.W_OK)):
                        fact = f"{os.path.relpath(parent, cwd)}/ is read-only for you, so writing {r.target.text} fails"
            if not fact and name and name not in SHELL_BUILTINS and os.sep not in name and not shutil.which(name):
                fact = f"`{name}` is not installed here (command not found), so that command fails"
            if fact and k not in fails:
                fails[k] = fact
                lines.append(fact)
            for w in args:
                if not w.dynamic:
                    named.add(full(w.text.rstrip("/")))
                    named.add(full(w.text))
            for r in sc.redirects:
                if r.target is not None:
                    named.add(full(r.target.text))
    return fails, lines


def _permissions(view, plan: Plan) -> list:
    root = os.path.realpath(plan.cwd)
    lines = []
    for r in sorted(view.touched):
        full = r if os.path.isabs(r) else os.path.join(root, r)
        for x in (full, os.path.dirname(full)):
            if os.path.exists(x) and not os.access(x, os.W_OK):
                rel = os.path.relpath(x, root)
                lines.append(f"{rel}{'/' if os.path.isdir(x) else ''} is read-only for you")
    return list(dict.fromkeys(lines))


def _shell_prompt(view, plan: Plan, facts: list) -> str:
    extra = []
    perms = _permissions(view, plan)
    if perms:
        extra.append("Permissions: " + "; ".join(perms) + ".")
    if facts:
        extra.append("Facts: " + "; ".join(facts) + ".")
    notes = S.shell_notes(view)
    if any("mkdir" in f or "/` fails" in f or "is a file" in f for f in facts):
        notes = notes + [NOTE_MKDIR_FILE]
    return P.world_state(view.rules, view.state + ("\n" + "\n".join(extra) if extra else ""), view.commands,
                         notes=notes or None, notes_label=S.NOTES_LABEL)


# ---------------------------------------------------------------- the model's path

def _model_sql(plan: Plan, client, rows: bool, numbers: bool):
    state_text, facts = sql_state(plan.db, plan.steps, rows=rows)
    rules = sql_rules(plan, facts)
    prompt = P.world_state(rules, state_text, [s.text for s in plan.steps])
    n = len(plan.steps)
    ans = client.ask(prompt, {f"f{k}": sql_fails(k) for k in range(1, n + 1)})
    p = [ans[f"f{k}"].p_yes for k in range(1, n + 1)]
    by_code, by_numbers, req = [], [], 1
    nums = _numbers_plan(plan, facts) if numbers and rows else None
    start = _start_values(facts, nums) if nums else None
    if start:
        exact = _exact_numbers(plan, nums, start)
        if exact is not None:
            for i, fails in exact.items():
                p[i] = 1.0 if fails else 0.0
                by_code.append(i + 1)
        else:
            tracked = _track_numbers(plan, nums, start, rules, state_text, client)
            if tracked:
                req += n
                for i, pf in tracked.items():
                    p[i] = pf
                    by_numbers.append(i + 1)
    return p, prompt, by_code, by_numbers, req


def _model_shell(plan: Plan, client, rows: bool, numbers: bool, where: str | None, walk: bool, inner_p: dict):
    n = len(plan.steps)
    fails, fact_lines = shell_facts(plan)
    texts = [s.text for s in plan.steps]
    view = S.inspect(texts, plan.cwd, shell=plan.shell, where=where)
    prompt = _shell_prompt(view, plan, fact_lines)
    qs = {"lost": S.SHELL_LOST, **{f"f{k}": S.shell_fails(k) for k in range(1, n + 1)}}
    ans = client.ask(prompt, qs)
    req = 1
    p = [ans[f"f{k}"].p_yes for k in range(1, n + 1)]
    p_lost = ans["lost"].p_yes

    def one(k):
        v = S.inspect(texts[:k], plan.cwd, shell=plan.shell, where=where)
        sub = Plan(plan.kind, plan.steps[:k], plan.cwd, plan.source, shell=plan.shell)
        return client.ask(_shell_prompt(v, sub, shell_facts(sub)[1]), {"f": S.shell_fails(k)})["f"].p_yes

    if walk and n > 1:
        with cf.ThreadPoolExecutor(min(8, n - 1)) as ex:
            w = [0.0] + list(ex.map(one, range(2, n + 1)))
        req += n - 1
        p = [max(a, b) for a, b in zip(p, w)]
    # sqlite3 calls inside the chain: judged as SQL with their database's state
    for k, s in enumerate(plan.steps, 1):
        if s.sql and s.db:
            sub = Plan("sql", s.sql, s.cwd or plan.cwd, "sqlite3", db=s.db, stop_on_error=s.bail)
            ps, _, codes, _, r2 = _model_sql(sub, client, rows, numbers)
            req += r2
            inner_p[k] = ps
            p[k - 1] = 1 - math.prod(1 - x for x in ps)
            if codes and any(ps[c - 1] >= 0.5 for c in codes):
                fails.setdefault(k, "a bounded number, checked in code")
    by_code = []
    for k, fact in fails.items():
        p[k - 1] = 1.0
        by_code.append(k)
    return p, prompt, sorted(by_code), [], req, p_lost


# ---------------------------------------------------------------- the check

def check_plan(plan: Plan, client: Ekbasis | None = None, fail_threshold: float = FAIL_THRESHOLD, rows: bool = True,
               numbers: bool = True, why: bool = True, fail_closed: bool = False, where: str | None = None,
               walk: bool | None = None, copy: bool = True, work: str | None = None) -> PreflightVerdict:
    """Judge the plan: on a copy when it can run there, otherwise by Ekbasis; then what the first failure would leave.
    walk: the step walk for scripts and chains (default: on for them, off for SQL). fail_closed: a plan with parts
    preflight does not follow is a warning (default: it is not)."""
    t0 = time.monotonic()
    n = len(plan.steps)
    if plan.unread:
        return PreflightVerdict(plan, [0.0] * n, 0.0, None, risky=fail_closed, cannot_judge=True,
                                reasons=["cannot judge: " + "; ".join(plan.unread)])
    if plan.kind == "sql" and plan.sqlite3_line and not sqlite_cli():
        return PreflightVerdict(plan, [0.0] * n, 0.0, None, by="code", copy_note=(
            "the sqlite3 command-line tool is not installed here, so the line fails before any statement runs and "
            "nothing is changed"))
    v = None
    inner_first, inner_p = {}, {}
    note = copy_eligible(plan) if copy else "runs on a copy are off"
    if note is None:
        try:
            r = run_on_copy(plan, work)
            k = r.get("first")
            inner_first["k"] = r.get("inner")
            p = [1.0 if i == k else 0.0 for i in range(1, n + 1)]
            v = PreflightVerdict(plan, p, 1.0 if k else 0.0, k, error=r.get("error") or None, by="copy",
                                 ms=r.get("ms", 0.0))
        except CannotJudge as e:
            note = str(e)
    if v is None:
        client = client or Ekbasis()
        if plan.kind == "sql":
            p, prompt, by_code, by_numbers, req = _model_sql(plan, client, rows, numbers)
            p_lost, why_q = None, sql_why
        else:
            if walk is None:
                walk = True
            p, prompt, by_code, by_numbers, req, p_lost = _model_shell(plan, client, rows, numbers, where, walk,
                                                                       inner_p)
            why_q = shell_why
        p_any = 1 - math.prod(1 - x for x in p)
        first = next((k for k, x in enumerate(p, 1) if x >= fail_threshold), None)
        if first is None and p_any >= fail_threshold:
            first = max(range(1, n + 1), key=lambda k: p[k - 1])
        v = PreflightVerdict(plan, p, p_any, first, by="model", by_code=by_code, by_numbers=by_numbers, p_lost=p_lost,
                             state=prompt, requests=req, copy_note=note or "")
    if v.first is not None:
        half, v.applied_before, v.runs_after, v.atomic = half_applied(plan, v.first)
        st = plan.steps[v.first - 1]
        if not half and plan.kind == "shell" and st.sql:
            # the failing step is a sqlite3 call: is the call itself left half applied?
            sub = Plan("sql", st.sql, st.cwd or plan.cwd, "sqlite3", db=st.db, stop_on_error=st.bail)
            k_in = inner_first.get("k")
            if k_in is None and v.by == "model":
                ps = inner_p.get(v.first) or []
                k_in = next((i for i, x in enumerate(ps, 1) if x >= fail_threshold), None)
            if k_in:
                h2, a2, r2, at2 = half_applied(sub, k_in)
                if h2:
                    half = True
                    v.reasons.append(f"inside step {v.first}, statement {k_in} fails and the call is left half applied")
        v.risky = half
        if v.risky and v.by == "model":
            if v.first in v.by_code:
                v.reason, v.reason_p = ("check", 1.0) if plan.kind == "sql" else (None, None)
            elif why:
                a = client.ask(v.state, {"why": why_q(v.first)})["why"]
                v.requests += 1
                v.reason, v.reason_p = str(a.value), a.confidence
        v.reasons.append(f"step {v.first} {'failed on a copy' if v.by == 'copy' else 'likely fails'}: "
                         f"{plan.steps[v.first - 1].text[:120]}")
    v.ms = v.ms or 1000 * (time.monotonic() - t0)
    return v


def check_line(line: str, cwd: str = ".", client: Ekbasis | None = None, **kw) -> PreflightVerdict | None:
    """Preflight for one shell command line (what the Claude Code hook sees). None when it is not a multi-step change."""
    try:
        plan = plan_line(line, cwd)
    except CannotJudge as e:
        plan = Plan("shell", [Step(text=line)], os.path.realpath(cwd), "the command line", unread=[str(e)])
        return PreflightVerdict(plan, [0.0], 0.0, None, risky=bool(kw.get("fail_closed")), cannot_judge=True)
    if plan is None:
        return None
    return check_plan(plan, client=client, **kw)


def check_sql(db: str, sql: str, client: Ekbasis | None = None, bail: bool = False, cwd: str = ".",
              **kw) -> PreflightVerdict:
    plan = _sql_plan(os.path.abspath(os.path.join(cwd, db)), sql, bail, [], os.path.realpath(cwd), f"sqlite3 on {db}")
    return check_plan(plan, client=client, **kw)


def check_script(path: str, cwd: str = ".", client: Ekbasis | None = None, **kw) -> PreflightVerdict:
    plan = plan_line(f"bash {path}", cwd)
    if plan is None:
        with open(os.path.join(cwd, path), errors="replace") as fh:
            lines, unread, errexit = script_lines(fh.read())
        steps, un2 = _shell_steps(lines, "", os.path.realpath(cwd), {}, {}, from_script=True)
        plan = Plan("shell", steps, os.path.realpath(cwd), f"the script {path}", stop_on_error=errexit,
                    unread=unread + un2, script=True)
    return check_plan(plan, client=client, **kw)
