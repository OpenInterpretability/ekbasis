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
from .probes import probe_facts

LOST_THRESHOLD = 0.5
FAIL_THRESHOLD = 0.5
MAX_TABLES = 8
MAX_CHARS = 200000          # ~64k tokens (q99 0.31 token/char): the length up to which a pre-registered test found
                            # no loss in verdict accuracy (11 Oct 2026); above it, "cannot foresee"
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
              "generic": "the migration tool", "django": "Django", "alembic": "Alembic", "rails": "Rails"}

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
# BEGIN/COMMIT count only as a statement of their own, and nothing inside a dollar-quoted body or a string counts
# (a PL/pgSQL body starts with BEGIN).
NO_TX = re.compile(r"\b(CONCURRENTLY|VACUUM|ALTER\s+SYSTEM)\b|\A\s*(BEGIN|COMMIT|END|START\s+TRANSACTION)\b", re.I)
GOOSE_MARK = re.compile(r"^[ \t]*--[ \t]*\+goose[ \t]+(Up|Down)\b.*$", re.I | re.M)
GOOSE_NO_TX = re.compile(r"^[ \t]*--[ \t]*\+goose[ \t]+NO[ \t]+TRANSACTION\b", re.I | re.M)


def outside_bodies(stmt: str) -> str:
    """The statement with dollar-quoted bodies and string literals replaced by empty ones."""
    out, i = [], 0
    while True:
        m = DOLLAR.search(stmt, i)
        if not m:
            out.append(stmt[i:])
            break
        j = stmt.find(m.group(0), m.end())
        out.append(stmt[i:m.start()] + " $$ ")
        if j < 0:
            break
        i = j + len(m.group(0))
    return re.sub(r"'(?:[^']|'')*'", "''", "".join(out))


def goose_up(text: str) -> str:
    """For a goose file (-- +goose Up / Down), only what runs on the way up: the header and the Up sections. Other
    files are returned as they are."""
    marks = list(GOOSE_MARK.finditer(text))
    if not marks:
        return text
    out = [text[:marks[0].start()]]
    for k, m in enumerate(marks):
        if m.group(1).lower() == "up":
            out.append(text[m.start():marks[k + 1].start() if k + 1 < len(marks) else len(text)])
    return "".join(out)


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
                return goose_up(f.read())
        rc, out = _git(self.repo, "show", f"{self.ref}:{path}")
        if rc != 0:
            raise CannotJudge(f"cannot read {path} at {self.ref}")
        return goose_up(out)


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

    def __init__(self, admin_url: str, psql: str | None = None, setup: str | None = None):
        self.admin = Pg(admin_url, psql or scratch_psql())
        self.setup = setup or None          # setup SQL, run by the admin connection before any migration (setup-sql)
        self.setup_hash = hashlib.sha256(setup.encode()).hexdigest() if setup else None
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
        if self.setup:
            # The setup SQL is trusted (it comes from the base branch, never from the pull request) and runs with the
            # admin connection's privileges in the throwaway database: schemas, extensions, roles the migrations need.
            # :guard_role names the role the migrations run as, for GRANTs.
            admin_db = Pg(with_db(self.admin.url, self.name), self.admin.psql)
            rc, _, err = admin_db.run(["-v", "ON_ERROR_STOP=1", "-v", f"guard_role={self.role}", "-f", "-"],
                                      stdin=self.setup)
            if rc != 0:
                self.__exit__()
                raise CannotJudge(f"the setup SQL failed: {redact(err, self.password).strip()[:300]}")
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
   WHERE t.typtype = 'e' AND n.nspname NOT IN ('pg_catalog', 'information_schema')), '{}'::json),
 'views', COALESCE((SELECT json_agg(json_build_object('oid', c.oid, 'schema', n.nspname, 'name', c.relname,
    'kind', c.relkind, 'def', pg_get_viewdef(c.oid),
    'deps', (SELECT json_agg(DISTINCT jsonb_build_array(d.refobjid::text, a.attname)) FROM pg_rewrite r
             JOIN pg_depend d ON d.objid = r.oid AND d.classid = 'pg_rewrite'::regclass
               AND d.refclassid = 'pg_class'::regclass AND d.refobjid <> c.oid
             LEFT JOIN pg_attribute a ON a.attrelid = d.refobjid AND a.attnum = d.refobjsubid AND d.refobjsubid > 0
             WHERE r.ev_class = c.oid)) ORDER BY n.nspname, c.relname)
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE c.relkind IN ('v', 'm') AND n.nspname NOT IN ('pg_catalog', 'information_schema')
    AND n.nspname NOT LIKE 'pg_%'), '[]'::json),
 'triggers', COALESCE((SELECT json_agg(json_build_object('table', g.tgrelid, 'name', g.tgname,
    'def', pg_get_triggerdef(g.oid), 'func', g.tgfoid) ORDER BY g.tgrelid, g.tgname)
  FROM pg_trigger g JOIN pg_class c ON c.oid = g.tgrelid JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE NOT g.tgisinternal AND n.nspname NOT IN ('pg_catalog', 'information_schema')
    AND n.nspname NOT LIKE 'pg_%'), '[]'::json),
 'functions', COALESCE((SELECT json_object_agg(p.oid, json_build_object('schema', n.nspname, 'name', p.proname,
    'lang', l.lanname, 'def', pg_get_functiondef(p.oid)))
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace JOIN pg_language l ON l.oid = p.prolang
  WHERE p.oid IN (SELECT tgfoid FROM pg_trigger WHERE NOT tgisinternal)), '{}'::json),
 'sequences', COALESCE((SELECT json_agg(json_build_object('schema', n.nspname, 'name', s.relname,
    'table', d.refobjid, 'col', a.attname) ORDER BY n.nspname, s.relname)
  FROM pg_class s JOIN pg_namespace n ON n.oid = s.relnamespace
  LEFT JOIN pg_depend d ON d.objid = s.oid AND d.classid = 'pg_class'::regclass
    AND d.refclassid = 'pg_class'::regclass AND d.deptype IN ('a', 'i')
  LEFT JOIN pg_attribute a ON a.attrelid = d.refobjid AND a.attnum = d.refobjsubid
  WHERE s.relkind = 'S' AND n.nspname NOT IN ('pg_catalog', 'information_schema')
    AND n.nspname NOT LIKE 'pg_%'), '[]'::json),
 'domains', COALESCE((SELECT json_object_agg(t.typname, format_type(t.typbasetype, t.typtypmod)
    || CASE WHEN t.typnotnull THEN ' NOT NULL' ELSE '' END
    || COALESCE((SELECT ' ' || string_agg(pg_get_constraintdef(k.oid), ' ' ORDER BY k.conname)
                 FROM pg_constraint k WHERE k.contypid = t.oid), ''))
  FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
  WHERE t.typtype = 'd' AND n.nspname NOT IN ('pg_catalog', 'information_schema')), '{}'::json),
 'relations', COALESCE((SELECT json_agg(json_build_array(n.nspname, c.relname, c.relkind,
    CASE WHEN c.relkind IN ('i', 'I') THEN (SELECT i.indrelid FROM pg_index i WHERE i.indexrelid = c.oid)
         WHEN c.relispartition THEN (SELECT h.inhparent FROM pg_inherits h WHERE h.inhrelid = c.oid)
         ELSE c.oid END))
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname NOT IN ('pg_catalog', 'information_schema') AND n.nspname NOT LIKE 'pg_%'
    AND c.relkind NOT IN ('t', 'c')), '[]'::json))
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
                facts: list | None = None, notes: list | None = None, prune: bool | None = None) -> tuple[str, list]:
    """(the prompt in the world layout, the tables shown). facts: lines decided in code (shown before the rows).

    prune (default PRUNE): only the part of the schema the migration reaches (see schema_cut). When the cut cannot be
    made safely, the state is the one of 0.1.17 (the tables the migration names and their foreign-key neighbors, at
    most MAX_TABLES), and a line saying why goes to notes."""
    if prune is None:
        prune = PRUNE
    if prune:
        try:
            cut = schema_cut(catalog, stmts)
            if isinstance(cut, Cut):
                out = _cut_state(catalog, cut, stmts, stats, tool, transaction, facts)
                if len(out[0]) <= MAX_CHARS:
                    return out
                cut = f"the cut schema is too long, {len(out[0]):,} characters"
        except Exception as e:      # a catalog or statement the cut did not expect: never fail the check over it
            cut = f"the cut failed ({type(e).__name__})"

        if notes is not None:
            notes.append(f"schema not cut ({cut}): the state shows the tables the migration names and their foreign-key "
                         f"neighbors, at most {MAX_TABLES}")
    return _named_state(catalog, stmts, stats, tool, transaction, facts)


