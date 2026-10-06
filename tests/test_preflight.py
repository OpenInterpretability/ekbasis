"""0.1.6: preflight v2. Reading lines into plans (sqlite3 forms, groups of echo/cat, files written earlier on
the line, NAME=value, cd, scripts, chains, sqlite3 inside chains), effects (read / add / modify / destroy), what a
failure leaves (a failing read-only check is not half done; additive steps alone are not), runs on a copy (exact, the
real files untouched), the model's path with code-stated facts and the step walk, and the hook (silent when it cannot
judge, warn-once), and what keeps a run on a copy away from the real files (shell steps only inside a sandbox, SQL
that writes other files never on a copy). Offline: the copy runs use the real sqlite3 and bash; the model is a fake
client."""
import io
import json
import os
import shutil
import sqlite3
import stat
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from ekbasis import claude_code_hook as H
from ekbasis import preflight as PF
from ekbasis.client import Answer

# Plans on a SQLite database run on a copy only where the sqlite3 command-line tool is installed (preflight falls back
# to Ekbasis without it); root can write into read-only folders; shell steps run on a copy only inside a sandbox
# (macOS sandbox-exec), elsewhere Ekbasis judges them.
NEEDS_SQLITE3 = unittest.skipUnless(shutil.which("sqlite3"), "needs the sqlite3 command-line tool on PATH")
NOT_ROOT = unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root can write into read-only folders")
NEEDS_SANDBOX = unittest.skipUnless(PF.sandbox_here(), "shell steps run on a copy only inside sandbox-exec (macOS)")

REBUILD = """-- 0012: emails must be unique
CREATE TABLE users_new(id INTEGER PRIMARY KEY, email TEXT NOT NULL UNIQUE);
INSERT INTO users_new(id, email) SELECT id, lower(email) FROM users;
DROP TABLE users;
ALTER TABLE users_new RENAME TO users;
"""


class Fake:
    """Answers yes with probability fails.get(k) for fN questions (and `f` for the walk), `why` for the reason."""

    def __init__(self, fails=None, walk=None, why="unique", lost=0.0):
        self.fails, self.walk, self.why, self.lost, self.requests = fails or {}, walk or {}, why, lost, []

    def ask(self, state, questions, read_once=False, images=None):
        self.requests.append((state, sorted(questions)))
        out = {}
        for k in questions:
            if k == "why":
                out[k] = Answer(value=self.why, confidence=0.9, probabilities={self.why: 0.9})
                continue
            if k == "lost":
                p = self.lost
            elif k == "f":
                n = state.count("\n") and len([x for x in state.split("Actions, in order:")[1].split("\n\n")[0].splitlines()
                                                if x.strip()[:1].isdigit()])
                p = self.walk.get(n, 0.01)
            else:
                p = self.fails.get(int(k[1:]), 0.01)
            out[k] = Answer(value=p >= 0.5, confidence=max(p, 1 - p), probabilities={"yes": p, "no": 1 - p}, p_yes=p)
        return out


def project(root, dup=True):
    os.makedirs(os.path.join(root, "migrations"))
    os.makedirs(os.path.join(root, "data"))
    with open(os.path.join(root, "migrations", "0012.sql"), "w") as fh:
        fh.write(REBUILD)
    con = sqlite3.connect(os.path.join(root, "data", "app.db"))
    con.execute("CREATE TABLE users(id INTEGER PRIMARY KEY, email TEXT)")
    con.executemany("INSERT INTO users VALUES (?, ?)", [(1, "A@x.com"), (2, "a@x.com" if dup else "c@x.com"),
                                                        (3, "b@x.com")])
    con.commit()
    con.close()
    return root


def users(root):
    con = sqlite3.connect(os.path.join(root, "data", "app.db"))
    try:
        return con.execute("SELECT count(*) FROM users").fetchone()[0]
    finally:
        con.close()


def write(root, rel, text, mode=None):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as fh:
        fh.write(text)
    if mode is not None:
        os.chmod(p, mode)


