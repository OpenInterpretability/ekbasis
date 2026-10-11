"""Migration guard (0.1.12): before a pull request is merged, will its PostgreSQL migrations lose data or fail?

The state is built from facts, never from the model's guesses:
- **Schema.** The migrations the base already has are applied, in order, to a throwaway database (EKBASIS_PG_URL or
  --pg-url: a scratch PostgreSQL server; a database `ekbasis_mg_*` is created there and dropped afterwards). The
  catalog of the tables a new migration names, and of the tables linked to them by foreign keys, is written as DDL.
- **Statistics** (optional, EKBASIS_DB_STATS_URL or --stats-url: a read-only replica). Only aggregates, from the
  planner's statistics: estimated rows per table (pg_class.reltuples), the fraction of NULLs and the number of distinct
  values per column (pg_stats.null_frac / n_distinct). No value is ever read (pg_stats' most common values are not
  queried). Without a replica, the state says that the tables hold production data, row counts unknown.
- **How the file runs.** Prisma Migrate, Diesel and golang-migrate run a migration file as one transaction on
  PostgreSQL (Diesel: unless run_in_transaction = false; Prisma and golang-migrate send the file as one multi-statement
  batch, which PostgreSQL runs as one implicit transaction): if any statement fails, nothing in the file is applied.
  The rules say so, unless --autocommit (statements commit one by one and the next runs after a failure, as `psql -f`
  does). In the study this guard comes from, the model read autocommit rules and, when a migration failed, still
  predicted that its destructive statement ran: 27 of its 61 false alarms on data loss.
- **Facts decided in code.** A new migration is first run on the schema alone (no rows). If it fails there, it fails
  in production too: that is stated as a fact and decides `fails`, with the database's error.

The questions are the ones of the pre-registered study (cookbook: studies/migrations): data lost, a statement fails,
left half applied (the last only under --autocommit; in one transaction a failure applies nothing). SQL comments are
removed from what the model reads (generators write warnings such as "All the data in the column will be lost" there).

Only `psql` is used to talk to PostgreSQL (the client stays standard library only): EKBASIS_PSQL or `psql` on PATH.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import time
import urllib.parse
from dataclasses import dataclass, field

from . import prompts as P
from ._version import __version__
from .client import CannotJudge, Ekbasis, _cache_dir

LOST_THRESHOLD = 0.5
FAIL_THRESHOLD = 0.5
MAX_TABLES = 8
MAX_CHARS = 60000           # the hosted API reads up to 32k tokens; a bigger state is "cannot foresee"
PSQL_TIMEOUT = 120
MARKER = "<!-- ekbasis-migration-guard -->"
VERDICT_TTL_S = 30 * 86400  # a cached verdict is reused for this long

DEFAULT_GLOBS = (
    "*migrations/*/migration.sql",      # Prisma
    "*migrations/*/up.sql",             # Diesel
    "*.up.sql",                         # golang-migrate, dbmate-style pairs, many others
    "*migrations/*.sql",                # a folder of plain SQL files
    "*migrate/*.sql",
)
SKIP = re.compile(r"(down\.sql$|\.(mysql|sqlite3?|cockroach|mssql)\.)", re.I)

TOOL_NAMES = {"prisma": "Prisma Migrate", "diesel": "Diesel", "golang-migrate": "golang-migrate",
              "generic": "the migration tool"}

RULES_TX = ("A PostgreSQL database used by a running application. The migration file runs as one transaction, as "
            "{tool} runs it: its statements run in order, and if any statement fails (an error or a constraint "
            "violation), the whole transaction is rolled back and nothing in the file is applied.")
RULES_AUTO = ("A PostgreSQL database used by a running application. The statements of one migration run in order, each "
              "in autocommit mode (each statement commits on its own; BEGIN opens a transaction that COMMIT ends); a "
              "statement that fails (an error or a constraint violation) changes nothing and the next one still runs.")

# The study's frozen questions (cookbook studies/migrations, statebuild.QUESTIONS), word for word.
Q_LOST = P.yes_no(
    "Does this migration permanently lose any data: a non-NULL value that is stored in some row before and afterwards "
    "is in no table at all (a deleted row, a dropped table or column whose values were not copied elsewhere, a value "
    "overwritten, or a value changed by a type conversion)? Values that were copied or moved to another column or "
    "table are not lost, and renaming a table or column loses nothing.")
Q_FAILS = P.yes_no("Does any statement of this migration fail (end with an error or a constraint violation) on this "
                   "database?")
Q_HALF = P.yes_no("Is this migration left half applied: some statement fails while the statements that do not fail "
                  "still change the schema or the data?")


# ---------------------------------------------------------------- SQL text

DOLLAR = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)?\$")


def split_sql(text: str) -> list:
    """PostgreSQL statements, comments outside string and dollar-quoted bodies removed (bodies are kept verbatim)."""
    out, buf, i, n = [], [], 0, len(text)
    while i < n:
        c = text[i]
        if c == "-" and text.startswith("--", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
            continue
        if c == "/" and text.startswith("/*", i):
            depth, j = 1, i + 2
            while j < n and depth:
                if text.startswith("/*", j):
                    depth, j = depth + 1, j + 2
                elif text.startswith("*/", j):
                    depth, j = depth - 1, j + 2
                else:
                    j += 1
            buf.append(" ")
            i = j
            continue
        if c == "'":
            esc = i > 0 and text[i - 1] in "eE" and (i < 2 or not (text[i - 2].isalnum() or text[i - 2] == "_"))
            j = i + 1
            while j < n:
                if esc and text[j] == "\\":
                    j += 2
                    continue
                if text[j] == "'":
                    if j + 1 < n and text[j + 1] == "'":
                        j += 2
                        continue
                    break
                j += 1
            buf.append(text[i:j + 1])
            i = j + 1
            continue
        if c == '"':
            j = text.find('"', i + 1)
            j = n - 1 if j < 0 else j
            buf.append(text[i:j + 1])
            i = j + 1
            continue
        if c == "$":
            m = DOLLAR.match(text, i)
            if m and not (i > 0 and (text[i - 1].isalnum() or text[i - 1] == "_")):
                tag = m.group(0)
                j = text.find(tag, m.end())
                j = n if j < 0 else j + len(tag)
                buf.append(text[i:j])
                i = j
                continue
        if c == ";":
            s = "".join(buf).strip()
            if s:
                out.append(s)
            buf = []
            i += 1
            continue
        buf.append(c)
        i += 1
    s = "".join(buf).strip()
    if s:
        out.append(s)
    return [re.sub(r"\n\s*\n+", "\n", s) for s in out]


# Statements that cannot run inside a transaction block, or a file that manages its own transaction. (ALTER TYPE ... ADD
# VALUE runs inside a transaction since PostgreSQL 12; only using the new value in the same transaction fails.)
NO_TX = re.compile(r"\b(CONCURRENTLY|VACUUM|ALTER\s+SYSTEM)\b|^\s*(BEGIN|COMMIT|START\s+TRANSACTION)\b", re.I | re.M)


# ---------------------------------------------------------------- finding the migrations

def tool_of(path: str) -> str:
    p = path.replace("\\", "/")
    if p.endswith("/migration.sql"):
        return "prisma"
    if p.endswith("/up.sql"):
        return "diesel"
    if p.endswith(".up.sql"):
        return "golang-migrate"
    return "generic"


def set_dir(path: str) -> str:
    """The folder whose files form one ordered sequence of migrations."""
    d = os.path.dirname(path.replace("\\", "/"))
    return os.path.dirname(d) if tool_of(path) in ("prisma", "diesel") else d


def is_migration(path: str, globs=DEFAULT_GLOBS) -> bool:
    p = path.replace("\\", "/")
    return p.endswith(".sql") and not SKIP.search(p) and any(fnmatch.fnmatch(p, g) for g in globs)


def _git(repo: str, *args: str) -> tuple[int, str]:
    try:
        r = subprocess.run(["git", *args], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                           errors="replace", timeout=60, env=dict(os.environ, LC_ALL="C", GIT_TERMINAL_PROMPT="0"))
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, str(e)
    return r.returncode, r.stdout if r.returncode == 0 else r.stderr


@dataclass
class Source:
    """Where migration files come from: a git ref, or the working tree (ref None)."""
    repo: str
    ref: str | None = None

    def list(self, folder: str) -> list:
        if self.ref is None:
            base = os.path.join(self.repo, folder)
            out = []
            for root, _, files in os.walk(base):
                out += [os.path.relpath(os.path.join(root, f), self.repo).replace(os.sep, "/") for f in files]
            return sorted(out)
        rc, out = _git(self.repo, "ls-tree", "-r", "--name-only", self.ref, "--", folder)
        return sorted(out.split()) if rc == 0 else []

    def read(self, path: str) -> str:
        if self.ref is None:
            with open(os.path.join(self.repo, path), encoding="utf-8", errors="replace") as f:
                return f.read()
        rc, out = _git(self.repo, "show", f"{self.ref}:{path}")
        if rc != 0:
            raise CannotJudge(f"cannot read {path} at {self.ref}")
        return out


def changed_files(repo: str, base: str, head: str = "HEAD") -> tuple[list, list]:
    """(added, modified) files between the merge base of base and head, and head."""
    rc, mb = _git(repo, "merge-base", base, head)
    if rc != 0:
        raise CannotJudge(f"cannot find the merge base of {base} and {head} (fetch the base branch, or check out "
                          f"with fetch-depth: 0)")
    rc, out = _git(repo, "diff", "--name-status", "--no-renames", mb.strip(), head)
    if rc != 0:
        raise CannotJudge(f"git diff failed: {out.strip()[:200]}")
    added, modified = [], []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) == 2:
            (added if parts[0] == "A" else modified if parts[0] == "M" else []).append(parts[1])
    return added, modified


# ---------------------------------------------------------------- PostgreSQL through psql

def psql_bin() -> str | None:
    return os.environ.get("EKBASIS_PSQL") or shutil.which("psql")


def scratch_psql() -> str | None:
    """psql for the scratch server: EKBASIS_SCRATCH_PSQL (the Action points it at `docker exec` into a container with
    no network), else the same psql as everything else."""
    return os.environ.get("EKBASIS_SCRATCH_PSQL") or psql_bin()


def with_db(url: str, db: str, user: str | None = None, password: str | None = None) -> str:
    u = urllib.parse.urlsplit(url)
    netloc = u.netloc
    if user:
        host = netloc.rsplit("@", 1)[-1]
        netloc = urllib.parse.quote(user) + (":" + urllib.parse.quote(password) if password else "") + "@" + host
    return urllib.parse.urlunsplit((u.scheme, netloc, "/" + db, u.query, u.fragment))


def redact(text: str, *urls) -> str:
    for u in urls:
        if u:
            text = text.replace(u, "<url>")
            pw = urllib.parse.urlsplit(u).password
            if pw:
                text = text.replace(pw, "***")
    return text


class Pg:
    def __init__(self, url: str, psql: str | None = None):
        self.url = url
        self.psql = psql or psql_bin()
        self.last_sqlstate = None
        if not self.psql:
            raise CannotJudge("psql is not installed (set EKBASIS_PSQL or put psql on PATH)")

    def run(self, args: list, stdin: str | None = None, timeout: float = PSQL_TIMEOUT) -> tuple[int, str, str]:
        env = dict(os.environ, PGCONNECT_TIMEOUT="10", PGAPPNAME="ekbasis-migration-guard", LC_ALL="C")
        try:
            r = subprocess.run([self.psql, "-X", "-q", "-d", self.url, *args], input=stdin, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, errors="replace", timeout=timeout, env=env)
        except subprocess.TimeoutExpired:
            return 124, "", "timed out"
        except OSError as e:
            return 127, "", str(e)
        return r.returncode, r.stdout, redact(r.stderr, self.url)

    def json(self, query: str):
        rc, out, err = self.run(["-A", "-t", "-v", "ON_ERROR_STOP=1", "-c", query])
        if rc != 0:
            raise CannotJudge(f"PostgreSQL: {err.strip()[:300]}")
        out = out.strip()
        return json.loads(out) if out else None

    def apply(self, sql: str, transaction: bool = True) -> str | None:
        """Run a migration file; the first error (None when it ran), its SQLSTATE in last_sqlstate. transaction: one
        transaction, stop at the error."""
        args = ["-v", "VERBOSITY=verbose"] + (["-v", "ON_ERROR_STOP=1", "--single-transaction"] if transaction else [])
        rc, _, err = self.run(args + ["-f", "-"], stdin=sql)
        code, msg = _first_error(err)
        self.last_sqlstate = code
        if transaction:
            return None if rc == 0 else (msg or f"psql exit {rc}")
        return msg


def _first_error(err: str) -> tuple:
    for line in err.splitlines():
        m = re.search(r"ERROR:\s*(?:([0-9A-Z]{5}):\s*)?(.*)", line)
        if m:
            return m.group(1), m.group(2).strip()[:300]
    return None, None


# Errors that mean the migration needs privileges the guard never grants: it is not run as a superuser.
PRIVILEGE = re.compile(r"permission denied|must be (superuser|owner|a member)|only superusers?|privileges of "
                       r"pg_(execute_server_program|read_server_files|write_server_files)", re.I)


def needs_privilege(sqlstate: str | None, msg: str | None) -> bool:
    return sqlstate in ("42501",) or bool(msg and PRIVILEGE.search(msg))


class Scratch:
    """A throwaway database on the scratch server, created on enter and dropped on exit with its role.

    The migrations (the base's and the pull request's) run as a role made for this check alone: LOGIN, not a superuser,
    no CREATEDB, CREATEROLE, REPLICATION or BYPASSRLS, owner of the throwaway database and nothing else. The admin
    connection (EKBASIS_PG_URL) only creates and drops the database and the role. So `COPY ... TO PROGRAM`, untrusted
    languages, `pg_read_file` and the like fail with "permission denied" instead of running on the server; such a
    migration is reported as "cannot foresee", never run with more privileges."""

    def __init__(self, admin_url: str, psql: str | None = None):
        self.admin = Pg(admin_url, psql or scratch_psql())
        tag = secrets.token_hex(5)
        self.name = "ekbasis_mg_" + tag
        self.role = "ekbasis_mg_" + tag
        self.password = secrets.token_hex(16)
        self.db = None

    def _url(self, db: str) -> str:
        return with_db(self.admin.url, db, self.role, self.password)

    def __enter__(self):
        rc, _, err = self.admin.run(["-v", "ON_ERROR_STOP=1",
                                     "-c", f'CREATE ROLE "{self.role}" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE '
                                           f"NOREPLICATION NOBYPASSRLS PASSWORD '{self.password}'",
                                     "-c", f'CREATE DATABASE "{self.name}" OWNER "{self.role}"'])
        if rc != 0:
            self.__exit__()
            raise CannotJudge(f"cannot create a scratch database: {redact(err, self.password).strip()[:300]}")
        self.db = Pg(self._url(self.name), self.admin.psql)
        return self

    def clone(self) -> "Pg":
        name = self.name + "_" + secrets.token_hex(3)
        rc, _, err = self.admin.run(["-v", "ON_ERROR_STOP=1", "-c",
                                     f'CREATE DATABASE "{name}" TEMPLATE "{self.name}" OWNER "{self.role}"'])
        if rc != 0:
            raise CannotJudge(f"cannot copy the scratch database: {err.strip()[:300]}")
        return Pg(self._url(name), self.admin.psql)

    def drop(self, pg: "Pg"):
        name = urllib.parse.urlsplit(pg.url).path.lstrip("/")
        self.admin.run(["-c", f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'])

    def __exit__(self, *exc):
        if self.db:
            self.drop(self.db)
        self.admin.run(["-c", f'DROP DATABASE IF EXISTS "{self.name}" WITH (FORCE)',
                        "-c", f'DROP ROLE IF EXISTS "{self.role}"'])


CATALOG = r"""
SELECT json_build_object(
 'tables', COALESCE((SELECT json_agg(json_build_object(
    'oid', c.oid, 'schema', n.nspname, 'name', c.relname,
    'cols', (SELECT json_agg(json_build_object('name', a.attname, 'type', format_type(a.atttypid, a.atttypmod),
              'notnull', a.attnotnull, 'default', pg_get_expr(d.adbin, d.adrelid), 'generated', a.attgenerated <> '',
              'typname', t.typname) ORDER BY a.attnum)
             FROM pg_attribute a JOIN pg_type t ON t.oid = a.atttypid
             LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
             WHERE a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped),
    'cons', (SELECT json_agg(json_build_object('name', k.conname, 'type', k.contype, 'ref', k.confrelid,
              'def', pg_get_constraintdef(k.oid)) ORDER BY k.conname) FROM pg_constraint k WHERE k.conrelid = c.oid),
    'idx', (SELECT json_agg(pg_get_indexdef(i.indexrelid) ORDER BY pg_get_indexdef(i.indexrelid)) FROM pg_index i
            WHERE i.indrelid = c.oid AND NOT i.indisprimary
              AND NOT EXISTS (SELECT 1 FROM pg_constraint k WHERE k.conindid = i.indexrelid))
  ) ORDER BY n.nspname, c.relname)
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE c.relkind IN ('r', 'p') AND NOT c.relispartition
    AND n.nspname NOT IN ('pg_catalog', 'information_schema') AND n.nspname NOT LIKE 'pg_%'), '[]'::json),
 'enums', COALESCE((SELECT json_object_agg(t.typname, (SELECT json_agg(e.enumlabel ORDER BY e.enumsortorder)
            FROM pg_enum e WHERE e.enumtypid = t.oid) ORDER BY t.typname)
   FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
   WHERE t.typtype = 'e' AND n.nspname NOT IN ('pg_catalog', 'information_schema')), '{}'::json))
