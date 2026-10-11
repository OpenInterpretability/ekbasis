"""The safer route (ekbasis.safer): the candidates each rule writes, that the route really keeps the work when run, the
choice among the candidates the model passes, "none passed", and fail-closed behaviour (no route ever goes out
unchecked; a server that is down still gives CANNOT FORESEE, exit 3). Offline: a fake client and a port nobody listens
on."""
import io
import json
import os
import socket
import subprocess
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from ekbasis import claude_code_hook as H
from ekbasis import cli
from ekbasis import safer as SF
from ekbasis.client import Answer, CannotJudge

ENV = dict(os.environ, GIT_AUTHOR_NAME="Dev", GIT_AUTHOR_EMAIL="dev@example.invalid", GIT_COMMITTER_NAME="Dev",
           GIT_COMMITTER_EMAIL="dev@example.invalid", GIT_CONFIG_NOSYSTEM="1", LC_ALL="C")


def sh(cmd, cwd):
    return subprocess.run(["bash", "-c", cmd], cwd=cwd, env=ENV, check=True, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, text=True).stdout


def dead_url():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return f"http://127.0.0.1:{port}"


def commands_of(state):
    """The command list of a git prompt."""
    block = state.split("Commands, in order:\n", 1)[1].split("\n\n", 1)[0]
    return [l.split(". ", 1)[1] for l in block.splitlines()]


class Fake:
    """lost(commands) and fail(commands, k) give the probabilities; every request is kept."""

    def __init__(self, lost=lambda c: 0.0, fail=lambda c, k: 0.0, down=lambda c: False):
        self.lost, self.fail, self.down, self.requests = lost, fail, down, []

    def ask(self, state, questions, read_once=False, images=None):
        cmds = commands_of(state)
        self.requests.append(cmds)
        if self.down(cmds):
            raise CannotJudge("cannot reach the Ekbasis server (fake)")
        out = {}
        for k in questions:
            p = self.lost(cmds) if k == "lost" else (self.fail(cmds, int(k.split("_")[1])) if k.startswith("fails_") else 0.0)
            out[k] = Answer(value=p >= 0.5, confidence=max(p, 1 - p), probabilities={"yes": p, "no": 1 - p}, p_yes=p)
        return out


def make_repo(root):
    """main (2 commits) pushed to origin; feature (app.py differs), unmerged (1 own commit); app.py modified, notes.txt
    untracked, one stash entry."""
    os.makedirs(root)
    sh(f"git init -q --bare -b main {root}.remote.git", os.path.dirname(root))
    for c in ("git init -q -b main", "git config commit.gpgsign false", f"git remote add origin {root}.remote.git",
              "echo v1 > app.py", "echo r > README.md", "git add -A", "git commit -qm one", "echo v2 > app.py",
              "git commit -qam two", "git push -q -u origin main", "git checkout -qb feature", "echo f > app.py",
              "git commit -qam feat", "git checkout -q main", "git checkout -qb unmerged", "echo u > u.txt", "git add u.txt",
              "git commit -qm unmerged-work", "git checkout -q main", "echo stashed >> README.md", "git stash -q",
              "echo local >> app.py", "echo n > notes.txt"):
        sh(c, root)
    return root


def lines(cands):
    return [c.commands for c in cands]


