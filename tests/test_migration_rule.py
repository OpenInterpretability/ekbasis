"""0.1.22: the migration guard's rule (ekbasis.migration_rule) and the policy that makes it decide (policy rule, the
default): the rule decides whether a file fails the check, and when it finds nothing while the model's answer is risky
the file is a "review" that does not fail the check. policy model keeps the 0.1.21 behavior. Offline: the rule on
catalogs and statistics written by hand, the statistics it may read (only what the state prints), the verdict, reason,
JSON, summary, comment, cache key, CLI flag and Action input. With a PostgreSQL server (EKBASIS_TEST_PG_URL): the policy
end to end through check() and check_bundle()."""
import json
import os
import shutil
import tempfile
import unittest

from ekbasis import cli
from ekbasis import migration_rule as R
from ekbasis import migrations as M

from test_migrations import Fake, PG, NEEDS_PG, prisma_repo, write   # noqa: E402

os.environ["EKBASIS_VERDICT_CACHE"] = "off"


def col(name, typ, notnull=False, default=None):
    return {"name": name, "type": typ, "notnull": notnull, "default": default, "generated": False, "typname": typ}


USERS = {"oid": 1, "schema": "public", "name": "users",
         "cols": [col("id", "integer", True), col("email", "text", True), col("nick", "text"),
                  col("status", "text")],
         "cons": [{"name": "users_pkey", "type": "p", "ref": None, "def": "PRIMARY KEY (id)"}], "idx": []}
POSTS = {"oid": 2, "schema": "public", "name": "posts",
         "cols": [col("id", "integer", True), col("user_id", "integer", True), col("body", "text")],
         "cons": [{"name": "posts_user_fkey", "type": "f", "ref": 1,
                   "def": "FOREIGN KEY (user_id) REFERENCES users(id)"}], "idx": []}
CATALOG = {"tables": [USERS, POSTS], "enums": {}}


def stats(users=20, posts=20, nick_null=0.25):
    return {"rows": {"public.users": users, "public.posts": posts},
            "cols": {"public.users.id": [0, -1], "public.users.email": [0, -1], "public.users.nick": [nick_null, -0.75],
                     "public.posts.user_id": [0, 5]}}


def rule(stmts, st=None, tx=True, probes=()):
    return R.decide(R.facts_from(CATALOG, stmts, st, tx, None, probes))


