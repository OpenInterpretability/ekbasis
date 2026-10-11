"""0.1.12: the migration guard. Offline: SQL splitting (comments removed, dollar bodies kept), which files are
migrations and how they are grouped, the files a change adds (a throwaway git repository), the state (transactional
and autocommit rules, statistics as aggregates only), the verdicts and exit codes with a fake model, and the pull
request comment. With a PostgreSQL server (EKBASIS_TEST_PG_URL, and psql on PATH or EKBASIS_PSQL): the schema built
from the base's migrations, a migration that fails on the schema alone (decided in code, no model call), statistics
read from an analyzed database without any value reaching the state, and the scratch databases dropped."""
import io
import json
import re
import os
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout

from ekbasis import cli
from ekbasis import migrations as M
from ekbasis.client import Answer

PG = os.environ.get("EKBASIS_TEST_PG_URL")
NEEDS_PG = unittest.skipUnless(PG and M.psql_bin(), "needs EKBASIS_TEST_PG_URL and psql")


class Fake:
    def __init__(self, lost=0.1, fails=0.1, half=0.1):
        self.p = {"lost": lost, "fails": fails, "half": half}
        self.requests = []

    def ask(self, state, questions, read_once=False, images=None):
        self.requests.append((state, sorted(questions)))
        return {k: Answer(value=self.p[k] >= 0.5, confidence=max(self.p[k], 1 - self.p[k]),
                          probabilities={"yes": self.p[k], "no": 1 - self.p[k]}, p_yes=self.p[k]) for k in questions}


