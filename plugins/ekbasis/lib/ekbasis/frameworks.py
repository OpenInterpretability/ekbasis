"""Migration guard for frameworks that keep migrations as code (0.1.13): Django, Alembic (and Flask-Migrate), Rails
(experimental). Their migrations are Python or Ruby, so the SQL a migration will run must be produced by the framework
itself, which means running the pull request's code. That happens only inside a container this module starts:

1. `docker network create --internal`: a network with no route out. A scratch PostgreSQL joins it.
2. A generator container (the project's image, `--image`) starts on the default network, gets the base and head trees
   as plain files (`git archive`: no .git, no credentials), and runs `--setup` (installing dependencies needs the
   network, as in any CI).
3. The generator is moved to the internal network: from then on it reaches the scratch PostgreSQL and nothing else.
   No secret is ever passed to it: no API key, no token, only the scratch database's URL. The migrations run as a
   throwaway role that is not a superuser (as in ekbasis.migrations.Scratch).
4. At the base tree, the framework migrates the scratch database (`manage.py migrate`, `alembic upgrade head`,
   `bin/rails db:migrate`), and `pg_dump --schema-only` (run in the PostgreSQL container) gives the base schema.
5. At the head tree, the framework renders each new migration as SQL: Django `sqlmigrate`, Alembic offline
   `upgrade A:B --sql`; Rails has no offline mode, so the new migrations run on the base schema (no rows) with SQL
   logging. Python or Ruby that is not SQL (Django RunPython, an Alembic migration that reads the database, a Rails
   migration that uses models) is reported, and the guard answers "cannot foresee" for that file, with the reason.
6. Everything is removed: containers and network.

The result is a bundle (JSON): the base schema and, per new migration, its SQL, whether it runs in one transaction, and
what could not be rendered. `ekbasis migrate-check --bundle` checks a bundle the same way it checks SQL files; the API
key is only needed there, never while the pull request's code runs.

Inside the generator, this module runs with the standard library only, under the project's own Python (Django and
Alembic renderers) or as a Ruby script given to `bin/rails runner`.
"""
from __future__ import annotations

import fnmatch
import io
import json
import os
import re
import secrets
import shlex
import subprocess
import sys
import tarfile

FRAMEWORKS = ("django", "alembic", "rails")
GLOBS = {
    "django": ("*/migrations/[0-9]*.py",),
    "alembic": ("*/versions/*.py", "*migrations/versions/*.py"),
    "rails": ("db/migrate/*.rb", "*/db/migrate/*.rb"),
}
MIGRATE = {
    "django": "python manage.py migrate --noinput",
    "alembic": "alembic upgrade head",
    "rails": "bin/rails db:migrate",
}
JSON_MARK = "EKBASIS-JSON:"
PG_IMAGE = "postgres:16"
DOCKER_TIMEOUT = 1800


def is_framework_migration(framework: str, path: str, globs=None) -> bool:
    p = path.replace("\\", "/")
    return any(fnmatch.fnmatch(p, g) for g in (globs or GLOBS[framework])) and not p.endswith("__init__.py")


# ---------------------------------------------------------------- inside the generator: renderers

def _strip_tx(sql: str) -> tuple:
    """(sql without a wrapping BEGIN; ... COMMIT;, whether it was wrapped)."""
    s = sql.strip()
    m = re.match(r"(?is)^\s*BEGIN\s*;(.*)COMMIT\s*;\s*$", s)
    return (m.group(1).strip(), True) if m else (s, False)