class TestRule(unittest.TestCase):
    def test_drop_column_with_values_loses(self):
        kind, why = rule(["ALTER TABLE users DROP COLUMN nick"], stats())
        self.assertEqual(kind, "loses")
        self.assertIn("users.nick", why[0])

    def test_drop_column_of_an_empty_table_loses_nothing(self):
        self.assertEqual(rule(["ALTER TABLE users DROP COLUMN nick"], stats(users=0))[0], "ok")

    def test_copied_then_dropped_loses_nothing(self):
        stmts = ["ALTER TABLE users ADD COLUMN nickname text", "UPDATE users SET nickname = nick",
                 "ALTER TABLE users DROP COLUMN nick"]
        self.assertEqual(rule(stmts, stats())[0], "ok")

    def test_not_null_without_default_on_rows_fails(self):
        kind, why = rule(["ALTER TABLE users ADD COLUMN age integer NOT NULL"], stats())
        self.assertEqual(kind, "fails")
        self.assertIn("NOT NULL without a DEFAULT", why[0])
        self.assertEqual(rule(["ALTER TABLE users ADD COLUMN age integer NOT NULL DEFAULT 0"], stats())[0], "ok")

    def test_set_not_null_on_nulls_fails_unless_filled(self):
        self.assertEqual(rule(["ALTER TABLE users ALTER COLUMN nick SET NOT NULL"], stats())[0], "fails")
        self.assertEqual(rule(["ALTER TABLE users ALTER COLUMN nick SET NOT NULL"], stats(nick_null=0))[0], "ok")
        filled = ["UPDATE users SET nick = '' WHERE nick IS NULL", "ALTER TABLE users ALTER COLUMN nick SET NOT NULL"]
        self.assertEqual(rule(filled, stats())[0], "ok")

    def test_no_replica_means_production_data(self):
        # nullable columns may hold NULLs and every table holds rows
        self.assertEqual(rule(["ALTER TABLE users ALTER COLUMN nick SET NOT NULL"], None)[0], "fails")
        self.assertEqual(rule(["ALTER TABLE users DROP COLUMN nick"], None)[0], "loses")

    def test_unique_on_repeated_values_fails(self):
        # posts.user_id: about 5 distinct values in 20 rows
        self.assertEqual(rule(["CREATE UNIQUE INDEX p_u ON posts (user_id)"], stats())[0], "fails")
        self.assertEqual(rule(["CREATE UNIQUE INDEX u_e ON users (email)"], stats())[0], "ok")

    def test_new_table_and_its_index_are_safe(self):
        stmts = ["CREATE TABLE tags (id serial PRIMARY KEY, name text NOT NULL)",
                 "CREATE UNIQUE INDEX tags_name ON tags (name)"]
        self.assertEqual(rule(stmts, stats())[0], "ok")

    def test_unknown_rows_count_as_risk(self):
        # the state shows no value: a specific literal may match rows; a deduplication may find duplicates
        self.assertEqual(rule(["UPDATE users SET status = 'active' WHERE status = 'pending'"], stats())[0], "loses")
        dedupe = ["DELETE FROM posts WHERE id NOT IN (SELECT min(id) FROM posts GROUP BY user_id, body)"]
        self.assertEqual(rule(dedupe, stats())[0], "loses")
        # the same deletion on a table still referenced (posts.user_id, NO ACTION) fails
        dedupe = ["DELETE FROM users WHERE id NOT IN (SELECT min(id) FROM users GROUP BY email)"]
        self.assertEqual(rule(dedupe, stats())[0], "fails")

    def test_delete_of_referenced_rows_fails(self):
        self.assertEqual(rule(["DELETE FROM users"], stats())[0], "fails")

    def test_transaction_rolls_back_and_autocommit_keeps(self):
        stmts = ["ALTER TABLE users DROP COLUMN status", "ALTER TABLE users ADD COLUMN age integer NOT NULL"]
        self.assertEqual(rule(stmts, stats(), tx=True)[0], "fails")
        kind, why = rule(stmts, stats(), tx=False)
        self.assertEqual(kind, "fails")
        self.assertTrue(any(w.startswith("also loses") for w in why))

    def test_probe_fact_counts_when_the_replica_satisfies_it(self):
        fact = ("Checked on a copy of the base schema: if users hold rows (one made-up row each, its optional columns "
                "NULL), action 1 fails with: null value in column \"x\".")
        self.assertEqual(rule(["INSERT INTO posts (user_id, body) SELECT id, nick FROM users"], stats(),
                              probes=[fact])[0], "fails")

    def test_statistics_reduced_to_what_the_state_prints(self):
        red = R.reduce_stats({"rows": {"public.users": 20}, "cols": {
            "public.users.nick": [0.25, -0.75], "public.users.email": [0, -1], "public.users.status": [0, 3],
            "public.users.id": [0.001, 15]}}, CATALOG)
        cs = red[("public", "users")].cols
        self.assertEqual(red[("public", "users")].rows, 20)
        self.assertEqual((cs["nick"].null_pct, cs["nick"].distinct, cs["nick"].all_distinct), (25, None, False))
        self.assertTrue(cs["email"].all_distinct)
        self.assertEqual(cs["status"].distinct, 3)
        self.assertEqual(cs["id"].null_pct, 0.1)          # "a few NULL"; 15 distinct is not printed
        self.assertIsNone(cs["id"].distinct)


def verdict(kind, lost=0.1, fail=0.1, why=("action 1: x",), tx=True):
    v = M.FileVerdict("m.sql", "generic", tx, p_lost=lost, p_fail=fail)
    v.risky = lost >= 0.5 or fail >= 0.5
    v.policy, v.rule_kind, v.rule_why = "rule", kind, list(why)
    model_risky = v.risky
    v.risky = kind != "ok"
    v.review = not v.risky and model_risky
    return v