def git(repo, *args):
    subprocess.run(["git", "-c", "user.email=t@example.com", "-c", "user.name=t", *args], cwd=repo, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def write(root, path, text):
    os.makedirs(os.path.dirname(os.path.join(root, path)), exist_ok=True)
    with open(os.path.join(root, path), "w") as f:
        f.write(text)


def prisma_repo(root, new: dict):
    git(root, "init", "-q", "-b", "main")
    write(root, "prisma/migrations/001_init/migration.sql",
          'CREATE TABLE "User" (id serial PRIMARY KEY, email text NOT NULL, nick text);\n')
    write(root, "prisma/migrations/migration_lock.toml", 'provider = "postgresql"\n')
    git(root, "add", "-A")
    git(root, "commit", "-qm", "init")
    git(root, "checkout", "-qb", "feature")
    for p, t in new.items():
        write(root, p, t)
    git(root, "add", "-A")
    git(root, "commit", "-qm", "feature")


CATALOG = {"tables": [
    {"oid": 1, "schema": "public", "name": "users", "cols": [
        {"name": "id", "type": "integer", "notnull": True, "default": None, "generated": False, "typname": "int4"},
        {"name": "email", "type": "text", "notnull": False, "default": None, "generated": False, "typname": "text"},
        {"name": "role", "type": "role", "notnull": True, "default": None, "generated": False, "typname": "role"}],
     "cons": [{"name": "users_pkey", "type": "p", "ref": 0, "def": "PRIMARY KEY (id)"}], "idx": None},
    {"oid": 2, "schema": "public", "name": "posts", "cols": [
        {"name": "user_id", "type": "integer", "notnull": True, "default": None, "generated": False, "typname": "int4"}],
     "cons": [{"name": "posts_user_fk", "type": "f", "ref": 1, "def": "FOREIGN KEY (user_id) REFERENCES users(id)"}],
     "idx": None},
    {"oid": 3, "schema": "public", "name": "audit", "cols": [], "cons": [], "idx": None}],
    "enums": {"role": ["admin", "member"]}}


class TestText(unittest.TestCase):
    def test_split_removes_comments_keeps_bodies(self):
        sql = ("/* Warnings:\n  - All the data in the column will be lost.\n*/\n-- drop it\n"
               "ALTER TABLE \"User\" DROP COLUMN \"email\"; -- trailing\n"
               "CREATE FUNCTION f() RETURNS int AS $$ BEGIN -- kept; inside\n RETURN 1; END $$ LANGUAGE plpgsql;\n"
               "INSERT INTO t VALUES ('a;--b', E'c\\'d');")
        st = M.split_sql(sql)
        self.assertEqual(len(st), 3)
        self.assertNotIn("Warnings", " ".join(st))
        self.assertNotIn("drop it", " ".join(st))
        self.assertIn("-- kept; inside", st[1])
        self.assertIn("'a;--b'", st[2])

    def test_which_files_are_migrations(self):
        self.assertTrue(M.is_migration("prisma/migrations/20240101_x/migration.sql"))
        self.assertTrue(M.is_migration("migrations/2024-01-01-x/up.sql"))
        self.assertFalse(M.is_migration("migrations/2024-01-01-x/down.sql"))
        self.assertTrue(M.is_migration("db/migrations/000012_users.up.sql"))
        self.assertFalse(M.is_migration("db/migrations/000012_users.down.sql"))
        self.assertFalse(M.is_migration("persistence/sql/migrations/1_x.mysql.up.sql"))
        self.assertFalse(M.is_migration("src/queries/report.sql"))
        self.assertTrue(M.is_migration("src/queries/report.sql", globs=("src/queries/*.sql",)))
        self.assertEqual(M.tool_of("a/migrations/1/migration.sql"), "prisma")
        self.assertEqual(M.tool_of("a/migrations/1/up.sql"), "diesel")
        self.assertEqual(M.tool_of("db/m/1.up.sql"), "golang-migrate")
        self.assertEqual(M.set_dir("a/migrations/1/migration.sql"), "a/migrations")
        self.assertEqual(M.set_dir("db/m/1.up.sql"), "db/m")

    def test_transaction_rules(self):
        notes = []
        self.assertTrue(M._transaction_for("prisma", ["ALTER TABLE t DROP COLUMN c"], False, notes))
        self.assertFalse(M._transaction_for("prisma", ["ALTER TABLE t DROP COLUMN c"], True, notes))
        self.assertFalse(M._transaction_for("golang-migrate", ["CREATE INDEX CONCURRENTLY i ON t(c)"], False, notes))
        self.assertIn("autocommit", notes[-1])


class TestState(unittest.TestCase):
    def test_transactional_rules_and_no_stats(self):
        st, shown = M.build_state(CATALOG, ['ALTER TABLE users DROP COLUMN email'], None, "prisma", True)
        self.assertIn("runs as one transaction, as Prisma Migrate runs it", st)
        self.assertIn("nothing in the file is applied", st)
        self.assertIn("users: holds production data (row count unknown)", st)
        self.assertEqual(shown, ["users", "posts"])          # the named table and its foreign-key neighbor
        self.assertIn("Enum types: role: 'admin', 'member'", st)
        self.assertIn("Other tables: audit", st)
        self.assertTrue(st.rstrip().endswith("The questions are about the state after all these actions."))

    def test_autocommit_and_stats_are_aggregates(self):
        stats = {"rows": {"public.users": 1200.0, "public.posts": 0.0},
                 "cols": {"public.users.email": [0.25, -1.0], "public.users.role": [0.0, 2.0]}}
        st, _ = M.build_state(CATALOG, ['UPDATE users SET role = \'member\''], stats, "generic", False)
        self.assertIn("each in autocommit mode", st)
        self.assertIn("users: about 1,200 rows; facts: email: about 25% NULL, all values distinct; role: about 2 "
                      "distinct values", st)
        self.assertIn("posts: empty (0 rows)", st)


class TestCheck(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_changed_files(self):
        prisma_repo(self.root, {"prisma/migrations/002_x/migration.sql": "SELECT 1;\n", "README.md": "x\n"})
        added, modified = M.changed_files(self.root, "main")
        self.assertEqual(added, ["README.md", "prisma/migrations/002_x/migration.sql"])
        self.assertEqual(modified, [])

    def test_no_new_migration_is_ok(self):
        prisma_repo(self.root, {"README.md": "x\n"})
        out = io.StringIO()
        with redirect_stdout(out):
            rc = cli.main(["migrate-check", "--repo", self.root, "--base", "main", "--json"])
        self.assertEqual(rc, cli.OK)
        self.assertEqual(json.loads(out.getvalue())["files"], [])

    def test_no_scratch_server_cannot_foresee(self):
        prisma_repo(self.root, {"prisma/migrations/002_x/migration.sql": 'ALTER TABLE "User" DROP COLUMN email;\n'})
        env = dict(os.environ)
        os.environ.pop("EKBASIS_PG_URL", None)
        try:
            out = io.StringIO()
            with redirect_stdout(out):
                rc = cli.main(["migrate-check", "--repo", self.root, "--base", "main", "--json"])
            self.assertEqual(rc, cli.CANNOT_JUDGE)
            d = json.loads(out.getvalue())
            self.assertTrue(d["cannot_foresee"])
            self.assertIn("EKBASIS_PG_URL", d["files"][0]["cannot_foresee"])
            with redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(["migrate-check", "--repo", self.root, "--base", "main", "--fail-open"]),
                                 cli.OK)
        finally:
            os.environ.clear()
            os.environ.update(env)

    def test_bad_base_cannot_foresee(self):
        prisma_repo(self.root, {"README.md": "x\n"})
        with redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(["migrate-check", "--repo", self.root, "--base", "nope"]), cli.CANNOT_JUDGE)

    def test_edited_migration_is_noted(self):
        prisma_repo(self.root, {"prisma/migrations/001_init/migration.sql": 'CREATE TABLE "User" (id int);\n'})
        v = M.check(self.root, base="main", pg_url="postgresql://unused/x", client=Fake())
        self.assertEqual(v.files, [])
        self.assertIn("edits migrations that already exist", v.notes[0])