def django_main() -> None:
    """Run inside `python manage.py shell -c`: render EKBASIS_PATHS (repo-relative paths, JSON) with sqlmigrate."""
    import contextlib
    from django.core.management import call_command
    from django.db.migrations.loader import MigrationLoader

    paths = json.loads(os.environ["EKBASIS_PATHS"])
    root = os.path.realpath(os.environ["EKBASIS_ROOT"])
    loader = MigrationLoader(None, ignore_no_migrations=True)
    byfile = {}
    for (app, name), mig in loader.disk_migrations.items():
        f = getattr(sys.modules.get(type(mig).__module__) or sys.modules.get(mig.__module__), "__file__", None)
        if f:
            byfile[os.path.relpath(os.path.realpath(f), root).replace(os.sep, "/")] = (app, name, mig)
    order = {}
    for leaf in loader.graph.leaf_nodes():
        for node in loader.graph.forwards_plan(leaf):
            order.setdefault(node, len(order))
    out = []
    for p in paths:
        hit = byfile.get(p)
        if not hit:
            out.append({"path": p, "name": None, "sql": "", "transaction": True, "python_ops": [], "order": 10 ** 9,
                        "error": "Django does not load this file as a migration (is its app in INSTALLED_APPS?)"})
            continue
        app, name, mig = hit
        pyops = []

        def walk(ops):
            for o in ops:
                cn = type(o).__name__
                if cn == "SeparateDatabaseAndState":
                    walk(o.database_operations)
                elif cn == "RunPython" or any(c.__name__ == "RunPython" for c in type(o).__mro__):
                    pyops.append(cn)

        walk(mig.operations)
        buf, err = io.StringIO(), None
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                call_command("sqlmigrate", app, name, stdout=buf, no_color=True)
        except Exception as e:  # noqa: BLE001 - any failure is reported, never raised
            err = f"{type(e).__name__}: {e}"[:500]
        raw = buf.getvalue()
        if "Raw Python operation" in raw or "CANNOT BE WRITTEN AS SQL" in raw:
            pyops = pyops or ["RunPython"]
        sql, wrapped = _strip_tx(raw)
        out.append({"path": p, "name": f"{app}.{name}", "sql": sql, "transaction": bool(getattr(mig, "atomic", True))
                    and wrapped, "python_ops": pyops, "order": order.get((app, name), 10 ** 9), "error": err})
    out.sort(key=lambda r: (r["order"], r["path"]))
    print(JSON_MARK + json.dumps(out))


REV = re.compile(r"""^\s*revision\s*(?::\s*\w+\s*)?=\s*['"]([^'"]+)['"]""", re.M)
DOWN = re.compile(r"""^\s*down_revision\s*(?::[^=]+)?=\s*(None|['"][^'"]*['"]|\(.*?\)|\[.*?\])""", re.M | re.S)


def alembic_revisions(text: str) -> tuple:
    """(revision, down_revision or None, is_merge) read from the file's text, without importing it."""
    r = REV.search(text)
    d = DOWN.search(text)
    rev = r.group(1) if r else None
    if not d or d.group(1) == "None":
        return rev, None, False
    v = d.group(1)
    ids = re.findall(r"""['"]([^'"]+)['"]""", v)
    return rev, (ids[0] if ids else None), len(ids) > 1


