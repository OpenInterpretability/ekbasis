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
import unittest.mock
from contextlib import redirect_stdout

from ekbasis import cli
from ekbasis import migrations as M
from ekbasis.client import Answer

# The other tests count model calls: the verdict cache stays off unless a test gives it a folder (TestVerdictCache).
os.environ["EKBASIS_VERDICT_CACHE"] = "off"
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

    def test_begin_inside_a_body_is_not_a_transaction(self):
        notes = []
        fn = M.split_sql("CREATE FUNCTION f() RETURNS trigger AS $$\nBEGIN\n  RETURN NEW;\nEND;\n$$ LANGUAGE plpgsql;\n"
                         "ALTER TABLE t ADD COLUMN note text DEFAULT 'BEGIN';")
        self.assertTrue(M._transaction_for("generic", fn, False, notes))
        self.assertEqual(notes, [])
        self.assertFalse(M._transaction_for("generic", M.split_sql("BEGIN;\nALTER TABLE t DROP c;\nCOMMIT;"), False, notes))
        self.assertFalse(M._transaction_for("generic", ["CREATE INDEX CONCURRENTLY i ON t(c)"], False, notes))

    def test_goose_up_only_and_no_transaction(self):
        text = ("-- +goose NO TRANSACTION\n-- +goose Up\n-- +goose StatementBegin\nCREATE INDEX CONCURRENTLY i ON t(c);\n"
                "-- +goose StatementEnd\n\n-- +goose Down\nDROP TABLE t;\n")
        up = M.goose_up(text)
        self.assertIn("CONCURRENTLY", up)
        self.assertNotIn("DROP TABLE", up)
        notes = []
        self.assertFalse(M._transaction_for("generic", M.split_sql(up), False, notes, up))
        self.assertIn("goose NO TRANSACTION", notes[-1])
        plain = "-- +goose Up\nALTER TABLE t ADD c int;\n-- +goose Down\nALTER TABLE t DROP c;\n"
        self.assertEqual(M.split_sql(M.goose_up(plain)), ["ALTER TABLE t ADD c int"])
        self.assertTrue(M._transaction_for("generic", M.split_sql(M.goose_up(plain)), False, [], M.goose_up(plain)))
        self.assertEqual(M.goose_up("ALTER TABLE t ADD c int;"), "ALTER TABLE t ADD c int;")


