"""0.1.3: less friction in the Claude Code hook (from the real-terminal study). Read-only git does not ask the model;
cd, pushd/popd, subshells and git -C are followed; folders the line creates (git worktree add) hold no uncommitted
work, so the worktree route passes; the shell part of git lines is judged; nothing recoverable asks; lost committed
work is checked by code; the coreutils version text. Offline: a fake client or a port nobody listens on."""
import io
import json
import os
import socket
import subprocess
import tempfile
import unittest
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from unittest import mock

from ekbasis import claude_code_hook as H
from ekbasis import git as G
from ekbasis import recover as R
from ekbasis import shell as S
from ekbasis.client import Answer

ENV = dict(os.environ, GIT_AUTHOR_NAME="Dev", GIT_AUTHOR_EMAIL="dev@example.invalid", GIT_COMMITTER_NAME="Dev",
           GIT_COMMITTER_EMAIL="dev@example.invalid", GIT_CONFIG_NOSYSTEM="1", LC_ALL="C")


def sh(cmd, cwd):
    subprocess.run(["bash", "-c", cmd], cwd=cwd, env=ENV, check=True, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL)


def dead_url():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return f"http://127.0.0.1:{port}"


class Fake:
    """Answers every question; counts the requests (a request means the model was asked)."""

    def __init__(self, p_lost=0.0):
        self.p_lost, self.requests = p_lost, []

    def ask(self, state, questions, read_once=False, images=None):
        self.requests.append(state)
        return {k: Answer(value=False, confidence=0.99, probabilities={"yes": self.p_lost if k == "lost" else 0.0},
                          p_yes=self.p_lost if k == "lost" else 0.0) for k in questions}


def make_repo(root):
    """main (2 commits) with origin; branches: merged (behind main), unmerged (1 own commit), pushed (1 commit that
    origin/pushed also has), a tag on the unmerged commit's parent; .gitignore with build/ and .env."""
    os.makedirs(root)
    remote = root + ".remote.git"
    for c in (f"git init -q --bare -b main {remote}",):
        sh(c, os.path.dirname(root))
    for c in ("git init -q -b main", "git config commit.gpgsign false", f"git remote add origin {remote}",
              "printf 'build/\\n.env\\n*.pyc\\n' > .gitignore", "echo v1 > app.py", "git add -A", "git commit -qm one",
              "git branch merged", "echo v2 > app.py", "git commit -qam two", "git push -q origin main",
              "git checkout -qb unmerged", "echo u > u.txt", "git add u.txt", "git commit -qm unmerged-work",
              "git checkout -q main", "git checkout -qb pushed", "echo p > p.txt", "git add p.txt",
              "git commit -qm pushed-work", "git push -q origin pushed", "git checkout -q main",
              "git tag keep unmerged", "git fetch -q origin"):
        sh(c, root)
    return root


class TestReadOnly(unittest.TestCase):
    def test_classification(self):
        ro = ["git status", "git status --short --ignored", "git log --oneline -5 --all", "git diff --stat",
              "git show HEAD:app.py", "git branch", "git branch -a", "git branch --merged master",
              "git branch -vv", "git branch --show-current", "git tag", "git tag -l 'v1*'", "git stash list",
              "git stash show -p", "git worktree list", "git remote -v", "git config --get user.name",
              "git rev-parse HEAD", "git ls-files", "git reflog", "git grep -n foo", "git -C ../x log -1",
              "git -c color.ui=false log", "git cat-file -p HEAD", "git merge-base HEAD main", "git --version"]
        rw = ["git branch foo", "git branch -D foo", "git branch -d foo", "git branch -f foo HEAD~1",
              "git branch -m old new", "git tag v1", "git tag -d v1", "git stash", "git stash drop",
              "git worktree add ../wt main", "git remote add up url", "git config user.name x",
              "git diff --output=x.patch", "git log --output x.txt", "git reflog expire --all", "git checkout main",
              "git reset --hard", "git clean -fdx", "git commit -m x", "git fetch", "git grep -O foo"]
        for c in ro:
            self.assertTrue(G.read_only(c), c)
        for c in rw:
            self.assertFalse(G.read_only(c), c)