def alembic_main(paths: list, root: str, command: str) -> None:
    """Render each new revision with offline mode: `<command> upgrade --sql <down>:<rev>` (alembic or `flask db`)."""
    revs = []
    for p in paths:
        with open(os.path.join(root, p), encoding="utf-8", errors="replace") as fh:
            rev, down, merge = alembic_revisions(fh.read())
        revs.append({"path": p, "rev": rev, "down": down, "merge": merge})
    ids = {r["rev"] for r in revs}
    order, seen = [], set()
    while len(order) < len(revs):            # base first: a revision comes after the one it builds on
        progressed = False
        for r in revs:
            if r["rev"] not in seen and (r["down"] not in ids or r["down"] in seen):
                order.append(r)
                seen.add(r["rev"])
                progressed = True
        if not progressed:
            order += [r for r in revs if r["rev"] not in seen]
            break
    out = []
    for i, r in enumerate(order):
        rec = {"path": r["path"], "name": r["rev"], "sql": "", "transaction": True, "python_ops": [], "order": i,
               "error": None}
        if not r["rev"]:
            rec["error"] = "no `revision = ...` found in the file"
        elif r["merge"]:
            rec["sql"] = ""
            rec["note"] = "a merge revision (joins branches; no schema change of its own)"
        else:
            rng = f"{r['down']}:{r['rev']}" if r["down"] else r["rev"]
            try:
                p = subprocess.run(shlex.split(command) + ["upgrade", "--sql", rng], cwd=os.getcwd(),
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="replace",
                                   timeout=600)
                if p.returncode != 0:
                    tail = [l for l in p.stderr.strip().splitlines() if l.strip()][-3:]
                    rec["error"] = ("offline rendering failed (a migration that reads the database, e.g. with "
                                    "op.get_bind(), cannot be written as SQL): " + " | ".join(tail))[:500]
                else:
                    lines = [l for l in p.stdout.splitlines() if not re.search(r"\balembic_version\b", l)]
                    rec["sql"], rec["transaction"] = _strip_tx("\n".join(lines))
            except (OSError, subprocess.TimeoutExpired) as e:
                rec["error"] = f"{type(e).__name__}: {e}"[:500]
        out.append(rec)
    print(JSON_MARK + json.dumps(out))


# Rails (experimental): run the pending migrations on the base schema (no rows) and keep the SQL they send. Statements
# that only read, and Rails' own bookkeeping, are dropped. A migration whose Ruby goes beyond the schema DSL (models,
# loops, find_each/update_all on classes) is reported: with no rows it does nothing here, so its effect on data cannot
# be foreseen.
RAILS_SCRIPT = r'''
require "json"
paths = JSON.parse(ENV.fetch("EKBASIS_PATHS"))
versions = paths.map { |p| File.basename(p)[/\A(\d+)_/, 1] }
sqls = Hash.new { |h, k| h[k] = [] }
current = nil
ActiveSupport::Notifications.subscribe("sql.active_record") do |*, payload|
  sql = payload[:sql].to_s
  next if current.nil? || payload[:name] == "SCHEMA" || sql =~ /\A\s*(SELECT|SHOW|SET|BEGIN|COMMIT|SAVEPOINT|RELEASE|ROLLBACK)\b/i
  next if sql =~ /schema_migrations|ar_internal_metadata/
  sqls[current] << sql
end
ctx = ActiveRecord::Base.connection_pool.migration_context
out = []
ctx.migrations.select { |m| versions.include?(m.version.to_s) }.sort_by(&:version).each do |m|
  path = paths.find { |p| File.basename(p).start_with?("#{m.version}_") }
  current = m.version
  rec = { "path" => path, "name" => m.name, "transaction" => !m.disable_ddl_transaction, "python_ops" => [], "order" => m.version.to_i, "error" => nil }
  begin
    ctx.run(:up, m.version)
  rescue StandardError => e
    rec["error"] = "#{e.class}: #{e.message}"[0, 500]
  end
  rec["sql"] = sqls[m.version].map { |s| s.strip.sub(/;\s*\z/, "") + ";" }.join("\n")
  out << rec
end
puts "EKBASIS-JSON:" + JSON.generate(out)
'''

RAILS_DSL = {
    "create_table", "drop_table", "rename_table", "change_table", "create_join_table", "drop_join_table",
    "add_column", "remove_column", "remove_columns", "rename_column", "change_column", "change_column_null",
    "change_column_default", "change_column_comment", "change_table_comment", "add_index", "remove_index",
    "rename_index", "add_reference", "remove_reference", "add_belongs_to", "remove_belongs_to", "add_foreign_key",
    "remove_foreign_key", "add_timestamps", "remove_timestamps", "add_check_constraint", "remove_check_constraint",
    "enable_extension", "disable_extension", "create_enum", "drop_enum", "rename_enum", "add_enum_value",
    "execute", "reversible", "revert", "safety_assured", "up_only", "say", "say_with_time", "suppress_messages",
    "def", "end", "t", "dir", "class", "disable_ddl_transaction!", "validate_foreign_key", "add_unique_constraint",
    "remove_unique_constraint", "add_exclusion_constraint", "remove_exclusion_constraint", "create_schema",
    "drop_schema", "transaction", "if", "else", "unless", "return", "puts",
}


