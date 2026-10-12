"""0.1.23: remote work this clone never fetched (git ls-remote) and the commit a `rebase --skip` drops."""
import os
import subprocess
import tempfile
import unittest

from ekbasis import git as G

ENV = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1", GIT_AUTHOR_NAME="t",
           GIT_AUTHOR_EMAIL="t@x", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@x", GIT_EDITOR="true")


def git(repo, *a, check=True):
    return subprocess.run(["git", "-C", repo, *a], check=check, capture_output=True, text=True, env=ENV)


def commit(repo, name, text, msg):
    open(os.path.join(repo, name), "w").write(text)
    git(repo, "add", name)
    git(repo, "commit", "-q", "-m", msg)


class TestRemoteUnseen(unittest.TestCase):
    def setUp(self):
        d = tempfile.mkdtemp()
        self.bare, self.me, other = f"{d}/r.git", f"{d}/me", f"{d}/other"
        git(d, "init", "-q", "--bare", "-b", "main", self.bare)
        git(d, "clone", "-q", self.bare, self.me)
        commit(self.me, "a", "1\n", "a")
        git(self.me, "push", "-q", "origin", "main")
        git(d, "clone", "-q", self.bare, other)
        commit(other, "b", "colleague\n", "b")
        git(other, "push", "-q", "origin", "main")
        git(other, "push", "-q", "origin", "main:infra")
        commit(self.me, "a", "2\n", "mine")

    def test_force_over_unfetched(self):
        self.assertEqual(G.remote_unseen(self.me, ["git push --force origin main"]),
                         [{"ref": "origin/main", "deleted": False}])
        self.assertEqual(G.remote_unseen(self.me, ["git push origin main"]), [])
        self.assertEqual(G.remote_unseen(self.me, ["git push --force-with-lease origin main"]), [])

    def test_mirror_deletes_unknown_branches(self):
        got = G.remote_unseen(self.me, ["git push --mirror origin"])
        self.assertIn({"ref": "origin/infra", "deleted": True}, got)

    def test_after_fetch_nothing_unseen(self):
        git(self.me, "fetch", "-q", "origin")
        self.assertEqual(G.remote_unseen(self.me, ["git push --force origin main"]), [])

    def test_unreachable_remote_adds_nothing(self):
        git(self.me, "remote", "add", "gone", "/nonexistent/x.git")
        self.assertEqual(G.remote_unseen(self.me, ["git push --force gone main", "git push --mirror gone"]), [])


class TestSkipLoss(unittest.TestCase):
    def test_skip_drops_unique_commit(self):
        r = tempfile.mkdtemp()
        git(r, "init", "-q", "-b", "main")
        commit(r, "f", "base\n", "base")
        git(r, "checkout", "-q", "-b", "feat")
        commit(r, "f", "mine\n", "mine")
        git(r, "checkout", "-q", "main")
        commit(r, "f", "theirs\n", "theirs")
        git(r, "checkout", "-q", "feat")
        git(r, "rebase", "main", check=False)
        got = G.skip_loss(r, "git rebase --skip")
        self.assertIsNotNone(got)
        self.assertEqual(got["subject"], "mine")
        self.assertIsNone(G.skip_loss(r, "git rebase --continue"))
        git(r, "branch", "keep", "REBASE_HEAD")
        self.assertIsNone(G.skip_loss(r, "git rebase --skip"))


if __name__ == "__main__":
    unittest.main()


class TestOverwrites(unittest.TestCase):
    def test_cp_over_a_different_untracked_file(self):
        from ekbasis import recover as R
        from ekbasis import shell as S
        d = tempfile.mkdtemp()
        os.makedirs(f"{d}/ex")
        os.makedirs(f"{d}/cfg")
        for n, t in (("ex/a.yaml", "x"), ("ex/b.yaml", "y"), ("cfg/a.yaml", "mine"), ("cfg/b.yaml", "y")):
            open(f"{d}/{n}", "w").write(t)
        over = lambda line: R.overwrites(S.inspect([line], d), d)  # noqa: E731
        self.assertEqual(over("cp ex/* cfg/"), [("cfg/a.yaml", "ex/a.yaml")])
        self.assertEqual(over("cp -n ex/* cfg/"), [])
        self.assertEqual(over("mv ex/a.yaml cfg/a.yaml"), [("cfg/a.yaml", "ex/a.yaml")])
        self.assertEqual(over("cp ex/b.yaml cfg/"), [])   # same content
        git(d, "init", "-q")
        git(d, "add", "cfg/a.yaml")
        git(d, "commit", "-q", "-m", "a")
        self.assertEqual(over("cp ex/a.yaml cfg/"), [])   # committed and unchanged: recoverable


class TestAtStakeStash(unittest.TestCase):
    def test_unique_stash_is_named(self):
        r = tempfile.mkdtemp()
        git(r, "init", "-q", "-b", "main")
        commit(r, "a", "1\n", "a")
        open(os.path.join(r, "a"), "w").write("merged\n")
        git(r, "stash", "push", "-q", "-m", "old")
        git(r, "stash", "apply", "-q")
        git(r, "commit", "-qam", "merged")
        open(os.path.join(r, "a"), "w").write("unique\n")
        git(r, "stash", "push", "-q", "-m", "wip")
        s = G.at_stake(r, ["git stash clear"])
        self.assertIn('NO branch, lost for good if dropped: stash@{0} "On main: wip"', s)
        self.assertIn("stash@{1} (already on branch main)", s)