def _named_state(catalog: dict, stmts: list, stats: dict | None, tool: str, transaction: bool,
                 facts: list | None = None) -> tuple[str, list]:
    """The state of 0.1.17: the tables whose names appear in the migration, and their foreign-key neighbors."""
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


# ---------------------------------------------------------------- the schema cut (0.1.19)
#
# The state shows only the part of the schema a migration reaches. In full: the tables it touches (ALTER, INSERT, UPDATE,
# DELETE, TRUNCATE, CREATE INDEX ON, DROP, FROM/JOIN of its queries, REFERENCES, LIKE, PARTITION OF, the tables using a
# type or domain it alters or drops, the table of an index or sequence it alters or drops, the tables their triggers
# write). In one line each: the tables linked to those by a foreign key (one step, both ways: the key, and NOT NULL on
# its columns), the views that depend on them (pg_depend, transitively: the columns each one reads). Also their
# triggers with the functions' bodies (up to EXTRA_CHARS), the sequences they own, and the enums and domains of the
# columns shown. Every other table is counted in one line. A migration the parser cannot follow (dynamic SQL, a
# statement it does not know, a name it cannot resolve, a function body it cannot read) is not cut, and neither is one
# whose cut state is still longer than MAX_CHARS: the state is then the one of 0.1.17.

PRUNE = os.environ.get("EKBASIS_SCHEMA_CUT", "on").strip().lower() not in ("off", "0", "false", "no")
CUT_VERSION = 1             # part of the verdict cache key
EXTRA_CHARS = 20000         # trigger functions' bodies up to this; beyond it, their size only

TOKEN = re.compile(r'"(?:[^"]|"")*"|[A-Za-z_][A-Za-z0-9_$]*|\$\$|::|[0-9]+(?:\.[0-9]+)?|\S')
SERIAL = re.compile(r"\b(?:SMALL|BIG)?SERIAL[248]?\b|\bAS\s+IDENTITY\b", re.I)   # a sequence made implicitly
TRANSITION = re.compile(r"\b(?:NEW|OLD)\s+TABLE\s+AS\s+(\"(?:[^\"]|\"\")*\"|\w+)", re.I)
SEQ_CALL = re.compile(r"\b(?:nextval|setval|currval)\s*\(\s*'([^']+)'", re.I)
SERIAL_SEQ = re.compile(r"\bpg_get_serial_sequence\s*\(\s*'([^']+)'", re.I)
NOT_ALIAS = {
    "WHERE", "JOIN", "INNER", "LEFT", "RIGHT", "FULL", "CROSS", "NATURAL", "ON", "USING", "GROUP", "ORDER", "LIMIT",
    "OFFSET", "UNION", "EXCEPT", "INTERSECT", "RETURNING", "SET", "WINDOW", "HAVING", "FOR", "WHEN", "THEN", "LOOP",
    "INTO", "VALUES", "SELECT", "AND", "OR", "AS", "WITH", "FETCH", "TABLESAMPLE", "DO", "ELSE", "END", "IF", "LATERAL",
    "OUTER", "DEFAULT", "NOT", "IS", "IN", "BY", "FROM", "ONLY", "CASE", "EXISTS", "BETWEEN", "LIKE", "ILIKE",
    "UPDATE", "DELETE", "INSERT", "ALTER", "DROP", "CREATE", "MERGE", "TRUNCATE", "BEGIN", "COMMIT", "CONFLICT",
    "OVERRIDING", "EXCEPTION", "RAISE", "RETURN", "PERFORM", "STRICT", "NOTHING", "ELSIF", "NULL"}
# a FROM inside these calls is not a table: extract(epoch FROM x), substring(s FROM 2), trim(both FROM s), ...
FROM_CALLS = {"EXTRACT", "SUBSTRING", "TRIM", "OVERLAY", "POSITION", "SUBSTR", "NORMALIZE"}
# a statement can start a table position at these: UPDATE / INSERT / DELETE / MERGE as statements, not as a word
STMT_START = {None, ";", "(", ")", "AS", "THEN", "ELSE", "LOOP", "BEGIN", "DECLARE"}   # ")": after a CTE
NO_REFS = {  # statements that reach no table
    ("SET",), ("RESET",), ("BEGIN",), ("COMMIT",), ("END",), ("START",), ("SAVEPOINT",), ("RELEASE",), ("ROLLBACK",),
    ("CREATE", "EXTENSION"), ("CREATE", "SCHEMA"), ("CREATE", "ROLE"), ("CREATE", "USER"), ("CREATE", "COLLATION"),
    ("ALTER", "SCHEMA"), ("ALTER", "ROLE"), ("ALTER", "USER"), ("ALTER", "DEFAULT"), ("ALTER", "DATABASE"),
    ("ALTER", "EXTENSION"), ("DROP", "ROLE"), ("DROP", "USER"), ("ALTER", "FUNCTION"), ("ALTER", "PROCEDURE"),
    ("COMMENT", "ON"), ("NOTIFY",), ("LISTEN",), ("DISCARD",), ("CHECKPOINT",)}


@dataclass
class Cut:
    touched: list           # table oids, in the order the migration reaches them
    views: list = field(default_factory=list)        # view oids reached directly (FROM a view, ALTER VIEW, ...)
    seqs: list = field(default_factory=list)         # (schema, name) of sequences it names


def _norm(tok: str) -> str:
    return tok[1:-1].replace('""', '"') if tok.startswith('"') else tok.lower()