class TestReading(unittest.TestCase):
    def setUp(self):
        self.tmp = project(tempfile.mkdtemp())

    def plan(self, line):
        return PF.plan_line(line, self.tmp)

    def test_sqlite_forms(self):
        for line in ("sqlite3 data/app.db < migrations/0012.sql", "cat migrations/0012.sql | sqlite3 data/app.db",
                     "sqlite3 data/app.db \".read migrations/0012.sql\"",
                     "sqlite3 data/app.db <<'SQL'\n" + REBUILD + "SQL",
                     '{ echo "BEGIN;"; cat migrations/0012.sql; echo "COMMIT;"; } | sqlite3 -bail data/app.db',
                     '(echo "BEGIN;"; cat migrations/0012.sql; echo "COMMIT;") | sqlite3 -bail data/app.db',
                     '{ echo "BEGIN;"; cat migrations/0012.sql; echo "COMMIT;"; } > /tmp/ekb_apply_t.sql; '
                     'sqlite3 -bail data/app.db < /tmp/ekb_apply_t.sql',
                     f'cd {self.tmp}; R={self.tmp}; sqlite3 $R/data/app.db < $R/migrations/0012.sql'):
            p = self.plan(line)
            self.assertIsNotNone(p, line)
            self.assertEqual(p.kind, "sql", line)
            self.assertIn(len(p.steps), (4, 6), line)

    def test_effects(self):
        p = self.plan("sqlite3 data/app.db < migrations/0012.sql")
        self.assertEqual([s.effect for s in p.steps], ["add", "add", "destroy", "modify"])
        self.assertEqual(PF.sql_effect("UPDATE t SET x = 1;", set()), "modify")
        self.assertEqual(PF.sql_effect("SELECT 1;", set()), "read")

    def test_reads_are_not_changes(self):
        for line in ("ls -la; git status --short | head", "find . -name '*.sql' | head; cat README.md",
                     "sqlite3 data/app.db '.schema users' && sqlite3 data/app.db 'SELECT count(*) FROM users'",
                     "tar -tzf x.tgz | head && ls -l"):
            self.assertIsNone(self.plan(line), line)

    def test_one_change_in_a_chain(self):
        write(self.tmp, "scripts/m.sh", "mkdir -p out\nmv data/app.db out/\nrm -rf data\n")
        p = self.plan("bash scripts/m.sh && git status --short && ls out")
        self.assertTrue(p.script and len(p.steps) == 3)
        p = self.plan("cd " + self.tmp + " && sqlite3 data/app.db < migrations/0012.sql && sqlite3 data/app.db .schema")
        self.assertEqual(p.kind, "sql")

    def test_mixed_chain(self):
        p = self.plan("cp data/app.db /tmp/ekb_t.bak && sqlite3 data/app.db < migrations/0012.sql")
        self.assertEqual(p.kind, "sql")                        # a backup and one change: the change is the plan
        p = self.plan("sqlite3 data/app.db < migrations/0012.sql; rm -rf migrations")
        self.assertEqual(p.kind, "shell")
        self.assertEqual(len(p.steps[0].sql), 4)
        self.assertEqual(p.steps[1].effect, "destroy")

    def test_cannot_follow(self):
        write(self.tmp, "scripts/loop.sh", "for f in *.txt; do\n mv \"$f\" old/\ndone\nrm -rf tmp\n")
        self.assertTrue(self.plan("bash scripts/loop.sh").unread)


