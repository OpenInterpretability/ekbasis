"""Lost work checked by code, from an outside tester's report: a force-push is checked against the branch its refspec
names (not origin/HEAD), --force-with-lease without --force-if-includes does not protect fetched commits, deleting a
remote branch whose commits no other ref holds is flagged, and `git rebase --onto` counts the commits it drops.
Offline, on real repositories with a bare remote."""
import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from ekbasis import claude_code_hook as H
from ekbasis import git as G

ENV = dict(os.environ, GIT_AUTHOR_NAME="Dev", GIT_AUTHOR_EMAIL="dev@example.invalid", GIT_COMMITTER_NAME="Dev",
           GIT_COMMITTER_EMAIL="dev@example.invalid", GIT_CONFIG_NOSYSTEM="1", LC_ALL="C")


def sh(cmd, cwd):
    return subprocess.run(["bash", "-c", cmd], cwd=cwd, env=ENV, check=True, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, text=True).stdout


def lost(repo, *cmds):
    return sum(l["commits"] for l in G.committed_loss([{"repo": repo, "cmd": c, "fresh": None} for c in cmds]))


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = os.path.realpath(self.tmp.name)
        self.repo, self.remote = os.path.join(root, "work"), os.path.join(root, "origin.git")
        sh(f"git init -q --bare -b main {self.remote}", root)
        os.makedirs(self.repo)
        for c in ("git init -q -b main", "git config commit.gpgsign false", f"git remote add origin {self.remote}",
                  "echo 1 > a", "git add a", "git commit -qm one", "git push -q -u origin main"):
            sh(c, self.repo)
        # someone else pushes to main; we fetch it
        other = os.path.join(root, "other")
        sh(f"git clone -q {self.remote} {other}", root)
        sh("git config commit.gpgsign false && echo t > t && git add t && git commit -qm theirs && git push -q", other)
        sh("git fetch -q", self.repo)

    def tearDown(self):
        self.tmp.cleanup()

    def remote_head(self, branch="main"):
        return sh(f"git --git-dir={self.remote} log -1 --format=%s {branch}", self.repo).strip()


class TestPushDestination(Base):
    def test_branch_without_upstream_is_checked_against_its_own_name(self):
        sh("git checkout -qb topic && git commit -q --allow-empty -m mine", self.repo)
        for cmd in ("git push -f origin topic", "git push --force origin HEAD:topic", "git push -f origin topic:topic",
                    "git push origin +topic", "git push -f"):
            self.assertEqual(G.remote_loss(self.repo, [cmd]), [], cmd)   # origin/topic does not exist: a new branch
        # it was checked against origin/main before (the false alarm)
        sh("git push -q origin topic", self.repo)
        sh(f"git --git-dir={self.remote} update-ref refs/heads/topic main", self.repo)   # someone moves it
        sh("git fetch -q", self.repo)
        self.assertEqual(G.remote_loss(self.repo, ["git push -f origin topic"]),
                         [{"ref": "origin/topic", "commits": 1, "deleted": False}])
        self.assertEqual(G.remote_loss(self.repo, ["git push -f origin topic:main"])[0]["ref"], "origin/main")

    def test_lease_forms(self):
        sh("git commit -q --allow-empty -m mine", self.repo)
        sha = sh("git rev-parse origin/main", self.repo).strip()
        old = sh("git rev-parse origin/main~1", self.repo).strip()
        self.assertEqual(G.remote_loss(self.repo, ["git push --force-with-lease"])[0]["commits"], 1)
        self.assertEqual(len(G.remote_loss(self.repo, [f"git push --force-with-lease=main:{sha}"])), 1)
        self.assertEqual(G.remote_loss(self.repo, [f"git push --force-with-lease=main:{old}"]), [])  # would fail
        if G.git_version(self.repo) >= (2, 30):
            self.assertEqual(G.remote_loss(self.repo, ["git push --force-with-lease --force-if-includes"]), [])
        # what git really does with each form, on the bare remote
        r = subprocess.run(["git", "push", "--force-with-lease", "--force-if-includes"], cwd=self.repo, env=ENV,
                           capture_output=True)
        if G.git_version(self.repo) >= (2, 30):
            self.assertNotEqual(r.returncode, 0)
            self.assertEqual(self.remote_head(), "theirs")
        sh("git push -q --force-with-lease", self.repo)
        self.assertEqual(self.remote_head(), "mine")   # the plain lease overwrote the fetched commit


class TestRemoteDelete(Base):
    def test_delete_remote_only_branch(self):
        sh("git checkout -qb gone && git commit -q --allow-empty -m only-here && git push -q origin gone", self.repo)
        sh("git checkout -q main && git branch -D gone", self.repo)
        for cmd in ("git push origin --delete gone", "git push origin :gone", "git push -d origin gone"):
            self.assertEqual(G.remote_loss(self.repo, [cmd]), [{"ref": "origin/gone", "commits": 1, "deleted": True}], cmd)
        sh("git branch keep origin/gone", self.repo)
        self.assertEqual(G.remote_loss(self.repo, ["git push origin --delete gone"]), [])
        self.assertEqual(G.remote_loss(self.repo, ["git push origin --delete nothere"]), [])

    def test_hook_message(self):
        sh("git checkout -qb gone && git commit -q --allow-empty -m only-here && git push -q origin gone", self.repo)
        sh("git checkout -q main && git branch -D gone", self.repo)
        stdin = io.StringIO(json.dumps({"tool_name": "Bash", "tool_input": {"command": "git push origin --delete gone"},
                                        "cwd": self.repo}))
        out = io.StringIO()
        with mock.patch.dict(os.environ, {"EKBASIS_URL": "http://127.0.0.1:9", "EKBASIS_SAFER": "0"}), \
                mock.patch("sys.stdin", stdin), redirect_stdout(out), redirect_stderr(io.StringIO()):
            H.main()
        msg = json.loads(out.getvalue())["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("deletes the remote branch origin/gone, whose 1 commit(s) no other branch", msg)


class TestRebaseOnto(Base):
    def test_dropped_commits(self):
        sh("git reset -q --hard origin/main", self.repo)
        for n in (1, 2, 3, 4):
            sh(f"git commit -q --allow-empty -m c{n}", self.repo)
        self.assertEqual(lost(self.repo, "git rebase --onto HEAD~3 HEAD~1"), 2)    # c2, c3 are dropped
        self.assertEqual(lost(self.repo, "git rebase --onto HEAD~1 HEAD~1"), 0)    # nothing dropped
        self.assertEqual(lost(self.repo, "git rebase HEAD~2"), 0)                  # no --onto: commits are replayed
        self.assertEqual(lost(self.repo, "git rebase -i --onto HEAD~3 HEAD~1"), 2)
        # what git really does: c2 and c3 are no longer on any ref
        sh("git rebase -q --onto HEAD~3 HEAD~1", self.repo)
        self.assertEqual(sh("git log --format=%s", self.repo).split()[:2], ["c4", "c1"])

    def test_upstream_held_by_a_branch_and_branch_argument(self):
        sh("git reset -q --hard origin/main && git checkout -qb base && git commit -q --allow-empty -m b1", self.repo)
        sh("git checkout -qb topic && git commit -q --allow-empty -m t1 && git checkout -q main", self.repo)
        self.assertEqual(lost(self.repo, "git rebase --onto main base topic"), 0)   # b1 stays on base
        sh("git branch -D base", self.repo)
        self.assertEqual(lost(self.repo, "git rebase --onto main topic~1 topic"), 1)   # b1 was only on topic


if __name__ == "__main__":
    unittest.main()