def _is_ident(tok) -> bool:
    return bool(tok) and (tok[0] == '"' or tok[0].isalpha() or tok[0] == "_")


class _Toks:
    def __init__(self, text: str):
        self.t = TOKEN.findall(text)
        self.u = [x.upper() if not x.startswith('"') else x for x in self.t]

    def name(self, i: int) -> tuple:
        """(parts, next index) of the possibly qualified name at i, or (None, i)."""
        if i >= len(self.t) or not _is_ident(self.t[i]):
            return None, i
        parts = [_norm(self.t[i])]
        i += 1
        while i + 1 < len(self.t) and self.t[i] == "." and _is_ident(self.t[i + 1]):
            parts.append(_norm(self.t[i + 1]))
            i += 2
        return tuple(parts), i

    def skip(self, i: int, *words) -> int:
        while i < len(self.t) and self.u[i] in words:
            i += 1
        return i

    def skip_if_exists(self, i: int) -> int:
        if self.u[i:i + 2] == ["IF", "EXISTS"]:
            return i + 2
        if self.u[i:i + 3] == ["IF", "NOT", "EXISTS"]:
            return i + 3
        return i


class _Unresolved(Exception):
    pass


class _Index:
    """Names of the catalog: relations by (schema, name), and what each one is."""

    def __init__(self, catalog: dict):
        self.tables = {str(t["oid"]): t for t in catalog.get("tables") or []}
        self.views = {str(v["oid"]): v for v in catalog.get("views") or []}
        self.rel = {}
        for schema, name, kind, target in catalog.get("relations") or []:
            self.rel[(schema, name)] = (kind, str(target) if target is not None else None)
        for v in self.views.values():
            self.rel[(v["schema"], v["name"])] = (v["kind"], str(v["oid"]))
        self.types = {**{e: "enum" for e in catalog.get("enums") or {}},
                      **{d: "domain" for d in catalog.get("domains") or {}}}

    def lookup(self, parts: tuple):
        if len(parts) >= 2:
            return self.rel.get(parts[-2:]) and (parts[-2], parts[-1])
        if ("public", parts[0]) in self.rel:
            return ("public", parts[0])
        hits = [k for k in self.rel if k[1] == parts[0]]
        return hits[0] if len(hits) == 1 else None


def _scan(code: str, ix: "_Index", out: "_Reach", head: tuple = ()):
    """Table positions anywhere in a statement or a function body: FROM/JOIN lists, INSERT/MERGE INTO, UPDATE and DELETE
    as statements, TRUNCATE, REFERENCES; and the names a CTE or the statement itself creates (not resolved)."""
    k = _Toks(code)
    t, u = k.t, k.u
    stack = []                  # for each open parenthesis, the word before it
    for i, w in enumerate(u):
        prev = u[i - 1] if i else None
        if w == "(":
            stack.append(prev)
            continue
        if w == ")":
            if stack:
                stack.pop()
            continue
        if _is_ident(t[i]) and i + 2 < len(t) and u[i + 1] == "AS" and u[i + 2] in ("(", "MATERIALIZED", "NOT"):
            out.local.add(_norm(t[i]))                          # WITH name AS (...)
        if (w == "CONSTRAINT" or (w == "TO" and "RENAME" in u[:i])) and i + 1 < len(t) and _is_ident(t[i + 1]):
            out.local.add(_norm(t[i + 1]))                      # a constraint's index, a new name
        if w == "FROM":
            if prev in ("DISTINCT",) or (stack and stack[-1] in FROM_CALLS) or head[:1] == ("REVOKE",):
                continue
            out.from_list(k, i + 1)
        elif w == "JOIN":
            out.from_list(k, i + 1, one=True)
        elif w in ("INSERT", "MERGE") and i + 1 < len(u) and u[i + 1] == "INTO" and prev in STMT_START:
            out.ref(k, k.skip(i + 2, "ONLY"))
        elif w == "UPDATE" and prev in STMT_START and i + 1 < len(u) and u[i + 1] != "SET":
            out.ref(k, k.skip(i + 1, "ONLY"))
        elif w == "TRUNCATE" and prev in STMT_START:
            out.ref_list(k, k.skip(i + 1, "TABLE", "ONLY"))
        elif w == "REFERENCES":
            out.ref(k, i + 1)
        elif w == "EXECUTE" and head == ("BODY",) and (i + 1 >= len(u) or u[i + 1] not in ("FUNCTION", "PROCEDURE")):
            raise _Unresolved("dynamic SQL (EXECUTE)")


class _Reach:
    def __init__(self, ix: _Index):
        self.ix = ix
        self.names = []         # (parts, kind wanted) to resolve after the whole migration is read
        self.local = set()      # names the migration itself creates (tables, views, CTEs, aliases are not here)
        self.types = []         # type names it alters or drops
        self.seqs = []

    def ref(self, k: _Toks, i: int, kind: str = "rel"):
        """kind "opt": under IF EXISTS, a name that does not exist is a no-op, not an unresolved name."""
        if [w for w in k.u[max(0, i - 3):i] if w not in ("ONLY", "CONCURRENTLY")][-2:] == ["IF", "EXISTS"]:
            kind = "opt"
        parts, j = k.name(i)
        if parts:
            self.names.append((parts, kind))
        return j

    def ref_list(self, k: _Toks, i: int, kind: str = "rel"):
        if k.u[max(0, i - 2):i] == ["IF", "EXISTS"]:
            kind = "opt"
        while True:
            i = k.skip(i, "ONLY")
            j = self.ref(k, i, kind)
            if j == i:
                return
            i = j + (1 if j < len(k.t) and k.t[j] == "*" else 0)
            if i < len(k.t) and k.t[i] == ",":
                i += 1
                continue
            return

    def from_list(self, k: _Toks, i: int, one: bool = False):
        while i < len(k.t):
            i = k.skip(i, "ONLY", "LATERAL")
            if i >= len(k.t) or k.t[i] == "(":
                return                              # a subquery: its own FROM is scanned where it is
            parts, j = k.name(i)
            if not parts:
                return
            if j < len(k.t) and k.t[j] == "(":
                return                              # a function: generate_series(...), unnest(...)
            self.names.append((parts, "rel"))
            i = j
            if i < len(k.t) and k.u[i] == "AS":
                i += 1
            if i < len(k.t) and _is_ident(k.t[i]) and k.u[i] not in NOT_ALIAS:
                i += 1
            if one or i >= len(k.t) or k.t[i] != ",":
                return
            i += 1

    def create(self, k: _Toks, i: int):
        parts, j = k.name(i)
        if parts:
            self.local.add(parts[-1])
        return j


def _body_lang(stmt: str) -> str:
    m = re.search(r"\bLANGUAGE\s+'?\"?([A-Za-z0-9_]+)", outside_bodies(stmt), re.I)
    return m.group(1).lower() if m else "sql"


def _bodies(stmt: str) -> list:
    out, i = [], 0
    while True:
        m = DOLLAR.search(stmt, i)
        if not m:
            return out
        j = stmt.find(m.group(0), m.end())
        if j < 0:
            return out
        out.append(stmt[m.end():j])
        i = j + len(m.group(0))