class TestNoSqliteShell(unittest.TestCase):
    """Where the sqlite3 command-line tool is not installed, a sqlite3 command fails before any statement runs."""

    def setUp(self):
        self.tmp = project(tempfile.mkdtemp())
        which = shutil.which
        self.which = mock.patch.object(PF.shutil, "which", side_effect=lambda n, *a, **k: None if n == "sqlite3"
                                       else which(n, *a, **k))
        self.which.start()

    def tearDown(self):
        self.which.stop()

    def test_a_sqlite3_line_changes_nothing(self):
        for line in ("sqlite3 data/app.db < migrations/0012.sql",
                     'sqlite3 data/app.db "DELETE FROM users WHERE id = 1" && sqlite3 data/app.db "DROP TABLE users"',
                     "cp data/app.db /tmp/ekb_ns.bak && sqlite3 data/app.db < migrations/0012.sql"):
            f = Fake({2: 0.97})
            v = PF.check_line(line, self.tmp, client=f)
            self.assertEqual((v.by, v.first, v.risky), ("code", None, False), line)
            self.assertIn("not installed", v.copy_note)
            self.assertEqual(f.requests, [])                     # nothing to ask: no statement runs

    def test_in_a_longer_line_the_step_fails(self):
        f = Fake()
        v = PF.check_line("sqlite3 data/app.db < migrations/0012.sql; rm -rf migrations", self.tmp, client=f,
                          copy=False)
        self.assertEqual((v.by, v.first, v.risky), ("model", 1, True))
        self.assertIn(1, v.by_code)                              # a code-stated fact: sqlite3 is not installed
        self.assertEqual(v.runs_after, [2])

    def test_sql_given_to_the_api_is_judged(self):
        v = PF.check_sql("data/app.db", REBUILD, client=Fake({2: 0.97}), cwd=self.tmp)
        self.assertEqual((v.by, v.first), ("model", 2))           # SQL run some other way: no shell to copy with
        self.assertIn("sqlite3 shell", v.copy_note)


class TestCopySafety(unittest.TestCase):
    """A run on a copy never writes the real files: not through a path outside the folder, not without a sandbox."""

    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.proj = os.path.join(self.tmp, "proj")
        self.outside = os.path.join(self.tmp, "outside", "app.conf")
        write(self.proj, "new.conf", "new\n")
        write(self.proj, "old.txt", "old\n")
        write(self.tmp, "outside/app.conf", "real settings\n")
        self.line = f"cp new.conf {self.outside}; rm old.txt; rm missing.txt"
        # these folders stand for a project and a file elsewhere on the disk, not for temporary folders
        self.roots = mock.patch.object(PF, "_tmp_roots", return_value={os.path.join(self.tmp, "no-such-tmp")})
        self.roots.start()

    def tearDown(self):
        self.roots.stop()

    def outside_text(self):
        with open(self.outside) as fh:
            return fh.read()

    def test_no_sandbox_no_shell_copy(self):
        with mock.patch.object(PF, "sandbox_here", return_value=False):
            v = PF.check_line(self.line, self.proj, client=Fake())
        self.assertEqual(v.by, "model")
        self.assertIn("no sandbox", v.copy_note)
        self.assertEqual(self.outside_text(), "real settings\n")
        self.assertTrue(os.path.exists(os.path.join(self.proj, "old.txt")))

    def test_a_sandbox_that_does_not_start(self):
        with mock.patch.object(PF, "SANDBOX", "(version 1)\n(this is not a profile"):
            v = PF.check_line(self.line, self.proj, client=Fake())
        self.assertEqual(v.by, "model")
        self.assertEqual(self.outside_text(), "real settings\n")

    @NEEDS_SANDBOX
    def test_inside_the_sandbox(self):
        v = PF.check_line(self.line, self.proj, client=Fake())
        self.assertEqual(self.outside_text(), "real settings\n")    # the sandbox refused the write outside the copy
        self.assertEqual(v.by, "model")                              # so the copy's failure says nothing: the model
        self.assertIn("outside the folder", v.copy_note)

    def test_commands_that_run_other_programs(self):
        for name in ("x.txt", "list.txt"):
            write(self.proj, name, "1\n")
        refused = ["cat list.txt | xargs kill; rm old.txt", "find . -name '*.txt' -exec osascript {} \\; ; rm old.txt",
                   "awk 'BEGIN{system(\"touch y\")}' x.txt > y.txt; rm old.txt",
                   "tar --use-compress-program=evil -cf a.tar x.txt; rm old.txt",
                   "git -c core.pager=evil log > log.txt; rm old.txt", "sort --compress-program=evil x.txt > s.txt; rm old.txt"]
        for line in refused:
            plan = PF.plan_line(line, self.proj)
            self.assertIsNotNone(plan, line)
            self.assertIn("running", PF._copy_ok_text(line, self.proj, self.proj, set(), 0) or "", line)
        for line in ("cat list.txt | xargs rm -f; rm old.txt", "find . -name '*.tmp' -exec rm {} \\; ; rm old.txt",
                     "find . -name '*.tmp' -delete; rm old.txt", "awk '{print $1}' x.txt > y.txt; rm old.txt"):
            self.assertIsNone(PF._copy_ok_text(line, self.proj, self.proj, set(), 0), line)

    def test_vacuum_into_is_not_run_on_a_copy(self):
        project(self.proj)
        target = os.path.join(self.tmp, "outside", "backup.db")
        sql = f"VACUUM INTO '{target}';\nDELETE FROM users WHERE id = 3;\nDROP TABLE users;\n"
        v = PF.check_sql("data/app.db", sql, client=Fake(), cwd=self.proj)
        self.assertEqual(v.by, "model")
        self.assertFalse(os.path.exists(target))
        if shutil.which("sqlite3"):
            self.assertIn("another file", v.copy_note)

    @NEEDS_SANDBOX
    @NEEDS_SQLITE3
    def test_sql_copies_run_in_the_sandbox_too(self):
        project(self.proj)
        target = os.path.join(self.tmp, "outside", "backup.db")
        sql = f"DELETE FROM users WHERE id = 3;\nVACUUM INTO '{target}';\nDROP TABLE users;\n"
        with mock.patch.object(PF, "SQL_OUT", PF.re.compile("(?!)")):    # as if the check had missed it
            v = PF.check_sql("data/app.db", sql, client=Fake(), cwd=self.proj)
        self.assertEqual((v.by, v.first), ("copy", 2))
        self.assertFalse(os.path.exists(target))