class TestPolicyVerdict(unittest.TestCase):
    def test_rule_decides_and_model_can_only_ask_for_review(self):
        v = verdict("ok", lost=0.9)
        self.assertEqual((v.risky, v.review, v.kind), (False, True, "review"))
        self.assertIn("review suggested", v.reason)
        self.assertIn("does not fail the check", v.reason)
        v = verdict("loses", lost=0.05, why=["action 1: drops t.c, which holds values not copied elsewhere"])
        self.assertEqual((v.risky, v.review, v.kind), (True, False, "loses"))
        self.assertIn("drops t.c", v.reason)
        self.assertIn("second opinion: lose 5%", v.reason)
        v = verdict("fails", tx=True)
        self.assertIn("nothing in the file would be applied", v.reason)
        v = verdict("ok")
        self.assertEqual((v.risky, v.kind), (False, "ok"))
        self.assertIn("no data loss or failure foreseen by the rule", v.reason)

    def test_apply_rule_on_facts(self):
        v = M.FileVerdict("m.sql", "generic", True, p_lost=0.95, p_fail=0.1, risky=True)
        M._apply_rule(v, CATALOG, ["CREATE TABLE t (id int)"], stats(), True, [], "generic")
        self.assertEqual((v.policy, v.rule_kind, v.risky, v.review), ("rule", "ok", False, True))
        v = M.FileVerdict("m.sql", "generic", True, p_lost=0.01, p_fail=0.01)
        M._apply_rule(v, CATALOG, ["ALTER TABLE users DROP COLUMN nick"], stats(), True, [], "generic")
        self.assertEqual((v.rule_kind, v.risky, v.review), ("loses", True, False))

    def test_a_rule_error_keeps_the_model_verdict_and_says_so(self):
        v = M.FileVerdict("m.sql", "generic", True, p_lost=0.9, p_fail=0.1, risky=True)
        M._apply_rule(v, {"tables": "not a list"}, ["ALTER TABLE users DROP COLUMN nick"], None, True, [], "generic")
        self.assertEqual((v.policy, v.rule_kind, v.risky), ("model", None, True))
        self.assertIn("the rule could not read this migration", " ".join(v.notes))

    def test_json_summary_and_comment(self):
        g = M.GuardVerdict([verdict("ok", lost=0.9), verdict("ok")])
        d = g.as_json()
        self.assertEqual((d["risky"], d["review"]), (False, True))
        self.assertEqual((d["files"][0]["kind"], d["files"][0]["policy"], d["files"][0]["rule_kind"]),
                         ("review", "rule", "ok"))
        self.assertIn("review suggested", g.summary())
        self.assertIn("REVIEW", g.summary())
        c = M.comment(d)
        self.assertIn("**Review suggested:**", c)
        self.assertIn("| review |", c)
        risky = M.GuardVerdict([verdict("loses"), verdict("ok", lost=0.9)]).as_json()
        self.assertIn("**Risky:**", M.comment(risky))

    def test_cache_key_includes_the_policy(self):
        args = dict(text="x", catalog={}, transaction=True, stats=False, state="s", questions={"q": 1}, url="u")
        self.assertNotEqual(M.VerdictCache.key(**args, policy="rule"), M.VerdictCache.key(**args, policy="model"))
        self.assertEqual(M.VerdictCache.key(**args), M.VerdictCache.key(**args, policy=M.DEFAULT_POLICY))

    def test_cli_flag_and_bad_policy(self):
        self.assertEqual(M.DEFAULT_POLICY, "rule")
        import contextlib
        import io
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            cli.main(["migrate-check", "--policy", "other", "a.sql"])          # argparse: rule or model only
        with self.assertRaises(ValueError):
            M.check(".", files=["a.sql"], policy="other")
        with self.assertRaises(ValueError):
            M.check_bundle({"migrations": [{"path": "a"}]}, policy="other")

    def test_action_passes_the_policy(self):
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "..", "actions", "migration-guard", "action.yml")) as fh:
            a = fh.read()
        self.assertIn("  policy:\n", a)
        self.assertIn("default: rule", a)
        self.assertIn('--policy "${POLICY:-rule}"', a)
        self.assertIn("v=review", a)