"""

STATS = r"""
SELECT json_build_object(
 'rows', COALESCE((SELECT json_object_agg(n.nspname || '.' || c.relname, c.reltuples)
   FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE c.relkind IN ('r', 'p') AND n.nspname NOT IN ('pg_catalog', 'information_schema')
     AND n.nspname NOT LIKE 'pg_%'), '{}'::json),
 'cols', COALESCE((SELECT json_object_agg(s.schemaname || '.' || s.tablename || '.' || s.attname,
            json_build_array(s.null_frac, s.n_distinct))
   FROM pg_stats s WHERE s.schemaname NOT IN ('pg_catalog', 'information_schema')), '{}'::json))
"""


def read_stats(url: str, psql: str | None = None) -> dict:
    """Aggregates only (planner statistics): {'rows': {schema.table: estimate}, 'cols': {schema.table.col: [null_frac,
    n_distinct]}}. Never a value."""
    return Pg(url, psql).json(STATS) or {"rows": {}, "cols": {}}


# ---------------------------------------------------------------- the state

def disp(t: dict) -> str:
    return t["name"] if t["schema"] == "public" else f"{t['schema']}.{t['name']}"


def named_tables(text: str, tables: list) -> list:
    return [t for t in tables if re.search(r"(?<![\w$])[\"'`]?" + re.escape(t["name"]) + r"[\"'`]?(?![\w$])", text, re.I)]


def ddl(t: dict) -> str:
    lines = []
    for c in t["cols"] or []:
        d = f"  {c['name']} {c['type']}"
        if c["notnull"]:
            d += " NOT NULL"
        if c["default"]:
            d += f" DEFAULT {c['default']}"
        if c["generated"]:
            d += " (generated)"
        lines.append(d)
    for k in t["cons"] or []:
        if k["type"] in ("p", "u", "c", "f", "x"):
            lines.append(f"  CONSTRAINT {k['name']} {k['def']}")
    out = f"CREATE TABLE {disp(t)} (\n" + ",\n".join(lines) + "\n);"
    if t.get("idx"):
        out += "\n" + "\n".join(i + ";" for i in t["idx"])
    return out


def _count(x: float) -> str:
    return f"{int(round(x)):,}"


def table_facts(t: dict, stats: dict | None) -> str:
    key = f"{t['schema']}.{t['name']}"
    if not stats:
        return f"{disp(t)}: holds production data (row count unknown)"
    n = (stats.get("rows") or {}).get(key)
    if n is None or n < 0:
        head = f"{disp(t)}: row count unknown (never analyzed)"
    else:
        head = f"{disp(t)}: about {_count(n)} rows" if n else f"{disp(t)}: empty (0 rows)"
    facts = []
    for c in t["cols"] or []:
        s = (stats.get("cols") or {}).get(f"{key}.{c['name']}")
        if not s:
            continue
        nf, nd = s
        f = []
        if nf and nf > 0:
            f.append(f"about {nf * 100:.0f}% NULL" if nf >= 0.005 else "a few NULL")
        if nd is not None and nd != 0 and n:
            dist = -nd * n if nd < 0 else nd
            if nd == -1:
                f.append("all values distinct")
            elif dist <= 10:
                f.append(f"about {max(1, round(dist))} distinct value{'s' if round(dist) != 1 else ''}")
        if f:
            facts.append(f"{c['name']}: " + ", ".join(f))
    return head + ("; facts: " + "; ".join(facts) if facts else "")


def build_state(catalog: dict, stmts: list, stats: dict | None, tool: str, transaction: bool,
                facts: list | None = None) -> tuple[str, list]:
    """(the prompt in the world layout, the tables shown). facts: lines decided in code (shown before the rows)."""
    tables = catalog.get("tables") or []
    byoid = {t["oid"]: t for t in tables}
    text = "\n".join(stmts)
    named = named_tables(text, tables)
    partners = []
    for t in tables:
        for k in t["cons"] or []:
            if k["type"] != "f" or k["ref"] not in byoid:
                continue
            if t in named and byoid[k["ref"]] not in named:
                partners.append(byoid[k["ref"]])
            if byoid[k["ref"]] in named and t not in named:
                partners.append(t)
    shown = []
    for t in named + partners:
        if t not in shown:
            shown.append(t)
    shown = shown[:MAX_TABLES]
    used = {c["typname"].lstrip("_") for t in shown for c in t["cols"] or []}
    enums = [f"{e}: " + ", ".join("'" + v + "'" for v in labels) for e, labels in (catalog.get("enums") or {}).items()
             if e in used or re.search(r"(?<![\w$])\"?" + re.escape(e) + r"\"?(?![\w$])", text)]
    parts = ["Schema (the tables the migration names, and the tables linked to them by foreign keys):"]
    parts += [ddl(t) for t in shown] or ["(none of the tables it names exists yet)"]
    if enums:
        parts.append("Enum types: " + "; ".join(enums))
    parts += ["", "Rows:"] + [table_facts(t, stats) for t in shown]
    others = [disp(t) for t in tables if t not in shown]
    if others:
        parts.append("Other tables: " + ", ".join(others[:40]) + (", ..." if len(others) > 40 else ""))
    if facts:
        parts += ["", "Facts: " + " ".join(facts)]
    rules = RULES_TX.format(tool=TOOL_NAMES.get(tool, TOOL_NAMES["generic"])) if transaction else RULES_AUTO
    return P.world_state(rules, "\n".join(parts), stmts), [disp(t) for t in shown]


# ---------------------------------------------------------------- the check

@dataclass
class FileVerdict:
    path: str
    tool: str
    transaction: bool
    statements: int = 0
    p_lost: float | None = None
    p_fail: float | None = None
    p_half: float | None = None
    schema_error: str | None = None     # the migration fails on the schema alone (decided in code)
    risky: bool = False
    cannot_judge: str | None = None
    notes: list = field(default_factory=list)
    state: str = ""
    shown: list = field(default_factory=list)
    lost_threshold: float = LOST_THRESHOLD
    fail_threshold: float = FAIL_THRESHOLD
    cached: bool = False                # the answers came from the verdict cache (no model call)

    @property
    def kind(self) -> str:
        """Why it is risky, decided in code from the two answers (0.1.12): cannot_foresee, schema (fails on the base's
        schema before any data: the pull request's own error), fails (may fail on existing data), loses, or ok."""
        if self.cannot_judge:
            return "cannot_foresee"
        if self.schema_error:
            return "schema"
        if self.p_fail is not None and self.p_fail >= self.fail_threshold:
            return "fails"
        if self.p_lost is not None and self.p_lost >= self.lost_threshold:
            return "loses"
        return "ok"

    @property
    def reason(self) -> str:
        k = self.kind
        if k == "cannot_foresee":
            return self.cannot_judge
        if k == "schema":
            return (f"fails on the base branch's schema before touching any data: {self.schema_error} (an error in "
                    "the pull request itself, e.g. it depends on a migration missing from the base, or a typo)")
        lose = self.p_lost is not None and self.p_lost >= self.lost_threshold
        if k == "fails":
            if self.transaction:
                out = f"may fail on existing data ({self.p_fail:.0%}); nothing in the file would be applied"
                return out + (f"; if it ran, it would also lose data ({self.p_lost:.0%})" if lose else "")
            out = f"may fail on existing data ({self.p_fail:.0%}); the statements that do not fail stay applied"
            return out + (f"; may lose existing data ({self.p_lost:.0%})" if lose else "")
        if k == "loses":
            return f"may lose existing data ({self.p_lost:.0%})"
        return f"no data loss or failure foreseen (lose {self.p_lost:.0%}, fail {self.p_fail:.0%})"

    def as_json(self, state: bool = False) -> dict:
        d = {"path": self.path, "tool": self.tool, "transaction": self.transaction, "statements": self.statements,
             "risky": self.risky, "p_lost": self.p_lost, "p_fail": self.p_fail, "p_half": self.p_half,
             "schema_error": self.schema_error, "cannot_judge": self.cannot_judge, "cannot_foresee": self.cannot_judge,
             "reason": self.reason, "kind": self.kind, "notes": self.notes, "tables": self.shown,
             "cached": self.cached}
        if state:
            d["state"] = self.state
        return d


@dataclass
class GuardVerdict:
    files: list
    notes: list = field(default_factory=list)

    @property
    def risky(self) -> bool:
        return any(f.risky for f in self.files)

    @property
    def cannot_judge(self) -> bool:
        return any(f.cannot_judge for f in self.files)

    def summary(self) -> str:
        if not self.files:
            return "Ekbasis migration guard: no new migration files" + ("\n  " + "\n  ".join(self.notes) if self.notes else "")
        head = ("RISKY" if self.risky else "CANNOT FORESEE" if self.cannot_judge else "no risk found")
        lines = [f"Ekbasis migration guard: {head}"]
        for f in self.files:
            tag = "CANNOT FORESEE" if f.cannot_judge else "RISKY" if f.risky else "ok"
            lines.append(f"  {tag:<14} {f.path}: {f.reason}")
            lines += [f"                 note: {n}" for n in f.notes]
        lines += [f"  note: {n}" for n in self.notes]
        return "\n".join(lines)

    def as_json(self, state: bool = False) -> dict:
        return {"risky": self.risky, "cannot_judge": self.cannot_judge, "cannot_foresee": self.cannot_judge,
                "files": [f.as_json(state) for f in self.files], "notes": self.notes}


def _transaction_for(tool: str, stmts: list, autocommit: bool, notes: list) -> bool:
    if autocommit:
        return False
    hit = next((s for s in stmts if NO_TX.search(s)), None)
    if hit:
        notes.append("contains a statement that cannot run inside a transaction or manages its own transaction "
                     f"({hit.split()[0].upper()} ...): checked with autocommit rules")
        return False
    return True


def check(repo: str = ".", base: str | None = None, head: str = "HEAD", files: list | None = None,
          globs=DEFAULT_GLOBS, pg_url: str | None = None, stats_url: str | None = None, autocommit: bool = False,
          client: Ekbasis | None = None, lost_threshold: float = LOST_THRESHOLD,
          fail_threshold: float = FAIL_THRESHOLD, psql: str | None = None,
          cache: VerdictCache | None = None) -> GuardVerdict:
    """Check the new migrations of a change. With base: the files added between the merge base and head (the base's
    own migrations build the schema). With files: those files, and the schema is built from the files that sort before
    them in the same folder of the working tree."""
    pg_url = pg_url or os.environ.get("EKBASIS_PG_URL")
    stats_url = stats_url or os.environ.get("EKBASIS_DB_STATS_URL") or None
    notes = []
    if files:
        new = [f.replace("\\", "/") for f in files]
        src_new = src_base = Source(repo, None)
    else:
        if not base:
            raise ValueError("give --base REF or the migration files")
        added, modified = changed_files(repo, base, head)
        new = [f for f in added if is_migration(f, globs)]
        edited = [f for f in modified if is_migration(f, globs)]
        if edited:
            notes.append("edits migrations that already exist on the base (" + ", ".join(edited[:5]) + "): a database "
                         "that already applied them will not run the change, and tools that checksum migrations "
                         "(Prisma, golang-migrate's dirty flag) may refuse to deploy")
        src_new, src_base = Source(repo, head), Source(repo, base)
    if not new:
        return GuardVerdict([], notes)
    if not pg_url:
        return GuardVerdict([FileVerdict(f, tool_of(f), not autocommit, cannot_judge="no scratch PostgreSQL to build "
                             "the schema (set EKBASIS_PG_URL or --pg-url)") for f in new], notes)
    client = client or Ekbasis()
    cache = cache or VerdictCache()
    stats = None
    if stats_url:
        try:
            stats = read_stats(stats_url, psql)
        except CannotJudge as e:
            notes.append(f"statistics replica not read ({redact(str(e), stats_url)}); row counts unknown")
    out = []
    by_set = {}
    for f in new:
        by_set.setdefault(set_dir(f), []).append(f)
    for folder, fs in by_set.items():
        fs.sort()
        tool = tool_of(fs[0])
        try:
            scratch = Scratch(pg_url, psql)
            with scratch:
                # the schema: every migration of this folder on the base that sorts before the first new file
                prior = [p for p in (src_base.list(folder)) if is_migration(p, globs) and tool_of(p) == tool
                         and set_dir(p) == folder and p not in fs and (files is None or p < fs[0])]
                base_err, priv = [], False
                for p in prior:
                    e = scratch.db.apply(src_base.read(p), transaction=True)
                    if e:
                        e2 = scratch.db.apply(src_base.read(p), transaction=False)
                        if e2:
                            base_err.append(f"{p}: {e2}")
                            priv = priv or needs_privilege(scratch.db.last_sqlstate, e2)
                if base_err:
                    notes.append(f"{len(base_err)} earlier migration(s) in {folder} did not apply cleanly on the "
                                 f"scratch server (first: {base_err[0][:160]}); the schema may be incomplete" +
                                 ("; the guard runs migrations without superuser privileges" if priv else ""))
                for f in fs:
                    out.append(_check_file(f, tool, src_new.read(f), scratch, stats, autocommit, client,
                                           lost_threshold, fail_threshold, bool(base_err), cache))
                    scratch.db.apply(src_new.read(f), transaction=True)   # the next file sees this one applied
        except CannotJudge as e:
            for f in fs:
                if not any(v.path == f for v in out):
                    out.append(FileVerdict(f, tool, not autocommit, cannot_judge=redact(str(e), pg_url, stats_url)))
    return GuardVerdict(out, notes)


def _check_file(path, tool, text, scratch, stats, autocommit, client, lt, ft, base_dirty, cache=None) -> FileVerdict:
    stmts = split_sql(text)
    fnotes = []
    tx = _transaction_for(tool, stmts, autocommit, fnotes)
    v = FileVerdict(path, tool, tx, statements=len(stmts), notes=fnotes, lost_threshold=lt, fail_threshold=ft)
    if not stmts:
        v.p_lost = v.p_fail = 0.0
        v.notes.append("no SQL statements")
        return v
    probe = scratch.clone()
    try:
        v.schema_error = probe.apply(text, transaction=tx)
        sqlstate = probe.last_sqlstate
    finally:
        scratch.drop(probe)
    if v.schema_error and needs_privilege(sqlstate, v.schema_error):
        v.cannot_judge = ("it needs privileges the guard never grants (migrations run as a role that is not a superuser, "
                          f"so it was not run): {v.schema_error}. Migrations that need a superuser are not run by the "
                          "guard: review this one by hand")
        v.schema_error = None
        return v
    if v.schema_error and base_dirty:
        v.cannot_judge = f"it fails on the scratch schema, which may be incomplete ({v.schema_error})"
        v.schema_error = None
        return v
    if v.schema_error and tx:       # decided in code: it fails, and one transaction that fails applies nothing
        v.p_lost, v.p_fail, v.risky = 0.0, 1.0, True
        return v
    catalog = scratch.db.json(CATALOG) or {}
    facts = []
    if v.schema_error:
        facts.append(f"Run on this schema with no rows, the migration fails: {v.schema_error}.")
    v.state, v.shown = build_state(catalog, stmts, stats, tool, tx, facts)
    if len(v.state) > MAX_CHARS:
        v.cannot_judge = f"the migration and its schema are too long to read ({len(v.state):,} characters)"
        return v
    qs = {"lost": Q_LOST, "fails": Q_FAILS}
    if not tx:
        qs["half"] = Q_HALF
    key = VerdictCache.key(text, catalog, tx, stats is not None, v.state, qs, getattr(client, "url", ""))
    probs = cache.get(key) if cache else None
    if probs is not None and set(probs) == set(qs):
        v.cached = True
        v.notes.append("same migration, schema and rules as an earlier check: its answer was reused (no model call)")
    else:
        ans = client.ask(v.state, qs)
        probs = {k: ans[k].p_yes for k in qs}
        if cache:
            cache.put(key, probs)
    v.p_lost, v.p_fail = probs["lost"], probs["fails"]
    v.p_half = probs.get("half")
    if v.schema_error:
        v.p_fail = 1.0
    v.risky = bool(v.schema_error) or v.p_lost >= lt or v.p_fail >= ft
    return v


# ---------------------------------------------------------------- verdict cache

class VerdictCache:
    """The model's answers for a migration, reused when nothing they depend on changed: no model call, no quota.

    The key is sha256 over the migration file's text, a hash of the whole scratch schema it runs on, the client
    version, the transaction mode, whether replica statistics were used, the exact state and questions the model would
    read (so new statistics values miss too), and the server URL. Any change to one of them is a miss. Only the
    probabilities are kept (the verdict is decided again with the current thresholds), one JSON file per key, for
    VERDICT_TTL_S (30 days).

    Where: EKBASIS_VERDICT_CACHE (a folder; "off" disables it), else <EKBASIS_CACHE_DIR or ~/.cache/ekbasis>/verdicts.
    Best effort: a cache that cannot be read or written is a miss, never an error."""

    def __init__(self, folder=None, now=time.time, off: bool = False):
        env = os.environ.get("EKBASIS_VERDICT_CACHE", "")
        self.off = off or (folder is None and env.strip().lower() in ("off", "0", "false", "no"))
        self.dir = folder or (env if env and not self.off else str(_cache_dir() / "verdicts"))
        self.now = now

    @staticmethod
    def schema_hash(catalog) -> str:
        """The whole scratch schema, without the table oids (they differ in every scratch database): foreign keys
        point to the referenced table's name instead."""
        catalog = catalog or {}
        names = {t.get("oid"): f'{t.get("schema")}.{t.get("name")}' for t in catalog.get("tables") or []}
        tables = []
        for t in catalog.get("tables") or []:
            t = {k: v for k, v in t.items() if k != "oid"}
            t["cons"] = [dict(c, ref=names.get(c.get("ref"), None) if c.get("ref") else None)
                         for c in (t.get("cons") or [])]
            tables.append(t)
        norm = {"tables": tables, "enums": catalog.get("enums") or {}}
        return hashlib.sha256(json.dumps(norm, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    @staticmethod
    def key(text: str, catalog, transaction: bool, stats: bool, state: str, questions: dict, url: str) -> str:
        schema = VerdictCache.schema_hash(catalog)
        parts = {"v": __version__, "file": hashlib.sha256(text.encode()).hexdigest(), "schema": schema,
                 "tx": bool(transaction), "stats": bool(stats), "url": (url or "").rstrip("/"),
                 "state": hashlib.sha256(state.encode()).hexdigest(),
                 "q": hashlib.sha256(json.dumps(questions, sort_keys=True).encode()).hexdigest()}
        return hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()

    def _path(self, key: str) -> str:
        return os.path.join(self.dir, f"{key}.json")

    def get(self, key: str) -> dict | None:
        if self.off:
            return None
        try:
            with open(self._path(key)) as fh:
                d = json.load(fh)
            if self.now() - float(d["t"]) > VERDICT_TTL_S:
                os.remove(self._path(key))
                return None
            p = d["p"]
            if not all(isinstance(x, (int, float)) and 0 <= x <= 1 for x in p.values()):
                return None
            return p
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            return None

    def put(self, key: str, probs: dict) -> None:
        if self.off:
            return
        try:
            os.makedirs(self.dir, exist_ok=True)
            tmp = self._path(key) + f".{secrets.token_hex(4)}.tmp"
            with open(tmp, "w") as fh:
                json.dump({"t": int(self.now()), "p": probs}, fh)
            os.replace(tmp, self._path(key))
        except OSError:
            pass


# ---------------------------------------------------------------- the pull request comment

ZW = "\u200b"   # zero-width space: breaks @mentions and autolinks without changing what a reader sees
MD_SPECIAL = re.compile(r"([\\`*_{}\[\]()#!|~>])")


def md_safe(text, limit: int = 300) -> str:
    """Untrusted text (a path or an error from the pull request) made inert in a GitHub comment: cut to `limit`
    characters, HTML-escaped, markdown characters escaped, @mentions and links broken, on one line."""
    t = " ".join(str(text or "").split())
    if len(t) > limit:
        t = t[:limit - 1] + "…"
    t = t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    t = MD_SPECIAL.sub(r"\\\1", t)
    t = re.sub(r"@(?=\w)", "@" + ZW, t)
    t = re.sub(r"(?i)\b(https?|ftp|file)(:)(?=//)|\b(javascript|data|mailto)(:)(?=\S)",
               lambda m: (m.group(1) or m.group(3)) + ZW + (m.group(2) or m.group(4)), t)
    t = re.sub(r"(?i)\bwww\.", "www" + ZW + ".", t)
    return t


def comment(result: dict) -> str:
    """Markdown for the PR comment (one comment, updated in place: it starts with MARKER). Paths, probabilities and
    reasons only: the guard never reads data values, and nothing here comes from the environment."""
    files = result.get("files") or []
    if result.get("risky") and files:
        head = "**Risky:** at least one migration may lose data or fail on the existing database."
    elif result.get("cannot_judge"):
        head = "**Cannot foresee** the migrations of this pull request: treat them as risky and check them yourself."
    elif not files:
        head = "No new migration files in this pull request."
    else:
        head = "No data loss or failure foreseen."
    lines = [MARKER, "### Ekbasis migration guard", "", head, ""]
    if files:
        lines += ["| Migration | Verdict | Why |", "|---|---|---|"]
        for f in files:
            tag = "cannot foresee" if f.get("cannot_judge") else "**risky**" if f.get("risky") else "ok"
            why = md_safe(f.get("reason"), 400)
            mode = "one transaction" if f.get("transaction") else "autocommit"
            tool = f.get("tool") if f.get("tool") in TOOL_NAMES else "generic"
            lines.append(f"| {md_safe(f.get('path'), 200)} ({tool}, {mode}) | {tag} | {why} |")
        lines.append("")
    for n in (result.get("notes") or [])[:10]:
        lines.append(f"- {md_safe(n, 400)}")
    for f in files:
        for n in (f.get("notes") or [])[:5]:
            lines.append(f"- {md_safe(f.get('path'), 200)}: {md_safe(n, 400)}")
    lines += ["", "<sub>Ekbasis foresees from the schema (built from the base branch's migrations) and, when configured, "
              "aggregate statistics of a read-only replica; it never reads data values. [About](https://github.com/"
              f"OpenInterpretability/ekbasis/blob/v{__version__}/docs/MIGRATION_GUARD.md)</sub>"]
    return "\n".join(lines)


def main(argv=None) -> int:
    """`python -m ekbasis.migrations comment RESULT.json`: print the PR comment for a migrate-check --json result."""
    import sys
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) >= 2 and argv[0] == "comment":
        with open(argv[1]) as fh:
            raw = fh.read().strip()
        try:
            result = json.loads(raw.splitlines()[-1]) if raw else {}
        except ValueError:
            result = {"files": [], "cannot_judge": True, "notes": ["the guard printed no result"]}
        if "files" not in result:   # "cannot foresee" before any file was checked
            result = {"files": [], "cannot_judge": True, "notes": [result.get("cannot_foresee") or "no result"]}
        print(comment(result))
        return 0
    print("usage: python -m ekbasis.migrations comment RESULT.json", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