class TestSchemaOnly(unittest.TestCase):
    """0.1.20: "fails" decided in code when no statement can fail because of the rows (the migration already ran on
    the schema): drops, renames, new tables and their indexes, nullable or defaulted new columns, constraints on new
    tables or on columns that are NULL in every row."""

    def test_statements(self):
        yes = ['DROP TABLE "currencies"', 'DROP TABLE IF EXISTS "transfers" CASCADE',
               'ALTER TABLE "a" DROP COLUMN "name"', 'ALTER TABLE t RENAME COLUMN a TO b',
               "ALTER TABLE \"a\" ADD \"s\" account_status DEFAULT 'ok' NOT NULL", 'ALTER TABLE "a" ADD "x" integer',
               'CREATE INDEX "i" ON "t" ("a")', 'ALTER TABLE t ALTER COLUMN c DROP NOT NULL']
        no = ['ALTER TABLE "a" ADD "x" integer NOT NULL', "ALTER TABLE t ALTER COLUMN c SET NOT NULL",
              "ALTER TABLE t ALTER COLUMN c TYPE bigint", "ALTER TABLE t ADD CONSTRAINT f FOREIGN KEY (a) REFERENCES b(id)",
              'CREATE UNIQUE INDEX "i" ON "t" ("a")', "CREATE INDEX i ON t (lower(a))", "CREATE INDEX i ON t (a) WHERE b > 0",
              "CREATE TABLE x AS SELECT * FROM y", "UPDATE t SET a = 1", "DELETE FROM t",
              "ALTER TABLE t ADD COLUMN g int GENERATED ALWAYS AS (a + 1) STORED",
              "ALTER TABLE t DROP COLUMN a, ADD COLUMN b int NOT NULL"]
        for x in yes:
            self.assertTrue(M.schema_only(x), x)
        for x in no:
            self.assertFalse(M.schema_only(x), x)

    def test_plans(self):
        self.assertTrue(M.schema_only_plan(['CREATE TABLE "p" ("id" uuid NOT NULL PRIMARY KEY, "f" uuid NOT NULL)',
                                            'CREATE UNIQUE INDEX "u" ON "p" ("f")',
                                            'ALTER TABLE "p" ADD CONSTRAINT "fk" FOREIGN KEY ("f") REFERENCES "fam" ("id")']))
        self.assertTrue(M.schema_only_plan(['ALTER TABLE "accounts" ADD "pa_id" uuid',
                                            'ALTER TABLE "accounts" ADD CONSTRAINT "fk" FOREIGN KEY ("pa_id") REFERENCES "pa" ("id")']))
        self.assertTrue(M.schema_only_plan(["DO $$\nBEGIN\n IF NOT EXISTS (SELECT 1 FROM pg_type t WHERE t.typname = 's')"
                                            " THEN\n CREATE TYPE \"s\" AS ENUM ('ok', 'error');\n END IF;\nEND\n$$",
                                            'ALTER TABLE "accounts" DROP COLUMN "status"']))
        self.assertFalse(M.schema_only_plan(['ALTER TABLE "accounts" ADD CONSTRAINT "fk" FOREIGN KEY ("old_id") '
                                             'REFERENCES "pa" ("id")']))                  # existing rows are checked
        self.assertFalse(M.schema_only_plan(['CREATE TABLE "t" ("a" int)', 'CREATE UNIQUE INDEX "u" ON "t" ("a")',
                                             'INSERT INTO t SELECT a FROM old']))
        self.assertFalse(M.schema_only_plan([]))


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

    def test_edited_migration_gets_a_verdict(self):
        prisma_repo(self.root, {"prisma/migrations/001_init/migration.sql": 'CREATE TABLE "User" (id int);\n'})
        v = M.check(self.root, base="main", pg_url="postgresql://unused/x", client=Fake())
        (f,) = v.files
        self.assertTrue(f.edited)
        self.assertIn("databases that already applied it will not run the change", " ".join(f.notes))
        self.assertTrue(f.cannot_judge)                     # no scratch server here: fail closed, never silent


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