class TestComment(unittest.TestCase):
    def test_comment(self):
        f1 = M.FileVerdict("prisma/migrations/2/migration.sql", "prisma", True, statements=2, p_lost=0.97, p_fail=0.1,
                           risky=True)
        f2 = M.FileVerdict("db/m/3.up.sql", "golang-migrate", False, statements=1, p_lost=0.01, p_fail=0.02)
        body = M.comment(M.GuardVerdict([f1, f2], ["a note"]).as_json())
        self.assertTrue(body.startswith(M.MARKER))
        self.assertIn("**Risky:**", body)
        self.assertIn("| prisma/migrations/2/migration.sql (prisma, one transaction) | **risky** | may lose existing "
                      "data \\(97%\\) |", body)
        self.assertIn("| db/m/3.up.sql (golang-migrate, autocommit) | ok | no data loss or failure foreseen", body)
        self.assertIn("- a note", body)
        from ekbasis import __version__
        self.assertIn(f"/blob/v{__version__}/docs/MIGRATION_GUARD.md", body)

    def test_reasons_are_decided_in_code(self):
        def v(pl, pf, tx=True, **kw):
            return M.FileVerdict("m.sql", "prisma", tx, p_lost=pl, p_fail=pf, **kw)
        self.assertEqual(v(0.9, 0.8).kind, "fails")
        self.assertEqual(v(0.9, 0.8).reason, "may fail on existing data (80%); nothing in the file would be applied; "
                                             "if it ran, it would also lose data (90%)")
        self.assertEqual(v(0.1, 0.8).reason, "may fail on existing data (80%); nothing in the file would be applied")
        self.assertIn("the statements that do not fail stay applied; may lose existing data (90%)",
                      v(0.9, 0.8, tx=False).reason)
        self.assertEqual(v(0.9, 0.1).reason, "may lose existing data (90%)")
        self.assertEqual(v(0.1, 0.1).kind, "ok")
        s = v(0.0, 1.0, schema_error='column "replay_enabled" does not exist')
        self.assertEqual(s.kind, "schema")
        self.assertIn("an error in the pull request itself", s.reason)
        self.assertIn("missing from the base", s.reason)

    def test_untrusted_text_is_inert(self):
        evil_path = "db/migrations/@octocat [x](https://evil.example) <img src=x onerror=1> `|` @org/team.up.sql"
        f = M.FileVerdict(evil_path, "golang-migrate", True, p_lost=0.0, p_fail=1.0, risky=True,
                          schema_error="relation \"@admins\" does not exist; see https://evil.example/" + "x" * 600)
        body = M.comment(M.GuardVerdict([f], ["@here www.evil.example"]).as_json())
        body = body.rsplit("\n", 1)[0]                    # the footer is ours (it has the docs link)
        self.assertNotIn("<img", body)
        self.assertNotIn("](", body)
        self.assertNotIn("https://", body)
        self.assertNotIn("www.evil", body)
        for mention in ("@octocat", "@org", "@admins", "@here"):
            self.assertNotIn(mention, body)
        row = next(l for l in body.splitlines() if l.startswith("| db/"))
        self.assertEqual(len(re.findall(r"(?<!\\)\|", row)), 4)   # 3 cells: a | in the input does not add one
        self.assertLess(len(row), 900)                     # messages are cut
        self.assertEqual(M.md_safe("a" * 50, 10), "a" * 9 + "…")

    def test_comment_from_cli_output(self):
        d = tempfile.mkdtemp()
        try:
            p = os.path.join(d, "r.json")
            with open(p, "w") as fh:
                fh.write(json.dumps({"risky": True, "judged": False, "cannot_foresee": "server down"}) + "\n")
            out = io.StringIO()
            with redirect_stdout(out):
                M.main(["comment", p])
            self.assertIn("**Cannot foresee**", out.getvalue())
            self.assertIn("- server down", out.getvalue())
        finally:
            shutil.rmtree(d)

    def test_redact(self):
        url = "postgresql://ro:s3cret@db.internal:5432/app"
        self.assertEqual(M.redact(f"could not connect to {url}", url), "could not connect to <url>")
        self.assertEqual(M.redact("password s3cret rejected", url), "password *** rejected")