def rails_ruby_ops(text: str) -> list:
    """Ruby in a Rails migration beyond the schema DSL: calls on constants (models), and iteration."""
    out = []
    for line in text.splitlines():
        s = line.split("#", 1)[0].strip()
        if not s:
            continue
        if re.search(r"\b[A-Z]\w*(::\w+)*\.(find_each|find_in_batches|in_batches|where|update_all|delete_all|all|"
                     r"each|create!?|update!?|destroy_all|find|find_by|reset_column_information|unscoped)\b", s):
            out.append(s[:80])
        elif re.search(r"\.(each|map|find_each|in_batches)\s*(\{|do\b)", s):
            out.append(s[:80])
    return out


# ---------------------------------------------------------------- on the host: the containers

class GenError(RuntimeError):
    pass


def _docker(*args, input_bytes=None, timeout=DOCKER_TIMEOUT, check=True) -> subprocess.CompletedProcess:
    try:
        p = subprocess.run(["docker", *args], input=input_bytes, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           timeout=timeout)
    except FileNotFoundError:
        raise GenError("docker is not installed: the framework adapters run the pull request's code only inside a "
                       "container") from None
    except subprocess.TimeoutExpired:
        raise GenError(f"docker {args[0]} timed out") from None
    if check and p.returncode != 0:
        raise GenError(f"docker {args[0]} failed: {p.stderr.decode(errors='replace').strip()[-400:]}")
    return p


def _tree_tar(repo: str, ref: str, prefix: str) -> bytes:
    p = subprocess.run(["git", "archive", "--format=tar", f"--prefix={prefix}/", ref], cwd=repo, stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, timeout=600)
    if p.returncode != 0:
        raise GenError(f"git archive {ref} failed: {p.stderr.decode(errors='replace').strip()[:300]}")
    return p.stdout


def _client_tar() -> bytes:
    """This package, standard library only, for the renderers inside the generator."""
    here = os.path.dirname(os.path.abspath(__file__))
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as t:
        for f in sorted(os.listdir(here)):
            if f.endswith(".py"):
                t.add(os.path.join(here, f), arcname=f"opt/ekbasis_client/ekbasis/{f}")
    return buf.getvalue()


def discover(framework: str, repo: str, base: str, head: str = "HEAD", globs=None) -> tuple:
    from . import migrations as M
    added, modified = M.changed_files(repo, base, head)
    return ([f for f in added if is_framework_migration(framework, f, globs)],
            [f for f in modified if is_framework_migration(framework, f, globs)])