def _clean_body(body: str) -> str:
    """A function or DO body as the scanner reads it: comments removed, strings and nested dollar bodies emptied."""
    return " ; ".join(outside_bodies(s) for s in split_sql(body))


def _function_body(stmt: str, ix: _Index, r: _Reach, what: str):
    lang = _body_lang(stmt)
    if lang in ("c", "internal"):
        return
    if lang not in ("sql", "plpgsql"):
        raise _Unresolved(f"{what} in language {lang}")
    bodies = _bodies(stmt)
    if not bodies and re.search(r"\bAS\s*'", stmt, re.I):
        raise _Unresolved(f"{what} with a quoted body")
    for b in bodies:
        _scan(_clean_body(b), ix, r, ("BODY",))


def _statement(stmt: str, ix: _Index, r: _Reach):
    """What one statement reaches; raises _Unresolved when it cannot be followed."""
    code = outside_bodies(stmt)
    k = _Toks(code)
    u = k.u
    if not u:
        return
    head = tuple(w for w in u[:4] if w not in ("OR", "REPLACE", "UNIQUE", "TEMP", "TEMPORARY", "UNLOGGED", "CONSTRAINT",
                                                 "GLOBAL", "LOCAL"))
    r.local |= {_norm(x) for x in TRANSITION.findall(code)}    # REFERENCING NEW TABLE AS x
    for m in SEQ_CALL.finditer(stmt):
        r.seqs.append(tuple(_norm(p) for p in m.group(1).split(".")))
    for m in SERIAL_SEQ.finditer(stmt):
        r.names.append((tuple(_norm(p) for p in m.group(1).split(".")), "rel"))
    h1, h2 = head[:1], head[:2]
    if h1 == ("DO",):
        if not _bodies(stmt):
            raise _Unresolved("a DO block with a quoted body")
        _function_body(stmt, ix, r, "a DO block")
        return
    if h2 in (("CREATE", "FUNCTION"), ("CREATE", "PROCEDURE")):
        _function_body(stmt, ix, r, "a function")
        return
    if h1 in (("EXECUTE",), ("CALL",), ("PREPARE",), ("COPY",), ("IMPORT",), ("SECURITY",)):
        raise _Unresolved(f"{h1[0]} statement")
    if h2 in NO_REFS or h1 in NO_REFS:
        if h2 == ("COMMENT", "ON"):
            return _comment(k, r)
        return
    _scan(code, ix, r, head)
    if h2 == ("ALTER", "TABLE"):
        i = k.skip_if_exists(u.index("TABLE") + 1)
        if u[i:i + 3] == ["ALL", "IN", "TABLESPACE"]:
            raise _Unresolved("ALTER TABLE ALL IN TABLESPACE")
        j = r.ref(k, k.skip(i, "ONLY"))
        for n in range(j, len(u) - 1):
            if u[n] == "RENAME" and u[n + 1] == "TO":
                r.create(k, n + 2)
            if u[n] in ("ATTACH", "DETACH") and u[n + 1] == "PARTITION":
                r.ref(k, n + 2)
        return
    if h2 in (("ALTER", "INDEX"), ("ALTER", "SEQUENCE"), ("ALTER", "VIEW"), ("ALTER", "MATERIALIZED"),
              ("REFRESH", "MATERIALIZED")):
        i = u.index(h2[1]) + (2 if h2[1] == "MATERIALIZED" else 1)
        i = k.skip(k.skip_if_exists(k.skip(i, "CONCURRENTLY")), "ONLY")
        if u[i:i + 3] == ["ALL", "IN", "TABLESPACE"]:
            raise _Unresolved("ALTER ... ALL IN TABLESPACE")
        j = r.ref(k, i)
        for n in range(j, len(u) - 1):
            if u[n] == "RENAME" and u[n + 1] == "TO":
                r.create(k, n + 2)
            if u[n] == "OWNED" and u[n + 1] == "BY" and u[n + 2:n + 3] != ["NONE"]:
                parts, _ = k.name(n + 2)
                if parts and len(parts) >= 2:
                    r.names.append((parts[:-1], "rel"))
        return
    if h2 in (("ALTER", "TYPE"), ("ALTER", "DOMAIN")):
        parts, _ = k.name(2)
        if parts:
            r.types.append(parts[-1])
        return
    if h1 == ("CREATE",):
        return _create(k, r, head)
    if h1 == ("DROP",):
        return _drop(k, r, head)
    if h1 in (("GRANT",), ("REVOKE",)):
        n = u.index("ON") if "ON" in u else -1
        if n >= 0 and n + 1 < len(u):
            if u[n + 1] in ("SEQUENCE", "FUNCTION", "PROCEDURE", "ROUTINE", "SCHEMA", "DATABASE", "TYPE", "DOMAIN",
                            "LANGUAGE", "TABLESPACE", "FOREIGN", "LARGE", "ALL"):
                return
            r.ref_list(k, k.skip(n + 1, "TABLE"))
        return
    if h1 in (("LOCK",), ("ANALYZE",), ("VACUUM",), ("CLUSTER",)):
        i = 1
        if i < len(u) and u[i] == "(":
            i = u.index(")") + 1 if ")" in u else len(u)
        i = k.skip(i, "TABLE", "ONLY", "VERBOSE", "FULL", "FREEZE", "ANALYZE")
        if i < len(u):
            r.ref_list(k, i)
        return
    if h1 == ("REINDEX",):
        n = k.skip(1, "CONCURRENTLY")
        if n < len(u) and u[n] in ("TABLE", "INDEX"):
            r.ref(k, k.skip(n + 1, "CONCURRENTLY"))
            return
        if n < len(u) and u[n] in ("SCHEMA", "DATABASE", "SYSTEM"):
            return
        raise _Unresolved("REINDEX form")
    if h1 in (("SELECT",), ("WITH",), ("INSERT",), ("UPDATE",), ("DELETE",), ("TRUNCATE",), ("MERGE",), ("VALUES",),
              ("TABLE",)):
        if h1 == ("TABLE",):
            r.ref(k, 1)
        return
    raise _Unresolved(f"statement {' '.join(head[:2])} ...")


def _comment(k: _Toks, r: _Reach):
    u = k.u
    obj = u[2] if len(u) > 2 else ""
    if obj in ("TABLE", "VIEW", "INDEX", "SEQUENCE"):
        r.ref(k, 3)
    elif obj == "COLUMN":
        parts, _ = k.name(3)
        if parts and len(parts) >= 2:
            r.names.append((parts[:-1], "rel"))
    elif obj in ("CONSTRAINT", "TRIGGER", "POLICY", "RULE") and "ON" in u[3:]:
        r.ref(k, u.index("ON", 3) + 1)


