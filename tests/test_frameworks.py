"""0.1.13: the migration guard for Django, Alembic and Rails. Offline: which files are migrations, the BEGIN/COMMIT
wrapper, Alembic revisions read without importing the file, Ruby beyond the Rails schema DSL. With PostgreSQL
(EKBASIS_TEST_PG_URL): a bundle is checked like SQL files, and Python that is not SQL is "cannot foresee". With docker
(EKBASIS_TEST_DOCKER=1, and network for the setup step): tiny Django and Alembic projects (tests/data/frameworks) are
rendered inside the isolated generator, which has no route out once the setup is done."""
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout

from ekbasis import cli
from ekbasis import frameworks as FW
from ekbasis import migrations as M
from ekbasis.client import Answer

PG = os.environ.get("EKBASIS_TEST_PG_URL")
NEEDS_PG = unittest.skipUnless(PG and M.psql_bin(), "needs EKBASIS_TEST_PG_URL and psql")
NEEDS_DOCKER = unittest.skipUnless(os.environ.get("EKBASIS_TEST_DOCKER") == "1" and shutil.which("docker"),
                                   "needs EKBASIS_TEST_DOCKER=1 and docker")
DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "frameworks")


class Fake:
    def __init__(self, lost=0.1, fails=0.1):
        self.p = {"lost": lost, "fails": fails, "half": 0.1}
        self.requests = []

    def ask(self, state, questions, read_once=False, images=None):
        self.requests.append(state)
        return {k: Answer(value=self.p[k] >= 0.5, confidence=0.9, probabilities={}, p_yes=self.p[k]) for k in questions}


class TestOffline(unittest.TestCase):
    def test_files(self):
        self.assertTrue(FW.is_framework_migration("django", "hc/api/migrations/0042_x.py"))
        self.assertFalse(FW.is_framework_migration("django", "hc/api/migrations/__init__.py"))
        self.assertFalse(FW.is_framework_migration("django", "hc/api/models.py"))
        self.assertTrue(FW.is_framework_migration("alembic", "migrations/versions/4f2e_add.py"))
        self.assertTrue(FW.is_framework_migration("rails", "db/migrate/20240101000000_add_x.rb"))

    def test_strip_tx(self):
        self.assertEqual(FW._strip_tx("BEGIN;\nALTER TABLE t DROP COLUMN c;\nCOMMIT;\n"),
                         ("ALTER TABLE t DROP COLUMN c;", True))
        self.assertEqual(FW._strip_tx("CREATE INDEX CONCURRENTLY i ON t (c);"),
                         ("CREATE INDEX CONCURRENTLY i ON t (c);", False))

    def test_alembic_revisions(self):
        self.assertEqual(FW.alembic_revisions('revision = "b2"\ndown_revision = "a1"\n'), ("b2", "a1", False))
        self.assertEqual(FW.alembic_revisions("revision: str = 'b2'\ndown_revision: Union[str, None] = 'a1'\n"),
                         ("b2", "a1", False))
        self.assertEqual(FW.alembic_revisions('revision = "m"\ndown_revision = ("a1", "b2")\n'), ("m", "a1", True))
        self.assertEqual(FW.alembic_revisions('revision = "a1"\ndown_revision = None\n'), ("a1", None, False))

    def test_rails_is_off_by_default(self):
        env = dict(os.environ)
        os.environ.pop("EKBASIS_EXPERIMENTAL_RAILS", None)
        try:
            with self.assertRaises(ValueError):
                FW.generate("rails", repo=".", paths=["db/migrate/1_x.rb"])
        finally:
            os.environ.clear()
            os.environ.update(env)

    def test_rails_ruby_ops(self):
        dsl = "class X < ActiveRecord::Migration[7.1]\n  def change\n    remove_column :users, :email, :string\n  end\nend\n"
        self.assertEqual(FW.rails_ruby_ops(dsl), [])
        data = ("class X < ActiveRecord::Migration[7.1]\n  def up\n    User.find_each { |u| u.update!(name: u.email) }\n"
                "    remove_column :users, :email\n  end\nend\n")
        self.assertEqual(len(FW.rails_ruby_ops(data)), 1)


BASE_SCHEMA = """SET statement_timeout = 0;
SELECT pg_catalog.set_config('search_path', '', false);
CREATE TABLE public.shop_customer (id integer NOT NULL, name character varying(100) NOT NULL,
  email character varying(200));
ALTER TABLE ONLY public.shop_customer ADD CONSTRAINT shop_customer_pkey PRIMARY KEY (id);
"""


