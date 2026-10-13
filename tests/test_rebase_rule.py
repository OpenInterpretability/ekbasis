"""0.1.32: `git rebase` over uncommitted tracked changes fails by code (real git repositories)."""
import os
import subprocess
import tempfile
import unittest

from ekbasis import git as G


def sh(cwd, *args):
    subprocess.run(args, cwd=cwd, check=True, capture_output=True)


class TestRebaseRefused(unittest.TestCase):
    def repo(self):
        d = tempfile.mkdtemp()
        sh(d, "git", "init", "-q", "-b", "main")
        sh(d, "git", "config", "user.email", "t@t")
        sh(d, "git", "config", "user.name", "t")
        for f in ("a.txt", "b.txt"):
            open(os.path.join(d, f), "w").write(f)
        sh(d, "git", "add", ".")
        sh(d, "git", "commit", "-qm", "base")
        return d

    def test_unstaged_and_staged_changes_refuse(self):
        d = self.repo()
        open(os.path.join(d, "b.txt"), "a").write("x")
        self.assertIsNotNone(G.rebase_refused(d, ["git rebase main"]))
        sh(d, "git", "add", "b.txt")
        self.assertIsNotNone(G.rebase_refused(d, ["git rebase main", "git status"]))

    def test_clean_untracked_autostash_and_later_rebase_do_not(self):
        d = self.repo()
        self.assertIsNone(G.rebase_refused(d, ["git rebase main"]))
        open(os.path.join(d, "new.txt"), "w").write("u")
        self.assertIsNone(G.rebase_refused(d, ["git rebase main"]))
        open(os.path.join(d, "b.txt"), "a").write("x")
        self.assertIsNone(G.rebase_refused(d, ["git rebase --autostash main"]))
        self.assertIsNone(G.rebase_refused(d, ["git rebase --abort"]))
        self.assertIsNone(G.rebase_refused(d, ["git stash", "git rebase main"]))   # only the first command
        sh(d, "git", "config", "rebase.autoStash", "true")
        self.assertIsNone(G.rebase_refused(d, ["git rebase main"]))

    def test_check_sets_p_fail_by_code(self):
        d = self.repo()
        open(os.path.join(d, "b.txt"), "a").write("x")

        class Fake:
            def ask(self, state, qs):
                from ekbasis.client import Answer
                return {k: Answer(value=False, confidence=0.98, p_yes=0.02) for k in qs}
        v = G.check(["git rebase main"], repo=d, client=Fake())
        self.assertEqual(v.p_fail[0], 1.0)
        self.assertTrue(any("decided by code" in r for r in v.reasons))
        self.assertFalse(v.risky)   # a refusal loses nothing