class TestHalfApplied(unittest.TestCase):
    def shell(self, items, script=False, stop=False):
        steps = [PF.Step(text=t, effect=e, joined_by=j, ctx=t.startswith("cd ")) for t, e, j in items]
        return PF.Plan("shell", steps, "/", "x", script=script, stop_on_error=stop)

    def test_read_only_failure_is_not_half_done(self):
        plan = self.shell([("bash x.sh", "modify", ""), ("git status --short", "read", "&&")])
        self.assertFalse(PF.half_applied(plan, 2)[0])

    def test_additive_only_is_not_half_done(self):
        plan = self.shell([("cp db /tmp/db.bak", "add", ""), ("sqlite3 db 'UPDATE ...'", "modify", "&&")])
        self.assertFalse(PF.half_applied(plan, 2)[0])

    def test_a_failing_notification_is_not_half_done(self):
        sc = PF.S.parse("curl -fsS -X POST http://127.0.0.1:9/notify -d done").commands[0]
        self.assertEqual(PF.shell_effect(sc, "/")[0], "read")
        sc = PF.S.parse("curl -fsSL -o out.bin https://example.invalid/x").commands[0]
        self.assertEqual(PF.shell_effect(sc, "/")[0], "add")
        plan = self.shell([("tar -czf dist/x.tgz build", "add", "\n"), ("rm -rf build", "destroy", "\n"),
                           ("curl -X POST http://127.0.0.1:9/n", "read", "\n")], script=True)
        self.assertFalse(PF.half_applied(plan, 3)[0])

    def test_cd_then_rm(self):
        plan = self.shell([("cd build/output", "read", ""), ("rm -rf *", "destroy", "\n")], script=True)
        self.assertTrue(PF.half_applied(plan, 1)[0])

    def test_rebuild(self):
        plan = PF._sql_plan("/x.db", REBUILD, False, [], "/", "x")
        self.assertTrue(PF.half_applied(plan, 2)[0])
        plan = PF._sql_plan("/x.db", "BEGIN;\n" + REBUILD + "COMMIT;\n", True, [], "/", "x")
        self.assertFalse(PF.half_applied(plan, 3)[0])   # -bail inside a transaction: rolled back


