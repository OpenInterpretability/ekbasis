"""The guards fail closed (0.1.2): a line they cannot read, a folder or repository they cannot read, a server that is
down or too slow give "cannot judge", treated as risky (CLI exit 3; the Claude Code hook asks), unless the caller opts
out. Offline: a fake client, a port nobody listens on, and a local server that answers too late."""
import http.server
import io
import json
import os
import socket
import subprocess
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from ekbasis import claude_code_hook as H
from ekbasis import cli
from ekbasis import git as G
from ekbasis import shell as S
from ekbasis.client import Answer, CannotJudge, Ekbasis

ENV = dict(os.environ, GIT_AUTHOR_NAME="Dev", GIT_AUTHOR_EMAIL="dev@example.invalid", GIT_COMMITTER_NAME="Dev",
           GIT_COMMITTER_EMAIL="dev@example.invalid", GIT_CONFIG_NOSYSTEM="1", LC_ALL="C")


class FakeClient:
    def __init__(self, p_lost=0.0):
        self.p_lost = p_lost

    def ask(self, state, questions, read_once=False, images=None):
        return {k: Answer(value=False, confidence=0.99, probabilities={"yes": self.p_lost if k == "lost" else 0.0},
                          p_yes=self.p_lost if k == "lost" else 0.0) for k in questions}


def dead_url():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return f"http://127.0.0.1:{port}"


class Slow(http.server.BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        time.sleep(2)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *a):
        pass