class TestVerdictCache(unittest.TestCase):
    """The verdict cache (no model call, no quota for a check already answered): what invalidates it, TTL, damage."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.t = [1_000_000.0]
        self.cache = M.VerdictCache(folder=self.dir, now=lambda: self.t[0])
        self.args = dict(text='ALTER TABLE "User" DROP COLUMN email;\n', catalog=CATALOG, transaction=True,
                         stats=False, state="STATE", questions={"lost": M.Q_LOST, "fails": M.Q_FAILS},
                         url="https://openinterp.org/api/v1")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_any_input_change_is_a_miss(self):
        k = M.VerdictCache.key(**self.args)
        self.assertEqual(k, M.VerdictCache.key(**dict(self.args, url="https://openinterp.org/api/v1/")))
        cat2 = json.loads(json.dumps(CATALOG))
        cat2["tables"][0]["cols"][1]["notnull"] = True                         # one schema detail
        changes = [
            dict(text='ALTER TABLE "User" DROP COLUMN nick;\n'),               # one line of the file
            dict(text=self.args["text"] + "\n"),                               # even whitespace
            dict(catalog=cat2),
            dict(transaction=False),
            dict(stats=True),
            dict(state="STATE with new statistics"),
            dict(questions={"lost": M.Q_LOST, "fails": M.Q_FAILS, "half": M.Q_HALF}),
            dict(url="https://ekbasis.internal.example.com"),
        ]
        keys = {M.VerdictCache.key(**dict(self.args, **c)) for c in changes}
        # the same schema in another scratch database (other oids) is the same key
        moved = json.loads(json.dumps(CATALOG))
        for t in moved["tables"]:
            t["oid"] += 1000
            for c in t["cons"]:
                c["ref"] = c["ref"] + 1000 if c["ref"] else 0
        self.assertEqual(M.VerdictCache.key(**dict(self.args, catalog=moved)), k)
        self.assertEqual(len(keys), len(changes))
        self.assertNotIn(k, keys)
        with unittest.mock.patch.object(M, "__version__", "9.9.9"):            # a new client version
            self.assertNotEqual(M.VerdictCache.key(**self.args), k)

    def test_put_get_ttl_and_damage(self):
        k = M.VerdictCache.key(**self.args)
        self.assertIsNone(self.cache.get(k))
        self.cache.put(k, {"lost": 0.9, "fails": 0.1})
        self.assertEqual(self.cache.get(k), {"lost": 0.9, "fails": 0.1})
        self.t[0] += M.VERDICT_TTL_S - 1
        self.assertIsNotNone(self.cache.get(k))
        self.t[0] += 2                                                          # past 30 days: gone
        self.assertIsNone(self.cache.get(k))
        self.assertFalse(os.path.exists(os.path.join(self.dir, f"{k}.json")))
        for bad in ("not json", '{"t": 1000000, "p": {"lost": 7}}', '{"p": {}}'):
            with open(os.path.join(self.dir, f"{k}.json"), "w") as f:
                f.write(bad)
            self.assertIsNone(self.cache.get(k), bad)

    def test_off(self):
        off = M.VerdictCache(off=True)
        off.put("k", {"lost": 0.1})
        self.assertIsNone(off.get("k"))
        self.assertTrue(M.VerdictCache().off)                                  # EKBASIS_VERDICT_CACHE=off (above)

    def test_unwritable_folder_is_a_miss_not_an_error(self):
        c = M.VerdictCache(folder=os.path.join(self.dir, "file"))
        open(os.path.join(self.dir, "file"), "w").close()
        c.put("k", {"lost": 0.1})
        self.assertIsNone(c.get("k"))


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

    def test_verdict_cache_end_to_end(self):
        cache = M.VerdictCache(folder=os.path.join(self.root, ".verdicts"))
        prisma_repo(self.root, {"prisma/migrations/002_drop/migration.sql": 'ALTER TABLE "User" DROP COLUMN nick;\n'})
        fake = Fake(lost=0.93, fails=0.05)
        first = M.check(self.root, base="main", pg_url=PG, client=fake, cache=cache)
        again = M.check(self.root, base="main", pg_url=PG, client=fake, cache=cache)
        self.assertEqual(len(fake.requests), 1)                                # the second check made no call
        self.assertFalse(first.files[0].cached)
        self.assertTrue(again.files[0].cached)
        self.assertEqual((again.files[0].p_lost, again.files[0].risky), (0.93, True))
        self.assertIn("reused", " ".join(again.files[0].notes))
        # thresholds are applied again on the cached answer
        lax = M.check(self.root, base="main", pg_url=PG, client=fake, cache=cache, lost_threshold=0.95)
        self.assertEqual((len(fake.requests), lax.files[0].risky), (1, False))
        # one line of the migration changes: asked again
        write(self.root, "prisma/migrations/002_drop/migration.sql", 'ALTER TABLE "User" DROP COLUMN email;\n')
        git(self.root, "commit", "-qam", "edit")
        M.check(self.root, base="main", pg_url=PG, client=fake, cache=cache)
        self.assertEqual(len(fake.requests), 2)
        # the base's schema changes (same migration file): asked again
        git(self.root, "checkout", "-q", "main")
        write(self.root, "prisma/migrations/001_init/migration.sql",
              'CREATE TABLE "User" (id serial PRIMARY KEY, email text NOT NULL, nick text, age int);\n')
        git(self.root, "commit", "-qam", "base schema")
        git(self.root, "checkout", "-q", "feature")
        M.check(self.root, base="main", pg_url=PG, client=fake, cache=cache)
        self.assertEqual(len(fake.requests), 3)
        # the transaction mode changes: asked again
        M.check(self.root, base="main", pg_url=PG, client=fake, cache=cache, autocommit=True)
        self.assertEqual(len(fake.requests), 4)

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

    def test_fails_decided_by_schema(self):
        write(self.root, "db/migrations/0001_init.up.sql", "CREATE TABLE t (a int, b text);\n")
        write(self.root, "db/migrations/0002_drop.up.sql", "ALTER TABLE t DROP COLUMN b;\n")
        write(self.root, "db/migrations/0003_fill.up.sql", "UPDATE t SET a = a + 1;\n")
        fake = Fake(lost=0.95, fails=0.8)
        v = M.check(self.root, files=["db/migrations/0002_drop.up.sql"], pg_url=PG, client=fake,
                    cache=M.VerdictCache(off=True))
        f = v.files[0]
        self.assertTrue(f.fail_by_schema)
        self.assertEqual((f.p_fail, f.p_fail_model), (0.0, 0.8))
        self.assertEqual(f.kind, "loses")                   # the reason is the loss, not a failure
        self.assertIn("cannot fail on existing data", " ".join(f.notes))
        v = M.check(self.root, files=["db/migrations/0003_fill.up.sql"], pg_url=PG, client=fake,
                    cache=M.VerdictCache(off=True))
        self.assertFalse(v.files[0].fail_by_schema)         # an UPDATE can fail on the rows: the model decides
        self.assertEqual(v.files[0].kind, "fails")

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


def _col(name, typ="integer", typname="int4", notnull=False, default=None):
    return {"name": name, "type": typ, "notnull": notnull, "default": default, "generated": False, "typname": typname}


# 0.1.18: a catalog with what the schema cut reads (views, triggers, functions, sequences, domains, relations)
CUT_CATALOG = {
    "tables": [
        {"oid": "1", "schema": "public", "name": "User", "cols": [
            _col("id", default="nextval('\"User_id_seq\"'::regclass)", notnull=True), _col("email", "text", "text"),
            _col("role", '"Role"', "Role"), _col("age", "pos", "pos")],
         "cons": [{"name": "User_pkey", "type": "p", "ref": "0", "def": "PRIMARY KEY (id)"}], "idx": None},
        {"oid": "2", "schema": "public", "name": "Post", "cols": [_col("id"), _col("authorId", notnull=True)],
         "cons": [{"name": "Post_authorId_fkey", "type": "f", "ref": "1",
                   "def": 'FOREIGN KEY ("authorId") REFERENCES "User"(id) ON DELETE CASCADE'}],
         "idx": ['CREATE INDEX "Post_authorId_idx" ON public."Post" USING btree ("authorId")']},
        {"oid": "3", "schema": "public", "name": "audit", "cols": [_col("what", "text", "text")], "cons": [],
         "idx": None},
        {"oid": "4", "schema": "public", "name": "Team", "cols": [_col("id")], "cons": [], "idx": None},
        {"oid": "5", "schema": "billing", "name": "invoice", "cols": [_col("id")], "cons": [], "idx": None},
        {"oid": "6", "schema": "public", "name": "unrelated", "cols": [_col("x")], "cons": [], "idx": None}],
    "enums": {"Role": ["ADMIN", "MEMBER"], "Color": ["RED"]},
    "views": [{"oid": "10", "schema": "public", "name": "user_emails", "kind": "v",
               "def": ' SELECT id, email FROM "User";', "deps": [["1", "email"], ["1", "id"]]},
              {"oid": "11", "schema": "public", "name": "emails_2", "kind": "v",
               "def": " SELECT email FROM user_emails;", "deps": [["10", "email"]]},
              {"oid": "12", "schema": "public", "name": "teams", "kind": "v", "def": ' SELECT id FROM "Team";',
               "deps": [["4", "id"]]}],
    "triggers": [{"table": "1", "name": "user_audit", "func": "20",
                  "def": 'CREATE TRIGGER user_audit AFTER UPDATE ON public."User" FOR EACH ROW EXECUTE FUNCTION '
                         'log_user()'}],
    "functions": {"20": {"schema": "public", "name": "log_user", "lang": "plpgsql",
                         "def": "CREATE OR REPLACE FUNCTION public.log_user()\n RETURNS trigger\n LANGUAGE plpgsql\n"
                                "AS $function$ BEGIN INSERT INTO audit VALUES (NEW.email); RETURN NEW; END "
                                "$function$\n"}},
    "sequences": [{"schema": "public", "name": "User_id_seq", "table": "1", "col": "id"},
                  {"schema": "public", "name": "free_seq", "table": None, "col": None}],
    "domains": {"pos": "integer CHECK ((VALUE > 0))"},
    "relations": [["public", "User", "r", "1"], ["public", "Post", "r", "2"], ["public", "audit", "r", "3"],
                  ["public", "Team", "r", "4"], ["billing", "invoice", "r", "5"], ["public", "unrelated", "r", "6"],
                  ["public", "Post_authorId_idx", "i", "2"], ["public", "User_pkey", "i", "1"],
                  ["public", "User_id_seq", "S", "1"], ["public", "free_seq", "S", None],
                  ["public", "user_emails", "v", "10"], ["public", "emails_2", "v", "11"],
                  ["public", "teams", "v", "12"]]}


class TestSchemaCut(unittest.TestCase):
    def touched(self, *stmts):
        cut = M.schema_cut(CUT_CATALOG, list(stmts))
        self.assertIsInstance(cut, M.Cut, cut)
        byoid = {t["oid"]: M.disp(t) for t in CUT_CATALOG["tables"]}
        return [byoid[o] for o in cut.touched]

    def test_what_a_statement_touches(self):
        self.assertEqual(self.touched('ALTER TABLE "User" DROP COLUMN email'), ["User", "audit"])   # + its trigger's
        self.assertEqual(self.touched('ALTER TABLE ONLY public."Post" ADD COLUMN x int'), ["Post"])
        self.assertEqual(self.touched("ALTER TABLE IF EXISTS billing.invoice ADD y int"), ["billing.invoice"])
        self.assertEqual(self.touched('CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS i ON "Team" (id)'), ["Team"])
        self.assertEqual(self.touched('DROP INDEX "Post_authorId_idx"'), ["Post"])              # the index's table
        self.assertEqual(self.touched("DROP TABLE IF EXISTS audit, unrelated CASCADE"), ["audit", "unrelated"])
        self.assertEqual(self.touched('TRUNCATE TABLE ONLY "Team"'), ["Team"])
        self.assertEqual(self.touched('DELETE FROM "Post" WHERE id IN (SELECT id FROM "Team")'), ["Post", "Team"])
        self.assertEqual(self.touched('UPDATE "Post" p SET id = t.id FROM "Team" t WHERE p.id = t.id'),
                         ["Post", "Team"])
        self.assertEqual(self.touched('INSERT INTO audit (what) SELECT email FROM "User" u JOIN "Post" p ON '
                                      'p."authorId" = u.id'), ["audit", "User", "Post"])
        self.assertEqual(self.touched('CREATE TABLE "Membership" (team int REFERENCES "Team"(id))'), ["Team"])
        self.assertEqual(self.touched('ALTER TYPE "Role" ADD VALUE \'OWNER\''), ["User", "audit"])  # its columns
        self.assertEqual(self.touched("ALTER DOMAIN pos ADD CHECK (VALUE < 200)"), ["User", "audit"])
        self.assertEqual(self.touched("SELECT setval('\"User_id_seq\"', 10)"), ["User", "audit"])  # sequence owner
        self.assertEqual(self.touched("SELECT extract(epoch FROM now())", "SELECT substring('ab' FROM 1)"), [])
        self.assertEqual(self.touched('WITH gone AS (DELETE FROM "Team" RETURNING id) INSERT INTO audit SELECT '
                                      "id::text FROM gone"), ["Team", "audit"])
        self.assertEqual(self.touched('INSERT INTO "Team" (id) VALUES (1) ON CONFLICT (id) DO UPDATE SET id = 2'),
                         ["Team"])
        self.assertEqual(self.touched('ALTER TABLE "Team" RENAME TO "Squad"', 'ALTER TABLE "Squad" ADD z int'),
                         ["Team"])
        self.assertEqual(self.touched("CREATE TRIGGER t AFTER INSERT ON audit REFERENCING NEW TABLE AS fresh FOR EACH "
                                      "STATEMENT EXECUTE FUNCTION f()",
                                      "CREATE FUNCTION f() RETURNS trigger LANGUAGE sql AS $$ SELECT 1 FROM fresh $$"),
                         ["audit"])
        self.assertEqual(self.touched("CREATE TYPE mood AS ENUM ('a')", "CREATE EXTENSION IF NOT EXISTS citext",
                                      "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'x') THEN "
                                      "CREATE TYPE x AS ENUM ('a'); END IF; END $$"), [])

    def test_state_keeps_what_the_migration_reaches(self):
        notes = []
        st, shown = M.build_state(CUT_CATALOG, ['ALTER TABLE "User" DROP COLUMN email'], None, "prisma", True,
                                  notes=notes)
        self.assertEqual(notes, [])
        self.assertEqual(shown, ["User", "audit", "Post"])         # touched, its trigger's table, then FK neighbor
        self.assertIn("Views that depend on them: user_emails reads User(email, id); emails_2 reads user_emails(email)",
                      st)                                         # and a view on that view
        self.assertNotIn("teams", st)                             # a view on a table it does not reach
        self.assertIn("CREATE TRIGGER user_audit", st)
        self.assertIn("INSERT INTO audit VALUES (NEW.email)", st)  # the trigger's function
        self.assertIn("Sequences: User_id_seq (owned by User.id)", st)
        self.assertIn("Enum types: Role: 'ADMIN', 'MEMBER'", st)
        self.assertNotIn("Color", st)
        self.assertIn("Domains: pos: integer CHECK ((VALUE > 0))", st)
        self.assertIn("Facts: 3 other tables omitted: not touched by this migration and not linked to it by a "
                      "foreign key.", st)
        self.assertNotIn("Other tables", st)
        self.assertNotIn("unrelated", st)

    def test_cannot_cut_falls_back_to_the_named_tables(self):
        cases = {
            "DO $$ BEGIN EXECUTE 'DROP TABLE ' || 'audit'; END $$": "dynamic SQL",
            "CREATE FUNCTION f() RETURNS void LANGUAGE plpgsql AS $$ BEGIN EXECUTE format('x'); END $$": "dynamic SQL",
            "CREATE FUNCTION f() RETURNS int LANGUAGE plpython3u AS $$ return 1 $$": "language plpython3u",
            "COPY audit FROM STDIN": "COPY statement",
            "ALTER TABLE ghost ADD c int": "cannot resolve: ghost",
            "CREATE RULE r AS ON INSERT TO audit DO INSTEAD NOTHING": "CREATE RULE",
            "DROP SCHEMA billing CASCADE": "DROP SCHEMA",
        }
        for sql, why in cases.items():
            notes = []
            st, shown = M.build_state(CUT_CATALOG, [sql], None, "prisma", True, notes=notes)
            self.assertIn(why, notes[0], sql)
            self.assertTrue(notes[0].startswith("schema not cut"), sql)
            self.assertEqual((st, shown), M._named_state(CUT_CATALOG, [sql], None, "prisma", True), sql)
        # a trigger function the parser cannot follow: not cut either
        cat = json.loads(json.dumps(CUT_CATALOG))
        cat["functions"]["20"]["def"] = cat["functions"]["20"]["def"].replace("INSERT INTO audit VALUES (NEW.email)",
                                                                              "EXECUTE 'INSERT INTO ' || TG_ARGV[0]")
        self.assertIn("dynamic SQL", M.schema_cut(cat, ['UPDATE "User" SET email = NULL']))
        # a catalog without dependency information (an older scratch query): not cut
        self.assertEqual(M.schema_cut(CATALOG, ["ALTER TABLE users DROP COLUMN email"]),
                         "the catalog has no dependency information")
        # cut switched off
        notes = []
        self.assertEqual(M.build_state(CUT_CATALOG, ['ALTER TABLE "Team" ADD y int'], None, "prisma", True,
                                       notes=notes, prune=False),
                         M._named_state(CUT_CATALOG, ['ALTER TABLE "Team" ADD y int'], None, "prisma", True))
        self.assertEqual(notes, [])

    def test_neighbors_are_one_line_each(self):
        st, shown = M.build_state(CUT_CATALOG, ['ALTER TABLE "User" ADD z int'], None, "prisma", True)
        self.assertIn('Tables linked to them by a foreign key (their other columns not shown): Post: FOREIGN KEY '
                      '("authorId") REFERENCES "User"(id) ON DELETE CASCADE (authorId NOT NULL)', st)
        self.assertNotIn('CREATE TABLE Post', st)
        self.assertIn("Post: holds production data (row count unknown)", st)
        st, _ = M.build_state(CUT_CATALOG, ['ALTER TABLE "Post" ADD z int'], None, "prisma", True)
        self.assertIn("(their other columns not shown): User (referenced by them)", st)
        cat = json.loads(json.dumps(CUT_CATALOG))
        wide = [_col(f"column_{i}", "character varying(255)", "varchar") for i in range(600)]
        for n in range(30):
            cat["tables"].append({"oid": str(100 + n), "schema": "public", "name": f"child{n}", "idx": None,
                                  "cols": [_col("user_id")] + wide,
                                  "cons": [{"name": f"child{n}_fk", "type": "f", "ref": "1",
                                            "def": 'FOREIGN KEY (user_id) REFERENCES "User"(id)'}]})
            cat["relations"].append(["public", f"child{n}", "r", str(100 + n)])
        st, shown = M.build_state(cat, ['ALTER TABLE "User" ADD z int'], None, "prisma", True)
        self.assertLess(len(st), 10000)                               # 30 wide neighbors, one line each
        self.assertTrue('child29: FOREIGN KEY (user_id) REFERENCES "User"(id)' in st)
        # touched tables too long for the cut: the state of before the cut, with a note
        stmts = [f"ALTER TABLE child{n} ADD q int" for n in range(30)]
        notes = []
        st, _ = M.build_state(cat, stmts, None, "prisma", True, notes=notes)
        self.assertIn("the cut schema is too long", notes[0])
        self.assertEqual(st, M._named_state(cat, stmts, None, "prisma", True)[0])

    def test_cache_key_has_the_cut_version(self):
        args = dict(text="ALTER TABLE t ADD c int;", catalog=CUT_CATALOG, transaction=True, stats=False, state="S",
                    questions={"lost": M.Q_LOST}, url="u")
        k = M.VerdictCache.key(**args)
        with unittest.mock.patch.object(M, "CUT_VERSION", M.CUT_VERSION + 1):
            self.assertNotEqual(M.VerdictCache.key(**args), k)
        with unittest.mock.patch.object(M, "PRUNE", False):
            self.assertNotEqual(M.VerdictCache.key(**args), k)
        cat = json.loads(json.dumps(CUT_CATALOG))
        cat["views"][0]["def"] = " SELECT id FROM \"User\";"               # only a view changed
        self.assertNotEqual(M.VerdictCache.key(**dict(args, catalog=cat)), k)


@NEEDS_PG
class TestSchemaCutPostgres(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_cut_from_the_real_catalog(self):
        write(self.root, "db/migrations/0001_init.up.sql",
              "CREATE TYPE mood AS ENUM ('ok', 'sad');\nCREATE DOMAIN pos AS integer CHECK (VALUE > 0);\n"
              "CREATE TABLE users (id serial PRIMARY KEY, email text, m mood, age pos);\n"
              "CREATE TABLE posts (id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, "
              "user_id int REFERENCES users(id) ON DELETE CASCADE);\n"
              "CREATE TABLE audit (what text);\nCREATE TABLE far (x int);\nCREATE TABLE far2 (y int);\n"
              "CREATE FUNCTION log_user() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN INSERT INTO audit "
              "VALUES (NEW.email); RETURN NEW; END $$;\n"
              "CREATE TRIGGER user_audit AFTER UPDATE ON users FOR EACH ROW EXECUTE FUNCTION log_user();\n"
              "CREATE VIEW user_emails AS SELECT id, email FROM users;\n")
        write(self.root, "db/migrations/0002_drop.up.sql", "ALTER TABLE users DROP COLUMN email CASCADE;\n")
        write(self.root, "db/migrations/0003_dyn.up.sql",
              "DO $$ BEGIN EXECUTE 'ALTER TABLE far ADD z int'; END $$;\n")
        fake = Fake()
        v = M.check(self.root, files=["db/migrations/0002_drop.up.sql"], pg_url=PG, client=fake)
        st = v.files[0].state
        self.assertEqual(v.files[0].shown, ["users", "audit", "posts"])
        self.assertIn('posts: FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE', st)
        self.assertIn("Views that depend on them: user_emails reads users(email, id)", st)
        self.assertIn("CREATE TRIGGER user_audit AFTER UPDATE ON public.users", st)
        self.assertIn("INSERT INTO audit", st)
        self.assertIn("Sequences: users_id_seq (owned by users.id)", st)
        self.assertIn("Enum types: mood: 'ok', 'sad'", st)
        self.assertIn("Domains: pos: integer CHECK ((VALUE > 0))", st)
        self.assertIn("2 other tables omitted", st)
        self.assertNotIn("far", st.split("Actions, in order:")[0])
        self.assertEqual(v.files[0].notes, [])
        # dynamic SQL: the state of before the cut, and a note
        v = M.check(self.root, files=["db/migrations/0003_dyn.up.sql"], pg_url=PG, client=fake)
        self.assertIn("schema not cut (dynamic SQL (EXECUTE))", " ".join(v.files[0].notes))
        self.assertIn("Other tables:", v.files[0].state)