class TestCopy(unittest.TestCase):
    def setUp(self):
        self.tmp = project(tempfile.mkdtemp())

    @NEEDS_SQLITE3
    def test_sql_on_a_copy(self):
        v = PF.check_line("sqlite3 data/app.db < migrations/0012.sql", self.tmp, client=Fake())
        self.assertEqual((v.by, v.first, v.risky), ("copy", 2, True))
        self.assertIn("UNIQUE", v.error)
        self.assertEqual(users(self.tmp), 3)                         # the real database is untouched
        self.assertIn("ran this on a copy", v.message())

    @NEEDS_SQLITE3
    def test_clean_control_and_atomic(self):
        clean = project(tempfile.mkdtemp(), dup=False)
        v = PF.check_line("sqlite3 data/app.db < migrations/0012.sql", clean, client=Fake())
        self.assertEqual((v.by, v.first, v.risky), ("copy", None, False))
        v = PF.check_line('{ echo "BEGIN;"; cat migrations/0012.sql; echo "COMMIT;"; } | sqlite3 -bail data/app.db',
                          self.tmp, client=Fake())
        self.assertEqual(v.first is not None, True)
        self.assertFalse(v.risky)                                   # fails, but atomically

    @NEEDS_SQLITE3
    def test_backup_then_migrate(self):
        v = PF.check_line("cp data/app.db /tmp/ekb_t2.bak && sqlite3 data/app.db < migrations/0012.sql", self.tmp,
                          client=Fake())
        self.assertEqual((v.by, v.first), ("copy", 2))
        self.assertTrue(v.risky)                                    # the call itself is left half applied
        self.assertFalse(os.path.exists("/tmp/ekb_t2.bak"))         # nothing outside the copy was written

    @NEEDS_SANDBOX
    def test_shell_on_a_copy(self):
        write(self.tmp, "assets/fonts/a.woff2", "x")
        write(self.tmp, "assets/logo.png", "p")
        write(self.tmp, "static/fonts", "")
        write(self.tmp, "scripts/reorg.sh", "mkdir -p static/img\nmv assets/*.png static/img/\n"
                                            "mv assets/fonts static/fonts\nrm -rf assets\n")
        v = PF.check_line("bash scripts/reorg.sh", self.tmp, client=Fake())
        self.assertEqual((v.by, v.first, v.risky), ("copy", 3, True))
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "assets", "fonts", "a.woff2")))

    def test_not_eligible_goes_to_model(self):
        write(self.tmp, "scripts/rel.sh", "cp data/app.db releases/\nrm -rf data\ncurl -s -X POST http://127.0.0.1:9/x\n")
        f = Fake({1: 0.02})
        v = PF.check_line("bash scripts/rel.sh", self.tmp, client=f)
        self.assertEqual(v.by, "model")
        self.assertIn("curl", v.copy_note)
        self.assertEqual(v.first, 1)                               # a code-stated fact: releases/ does not exist
        self.assertIn(1, v.by_code)
        self.assertTrue(v.risky)


class TestFacts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def plan(self, text):
        return PF.plan_line(text, self.tmp) or PF.Plan("shell", [], self.tmp, "x")

    def facts(self, script):
        write(self.tmp, "s.sh", script)
        return PF.shell_facts(PF.plan_line("bash s.sh", self.tmp))[0]

    def test_mkdir_onto_file(self):
        write(self.tmp, "archive/2026-09", "")
        write(self.tmp, "reports/a.csv", "1")
        f = self.facts("mkdir -p archive/2026-09\ncp reports/*.csv archive/2026-09/\nrm -rf reports\n")
        self.assertIn(1, f)
        self.assertNotIn(2, f)                                    # named by step 1: it could change it

    @NOT_ROOT
    def test_read_only_folder(self):
        write(self.tmp, "build/x.csv", "1")
        os.makedirs(os.path.join(self.tmp, "exports"))
        os.chmod(os.path.join(self.tmp, "exports"), 0o555)
        try:
            f = self.facts("cp build/x.csv exports/x.csv\nrm -rf build\n")
            self.assertIn(1, f)
            self.assertIn("read-only", f[1])
        finally:
            os.chmod(os.path.join(self.tmp, "exports"), 0o755)

    def test_missing_source_and_cd(self):
        f = self.facts("cd nowhere\nrm -rf *\n")
        self.assertIn(1, f)
        f = self.facts("mkdir -p out\nmv missing.txt out/\nrm -rf x\n")
        self.assertIn(2, f)


