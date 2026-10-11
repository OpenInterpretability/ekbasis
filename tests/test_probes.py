"""Migration guard probes (code-probes): key collisions, missing or present source rows, rows still referenced by a
foreign key, decisions from the replica's statistics; the edited-migration verdict and the setup SQL read from the
base. Most need a PostgreSQL server (EKBASIS_TEST_PG_URL, and psql)."""
import os
import shutil
import tempfile
import unittest

from ekbasis import migrations as M
from ekbasis import probes as PR
from test_migrations import CATALOG, NEEDS_PG, PG, Fake, git, prisma_repo, write

os.environ["EKBASIS_VERDICT_CACHE"] = "off"


class TestMadeUpRows(unittest.TestCase):
    def test_values_are_fixed_and_typed(self):
        users = CATALOG["tables"][0]
        sql = " ".join(PR.insert_made_up(CATALOG, users, 1))
        self.assertIn("900000001::integer", sql)
        self.assertIn("'admin'::role", sql)                      # first enum label
        self.assertNotIn("email", sql)                           # nullable: left NULL

    def test_not_null_reference_uses_a_parent_row(self):
        posts = CATALOG["tables"][1]
        stmt = PR.made_up_row(CATALOG, posts, 2)
        self.assertIn('FROM (SELECT * FROM "public"."users" LIMIT 1) AS p0', stmt)
        self.assertIn('IF NOT EXISTS (SELECT 1 FROM "public"."users")', stmt)
        self.assertIn("no row inserted", stmt)

    def test_blocking_foreign_keys(self):
        users = CATALOG["tables"][0]
        (fk,) = PR.child_fks(CATALOG["tables"], users, "DELETE")
        self.assertEqual((fk[0]["name"], fk[1], fk[2], fk[3]), ("posts", "posts_user_fk", ["user_id"], ["id"]))


BASE = ('CREATE TABLE settings (name text PRIMARY KEY, value text NOT NULL);\n'
        "INSERT INTO settings VALUES ('pwd', 'x');\n"
        "CREATE TABLE parent (id serial PRIMARY KEY, kind text NOT NULL CHECK (kind <> ''));\n"
        'CREATE TABLE child (id serial PRIMARY KEY, parent_id int NOT NULL REFERENCES parent(id), note text);\n')