def repo(root):
    os.makedirs(root)
    for c in ("git init -q -b main", "git config commit.gpgsign false", "echo v1 > app.py", "git add -A",
              "git commit -qm init", "echo v2 > app.py"):
        subprocess.run(["bash", "-c", c], cwd=root, env=ENV, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return root


class TestClient(unittest.TestCase):
    def test_server_down(self):
        with self.assertRaises(CannotJudge):
            Ekbasis(url=dead_url(), timeout=2).ask("s", {"q": {"type": "noul", "instructions": "q?"}})

    def test_timeout(self):
        srv = http.server.HTTPServer(("127.0.0.1", 0), Slow)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            with self.assertRaises(CannotJudge) as cm:
                Ekbasis(url=f"http://127.0.0.1:{srv.server_address[1]}", timeout=0.3).ask("s", {})
            self.assertIn("did not answer within", str(cm.exception))
        finally:
            srv.shutdown()


class TestShell(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.box = os.path.join(self.tmp.name, "box")
        os.makedirs(self.box)
        open(os.path.join(self.box, "f.txt"), "w").write("x\n")

    def tearDown(self):
        self.tmp.cleanup()

    def test_unparseable_line_is_risky_unless_opted_out(self):
        for line in ("rm 'unclosed", "(cd x && rm -rf *)", 'rm -rf "$DIR"/*', "bash -c 'rm -rf x'"):
            v = S.check([line], cwd=self.box, client=FakeClient(0.0), salt="k", where="t")
            self.assertTrue(v.cannot_judge and v.risky and not v.judged, line)
            v = S.check([line], cwd=self.box, client=FakeClient(0.0), salt="k", where="t", fail_closed=False)
            self.assertFalse(v.risky, line)

    def test_missing_folder(self):
        with self.assertRaises(CannotJudge):
            S.check(["rm f.txt"], cwd=os.path.join(self.box, "nope"), client=FakeClient())

    def cli(self, *args, url=None):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main((["--url", url, "--timeout", "2"] if url else []) + list(args))
        return code, out.getvalue()

    def test_cli(self):
        self.assertEqual(self.cli("shell-check", "--cwd", os.path.join(self.box, "nope"), "ls")[0], 3)
        self.assertEqual(self.cli("shell-check", "--cwd", os.path.join(self.box, "nope"), "--fail-open", "ls")[0], 0)
        code, out = self.cli("shell-check", "--cwd", self.box, "rm f.txt", url=dead_url())
        self.assertEqual(code, 3)
        self.assertIn("CANNOT JUDGE", out)
        self.assertEqual(self.cli("shell-check", "--cwd", self.box, "--fail-open", "rm f.txt", url=dead_url())[0], 0)


class TestGit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = repo(os.path.join(self.tmp.name, "repo"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_unreadable_repository_other_repository_and_alias(self):
        with self.assertRaises(CannotJudge):
            G.check(["git reset --hard"], repo=os.path.join(self.tmp.name, "missing"), client=FakeClient())
        with self.assertRaises(CannotJudge):
            G.check(["git reset --hard"], repo=self.tmp.name, client=FakeClient())  # not a work tree
        with self.assertRaises(CannotJudge):
            G.check(["git -C ../elsewhere reset --hard"], repo=self.repo, client=FakeClient())
        subprocess.run(["git", "config", "alias.wipe", "reset --hard"], cwd=self.repo, env=ENV, check=True)
        with self.assertRaises(CannotJudge):
            G.check(["git wipe"], repo=self.repo, client=FakeClient())
        v = G.check(["git wipe"], repo=self.repo, client=FakeClient(), fail_closed=False)
        self.assertFalse(v.risky)

    def test_cli_server_down(self):
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = cli.main(["--url", dead_url(), "--timeout", "2", "git-check", "--repo", self.repo, "git reset --hard"])
        self.assertEqual(code, 3)
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            code = cli.main(["--url", dead_url(), "--timeout", "2", "git-check", "--repo", self.repo, "--fail-open",
                             "git reset --hard"])
        self.assertEqual(code, 0)


class TestHook(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = repo(os.path.join(self.tmp.name, "repo"))

    def tearDown(self):
        self.tmp.cleanup()

    def run_hook(self, command, env=None, cwd=None, raw=None):
        stdin = io.StringIO(raw if raw is not None else json.dumps({"tool_name": "Bash", "tool_input": {"command": command},
                                                                     "cwd": cwd or self.repo}))
        out = io.StringIO()
        base = {"EKBASIS_URL": dead_url(), "EKBASIS_HOOK_DEADLINE": "5"}
        with mock.patch.dict(os.environ, {**base, **(env or {})}), mock.patch("sys.stdin", stdin), \
                redirect_stdout(out), redirect_stderr(io.StringIO()):
            self.assertEqual(H.main(), 0)
        text = out.getvalue().strip()
        return json.loads(text)["hookSpecificOutput"]["permissionDecision"] if text else None

    def test_server_down_asks_unless_fail_open(self):
        self.assertEqual(self.run_hook("git reset --hard"), "ask")
        self.assertIsNone(self.run_hook("git reset --hard", env={"EKBASIS_FAIL_OPEN": "1"}))
        self.assertEqual(self.run_hook("git reset --hard", env={"EKBASIS_GUARD_MODE": "deny"}), "deny")

    def test_lines_it_cannot_follow(self):
        for line in ("(cd ../x && git reset --hard)", "pushd x; git checkout -f main", "bash -c 'git reset --hard'",
                     "git reset --hard $REF", "GIT_DIR=/tmp/x git reset --hard", "git -C ../x reset --hard"):
            self.assertEqual(self.run_hook(line), "ask", line)

    def test_timeout(self):
        slow = lambda *a, **k: time.sleep(3)  # noqa: E731
        with mock.patch.object(G, "check", slow):
            self.assertEqual(self.run_hook("git reset --hard", env={"EKBASIS_HOOK_DEADLINE": "0.3"}), "ask")

    def test_bad_input_and_harmless_lines(self):
        self.assertEqual(self.run_hook("", raw="not json"), "ask")
        self.assertIsNone(self.run_hook("ls -la"))
        self.assertIsNone(self.run_hook("git status", cwd=self.tmp.name))  # not a repository: nothing to lose
        with mock.patch.object(G, "check", lambda *a, **k: G.Verdict(commands=[], p_lost=0.01, p_fail=[], p_in_progress=0)):
            self.assertIsNone(self.run_hook('git commit -m "$(cat <<\'EOF\'\nfix: x\nEOF\n)"'))

    def test_shell_opt_in(self):
        box = os.path.join(self.tmp.name, "box")
        os.makedirs(box)
        self.assertIsNone(self.run_hook('rm -rf "$DIR"/*', cwd=box))  # not opted in
        self.assertEqual(self.run_hook('rm -rf "$DIR"/*', cwd=box, env={"EKBASIS_SHELL_GUARD": "1"}), "ask")
        # 0.1.3: nothing there to lose, so no model call and no ask
        self.assertIsNone(self.run_hook("rm -rf build", cwd=box, env={"EKBASIS_SHELL_GUARD": "1"}))
        os.makedirs(os.path.join(box, "build"))
        with open(os.path.join(box, "build", "out.txt"), "w") as f:
            f.write("x\n")
        self.assertEqual(self.run_hook("rm -rf build", cwd=box, env={"EKBASIS_SHELL_GUARD": "1"}), "ask")  # server down


if __name__ == "__main__":
    unittest.main()