class TestModelPath(unittest.TestCase):
    def setUp(self):
        self.tmp = project(tempfile.mkdtemp())

    def test_sql_by_model(self):
        f = Fake({2: 0.97})
        v = PF.check_sql("data/app.db", REBUILD, client=f, cwd=self.tmp, copy=False)
        self.assertEqual((v.by, v.first, v.risky, v.reason), ("model", 2, True, "unique"))
        self.assertIn("'A@x.com'", f.requests[0][0])

    def test_walk_for_scripts(self):
        write(self.tmp, "Design Assets/a.png", "p")
        write(self.tmp, "scripts/imp.sh", 'SRC="Design Assets"\nmkdir -p static/img\nmv $SRC/*.png static/img/\n'
                                          'rm -rf "$SRC"\n')
        f = Fake({}, walk={2: 0.98})
        v = PF.check_line("bash scripts/imp.sh", self.tmp, client=f, copy=False)
        self.assertEqual(v.first, 2)
        self.assertTrue(v.risky)
        self.assertGreaterEqual(len(f.requests), 3)               # the whole plan, then the walk


class TestHook(unittest.TestCase):
    def setUp(self):
        self.tmp = project(tempfile.mkdtemp())
        self.env = mock.patch.dict(os.environ, {"EKBASIS_PREFLIGHT": "1", "EKBASIS_GIT_GUARD": "0",
                                                "TMPDIR": tempfile.mkdtemp()})
        self.env.start()
        tempfile.tempdir = None

    def tearDown(self):
        self.env.stop()
        tempfile.tempdir = None

    def run_hook(self, line, fake, session="s1"):
        data = {"tool_name": "Bash", "tool_input": {"command": line}, "cwd": self.tmp, "session_id": session}
        out = io.StringIO()
        with mock.patch.object(H, "Ekbasis", return_value=fake), mock.patch("sys.stdin", io.StringIO(json.dumps(data))), \
                redirect_stdout(out):
            self.assertEqual(H.main(), 0)
        return json.loads(out.getvalue())["hookSpecificOutput"] if out.getvalue().strip() else None

    @NEEDS_SQLITE3
    def test_warns_once_on_a_copy(self):
        line = "sqlite3 data/app.db < migrations/0012.sql"
        a = self.run_hook(line, Fake())
        self.assertEqual(a["permissionDecision"], "ask")
        self.assertIn("ran this on a copy first", a["permissionDecisionReason"])
        self.assertIsNone(self.run_hook(line, Fake()))
        self.assertEqual(users(self.tmp), 3)

    @NEEDS_SQLITE3
    def test_edited_file_is_checked_again(self):
        line = "sqlite3 data/app.db < migrations/0012.sql"
        self.assertIsNotNone(self.run_hook(line, Fake()))
        with open(os.path.join(self.tmp, "migrations", "0012.sql"), "a") as fh:
            fh.write("-- edited\nDELETE FROM users WHERE id = 99;\n")
        self.assertIsNotNone(self.run_hook(line, Fake()))     # same command, new content: checked again

    def test_silent_when_it_cannot_judge(self):
        line = "sqlite3 data/app.db < migrations/missing.sql"
        self.assertIsNone(self.run_hook(line, Fake()))
        with mock.patch.dict(os.environ, {"EKBASIS_PREFLIGHT_FAIL_CLOSED": "1"}):
            a = self.run_hook(line, Fake(), session="s2")
            self.assertIn("could not check", a["permissionDecisionReason"])

    @NEEDS_SQLITE3
    def test_careful_agent_commands_pass(self):
        clean = project(tempfile.mkdtemp(), dup=False)
        self.tmp = clean
        for line in ('cp data/app.db /tmp/ekb_h.bak && { echo "BEGIN;"; cat migrations/0012.sql; echo "COMMIT;"; } '
                     '| sqlite3 -bail data/app.db && sqlite3 data/app.db ".schema users"',
                     "sqlite3 data/app.db < migrations/0012.sql && git status --short && ls data"):
            self.assertIsNone(self.run_hook(line, Fake({1: 0.9, 2: 0.9})), line)


if __name__ == "__main__":
    unittest.main()