@NEEDS_PG
class TestBundle(unittest.TestCase):
    def bundle(self):
        return {"framework": "django", "base_schema": BASE_SCHEMA, "notes": [], "migrations": [
            {"path": "shop/migrations/0002_remove_email.py", "name": "shop.0002", "order": 1, "transaction": True,
             "python_ops": [], "error": None, "sql": 'ALTER TABLE "shop_customer" DROP COLUMN "email" CASCADE;'},
            {"path": "shop/migrations/0003_fill_names.py", "name": "shop.0003", "order": 2, "transaction": True,
             "python_ops": ["RunPython"], "error": None, "sql": ""},
            {"path": "shop/migrations/0004_bad.py", "name": "shop.0004", "order": 3, "transaction": True,
             "python_ops": [], "error": "ImportError: no module named x", "sql": ""},
            {"path": "versions/c3_read.py", "name": "c3", "order": 4, "transaction": True, "python_ops": [],
             "error": "offline rendering failed (a migration that reads the database ...): x", "sql": ""}]}

    def test_check_bundle_warn(self):
        fake = Fake(lost=0.95)
        v = M.check_bundle(self.bundle(), pg_url=PG, client=fake, cache=M.VerdictCache(off=True))
        a, b, c, d = v.files
        self.assertTrue(a.risky)
        self.assertIn("email character varying(200)", a.state)      # the base schema came from the bundle
        self.assertIn("as Django runs it", a.state)                   # the framework's rule
        self.assertEqual(len(fake.requests), 1)
        # code that is not SQL: listed for review by hand, not risky, never "ok"
        self.assertEqual(b.kind, "code_not_foreseen")
        self.assertFalse(b.risky)
        self.assertIsNone(b.cannot_judge)
        self.assertIn("contains code the guard cannot foresee (Python that is not SQL: RunPython)", b.reason)
        self.assertIn("review it by hand", b.reason)
        self.assertEqual(d.kind, "code_not_foreseen")
        self.assertIn("no offline SQL", d.reason)
        # a file the framework could not render for another reason still fails closed
        self.assertEqual(c.kind, "cannot_foresee")
        self.assertIn("could not render it as SQL", c.reason)
        self.assertTrue(v.code_not_foreseen)
        body = M.comment(v.as_json())
        self.assertIn("| code not foreseen |", body)

    def test_check_bundle_block(self):
        bundle = self.bundle()
        bundle["migrations"] = [m for m in bundle["migrations"] if m["name"] != "shop.0004"]
        v = M.check_bundle(bundle, pg_url=PG, client=Fake(lost=0.0), on_code="block", cache=M.VerdictCache(off=True))
        a, b, d = v.files
        self.assertEqual(b.kind, "cannot_foresee")
        self.assertIn("review it by hand", b.reason)
        self.assertEqual(d.kind, "cannot_foresee")
        self.assertTrue(v.cannot_judge)

    def test_warn_only_does_not_fail_the_check(self):
        bundle = self.bundle()
        bundle["migrations"] = [m for m in bundle["migrations"] if m["name"] == "shop.0003"]
        d = tempfile.mkdtemp()
        try:
            p = os.path.join(d, "b.json")
            with open(p, "w") as fh:
                json.dump(bundle, fh)
            out = io.StringIO()
            with redirect_stdout(out):
                rc = cli.main(["migrate-check", "--bundle", p, "--pg-url", PG, "--json"])
            self.assertEqual(rc, cli.OK)
            self.assertTrue(json.loads(out.getvalue())["code_not_foreseen"])
            with redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(["migrate-check", "--bundle", p, "--pg-url", PG, "--on-code", "block"]),
                                 cli.CANNOT_JUDGE)
        finally:
            shutil.rmtree(d)

    def test_cli_bundle(self):
        d = tempfile.mkdtemp()
        try:
            p = os.path.join(d, "b.json")
            with open(p, "w") as fh:
                json.dump(self.bundle(), fh)
            out = io.StringIO()
            with redirect_stdout(out):
                rc = cli.main(["--url", "http://127.0.0.1:9", "--timeout", "1", "migrate-check", "--bundle", p,
                               "--pg-url", PG, "--json"])
            self.assertEqual(rc, cli.CANNOT_JUDGE)          # the server is down: fail closed
            with open(p, "w") as fh:
                json.dump({"framework": "django", "migrations": [], "error": "docker is not installed"}, fh)
            with redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(["migrate-check", "--bundle", p, "--pg-url", PG]), cli.CANNOT_JUDGE)
        finally:
            shutil.rmtree(d)


def git(repo, *args):
    subprocess.run(["git", "-c", "user.email=t@example.com", "-c", "user.name=t", *args], cwd=repo, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


@NEEDS_DOCKER
class TestGenerate(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def repo(self, name, later: dict):
        shutil.copytree(os.path.join(DATA, name), self.root, dirs_exist_ok=True)
        for src in later:
            os.remove(os.path.join(self.root, src))
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "base")
        git(self.root, "checkout", "-qb", "feature")
        for src, dst in later.items():
            shutil.copy(os.path.join(DATA, name, src), os.path.join(self.root, dst))
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "feature")

    def test_django(self):
        self.repo("django", {"0002_remove_email.py": "shop/migrations/0002_remove_email.py",
                             "0003_fill_names.py": "shop/migrations/0003_fill_names.py"})
        b = FW.generate("django", repo=self.root, base="main", setup='pip install -q "django>=4.2" "psycopg[binary]"',
                        log=lambda m: None)
        self.assertEqual(b["isolation"], "no route out")
        self.assertIn("CREATE TABLE public.shop_customer", b["base_schema"])
        m2, m3 = b["migrations"]
        self.assertEqual(m2["path"], "shop/migrations/0002_remove_email.py")
        self.assertIn('DROP COLUMN "email"', m2["sql"])
        self.assertTrue(m2["transaction"])
        self.assertEqual(m3["python_ops"], ["RunPython"])
        if PG and M.psql_bin():
            v = M.check_bundle(b, pg_url=PG, client=Fake(lost=0.9), cache=M.VerdictCache(off=True))
            self.assertTrue(v.files[0].risky)
            self.assertEqual(v.files[1].kind, "code_not_foreseen")

    def test_alembic(self):
        self.repo("alembic", {"b2_drop_email.py": "migrations/versions/b2_drop_email.py",
                              "c3_read_rows.py": "migrations/versions/c3_read_rows.py"})
        b = FW.generate("alembic", repo=self.root, base="main",
                        setup='pip install -q alembic sqlalchemy "psycopg[binary]"', log=lambda m: None)
        self.assertEqual(b["isolation"], "no route out")
        self.assertIn("CREATE TABLE public.customer", b["base_schema"])
        m2, m3 = b["migrations"]
        self.assertIn("DROP COLUMN email", m2["sql"])
        self.assertNotIn("alembic_version", m2["sql"])
        self.assertTrue(m3["error"])                       # reads the database: no offline SQL


if __name__ == "__main__":
    unittest.main()