def _create(k: _Toks, r: _Reach, head: tuple):
    u = k.u
    what = head[1] if len(head) > 1 else ""
    if what == "TABLE":
        i = k.skip_if_exists(u.index("TABLE") + 1)
        r.create(k, i)
        for n, w in enumerate(u):
            if w in ("LIKE", "INHERITS") or (w == "PARTITION" and n + 1 < len(u) and u[n + 1] == "OF"):
                r.ref(k, n + 2 if w == "PARTITION" else n + 1 + (1 if n + 1 < len(u) and u[n + 1] == "(" else 0))
        return
    if what in ("VIEW", "MATERIALIZED", "SEQUENCE", "TYPE", "DOMAIN", "INDEX", "TRIGGER", "POLICY", "AGGREGATE", "CAST",
                "OPERATOR"):
        if what in ("VIEW", "MATERIALIZED", "SEQUENCE", "TYPE", "DOMAIN"):
            i = u.index("VIEW" if what == "MATERIALIZED" else what) + 1
            r.create(k, k.skip_if_exists(i))
            if what == "SEQUENCE" and "OWNED" in u:
                parts, _ = k.name(u.index("OWNED") + 2)
                if parts and len(parts) >= 2:
                    r.names.append((parts[:-1], "rel"))
            return
        if what in ("INDEX", "TRIGGER", "POLICY"):
            if "ON" not in u:
                raise _Unresolved(f"CREATE {what} without ON")
            n = u.index("ON")
            if what == "TRIGGER":       # BEFORE UPDATE OF a, b ON t: the ON after the events
                n = max(i for i, w in enumerate(u) if w == "ON" and i < (u.index("EXECUTE") if "EXECUTE" in u else len(u)))
            r.ref(k, k.skip(n + 1, "ONLY"))
            return
        return
    if what == "RULE":
        raise _Unresolved("CREATE RULE")
    raise _Unresolved(f"CREATE {what}")


def _drop(k: _Toks, r: _Reach, head: tuple):
    u = k.u
    what = head[1] if len(head) > 1 else ""
    if what in ("TABLE", "VIEW", "SEQUENCE", "INDEX", "MATERIALIZED", "FOREIGN"):
        i = u.index("VIEW" if what == "MATERIALIZED" else "TABLE" if what == "FOREIGN" else what) + 1
        r.ref_list(k, k.skip_if_exists(k.skip(i, "CONCURRENTLY")))
        return
    if what in ("TYPE", "DOMAIN"):
        i = k.skip_if_exists(u.index(what) + 1)
        while i < len(u):
            parts, j = k.name(i)
            if not parts:
                break
            r.types.append(parts[-1])
            i = j + 1 if j < len(u) and k.t[j] == "," else len(u)
        return
    if what in ("TRIGGER", "POLICY", "RULE"):
        if "ON" in u:
            r.ref(k, u.index("ON") + 1)
        return
    if what in ("FUNCTION", "PROCEDURE", "ROUTINE"):
        if "CASCADE" in u:
            raise _Unresolved(f"DROP {what} ... CASCADE")
        return
    if what in ("EXTENSION", "SCHEMA", "OWNED"):
        if "CASCADE" in u or what == "OWNED":
            raise _Unresolved(f"DROP {what} ... CASCADE")
        return
    if what in ("ROLE", "USER", "CAST", "COLLATION", "AGGREGATE", "OPERATOR"):
        return
    raise _Unresolved(f"DROP {what}")


def _builtin(parts: tuple) -> bool:
    """The system catalogs (a DO block's `FROM pg_type WHERE typname = ...`) and the trigger records."""
    if len(parts) >= 2:
        return parts[-2] in ("pg_catalog", "information_schema")
    return parts[0].startswith("pg_") or parts[0] in ("new", "old", "excluded")


def schema_cut(catalog: dict, stmts: list):
    """The tables a migration reaches (a Cut), or why it cannot be cut (a string)."""
    if not catalog or "relations" not in catalog or "views" not in catalog:
        return "the catalog has no dependency information"
    ix = _Index(catalog)
    r = _Reach(ix)
    try:
        for s in stmts:
            _statement(s, ix, r)
    except _Unresolved as e:
        return str(e)
    except (ValueError, IndexError) as e:       # a statement shaped in a way the parser did not expect
        return f"a statement the parser cannot follow ({type(e).__name__})"
    touched, views, seqs, unresolved = [], [], [], []

    def add(lst, x):
        if x not in lst:
            lst.append(x)

    serial = any(SERIAL.search(outside_bodies(s)) for s in stmts)
    for parts, kind in r.names:
        key = ix.lookup(parts)
        if not key:
            if parts[-1] in r.local or _builtin(parts) or kind == "opt" or (serial and parts[-1].endswith("_seq")):
                continue
            unresolved.append(".".join(parts))
            continue
        kind, target = ix.rel[key]
        if kind in ("r", "p", "i", "I"):
            if target in ix.tables:
                add(touched, target)
            elif target in ix.views:        # an index on a materialized view
                add(views, target)
        elif kind in ("v", "m"):
            add(views, target)
        elif kind == "S":
            add(seqs, key)
        else:
            unresolved.append(".".join(parts) + f" (relation kind {kind})")
    for parts in r.seqs:
        key = ix.lookup(parts)
        if key and ix.rel[key][0] == "S":
            add(seqs, key)
        elif parts[-1] not in r.local and not serial:
            unresolved.append(".".join(parts) + " (sequence)")
    for name in r.types:
        if name not in ix.types and name not in r.local:
            continue                        # a type this migration creates, or not a user type (DROP TYPE IF EXISTS)
        for oid, t in ix.tables.items():
            if any((c.get("typname") or "").lstrip("_") == name for c in t["cols"] or []):
                add(touched, oid)
    owners = {(s["schema"], s["name"]): str(s["table"]) for s in catalog.get("sequences") or [] if s.get("table")}
    for key in seqs:
        if owners.get(key) in ix.tables:
            add(touched, owners[key])
    if unresolved:
        return "names it cannot resolve: " + ", ".join(sorted(set(unresolved))[:5])
    # trigger functions of the touched tables run with the migration: what they reach is reached too
    funcs = catalog.get("functions") or {}
    seen = set()
    while True:
        more = []
        for g in catalog.get("triggers") or []:
            if str(g["table"]) in touched and str(g["func"]) not in seen:
                seen.add(str(g["func"]))
                f = funcs.get(str(g["func"]))
                if not f:
                    return f"trigger {g['name']}: its function is not in the catalog"
                fr = _Reach(ix)
                fr.local |= {_norm(x) for x in TRANSITION.findall(g["def"])}
                try:
                    _function_body(f["def"], ix, fr, f"trigger function {f['name']}")
                except _Unresolved as e:
                    return str(e)
                for parts, _ in fr.names:
                    key = ix.lookup(parts)
                    if not key:
                        if parts[-1] in fr.local or _builtin(parts):
                            continue
                        return f"trigger function {f['name']} reaches a name it cannot resolve: {'.'.join(parts)}"
                    kind, target = ix.rel[key]
                    if kind in ("r", "p") and target in ix.tables and target not in touched:
                        more.append(target)
        if not more:
            break
        for x in more:
            add(touched, x)
    return Cut(touched, views, seqs)


def _fk_line(t: dict, k: dict) -> str:
    return f"{disp(t)}: CONSTRAINT {k['name']} {k['def']}"