@NEEDS_PG
class TestProbes(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def facts(self, sql, stats=None):
        with M.Scratch(PG) as sc:
            self.assertIsNone(sc.db.apply(BASE, transaction=True))
            cat = sc.db.json(M.CATALOG)
            return PR.probe_facts(sc, cat, M.split_sql(sql), stats, True, M.outside_bodies)

    def test_key_collision(self):
        f, d = self.facts("INSERT INTO settings (name, value) VALUES ('otel', '{}');")
        self.assertIsNone(d)
        self.assertEqual(len(f), 1)
        self.assertIn("if settings already holds a row with the key that action 1 inserts", f[0])
        self.assertIn('duplicate key value violates unique constraint "settings_pkey"', f[0])
        self.assertEqual(self.facts("INSERT INTO settings VALUES ('otel', '{}') ON CONFLICT DO NOTHING;")[0], [])

    def test_a_file_that_collides_with_itself_or_the_base_is_decided_not_a_fact(self):
        for sql in ("INSERT INTO settings VALUES ('dup', 'a'); INSERT INTO settings VALUES ('dup', 'b');",
                    "INSERT INTO settings VALUES ('pwd', 'y');"):          # 'pwd' is a row the base inserted
            prisma_repo(self.root, {"prisma/migrations/002_base/migration.sql": BASE,
                                    "prisma/migrations/003_new/migration.sql": sql})
            fake = Fake()
            v = M.check(self.root, base="main", pg_url=PG, client=fake)
            f = v.files[-1]
            self.assertEqual(f.kind, "schema")                                  # a real error, decided in code
            self.assertIn("duplicate key", f.reason)
            shutil.rmtree(self.root)
            self.root = tempfile.mkdtemp()

    def test_missing_source_row(self):
        f, _ = self.facts("INSERT INTO settings (name, value) VALUES ('new', "
                          "(SELECT value FROM settings WHERE name = 'pwd')) ON CONFLICT DO NOTHING;")
        self.assertTrue(any("do not hold the rows that earlier migrations inserted" in x and "null value" in x
                            for x in f), f)

    def test_present_source_row(self):
        f, _ = self.facts("CREATE TABLE copy (id int PRIMARY KEY, note text NOT NULL);"
                          "INSERT INTO copy SELECT id, note FROM child;")
        self.assertTrue(any("if child hold rows" in x and 'null value in column "note"' in x for x in f), f)

    def test_row_still_referenced(self):
        f, d = self.facts("DELETE FROM parent WHERE kind <> 'keep';")
        self.assertIsNone(d)
        self.assertTrue(any("if a row of child still references a row that action 1 deletes" in x and
                            'violates foreign key constraint "child_parent_id_fkey"' in x for x in f), f)

    def test_replica_decides_delete_of_every_row(self):
        stats = {"rows": {"public.child": 120.0, "public.parent": 30.0},
                 "cols": {"public.child.parent_id": [0.0, -0.2]}}
        _, d = self.facts("DELETE FROM parent;", stats)
        self.assertIn("deletes every row of parent", d)
        self.assertIn("child holding about 120 rows", d)
        _, d = self.facts("DELETE FROM parent WHERE id = 1;", stats)
        self.assertIsNone(d)

    def test_scratch_databases_dropped(self):
        before = M.Pg(PG).json("SELECT count(*) FROM pg_database WHERE datname LIKE 'ekbasis_mg_%'")
        self.facts("DELETE FROM parent;")
        self.assertEqual(M.Pg(PG).json("SELECT count(*) FROM pg_database WHERE datname LIKE 'ekbasis_mg_%'"), before)


@NEEDS_PG
class TestEditedAndSetup(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_edited_migration_checked_on_the_schema_before_it(self):
        prisma_repo(self.root, {"prisma/migrations/001_init/migration.sql":
                                'CREATE TABLE "User" (id serial PRIMARY KEY, email text NOT NULL, nick text);\n'
                                'ALTER TABLE "User" DROP COLUMN "nope";\n'})
        v = M.check(self.root, base="main", pg_url=PG, client=Fake())
        (f,) = v.files
        self.assertTrue(f.edited and f.risky)
        self.assertEqual(f.kind, "schema")
        self.assertIn('column "nope"', f.reason)
        self.assertIn("databases that already applied it will not run the change", " ".join(f.notes))

    def _supabase_like(self, head_setup=None):
        git(self.root, "init", "-q", "-b", "main")
        write(self.root, "setup.sql", "CREATE SCHEMA IF NOT EXISTS auth AUTHORIZATION :\"guard_role\";\n")
        write(self.root, "migrations/00_init.up.sql", "CREATE TABLE auth.users (id uuid PRIMARY KEY);\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "init")
        git(self.root, "checkout", "-qb", "feature")
        write(self.root, "migrations/01_more.up.sql", "ALTER TABLE auth.users ADD COLUMN email text;\n")
        if head_setup is not None:
            write(self.root, "setup.sql", head_setup)
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "feature")

    def test_setup_sql_builds_the_platform_schema(self):
        self._supabase_like()
        v = M.check(self.root, base="main", pg_url=PG, client=Fake())
        self.assertTrue(v.files[0].cannot_judge)                 # without it: schema "auth" does not exist
        v = M.check(self.root, base="main", pg_url=PG, client=Fake(), setup_sql="setup.sql")
        (f,) = v.files
        self.assertFalse(f.cannot_judge, f.reason)
        self.assertIn("CREATE TABLE auth.users", f.state)

    def test_setup_sql_is_read_from_the_base_never_the_head(self):
        self._supabase_like(head_setup="SELECT 1/0;\n")          # the pull request's version would fail
        v = M.check(self.root, base="main", pg_url=PG, client=Fake(), setup_sql="setup.sql")
        self.assertFalse(v.files[0].cannot_judge, v.files[0].reason)

    def test_setup_sql_missing_on_the_base_is_cannot_foresee(self):
        self._supabase_like()
        v = M.check(self.root, base="main", pg_url=PG, client=Fake(), setup_sql="nope.sql")
        self.assertIn("cannot be read from the base", v.files[0].cannot_judge)


if __name__ == "__main__":
    unittest.main()