@NEEDS_PG
class TestPostgres(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def scratch_dbs(self):
        return M.Pg(PG).json("SELECT COALESCE(json_agg(datname), '[]') FROM pg_database WHERE datname LIKE "
                             "'ekbasis_mg_%'")

    def test_schema_from_base_and_verdicts(self):
        prisma_repo(self.root, {
            "prisma/migrations/002_drop/migration.sql": "-- All the data in the column will be lost\n"
                                                        'ALTER TABLE "User" DROP COLUMN "email";\n',
            "prisma/migrations/003_bad/migration.sql": 'ALTER TABLE "User" DROP COLUMN "nope";\n'})
        before = self.scratch_dbs()
        fake = Fake(lost=0.93, fails=0.05)
        v = M.check(self.root, base="main", pg_url=PG, client=fake)
        a, b = v.files
        self.assertTrue(a.risky)
        self.assertIn("email text NOT NULL", a.state)                 # the base's schema was built
        self.assertNotIn("will be lost", a.state)                     # comments removed
        self.assertEqual(len(fake.requests), 1)                       # 003 decided in code, no model call
        self.assertTrue(b.risky)
        self.assertIn('column "nope" of relation "User" does not exist', b.reason)
        self.assertEqual(b.kind, "schema")
        self.assertEqual((b.p_lost, b.p_fail), (0.0, 1.0))
        self.assertEqual(self.scratch_dbs(), before)                  # scratch databases dropped

    def test_statistics_never_values(self):
        stats_db = "ekbasis_test_stats"
        admin = M.Pg(PG)
        admin.run(["-c", f'DROP DATABASE IF EXISTS "{stats_db}"'])
        admin.run(["-v", "ON_ERROR_STOP=1", "-c", f'CREATE DATABASE "{stats_db}"'])
        try:
            replica = M.Pg(M.with_db(PG, stats_db))
            replica.apply('CREATE TABLE "User" (id serial PRIMARY KEY, email text NOT NULL, nick text);'
                          "INSERT INTO \"User\" (email, nick) VALUES ('secret-1@x.org', NULL), ('secret-2@x.org', "
                          "'zz-private'), ('secret-3@x.org', NULL); ANALYZE;")
            prisma_repo(self.root, {"prisma/migrations/002/migration.sql": 'ALTER TABLE "User" ALTER COLUMN nick '
                                                                           "SET NOT NULL;\n"})
            v = M.check(self.root, base="main", pg_url=PG, stats_url=replica.url, client=Fake(fails=0.8))
            st = v.files[0].state
            self.assertIn("User: about 3 rows; facts: id: all values distinct; email: all values distinct; nick: about "
                          "67% NULL, about 1 distinct value", st)
            self.assertNotIn("secret", st)
            self.assertNotIn("zz-private", st)
            self.assertTrue(v.files[0].risky)
            self.assertIn("nothing in the file would be applied", v.files[0].reason)
        finally:
            admin.run(["-c", f'DROP DATABASE IF EXISTS "{stats_db}" WITH (FORCE)'])

    def test_malicious_migration_is_not_run_with_privileges(self):
        marker = os.path.join(tempfile.gettempdir(), "ekbasis_pwned_" + os.urandom(4).hex())
        write(self.root, "db/migrations/0001_init.up.sql", "CREATE TABLE t (a int);\n")
        write(self.root, "db/migrations/0002_evil.up.sql",
              f"COPY (SELECT 1) TO PROGRAM 'touch {marker}';\nCREATE TABLE u (b int);\n")
        write(self.root, "db/migrations/0003_evil.up.sql", "SELECT pg_read_file('/etc/passwd');\n")
        before = self.scratch_roles()
        fake = Fake()
        for f in ("db/migrations/0002_evil.up.sql", "db/migrations/0003_evil.up.sql"):
            v = M.check(self.root, files=[f], pg_url=PG, client=fake)
            self.assertTrue(v.cannot_judge, f)
            self.assertIn("not a superuser", v.files[0].reason)
            self.assertIn("review this one by hand", v.files[0].reason)
            self.assertFalse(v.files[0].reason.startswith("cannot foresee"))   # the verdict column says it already
        self.assertFalse(os.path.exists(marker))
        self.assertEqual(fake.requests, [])                  # never sent to the model
        self.assertEqual(self.scratch_roles(), before)        # the throwaway roles are dropped
        out = io.StringIO()
        with redirect_stdout(out):
            rc = cli.main(["migrate-check", "--repo", self.root, "--pg-url", PG, "db/migrations/0002_evil.up.sql"])
        self.assertEqual(rc, cli.CANNOT_JUDGE)

    def scratch_roles(self):
        return M.Pg(PG).json("SELECT COALESCE(json_agg(rolname), '[]') FROM pg_roles WHERE rolname LIKE 'ekbasis_mg_%'")

    def test_files_mode_autocommit(self):
        write(self.root, "db/migrations/0001_init.up.sql", "CREATE TABLE t (a int, b text);\n")
        write(self.root, "db/migrations/0002_drop.up.sql", "ALTER TABLE t DROP COLUMN b;\nALTER TABLE t ADD c int;\n")
        fake = Fake(lost=0.9, fails=0.1, half=0.1)
        v = M.check(self.root, files=["db/migrations/0002_drop.up.sql"], pg_url=PG, autocommit=True, client=fake)
        self.assertIn("b text", v.files[0].state)
        self.assertIn("each in autocommit mode", v.files[0].state)
        self.assertEqual(fake.requests[0][1], ["fails", "half", "lost"])
        self.assertEqual(v.files[0].p_half, 0.1)


if __name__ == "__main__":
    unittest.main()