def _link(t: dict, keep: set) -> str:
    """A neighbor in one line: its foreign keys to the touched tables (with NOT NULL on their columns), or that the
    touched tables reference it."""
    notnull = {c["name"] for c in t["cols"] or [] if c["notnull"]}
    fks = []
    for k in t["cons"] or []:
        if k["type"] == "f" and str(k["ref"]) in keep:
            m = re.match(r"FOREIGN KEY \(([^)]*)\)", k["def"])
            cols = [c.strip().strip('"') for c in m.group(1).split(",")] if m else []
            nn = [c for c in cols if c in notnull]
            fks.append(k["def"] + (f" ({', '.join(nn)} NOT NULL)" if nn else ""))
    return disp(t) + (": " + ", ".join(fks) if fks else " (referenced by them)")


def _cut_state(catalog: dict, cut: Cut, stmts: list, stats: dict | None, tool: str, transaction: bool,
               facts: list | None) -> tuple[str, list]:
    tables = catalog.get("tables") or []
    byoid = {str(t["oid"]): t for t in tables}
    touched = [byoid[o] for o in cut.touched if o in byoid]
    keep = set(cut.touched)
    neighbors = []
    for t in tables:                          # one foreign-key step, both ways; outgoing first
        if str(t["oid"]) in keep:
            for k in t["cons"] or []:
                ref = str(k["ref"])
                if k["type"] == "f" and ref in byoid and ref not in keep and byoid[ref] not in neighbors:
                    neighbors.append(byoid[ref])
    for t in tables:
        if str(t["oid"]) not in keep and t not in neighbors and any(
                k["type"] == "f" and str(k["ref"]) in keep for k in t["cons"] or []):
            neighbors.append(t)
    # the trigger functions run with the migration: their bodies, up to a budget
    trig = [g for g in catalog.get("triggers") or [] if str(g["table"]) in keep]
    funcs = catalog.get("functions") or {}
    budget = EXTRA_CHARS
    bodies = {}
    for g in trig:
        f = funcs.get(str(g["func"]))
        if f and str(g["func"]) not in bodies:
            d = f["def"].strip()
            bodies[str(g["func"])] = d if len(d) <= budget else None
            budget -= len(d) if len(d) <= budget else 0
    shown = touched
    allkept = {str(t["oid"]) for t in touched + neighbors}
    # views that depend on the touched tables, and views on those views: what each one reads
    views = {str(v["oid"]): v for v in catalog.get("views") or []}
    names = {**{o: disp(t) for o, t in byoid.items()}, **{o: disp(v) for o, v in views.items()}}
    vkeep = [o for o in cut.views if o in views]
    grow = True
    while grow:
        grow = False
        for o, v in views.items():
            if o not in vkeep and any(str(d[0]) in keep or str(d[0]) in vkeep for d in v.get("deps") or []):
                vkeep.append(o)
                grow = True
    seqs = [q for q in catalog.get("sequences") or [] if str(q.get("table")) in keep
            or (q["schema"], q["name"]) in cut.seqs]
    used = {(c.get("typname") or "").lstrip("_") for t in shown for c in t["cols"] or []}
    text = "\n".join(stmts)

    def named(e):
        return re.search(r"(?<![\w$])\"?" + re.escape(e) + r"\"?(?![\w$])", text)

    enums = [f"{e}: " + ", ".join("'" + x + "'" for x in labels) for e, labels in (catalog.get("enums") or {}).items()
             if e in used or named(e)]
    domains = [f"{d}: {defn}" for d, defn in (catalog.get("domains") or {}).items() if d in used or named(d)]

    parts = ["Schema (the tables the migration touches, the tables linked to them by foreign keys, and what depends on "
             "them):"]
    parts += [ddl(t) for t in shown] or ["(none of the tables it touches exists yet)"]
    if neighbors:
        parts.append("Tables linked to them by a foreign key (their other columns not shown): " +
                     "; ".join(_link(t, keep) for t in neighbors))
    if vkeep:
        def reads(v):
            by = {}
            for o, col in v.get("deps") or []:
                by.setdefault(str(o), []).append(col)
            return ", ".join(names.get(o, "?") + (f"({', '.join(sorted(c for c in cs if c))})" if any(cs) else "")
                             for o, cs in by.items())
        parts.append("Views that depend on them: " + "; ".join(
            f"{'materialized view ' if views[o]['kind'] == 'm' else ''}{names[o]} reads {reads(views[o])}"
            for o in vkeep))
    if trig:
        parts.append("Triggers on them:")
        done = set()
        for g in trig:
            parts.append(g["def"] + ";")
            fo = str(g["func"])
            if fo not in done and fo in bodies:
                done.add(fo)
                parts.append(bodies[fo] if bodies[fo] else
                             f"(the body of {funcs[fo]['name']}() is not shown: {len(funcs[fo]['def']):,} characters)")
    if seqs:
        parts.append("Sequences: " + "; ".join(
            (q["name"] if q["schema"] == "public" else f"{q['schema']}.{q['name']}") +
            (f" (owned by {disp(byoid[str(q['table'])])}.{q['col']})" if str(q.get("table")) in byoid else "")
            for q in seqs))
    if enums:
        parts.append("Enum types: " + "; ".join(enums))
    if domains:
        parts.append("Domains: " + "; ".join(domains))
    parts += ["", "Rows:"] + [table_facts(t, stats) for t in shown + neighbors]
    omitted = len([t for t in tables if str(t["oid"]) not in allkept])
    lines = []
    if omitted:
        lines.append(f"{omitted} other table{'s' if omitted != 1 else ''} omitted: not touched by this migration and not "
                     "linked to it by a foreign key.")
    lines += facts or []
    if lines:
        parts += ["", "Facts: " + " ".join(lines)]
    rules = RULES_TX.format(tool=TOOL_NAMES.get(tool, TOOL_NAMES["generic"])) if transaction else RULES_AUTO
    return P.world_state(rules, "\n".join(parts), stmts), [disp(t) for t in shown + neighbors]


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
    code_not_foreseen: str | None = None  # framework migrations, on-code=warn: code that is not SQL (not blocking)
    decided: str | None = None          # a failure on existing data decided in code (probes: replica statistics)
    edited: bool = False                # the pull request edits this migration, which the base already has

    @property
    def kind(self) -> str:
        """Why it is risky, decided in code from the two answers (0.1.12): cannot_foresee, schema (fails on the base's
        schema before any data: the pull request's own error), fails (may fail on existing data), loses, or ok."""
        if self.cannot_judge:
            return "cannot_foresee"
        if self.code_not_foreseen:
            return "code_not_foreseen"
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
        if k == "code_not_foreseen":
            return f"contains code the guard cannot foresee ({self.code_not_foreseen}): review it by hand"
        if k == "schema":
            return (f"fails on the base branch's schema before touching any data: {self.schema_error} (an error in "
                    "the pull request itself, e.g. it depends on a migration missing from the base, or a typo)")
        lose = self.p_lost is not None and self.p_lost >= self.lost_threshold
        if k == "fails" and self.decided:
            return f"fails on existing data: {self.decided}" + ("; nothing in the file would be applied"
                                                                if self.transaction else "")
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
             "cached": self.cached, "code_not_foreseen": self.code_not_foreseen, "decided": self.decided,
             "edited": self.edited}
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

    @property
    def code_not_foreseen(self) -> bool:
        return any(f.code_not_foreseen for f in self.files)

    def summary(self) -> str:
        if not self.files:
            return "Ekbasis migration guard: no new migration files" + ("\n  " + "\n  ".join(self.notes) if self.notes else "")
        head = ("RISKY" if self.risky else "CANNOT FORESEE" if self.cannot_judge else
                "no risk found in the SQL; code to review by hand" if self.code_not_foreseen else "no risk found")
        lines = [f"Ekbasis migration guard: {head}"]
        for f in self.files:
            tag = ("CANNOT FORESEE" if f.cannot_judge else "RISKY" if f.risky else
                   "REVIEW BY HAND" if f.code_not_foreseen else "ok")
            lines.append(f"  {tag:<14} {f.path}: {f.reason}")
            lines += [f"                 note: {n}" for n in f.notes]
        lines += [f"  note: {n}" for n in self.notes]
        return "\n".join(lines)

    def as_json(self, state: bool = False) -> dict:
        return {"risky": self.risky, "cannot_judge": self.cannot_judge, "cannot_foresee": self.cannot_judge,
                "code_not_foreseen": self.code_not_foreseen,
                "files": [f.as_json(state) for f in self.files], "notes": self.notes}


