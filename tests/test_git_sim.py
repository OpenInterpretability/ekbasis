"""0.1.33: failures found by running the git commands on a copy (real repositories; the real one is never touched)."""
import hashlib
import os
import subprocess
import tempfile
import unittest

from ekbasis import git as G
from ekbasis import git_sim


def sh(cwd, *args):
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True).stdout


def snapshot(d):
    """Every file under d (the .git folder included), hashed: the real repository must not change."""
    h = hashlib.sha256()
    for root, dirs, files in sorted(os.walk(d)):
        dirs.sort()
        for f in sorted(files):
            p = os.path.join(root, f)
            h.update(p.encode())
            with open(p, "rb") as fh:
                h.update(fh.read())
    return h.hexdigest()


class Fake:
    def ask(self, state, qs):
        from ekbasis.client import Answer
        return {k: Answer(value=False, confidence=0.98, p_yes=0.02) for k in qs}   # "nothing fails, nothing lost"


class TestGitSim(unittest.TestCase):
    def repo(self):
        d = tempfile.mkdtemp()
        sh(d, "git", "init", "-q", "-b", "main")
        sh(d, "git", "config", "user.email", "t@t")
        sh(d, "git", "config", "user.name", "t")
        for f in ("a.txt", "b.txt"):
            open(os.path.join(d, f), "w").write(f)
        sh(d, "git", "add", ".")
        sh(d, "git", "commit", "-qm", "base")
        sh(d, "git", "switch", "-q", "-c", "exp")
        open(os.path.join(d, "e.txt"), "w").write("e")
        sh(d, "git", "add", "e.txt")
        sh(d, "git", "commit", "-qm", "exp")
        sh(d, "git", "switch", "-q", "main")
        open(os.path.join(d, "a.txt"), "a").write("m")
        sh(d, "git", "commit", "-qam", "main")
        sh(d, "git", "switch", "-q", "exp")
        return d

    def test_rebase_after_git_rm_fails_and_the_real_repo_is_untouched(self):
        d = self.repo()
        before = snapshot(d)
        out = git_sim.run_on_copy(d, ["git rm -q b.txt", "git rebase main", "git status"])
        self.assertEqual(snapshot(d), before)
        self.assertEqual(out["ran"], 3)
        self.assertEqual(out["exit"][0], 0)
        self.assertNotEqual(out["exit"][1], 0)    # git refuses: the index has uncommitted changes
        self.assertEqual(out["exit"][2], 0)

    def test_stash_then_rebase_succeeds(self):
        d = self.repo()
        open(os.path.join(d, "b.txt"), "a").write("x")
        out = git_sim.run_on_copy(d, ["git stash", "git rebase main"])
        self.assertEqual(out["exit"], [0, 0])

    def test_stops_before_network_and_unknown_commands(self):
        d = self.repo()
        out = git_sim.run_on_copy(d, ["git status", "git push origin main", "git status"])
        self.assertEqual(out["ran"], 1)
        self.assertIn("push", out["stopped"])

    def test_hooks_do_not_run(self):
        d = self.repo()
        marker = os.path.join(tempfile.mkdtemp(), "hook-ran")
        hook = os.path.join(d, ".git", "hooks", "pre-commit")
        with open(hook, "w") as f:
            f.write(f"#!/bin/sh\ntouch {marker}\n")
        os.chmod(hook, 0o755)
        open(os.path.join(d, "b.txt"), "a").write("x")
        out = git_sim.run_on_copy(d, ["git commit -qam msg"])
        self.assertEqual(out["exit"], [0])
        self.assertFalse(os.path.exists(marker))

    def test_check_uses_the_copy_only_when_asked(self):
        d = self.repo()
        sh(d, "git", "rm", "-q", "b.txt")
        v = G.check(["git status", "git rebase main"], repo=d, client=Fake(), simulate=True)
        self.assertEqual(v.p_fail, [0.0, 1.0])
        self.assertEqual(v.simulated, 2)
        self.assertTrue(any("run on a copy" in r for r in v.reasons))
        self.assertFalse(v.risky)
        w = G.check(["git status", "git rebase main"], repo=d, client=Fake(), simulate=False)
        self.assertEqual(w.p_fail, [0.02, 0.02])   # the model's answers, unchanged