@NEEDS_PG
class TestPolicyPostgres(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_rule_decides_a_loss_the_model_missed(self):
        prisma_repo(self.root, {"prisma/migrations/002_drop/migration.sql": 'ALTER TABLE "User" DROP COLUMN nick;\n'})
        v = M.check(self.root, base="main", pg_url=PG, client=Fake(lost=0.05, fails=0.05))
        f = v.files[0]
        self.assertEqual((f.policy, f.rule_kind, f.kind, f.risky, v.risky), ("rule", "loses", "loses", True, True))
        m = M.check(self.root, base="main", pg_url=PG, client=Fake(lost=0.05, fails=0.05), policy="model")
        self.assertEqual((m.files[0].policy, m.files[0].kind, m.risky), ("model", "ok", False))

    def test_model_alone_is_a_review_that_does_not_fail(self):
        prisma_repo(self.root, {"prisma/migrations/002_tags/migration.sql":
                                'CREATE TABLE "Tag" (id serial PRIMARY KEY, name text NOT NULL);\n'})
        v = M.check(self.root, base="main", pg_url=PG, client=Fake(lost=0.9, fails=0.1))
        f = v.files[0]
        self.assertEqual((f.rule_kind, f.review, f.risky, f.kind), ("ok", True, False, "review"))
        self.assertFalse(v.risky)
        self.assertTrue(v.as_json()["review"])
        m = M.check(self.root, base="main", pg_url=PG, client=Fake(lost=0.9, fails=0.1), policy="model")
        self.assertTrue(m.risky)

    def test_decisions_in_code_unchanged(self):
        # a transactional file that fails on the schema: decided in code, no model call, under both policies
        prisma_repo(self.root, {"prisma/migrations/002_bad/migration.sql": 'ALTER TABLE "User" DROP COLUMN nope;\n'})
        for policy in M.POLICIES:
            fake = Fake()
            v = M.check(self.root, base="main", pg_url=PG, client=fake, policy=policy)
            self.assertEqual((v.files[0].kind, v.risky, len(fake.requests), v.files[0].rule_kind),
                             ("schema", True, 0, None))

    def test_bundle_uses_the_policy(self):
        bundle = {"framework": "rails", "base_schema": "CREATE TABLE users (id integer PRIMARY KEY, nick text);",
                  "migrations": [{"path": "db/migrate/1_drop.rb", "sql": "ALTER TABLE users DROP COLUMN nick;",
                                  "transaction": True}]}
        v = M.check_bundle(bundle, pg_url=PG, client=Fake(lost=0.05, fails=0.05))
        self.assertEqual((v.files[0].rule_kind, v.risky), ("loses", True))
        v = M.check_bundle(bundle, pg_url=PG, client=Fake(lost=0.05, fails=0.05), policy="model")
        self.assertEqual((v.files[0].rule_kind, v.risky), (None, False))

    def test_cli_exit_codes(self):
        prisma_repo(self.root, {"prisma/migrations/002_tags/migration.sql":
                                'CREATE TABLE "Tag" (id serial PRIMARY KEY, name text NOT NULL);\n'})
        import io
        import unittest.mock
        from contextlib import redirect_stdout
        out = io.StringIO()
        with unittest.mock.patch.object(cli, "Ekbasis", lambda *a, **k: Fake(lost=0.9)), redirect_stdout(out):
            rc = cli.main(["migrate-check", "--repo", self.root, "--base", "main", "--pg-url", PG, "--json"])
        self.assertEqual(rc, 0)                                     # a review does not fail the check
        self.assertTrue(json.loads(out.getvalue().splitlines()[-1])["review"])
        with unittest.mock.patch.object(cli, "Ekbasis", lambda *a, **k: Fake(lost=0.9)), redirect_stdout(io.StringIO()):
            rc = cli.main(["migrate-check", "--repo", self.root, "--base", "main", "--pg-url", PG, "--policy", "model"])
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