def _transaction_for(tool: str, stmts: list, autocommit: bool, notes: list, text: str = "") -> bool:
    if autocommit:
        return False
    if GOOSE_NO_TX.search(text):
        notes.append("goose NO TRANSACTION: checked with autocommit rules")
        return False
    hit = next((s for s in stmts if NO_TX.search(outside_bodies(s))), None)
    if hit:
        notes.append("contains a statement that cannot run inside a transaction or manages its own transaction "
                     f"({hit.split()[0].upper()} ...): checked with autocommit rules")
        return False
    return True


def check(repo: str = ".", base: str | None = None, head: str = "HEAD", files: list | None = None,
          globs=DEFAULT_GLOBS, pg_url: str | None = None, stats_url: str | None = None, autocommit: bool = False,
          client: Ekbasis | None = None, lost_threshold: float = LOST_THRESHOLD,
          fail_threshold: float = FAIL_THRESHOLD, psql: str | None = None,
          cache: VerdictCache | None = None, setup_sql: str | None = None) -> GuardVerdict:
    """Check the new migrations of a change. With base: the files added between the merge base and head (the base's
    own migrations build the schema), and the migrations the change edits (their new content on the schema of the
    migrations before them). With files: those files, and the schema is built from the files that sort before them in
    the same folder of the working tree.

    setup_sql: path of a SQL file run by the admin connection before the base's migrations (a schema, a role or an
    extension the platform creates outside the migrations). With base it is read from the BASE ref, never from the
    pull request's head, because it runs with privileges; with files, from the working tree."""
    pg_url = pg_url or os.environ.get("EKBASIS_PG_URL")
    stats_url = stats_url or os.environ.get("EKBASIS_DB_STATS_URL") or None
    notes = []
    edited = []
    if files:
        new = [f.replace("\\", "/") for f in files]
        src_new = src_base = Source(repo, None)
    else:
        if not base:
            raise ValueError("give --base REF or the migration files")
        added, modified = changed_files(repo, base, head)
        new = [f for f in added if is_migration(f, globs)]
        edited = sorted(f for f in modified if is_migration(f, globs))
        src_new, src_base = Source(repo, head), Source(repo, base)
    setup = None
    if setup_sql:
        try:
            setup = src_base.read(setup_sql.replace("\\", "/").removeprefix("./") if src_base.ref else setup_sql)
        except (CannotJudge, OSError) as e:
            return GuardVerdict([FileVerdict(f, tool_of(f), not autocommit, cannot_judge=f"the setup SQL {setup_sql} "
                                 f"cannot be read from the base ({e})") for f in new + edited], notes)
    if not new and not edited:
        return GuardVerdict([], notes)
    if not pg_url:
        return GuardVerdict([FileVerdict(f, tool_of(f), not autocommit, cannot_judge="no scratch PostgreSQL to build "
                             "the schema (set EKBASIS_PG_URL or --pg-url)") for f in new + edited], notes)
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
            scratch = Scratch(pg_url, psql, setup)
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
    for f in edited:
        out.append(_check_edited(f, src_base, src_new, globs, pg_url, psql, setup, stats, autocommit, client,
                                 lost_threshold, fail_threshold, cache, stats_url))
    return GuardVerdict(out, notes)


EDIT_NOTE = ("this pull request edits a migration the base already has: databases that already applied it will not run "
             "the change (and tools that checksum migrations, such as Prisma or golang-migrate's dirty flag, may refuse "
             "to deploy); the verdict is for the new content on a database that has not applied it yet")


def _check_edited(path, src_base, src_new, globs, pg_url, psql, setup, stats, autocommit, client, lt, ft, cache,
                  stats_url) -> FileVerdict:
    """An edited migration: its new content checked on the schema of the base's migrations that sort before it."""
    folder, tool = set_dir(path), tool_of(path)
    try:
        with Scratch(pg_url, psql, setup) as scratch:
            prior = [p for p in src_base.list(folder) if is_migration(p, globs) and tool_of(p) == tool
                     and set_dir(p) == folder and p < path]
            dirty = False
            for p in prior:
                if scratch.db.apply(src_base.read(p), transaction=True) and \
                        scratch.db.apply(src_base.read(p), transaction=False):
                    dirty = True
            v = _check_file(path, tool, src_new.read(path), scratch, stats, autocommit, client, lt, ft, dirty, cache)
    except CannotJudge as e:
        v = FileVerdict(path, tool, not autocommit, cannot_judge=redact(str(e), pg_url, stats_url))
    v.edited = True
    v.notes.append(EDIT_NOTE)
    return v