class TestRules(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = make_repo(os.path.join(os.path.realpath(self.tmp.name), "repo"))

    def tearDown(self):
        self.tmp.cleanup()

    def c(self, *cmds):
        return lines(SF.candidates(list(cmds), self.repo))

    def test_reset_hard(self):
        self.assertEqual(self.c("git reset --hard"), [["git stash push", "git reset --hard"],
                                                      ["git stash push -u", "git reset --hard"]])
        sh("rm notes.txt", self.repo)
        self.assertEqual(self.c("git reset --hard"), [["git stash push", "git reset --hard"]])
        # dropping a commit no other ref holds: a backup branch keeps it
        self.assertEqual(self.c("git reset --hard HEAD~1"), [["git stash push", "git reset --hard HEAD~1"]])  # pushed
        sh("git commit -q --allow-empty -m local-only", self.repo)
        self.assertEqual(self.c("git reset --hard HEAD~1"),
                         [["git stash push", "git branch backup/main", "git reset --hard HEAD~1"]])

    def test_discard_files(self):
        self.assertEqual(self.c("git checkout -- app.py"), [["git stash push -- app.py", "git checkout -- app.py"]])
        self.assertEqual(self.c("git checkout app.py"), [["git stash push -- app.py", "git checkout app.py"]])
        self.assertEqual(self.c("git restore app.py"), [["git stash push -- app.py", "git restore app.py"]])
        self.assertEqual(self.c("git checkout -- ."), [["git stash push", "git checkout -- ."]])
        self.assertEqual(self.c("git checkout feature -- app.py"),
                         [["git stash push -- app.py", "git checkout feature -- app.py"]])

    def test_forced_switch(self):
        self.assertEqual(self.c("git checkout -f feature"), [["git stash push -u", "git checkout feature"],
                                                             ["git stash push -u", "git checkout -f feature"]])
        self.assertEqual(self.c("git switch --discard-changes feature")[0], ["git stash push -u", "git switch feature"])
        self.assertEqual(self.c("git checkout -fb fix")[0], ["git stash push -u", "git checkout -b fix"])

    def test_clean(self):
        os.makedirs(os.path.join(self.repo, "tmpdir"))
        open(os.path.join(self.repo, "tmpdir", "x"), "w").close()
        self.assertEqual(self.c("git clean -fd"), [["git stash push -u -- notes.txt tmpdir/"]])
        self.assertEqual(self.c("git clean -f"), [["git stash push -u -- notes.txt"]])
        self.assertEqual(self.c("git clean -fdx"), [["git stash push -a -- notes.txt tmpdir/"]])
        self.assertEqual(self.c("git clean -n"), [])   # only reads

    def test_branch_delete(self):
        self.assertEqual(self.c("git branch -D unmerged"), [["git branch -m unmerged backup/unmerged"]])
        self.assertEqual(self.c("git branch -D feature"), [["git branch -m feature backup/feature"]])
        sh("git branch backup/unmerged unmerged", self.repo)   # now held by another branch: -d first
        self.assertEqual(self.c("git branch -d -f unmerged"), [["git branch -d unmerged"],
                                                               ["git branch -m unmerged backup/unmerged-2"]])

    def test_stash_drop_and_clear(self):
        self.assertEqual(self.c("git stash drop"), [["git branch backup/stash-0 stash@{0}", "git stash drop"]])
        self.assertEqual(self.c("git stash drop stash@{0}")[0][0], "git branch backup/stash-0 stash@{0}")
        self.assertEqual(self.c("git stash clear"), [["git branch backup/stash-0 stash@{0}", "git stash clear"]])

    def theirs(self):
        """The remote gets a commit the local branch lacks, and it is fetched."""
        other = os.path.join(self.tmp.name, "other")
        sh(f"git clone -q {self.repo}.remote.git {other}", self.tmp.name)
        sh("git config commit.gpgsign false && echo o > o.txt && git add o.txt && git commit -qm theirs && git push -q",
           other)
        sh("git fetch -q && git commit -q --allow-empty -m mine", self.repo)

    def test_force_push(self):
        safe = "git push --force-with-lease --force-if-includes"
        self.assertEqual(self.c("git push --force"), [[safe]])
        self.theirs()
        self.assertEqual(self.c("git push -f origin main"), [[safe + " origin main"]])
        self.assertEqual(self.c("git push origin +main"), [[safe + " origin main"]])
        self.assertEqual(SF.candidates(["git push -f"], self.repo)[0].may_fail, {safe})
        # --force-with-lease alone, or with a value read from this state, overwrites the fetched commit: code check fails
        sha = sh("git rev-parse origin/main", self.repo).strip()
        self.assertTrue(SF.code_problems(["git push --force-with-lease origin main"], self.repo))
        self.assertTrue(SF.code_problems([f"git push --force-with-lease=main:{sha} origin main"], self.repo))
        self.assertEqual(SF.code_problems([safe + " origin main"], self.repo), [])
        # older git: a backup branch, then the lease
        with mock.patch.object(SF.G, "git_version", lambda repo=".": (2, 29)):
            self.assertEqual(self.c("git push -f origin main"),
                             [["git branch backup/origin-main origin/main", "git push --force-with-lease origin main"]])
        self.assertEqual(SF.code_problems(["git branch backup/origin-main origin/main",
                                           "git push --force-with-lease origin main"], self.repo), [])

    def test_remote_branch_delete(self):
        sh("git push -q origin unmerged && git branch -D unmerged", self.repo)
        for cmd in ("git push origin --delete unmerged", "git push origin :unmerged", "git push -d origin unmerged"):
            self.assertEqual(self.c(cmd), [["git branch backup/origin-unmerged origin/unmerged", cmd]], cmd)
            self.assertTrue(SF.code_problems([cmd], self.repo))
            self.assertEqual(SF.code_problems(["git branch backup/origin-unmerged origin/unmerged", cmd], self.repo), [])

    def test_generic_and_none(self):
        self.assertEqual(self.c("git merge feature"), [["git stash push -u", "git merge feature"]])
        sh("git commit -q --allow-empty -m c1 && git commit -q --allow-empty -m c2", self.repo)
        self.assertEqual(self.c("git rebase --onto HEAD~2 HEAD~1"),
                         [["git stash push -u", "git branch backup/main", "git rebase --onto HEAD~2 HEAD~1"]])
        self.assertEqual(self.c("git commit -am x"), [])
        self.assertEqual(self.c("git -c core.x=1 reset --hard"), [])   # global options: no rule
        # two risky commands: each replaced, at most MAX_CANDIDATES lines
        many = SF.candidates(["git checkout -f feature", "git reset --hard"], self.repo)
        self.assertLessEqual(len(many), SF.MAX_CANDIDATES)
        self.assertEqual(many[0].commands, ["git stash push -u", "git checkout feature", "git stash push", "git reset --hard"])

    def test_backup_branch_keeps_commits_for_the_code_check(self):
        sh("git commit -q --allow-empty -m local-only", self.repo)
        self.assertTrue(SF.code_problems(["git reset --hard HEAD~1"], self.repo))
        self.assertEqual(SF.code_problems(["git branch keep", "git reset --hard HEAD~1"], self.repo), [])
        self.assertEqual(SF.code_problems(["git tag keep", "git reset --hard HEAD~1"], self.repo), [])
        self.assertTrue(SF.code_problems(["git branch --list keep", "git reset --hard HEAD~1"], self.repo))
        self.assertTrue(SF.code_problems(["git branch -D unmerged"], self.repo))
        self.assertEqual(SF.code_problems(["git branch -m unmerged backup/unmerged"], self.repo), [])


class TestRoutesKeepTheWork(unittest.TestCase):
    """Run each rule's first candidate in a real repository: what the original would lose is still there."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = make_repo(os.path.join(os.path.realpath(self.tmp.name), "repo"))

    def tearDown(self):
        self.tmp.cleanup()

    def run_route(self, cmd, k=0):
        route = SF.candidates([cmd], self.repo)[k].commands
        sh(" && ".join(route), self.repo)
        return route

    def test_reset_hard_keeps_changes_in_stash(self):
        self.run_route("git reset --hard")
        self.assertEqual(sh("git status --porcelain -uno", self.repo), "")
        self.assertIn("local", sh("git stash show -p stash@{0}", self.repo))

    def test_reset_to_older_commit_keeps_the_commit(self):
        sh("git commit -q --allow-empty -m local-only", self.repo)
        head = sh("git rev-parse HEAD", self.repo).strip()
        self.run_route("git reset --hard HEAD~1")
        self.assertEqual(sh("git rev-parse backup/main", self.repo).strip(), head)

    def test_checkout_file_and_clean(self):
        self.run_route("git checkout -- app.py")
        self.assertIn("local", sh("git stash show -p stash@{0}", self.repo))
        self.run_route("git clean -fd")
        self.assertFalse(os.path.exists(os.path.join(self.repo, "notes.txt")))
        self.assertIn("notes.txt", sh("git show --name-only --format= 'stash@{0}^3'", self.repo))

    def test_branch_and_stash_and_push(self):
        tip = sh("git rev-parse unmerged", self.repo).strip()
        self.run_route("git branch -D unmerged")
        self.assertEqual(sh("git rev-parse backup/unmerged", self.repo).strip(), tip)
        st = sh("git rev-parse stash@{0}", self.repo).strip()
        self.run_route("git stash drop")
        self.assertEqual(sh("git rev-parse backup/stash-0", self.repo).strip(), st)

    def test_protected_push_refuses_fetched_commits(self):
        other = os.path.join(self.tmp.name, "other")
        sh(f"git clone -q {self.repo}.remote.git {other}", self.tmp.name)
        sh("git config commit.gpgsign false && echo o > o.txt && git add o.txt && git commit -qm theirs && git push -q",
           other)
        sh("git fetch -q && git commit -q --allow-empty -m mine", self.repo)
        route = SF.candidates(["git push -f"], self.repo)[0].commands
        with self.assertRaises(subprocess.CalledProcessError):
            sh(" && ".join(route), self.repo)
        self.assertEqual(sh(f"git --git-dir={self.repo}.remote.git log -1 --format=%s main", self.repo).strip(), "theirs")
        # integrated (rebased onto the remote), the same route goes through
        sh("git stash -q -u && git rebase -q origin/main", self.repo)
        sh(" && ".join(route), self.repo)
        self.assertEqual(sh(f"git --git-dir={self.repo}.remote.git log -1 --format=%s main", self.repo).strip(), "mine")


class TestSearch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = make_repo(os.path.join(os.path.realpath(self.tmp.name), "repo"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_lowest_p_lost_then_fewest_steps(self):
        fake = Fake(lost=lambda c: {"git stash push -u": 0.01}.get(c[0], 0.9 if c == ["git reset --hard"] else 0.05))
        s = SF.search(["git reset --hard"], self.repo, client=fake)
        self.assertEqual(s.route.commands, ["git stash push -u", "git reset --hard"])
        self.assertEqual(s.tried, 2)
        self.assertEqual(s.route.text(), "Safer: git stash push -u && git reset --hard  (lose uncommitted work: 1%)")
        # equal at the shown precision: the one with fewer extra steps (branch -d: 0; the renames of two branches: 1)
        sh("git branch other unmerged && git branch third unmerged", self.repo)
        s = SF.search(["git branch -D unmerged other"], self.repo, client=Fake(lost=lambda c: 0.001))
        self.assertEqual(s.route.commands, ["git branch -d unmerged other"])

    def test_fail_and_code_checks_reject(self):
        # a step the model expects to fail is not offered: the next candidate is
        sh("git branch keep unmerged", self.repo)
        fake = Fake(fail=lambda c, k: 0.97 if c[k - 1].startswith("git branch -d") else 0.0)
        s = SF.search(["git branch -D unmerged"], self.repo, client=fake)
        self.assertEqual(s.route.commands, ["git branch -m unmerged backup/unmerged"])
        self.assertEqual(s.route.extra, 0)
        # a candidate the code checks reject is not offered even when the model passes it
        self.assertEqual(SF.search(["git push --force"], self.repo, client=Fake()).route.commands,
                         ["git push --force-with-lease --force-if-includes"])
        with mock.patch.object(SF, "code_problems", lambda c, r: ["overwrites 1 commit(s) that origin/main holds"]):
            self.assertIsNone(SF.search(["git push --force"], self.repo, client=Fake()).route)
        # the refused push is the safe outcome: the model's "fails" for that step does not reject the route
        s = SF.search(["git push --force"], self.repo, client=Fake(fail=lambda c, k: 0.95))
        self.assertEqual(s.route.commands, ["git push --force-with-lease --force-if-includes"])
        self.assertIn("rejected if the remote moved: fetch and rebase first", s.route.keeps[0])

    def test_none_passes(self):
        s = SF.search(["git reset --hard"], self.repo, client=Fake(lost=lambda c: 0.6))
        self.assertIsNone(s.route)
        self.assertEqual(s.note, "2 alternatives checked, none passed")
        self.assertEqual(s.summary(), "Safer: none (2 alternatives checked, none passed)")
        s = SF.search(["git commit -am x"], self.repo, client=Fake())
        self.assertIsNone(s.route)
        self.assertEqual(s.tried, 0)

    def test_cannot_foresee_alternatives_gives_no_route(self):
        s = SF.search(["git reset --hard"], self.repo, client=Fake(down=lambda c: True))
        self.assertIsNone(s.route)
        self.assertTrue(s.note.startswith("cannot foresee the alternatives"))
        # one candidate checked, the other not: only the checked one can be offered
        s = SF.search(["git reset --hard"], self.repo, client=Fake(down=lambda c: c[0] == "git stash push"))
        self.assertEqual(s.route.commands[0], "git stash push -u")


class TestSurfaces(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = make_repo(os.path.join(os.path.realpath(self.tmp.name), "repo"))
        self.fake = Fake(lost=lambda c: 0.99 if c == ["git reset --hard"] else 0.01)

    def tearDown(self):
        self.tmp.cleanup()

    def cli(self, *args, url=None, env=None):
        out = io.StringIO()
        patch = mock.patch.object(cli, "Ekbasis", lambda **k: self.fake) if url is None else mock.patch.dict(os.environ, {})
        with patch, mock.patch.dict(os.environ, env or {}), redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = cli.main((["--url", url, "--timeout", "2"] if url else []) + ["git-check", "--repo", self.repo, *args])
        return code, out.getvalue()

    def test_cli_text_and_json(self):
        code, out = self.cli("git reset --hard")
        self.assertEqual(code, 2)
        self.assertIn("Safer: git stash push && git reset --hard  (lose uncommitted work: 1%)", out)
        code, out = self.cli("--json", "git reset --hard")
        d = json.loads(out)
        self.assertEqual(d["safer"]["commands"], ["git stash push", "git reset --hard"])
        self.assertEqual(d["safer"]["p_lost"], 0.01)
        self.assertIsNone(d["safer_note"])

    def test_cli_opt_out_and_not_risky(self):
        n = len(self.fake.requests)
        code, out = self.cli("--no-safer", "git reset --hard")
        self.assertEqual((code, "Safer" in out, len(self.fake.requests) - n), (2, False, 1))
        code, out = self.cli("git reset --hard", env={"EKBASIS_SAFER": "0"})
        self.assertNotIn("Safer", out)
        code, out = self.cli("--json", "git stash push")
        self.assertEqual(code, 0)
        self.assertIsNone(json.loads(out)["safer"])

    def test_cli_none_passes(self):
        self.fake = Fake(lost=lambda c: 0.99)
        code, out = self.cli("git reset --hard")
        self.assertEqual(code, 2)
        self.assertIn("Safer: none (2 alternatives checked, none passed)", out)
        code, out = self.cli("--json", "git reset --hard")
        self.assertIsNone(json.loads(out)["safer"])
        self.assertEqual(json.loads(out)["safer_note"], "2 alternatives checked, none passed")

    def test_cli_server_down_still_cannot_foresee(self):
        code, out = self.cli("git reset --hard", url=dead_url())
        self.assertEqual(code, 3)
        self.assertIn("CANNOT FORESEE", out)
        self.assertNotIn("Safer", out)

    def run_hook(self, command, env=None):
        stdin = io.StringIO(json.dumps({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": self.repo}))
        out = io.StringIO()
        with mock.patch.dict(os.environ, {"EKBASIS_HOOK_DEADLINE": "10", **(env or {})}), \
                mock.patch.object(H, "Ekbasis", lambda **k: self.fake), mock.patch("sys.stdin", stdin), \
                redirect_stdout(out), redirect_stderr(io.StringIO()):
            self.assertEqual(H.main(), 0)
        text = out.getvalue().strip()
        return json.loads(text)["hookSpecificOutput"] if text else None

    def test_hook(self):
        r = self.run_hook("git reset --hard")
        self.assertEqual(r["permissionDecision"], "ask")
        self.assertIn("Safer route, checked by Ekbasis: `git stash push && git reset --hard` (lose uncommitted work: 1%; "
                      "the discarded changes stay in a stash", r["permissionDecisionReason"])
        r = self.run_hook("git reset --hard", env={"EKBASIS_SAFER": "0"})
        self.assertNotIn("Safer", r["permissionDecisionReason"])
        # a loss found by code (branch -D of an unmerged branch): the route is checked by the model too
        self.fake = Fake(fail=lambda c, k: 0.97 if c[k - 1].startswith("git branch -d") else 0.0)
        r = self.run_hook("git branch -D unmerged")
        self.assertIn("`git branch -m unmerged backup/unmerged`", r["permissionDecisionReason"])
        self.assertIn(["git branch -m unmerged backup/unmerged"], self.fake.requests)
        self.fake = Fake(lost=lambda c: 0.99)
        r = self.run_hook("git reset --hard")
        self.assertIn("No safer route passed Ekbasis's check (2 alternatives checked, none passed).",
                      r["permissionDecisionReason"])

    def test_hook_server_down_and_slow_search(self):
        self.fake = Fake(down=lambda c: True)
        r = self.run_hook("git reset --hard")
        self.assertEqual(r["permissionDecision"], "ask")
        self.assertIn("could not foresee", r["permissionDecisionReason"])
        self.assertNotIn("Safer", r["permissionDecisionReason"])
        # the original is answered, the search runs out of time: the warning goes out without a route
        slow = Fake(lost=lambda c: 0.99 if c == ["git reset --hard"] else 0.01)
        orig_ask = slow.ask
        slow.ask = lambda state, q, **k: (time.sleep(2) if commands_of(state) != ["git reset --hard"] else None) or \
            orig_ask(state, q, **k)
        self.fake = slow
        r = self.run_hook("git reset --hard", env={"EKBASIS_HOOK_DEADLINE": "1"})
        self.assertEqual(r["permissionDecision"], "ask")
        self.assertIn("may permanently lose uncommitted work", r["permissionDecisionReason"])
        self.assertNotIn("Safer", r["permissionDecisionReason"])


if __name__ == "__main__":
    unittest.main()