class TestPlan(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.realpath(self.tmp.name)
        self.repo = make_repo(os.path.join(self.root, "repo"))
        os.makedirs(os.path.join(self.repo, "sub"))

    def tearDown(self):
        self.tmp.cleanup()

    def steps(self, line):
        p = H.plan_line(line, self.repo)
        return p, [(os.path.relpath(s["repo"], self.root), s["cmd"], (s["fresh"] or {}).get("kind")) for s in p.steps]

    def test_cd_and_dash_c(self):
        p, st = self.steps("cd sub && git status && cd .. && git -C sub log -1")
        self.assertEqual(p.why, [])
        self.assertEqual(st, [("repo/sub", "git status", None), ("repo/sub", "git log -1", None)])

    def test_worktree_route(self):
        for line in ("git worktree add -q ../wt unmerged && cd ../wt && git cherry-pick HEAD~1 && go test ./... 2>&1 | "
                     "tail -20",
                     "git worktree add -q ../wt unmerged && git -C ../wt cherry-pick main",
                     "git worktree add -q ../wt unmerged && (cd ../wt && go test ./... 2>&1 | tail -20); "
                     "git -C ../wt log --oneline -3"):
            p, st = self.steps(line)
            self.assertEqual(p.why, [], line)
            self.assertEqual(st[0], ("repo", "git worktree add -q ../wt unmerged", None), line)
            self.assertTrue(all(r == "wt" and kind == "worktree" for r, _, kind in st[1:]), (line, st))

    def test_subshell_cd_does_not_leak(self):
        p, st = self.steps("(cd sub && ls); git status")
        self.assertEqual(st, [("repo", "git status", None)])

    def test_cannot_follow(self):
        for line in ("cd ../missing; git reset --hard", "cd $DIR && git reset --hard", "cd - && git reset --hard",
                     "git -C ../missing reset --hard", "git --git-dir=../x/.git status",
                     "git branch | grep -v main | xargs git branch -D", "{ cd sub; git status; }"):
            self.assertTrue(H.plan_line(line, self.repo).why, line)

    def test_xargs_safe_forms(self):
        for line in ("git branch --merged main | grep -v main | xargs git branch -d",
                     "git ls-files | xargs git log -1 --"):
            self.assertEqual(H.plan_line(line, self.repo).why, [], line)

    def test_shell_part(self):
        p = H.plan_line("git diff > out.patch && rm -rf build; git status", self.repo)
        self.assertEqual(p.shell_line.split(), ["true", ">", "out.patch", "&&", "rm", "-rf", "build;", "true"])
        msg = "git add -A && git commit -m \"$(cat <<'EOF'\nfix: x\nEOF\n)\""
        self.assertFalse(H.changes_files(H.plan_line(msg, self.repo).shell_line))
        self.assertEqual(H.plan_line("rm -rf build", self.repo).shell_line, "rm -rf build")  # no git: the line as is


class TestCommittedLoss(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = make_repo(os.path.join(os.path.realpath(self.tmp.name), "repo"))

    def tearDown(self):
        self.tmp.cleanup()

    def loss(self, *cmds):
        out = G.committed_loss([{"repo": self.repo, "cmd": c, "fresh": None} for c in cmds])
        return sum(x["commits"] for x in out), [d["ref"] for x in out for d in x["refs"]]

    def test_cases(self):
        self.assertEqual(self.loss("git branch -D merged"), (0, []))
        self.assertEqual(self.loss("git branch -D pushed"), (0, []))           # origin/pushed holds it
        self.assertEqual(self.loss("git branch -d unmerged"), (0, []))         # git refuses
        self.assertEqual(self.loss("git branch -D unmerged"), (0, []))         # the tag keep holds it
        self.assertEqual(self.loss("git branch -D unmerged", "git tag -d keep"),
                         (1, ["refs/heads/unmerged", "refs/tags/keep"]))
        self.assertEqual(self.loss("git tag -d keep", "git branch -D unmerged")[0], 1)
        self.assertEqual(self.loss("git branch --delete --force unmerged", "git tag --delete keep")[0], 1)
        self.assertEqual(self.loss("git status", "git log"), (0, []))
        sh("git commit -q --allow-empty -m local-only", self.repo)
        self.assertEqual(self.loss("git reset --hard HEAD~1"), (1, ["refs/heads/main"]))
        self.assertEqual(self.loss("git reset --hard origin/main"), (1, ["refs/heads/main"]))
        self.assertEqual(self.loss("git reset HEAD~1 -- app.py"), (0, []))     # a path reset moves no branch
        self.assertEqual(self.loss("git reset --soft HEAD~1"), (0, []))       # the changes stay in the work tree
        self.assertEqual(self.loss("git reset HEAD~1"), (0, []))
        self.assertEqual(self.loss("git reset --keep HEAD~1"), (1, ["refs/heads/main"]))
        self.assertEqual(self.loss("git checkout -B main HEAD~1"), (1, ["refs/heads/main"]))
        self.assertEqual(self.loss("git checkout -q merged", "git branch -f main merged"), (1, ["refs/heads/main"]))
        self.assertEqual(self.loss("git stash drop"), (0, []))                 # the model's question, not this one
        self.assertIn("deletes branch unmerged", G.describe_loss(
            G.committed_loss([{"repo": self.repo, "cmd": c, "fresh": None}
                              for c in ("git tag -d keep", "git branch -D unmerged")])[0]))


class TestRecover(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = make_repo(os.path.join(os.path.realpath(self.tmp.name), "repo"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_rebuildable(self):
        for p in ("build/x.o", "a/__pycache__/m.pyc", "node_modules/x/index.js", "pkg.egg-info/PKG-INFO", ".DS_Store",
                  "dist", ".pytest_cache/v/cache"):
            self.assertTrue(R.rebuildable(p), p)
        for p in (".env", ".venv/bin/python", "notes/todo.md", ".idea/workspace.xml", "secrets.json"):
            self.assertFalse(R.rebuildable(p), p)

    def test_no_uncommitted_work(self):
        self.assertTrue(R.no_uncommitted_work(self.repo))
        os.makedirs(os.path.join(self.repo, "build"))
        open(os.path.join(self.repo, "build", "out.o"), "w").write("x")
        self.assertTrue(R.no_uncommitted_work(self.repo))                     # ignored and rebuildable
        open(os.path.join(self.repo, ".env"), "w").write("KEY=1")
        self.assertIsNone(R.no_uncommitted_work(self.repo))                   # ignored but not rebuildable
        os.remove(os.path.join(self.repo, ".env"))
        open(os.path.join(self.repo, "notes.md"), "w").write("mine")
        self.assertIsNone(R.no_uncommitted_work(self.repo))                   # untracked
        os.remove(os.path.join(self.repo, "notes.md"))
        sh("echo v3 > app.py && git stash -q", self.repo)
        self.assertIsNone(R.no_uncommitted_work(self.repo))                   # a stash entry

    def touched(self, line):
        view = S.inspect([line], self.repo)
        return R.touched_recoverable(view, self.repo)

    def test_git_clean_dry_run(self):
        os.makedirs(os.path.join(self.repo, "build"))
        open(os.path.join(self.repo, "build", "out.o"), "w").write("x")
        self.assertTrue(R.clean_recoverable(self.repo, "git clean -fdX"))
        open(os.path.join(self.repo, ".env"), "w").write("KEY=1")
        self.assertFalse(R.clean_recoverable(self.repo, "git clean -fdX"))      # .env is ignored, not rebuildable
        os.remove(os.path.join(self.repo, ".env"))
        open(os.path.join(self.repo, "notes.md"), "w").write("mine")
        self.assertTrue(R.clean_recoverable(self.repo, "git clean -fdX"))       # -X leaves untracked files alone
        self.assertFalse(R.clean_recoverable(self.repo, "git clean -fd"))       # notes.md would go
        self.assertFalse(R.clean_recoverable(self.repo, "git clean -fdx"))      # -x: left to the model
        os.makedirs(os.path.join(self.repo, "pkg", "__pycache__"))            # a folder of only ignored files
        open(os.path.join(self.repo, "pkg", "__pycache__", "m.pyc"), "w").write("x")
        self.assertTrue(R.clean_recoverable(self.repo, "git clean -fdX"))
        self.assertTrue(G.read_only("git clean -ndx"))

    def test_touched(self):
        os.makedirs(os.path.join(self.repo, "build"))
        open(os.path.join(self.repo, "build", "out.o"), "w").write("x")
        self.assertTrue(self.touched("sed -i '' 's/v2/v3/' app.py"))           # clean, tracked
        self.assertTrue(self.touched("rm -rf build dist"))                     # ignored, rebuildable; dist missing
        self.assertTrue(self.touched("grep -rn v2 . && sed -i '' 's/v2/v3/' app.py"))  # the grep only reads
        self.assertTrue(self.touched("sed -i '' 's/v2/v3/' app.py && gofmt -l . ; go test ./... && python -m pytest -q"))
        self.assertIsNone(self.touched("sed -i '' 's/v2/v3/' app.py && gofmt -w ."))  # gofmt -w writes the folder
        self.assertIsNone(self.touched("rm -rf .git"))
        self.assertIsNone(self.touched("rm -rf ."))
        self.assertIsNone(self.touched("ls | xargs rm"))
        open(os.path.join(self.repo, "notes.md"), "w").write("mine")
        self.assertIsNone(self.touched("rm notes.md"))                         # untracked
        sh("echo v9 > app.py", self.repo)
        self.assertIsNone(self.touched("sed -i '' 's/v9/v3/' app.py"))         # uncommitted change


class TestHook(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.realpath(self.tmp.name)
        self.repo = make_repo(os.path.join(self.root, "repo"))

    def tearDown(self):
        self.tmp.cleanup()

    def run_hook(self, command, env=None, client=None):
        stdin = io.StringIO(json.dumps({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": self.repo}))
        out = io.StringIO()
        base = {"EKBASIS_URL": dead_url(), "EKBASIS_HOOK_DEADLINE": "5", "EKBASIS_SHELL_GUARD": "1"}
        with ExitStack() as stack:
            stack.enter_context(mock.patch.dict(os.environ, {**base, **(env or {})}))
            stack.enter_context(mock.patch("sys.stdin", stdin))
            if client is not None:
                stack.enter_context(mock.patch.object(H, "Ekbasis", lambda **k: client))
            stack.enter_context(redirect_stdout(out))
            stack.enter_context(redirect_stderr(io.StringIO()))
            self.assertEqual(H.main(), 0)
        text = out.getvalue().strip()
        if not text:
            return None, ""
        h = json.loads(text)["hookSpecificOutput"]
        return h["permissionDecision"], h["permissionDecisionReason"]

    def test_read_only_and_clean(self):
        sh("echo v3 > app.py", self.repo)  # uncommitted work: the git guard would ask the (dead) server
        for line in ("git status", "git log --oneline -5 && git diff --stat", "git branch --merged main"):
            self.assertEqual(self.run_hook(line), (None, ""), line)
        self.assertEqual(self.run_hook("git checkout -- app.py")[0], "ask")  # server down: cannot judge
        sh("git checkout -- app.py", self.repo)
        self.assertEqual(self.run_hook("git checkout -- app.py"), (None, ""))  # nothing uncommitted anywhere
        self.assertEqual(self.run_hook("git checkout -- app.py", env={"EKBASIS_SHORTCUTS": "0"})[0], "ask")

    def test_committed_work(self):
        d, why = self.run_hook("git tag -d keep && git branch -D unmerged")
        self.assertEqual(d, "ask")
        self.assertIn("committed work", why)
        self.assertIn("deletes branch unmerged", why)
        self.assertEqual(self.run_hook("git branch -D merged"), (None, ""))

    def test_worktree_route_passes(self):
        sh("echo wip >> app.py", self.repo)  # uncommitted work in the main worktree, as in the study's backport
        fake = Fake(p_lost=0.0)
        line = "git worktree add -q ../wt unmerged && cd ../wt && git cherry-pick pushed && go test ./... 2>&1 | tail -5"
        self.assertEqual(self.run_hook(line, client=fake), (None, ""))
        self.assertEqual(len(fake.requests), 1)  # the worktree add in the main repo; nothing for the new worktree

    def test_shell_part_and_recoverable(self):
        fake = Fake(p_lost=0.9)
        self.assertEqual(self.run_hook("sed -i '' 's/v2/v3/' app.py && git diff --stat", client=fake), (None, ""))
        self.assertEqual(fake.requests, [])  # committed content: no model call
        open(os.path.join(self.repo, "notes.md"), "w").write("mine")
        d, why = self.run_hook("git status && rm notes.md", client=fake)
        self.assertEqual(d, "ask")
        self.assertIn("shell guard", why)

    def test_unchanged_prompt_for_lines_0_1_2_judged(self):
        sh("echo v3 > app.py", self.repo)
        a, b = Fake(), Fake()
        self.run_hook("git stash && git checkout merged", client=a)
        G.check(["git stash", "git checkout merged"], repo=self.repo, client=b)
        self.assertEqual(len(a.requests), 1)
        self.assertEqual(a.requests, b.requests)


class TestCoreutilsText(unittest.TestCase):
    def test_format_per_call(self):
        cmd = ["echo", "ls (GNU coreutils) 9.4"]
        S._VERSIONS.pop(" ".join(cmd), None)
        self.assertEqual(S._version(cmd, r"coreutils\)?\s*([\d.]+)", "{}"), "9.4")
        self.assertEqual(S._version(cmd, r"coreutils\)?\s*([\d.]+)", "GNU coreutils {}"), "GNU coreutils 9.4")


if __name__ == "__main__":
    unittest.main()