def _check_file(path, tool, text, scratch, stats, autocommit, client, lt, ft, base_dirty, cache=None) -> FileVerdict:
    stmts = split_sql(text)
    fnotes = []
    tx = _transaction_for(tool, stmts, autocommit, fnotes, text)
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
    decided = None
    if not v.schema_error:          # the probes report only data errors (23502/23503/23505), so an incomplete base
        pfacts, decided = probe_facts(scratch, catalog, stmts, stats, tx, outside_bodies)
        facts += pfacts
    v.state, v.shown = build_state(catalog, stmts, stats, tool, tx, facts, notes=v.notes)
    if decided:                     # decided in code from the replica's statistics (probes)
        v.decided, v.p_lost, v.p_fail, v.risky = decided, 0.0, 1.0, True
        return v
    if len(v.state) > MAX_CHARS:
        v.cannot_judge = f"the migration and its schema are too long to read ({len(v.state):,} characters)"
        return v
    qs = {"lost": Q_LOST, "fails": Q_FAILS}
    if not tx:
        qs["half"] = Q_HALF
    key = VerdictCache.key(text + (f"\n-- setup {scratch.setup_hash}" if getattr(scratch, "setup_hash", None) else ""),
                           catalog, tx, stats is not None, v.state, qs, getattr(client, "url", ""))
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
        norm = {"tables": tables, "enums": catalog.get("enums") or {},
                # what the schema cut can show besides the tables, without oids
                "views": sorted([v.get("schema"), v.get("name"), v.get("kind"), v.get("def") or ""]
                                for v in catalog.get("views") or []),
                "triggers": sorted([names.get(g.get("table")) or "", g.get("def") or ""] for g in catalog.get("triggers") or []),
                "functions": sorted(f.get("def") or "" for f in (catalog.get("functions") or {}).values()),
                "sequences": sorted([q.get("schema"), q.get("name"), names.get(q.get("table")) or "", q.get("col") or ""]
                                    for q in catalog.get("sequences") or []),
                "domains": catalog.get("domains") or {},
                "relations": sorted([r[0], r[1], r[2]] for r in catalog.get("relations") or [])}
        return hashlib.sha256(json.dumps(norm, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    @staticmethod
    def key(text: str, catalog, transaction: bool, stats: bool, state: str, questions: dict, url: str) -> str:
        schema = VerdictCache.schema_hash(catalog)
        parts = {"v": __version__, "cut": CUT_VERSION if PRUNE else 0,
                 "file": hashlib.sha256(text.encode()).hexdigest(), "schema": schema,
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


ON_CODE = ("warn", "block")
DJANGO_NOTE = "Django support is experimental: in its evaluation it missed 6 of 34 risky migrations."
OFFLINE_FAIL = "offline rendering failed"


def check_bundle(bundle: dict, pg_url: str | None = None, stats_url: str | None = None, autocommit: bool = False,
                 client: Ekbasis | None = None, lost_threshold: float = LOST_THRESHOLD,
                 fail_threshold: float = FAIL_THRESHOLD, psql: str | None = None, on_code: str = "warn",
                 cache: VerdictCache | None = None) -> GuardVerdict:
    """Check the migrations of a framework bundle (ekbasis.frameworks.generate): the base schema it carries is loaded
    into a scratch database as the throwaway role, then each migration's SQL is checked as a SQL file is.

    Code that is not SQL (Django RunPython, an Alembic migration that has no offline SQL because it reads the database)
    cannot be foreseen. on_code="warn" (default): the file is listed as "code_not_foreseen", review it by hand, and it
    does not fail the check (it is never "ok"); on_code="block": it is "cannot foresee", which fails closed. A file the
    framework could not render for another reason (not loaded, a crash) is always "cannot foresee". The file's SQL
    still applies to the scratch schema, so the next one sees it."""
    if on_code not in ON_CODE:
        raise ValueError(f"on_code must be one of {', '.join(ON_CODE)}")
    pg_url = pg_url or os.environ.get("EKBASIS_PG_URL")
    stats_url = stats_url or os.environ.get("EKBASIS_DB_STATS_URL") or None
    fw = bundle.get("framework") or "generic"
    notes = list(bundle.get("notes") or [])
    if fw == "django":
        notes.insert(0, DJANGO_NOTE)
    migs = sorted(bundle.get("migrations") or [], key=lambda m: (m.get("order", 0), m.get("path", "")))
    if not migs:
        return GuardVerdict([], notes)
    if not pg_url:
        return GuardVerdict([FileVerdict(m["path"], fw, bool(m.get("transaction", True)), cannot_judge="no scratch "
                             "PostgreSQL to build the schema (set EKBASIS_PG_URL or --pg-url)") for m in migs], notes)
    client = client or Ekbasis()
    stats = None
    if stats_url:
        try:
            stats = read_stats(stats_url, psql)
        except CannotJudge as e:
            notes.append(f"statistics replica not read ({redact(str(e), stats_url)}); row counts unknown")
    out = []
    try:
        with Scratch(pg_url, psql) as scratch:
            # pg_dump's preamble (SET, set_config, CREATE SCHEMA public) errors are harmless; anything else means the
            # schema may be incomplete
            err = scratch.db.apply(bundle.get("base_schema") or "", transaction=False)
            dirty = bool(bundle.get("base_incomplete"))
            if err and not re.search(r'schema "public" already exists|must be owner of|permission denied to set', err):
                dirty = True
                notes.append(f"the base schema did not load cleanly ({err[:160]}); the schema may be incomplete")
            for m in migs:
                sql = m.get("sql") or ""
                tx = bool(m.get("transaction", True)) and not autocommit
                code = None
                if m.get("error") and str(m["error"]).startswith(OFFLINE_FAIL):
                    code = "it reads the database, so it has no offline SQL"
                elif m.get("python_ops") and not m.get("error"):
                    what = ", ".join(sorted(set(m["python_ops"])))[:200]
                    code = f"{'Ruby' if fw == 'rails' else 'Python'} that is not SQL: {what}"
                if code and on_code == "warn":
                    out.append(FileVerdict(m["path"], fw, tx, statements=len(split_sql(sql)), code_not_foreseen=code,
                                           lost_threshold=lost_threshold, fail_threshold=fail_threshold))
                elif m.get("error"):
                    out.append(FileVerdict(m["path"], fw, tx, cannot_judge="the framework could not render it as SQL "
                                           f"({m['error']}); review it by hand"))
                elif code:
                    out.append(FileVerdict(m["path"], fw, tx, statements=len(split_sql(sql)), cannot_judge=(
                        f"it runs code that is not SQL ({code}): a data migration the guard cannot foresee; "
                        "review it by hand")))
                elif not split_sql(sql):
                    v = FileVerdict(m["path"], fw, tx, p_lost=0.0, p_fail=0.0,
                                    lost_threshold=lost_threshold, fail_threshold=fail_threshold)
                    v.notes.append(m.get("note") or "no SQL statements")
                    out.append(v)
                    continue
                else:
                    out.append(_check_file(m["path"], fw, sql, scratch, stats, not tx, client, lost_threshold,
                                           fail_threshold, dirty, cache or VerdictCache()))
                if sql.strip():
                    scratch.db.apply(sql, transaction=tx)        # the next migration sees this one applied
    except CannotJudge as e:
        done = {v.path for v in out}
        out += [FileVerdict(m["path"], fw, True, cannot_judge=redact(str(e), pg_url, stats_url)) for m in migs
                if m["path"] not in done]
    return GuardVerdict(out, notes)


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
    elif result.get("code_not_foreseen"):
        head = ("No data loss or failure foreseen in the SQL. **Review by hand:** at least one migration contains code "
                "the guard cannot foresee.")
    elif not files:
        head = "No new migration files in this pull request."
    else:
        head = "No data loss or failure foreseen."
    lines = [MARKER, "### Ekbasis migration guard", "", head, ""]
    if files:
        lines += ["| Migration | Verdict | Why |", "|---|---|---|"]
        for f in files:
            tag = ("cannot foresee" if f.get("cannot_judge") else "**risky**" if f.get("risky") else
                   "code not foreseen" if f.get("code_not_foreseen") else "ok")
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