def generate(framework: str, repo: str = ".", base: str | None = None, head: str = "HEAD", paths: list | None = None,
             image: str | None = None, setup: str | None = None, workdir: str = ".", env: dict | None = None,
             migrate: str | None = None, command: str | None = None, pg_image: str = PG_IMAGE,
             log=None) -> dict:
    """The bundle for the new migrations of a change (see the module doc). paths: the files to render (default: the
    framework's migrations added between the merge base of base and head)."""
    if framework not in FRAMEWORKS:
        raise ValueError(f"framework must be one of {', '.join(FRAMEWORKS)}")
    log = log or (lambda m: print(m, file=sys.stderr))
    edited = []
    if paths is None:
        if not base:
            raise ValueError("give --base REF or the migration files")
        paths, edited = discover(framework, repo, base, head)
    bundle = {"framework": framework, "base": base, "head": head, "base_schema": "", "migrations": [], "notes": []}
    if edited:
        bundle["notes"].append("edits migrations that already exist on the base (" + ", ".join(edited[:5]) + "): a "
                               "database that already applied them will not run the change")
    if not paths:
        return bundle
    image = image or ("ruby:3.3" if framework == "rails" else "python:3.12-slim")
    tag = secrets.token_hex(4)
    net, pg, gen = f"ekbasis-mg-net-{tag}", f"ekbasis-mg-pg-{tag}", f"ekbasis-mg-gen-{tag}"
    role, pw, db = f"ekbasis_mg_{tag}", secrets.token_hex(16), f"ekbasis_mg_{tag}"
    started = []
    try:
        _docker("network", "create", "--internal", net)
        started.append(("network", net))
        _docker("run", "-d", "--rm", "--name", pg, "--network", net, "-e", "POSTGRES_HOST_AUTH_METHOD=trust", pg_image)
        started.append(("container", pg))
        _docker("run", "-d", "--rm", "--name", gen, "--entrypoint", "sleep", image, "infinity")
        started.append(("container", gen))
        log(f"generator {image}: copying the base and head trees")
        base_ref = base if base else head
        if base:
            rc, mb = subprocess.getstatusoutput(f"git -C {shlex.quote(repo)} merge-base {shlex.quote(base)} "
                                                f"{shlex.quote(head)}")
            base_ref = mb.strip() if rc == 0 else base
        for ref, prefix in ((base_ref, "src/base"), (head, "src/head")):
            _docker("exec", "-i", gen, "tar", "-x", "-C", "/", input_bytes=_tree_tar(repo, ref, prefix))
        if framework != "rails":
            _docker("exec", "-i", gen, "tar", "-x", "-C", "/", input_bytes=_client_tar())
        wd = lambda side: "/" + "/".join(x for x in (f"src/{side}", workdir.strip("/")) if x and x != ".")
        if setup:
            log("setup (with network): " + setup)
            p = _docker("exec", "-w", wd("head"), gen, "sh", "-c", setup, check=False)
            if p.returncode != 0:
                raise GenError("setup failed: " + p.stderr.decode(errors="replace").strip()[-400:])
        # from here on: no network except the scratch PostgreSQL, no secret
        _docker("network", "disconnect", "bridge", gen)
        _docker("network", "connect", net, gen)
        probe = _docker("exec", gen, "sh", "-c", "getent hosts pypi.org >/dev/null 2>&1 && echo reachable "
                        "|| echo isolated", check=False)
        bundle["isolation"] = "no route out" if b"isolated" in probe.stdout else "NOT isolated"
        if bundle["isolation"] != "no route out":
            raise GenError("the generator container still reaches the network after it was moved to the internal "
                           "network; refusing to run the pull request's code")
        for _ in range(60):
            if _docker("exec", pg, "pg_isready", "-U", "postgres", "-q", check=False).returncode == 0:
                break
            subprocess.run(["sleep", "1"])
        _docker("exec", pg, "psql", "-U", "postgres", "-v", "ON_ERROR_STOP=1", "-q",
                "-c", f"CREATE ROLE \"{role}\" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS "
                      f"PASSWORD '{pw}'",
                "-c", f'CREATE DATABASE "{db}" OWNER "{role}"')
        url = f"postgresql://{role}:{pw}@{pg}:5432/{db}"
        dbenv = {"DATABASE_URL": url, "DB_HOST": pg, "DB_PORT": "5432", "DB_NAME": db, "DB_USER": role,
                 "DB_PASSWORD": pw, "PGHOST": pg, "PGPORT": "5432", "PGDATABASE": db, "PGUSER": role,
                 "PGPASSWORD": pw, "POSTGRES_HOST": pg, "POSTGRES_PORT": "5432", "POSTGRES_DB": db,
                 "POSTGRES_USER": role, "POSTGRES_PASSWORD": pw, "EKBASIS_DB_URL": url,
                 "PYTHONPATH": "/opt/ekbasis_client", "RAILS_ENV": "development", "PYTHONDONTWRITEBYTECODE": "1"}
        for k, v in (env or {}).items():
            dbenv[k] = v.replace("${EKBASIS_DB_URL}", url)
        eargs = [x for k, v in dbenv.items() for x in ("-e", f"{k}={v}")]
        log("base: " + (migrate or MIGRATE[framework]))
        p = _docker("exec", *eargs, "-w", wd("base"), gen, "sh", "-c", migrate or MIGRATE[framework], check=False)
        if p.returncode != 0:
            bundle["notes"].append("the base's migrations did not all apply on the scratch database (" +
                                   _redact(p.stderr.decode(errors="replace").strip()[-300:], pw) +
                                   "); the schema may be incomplete")
            bundle["base_incomplete"] = True
        d = _docker("exec", pg, "pg_dump", "-U", "postgres", "--schema-only", "--no-owner", "--no-privileges",
                    "--no-comments", db)
        bundle["base_schema"] = d.stdout.decode(errors="replace")
        rels = json.dumps(paths)
        renv = eargs + ["-e", f"EKBASIS_PATHS={rels}", "-e", "EKBASIS_ROOT=/src/head"]
        if framework == "django":
            cmd = ["python", "manage.py", "shell", "-c", "from ekbasis.frameworks import django_main; django_main()"]
        elif framework == "alembic":
            cmd = ["python", "-c", "import json, os, sys; from ekbasis.frameworks import alembic_main; "
                   f"alembic_main(json.loads(os.environ['EKBASIS_PATHS']), '/src/head', {command or 'alembic'!r})"]
        else:
            _docker("exec", "-i", gen, "sh", "-c", "cat > /tmp/ekbasis_rails.rb", input_bytes=RAILS_SCRIPT.encode())
            cmd = ["bin/rails", "runner", "/tmp/ekbasis_rails.rb"]
        log("head: rendering " + str(len(paths)) + " migration(s)")
        p = _docker("exec", *renv, "-w", wd("head"), gen, *cmd, check=False)
        outl = [l for l in p.stdout.decode(errors="replace").splitlines() if l.startswith(JSON_MARK)]
        if not outl:
            raise GenError("rendering failed: " + _redact(p.stderr.decode(errors="replace").strip()[-500:], pw))
        migs = json.loads(outl[-1][len(JSON_MARK):])
        if framework == "rails":
            for m in migs:
                _, text = _read_ref(repo, head, m["path"])
                m["python_ops"] = rails_ruby_ops(text)
        for m in migs:
            if m.get("error"):
                m["error"] = _redact(m["error"], pw)
        missing = [x for x in paths if x not in {m["path"] for m in migs}]
        migs += [{"path": x, "name": None, "sql": "", "transaction": True, "python_ops": [], "order": 10 ** 9,
                  "error": "the framework did not render this file"} for x in missing]
        bundle["migrations"] = migs
        return bundle
    finally:
        for kind, name in reversed(started):
            if kind == "container":
                _docker("rm", "-f", name, check=False)
            else:
                _docker("network", "rm", name, check=False)


def _redact(text: str, pw: str) -> str:
    return text.replace(pw, "***")


def _read_ref(repo: str, ref: str, path: str) -> tuple:
    p = subprocess.run(["git", "show", f"{ref}:{path}"], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       text=True, errors="replace")
    return p.returncode, p.stdout


def main(argv=None) -> int:
    """`python -m ekbasis.frameworks alembic-render` (inside the generator; used by generate)."""
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["alembic-render"]:
        alembic_main(json.loads(os.environ["EKBASIS_PATHS"]), os.environ.get("EKBASIS_ROOT", "/src/head"),
                     argv[1] if len(argv) > 1 else "alembic")
        return 0
    print("usage: python -m ekbasis.frameworks alembic-render [COMMAND]", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
