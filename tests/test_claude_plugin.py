"""The Claude Code plugin's entry points (ekbasis.claude_plugin, scripts/claude_plugin.py): not set up, the hook says
nothing and the session starts with one setup line; set up, it is the same fail-closed hook as ekbasis-claude-hook.
Also `ekbasis mcp`. Offline: a port nobody listens on, and a fake MCP server module."""
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from unittest import mock

import ekbasis
from ekbasis import claude_plugin as CP
from ekbasis import cli

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAUNCHER = os.path.join(ROOT, "scripts", "claude_plugin.py")
GIT_ENV = dict(GIT_AUTHOR_NAME="Dev", GIT_AUTHOR_EMAIL="dev@example.invalid", GIT_COMMITTER_NAME="Dev",
               GIT_COMMITTER_EMAIL="dev@example.invalid", GIT_CONFIG_NOSYSTEM="1", LC_ALL="C")


def dead_url():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return f"http://127.0.0.1:{port}"


def run_launcher(mode, env, stdin=""):
    base = {k: v for k, v in os.environ.items() if not k.startswith("EKBASIS_")}
    return subprocess.run([sys.executable, LAUNCHER, mode], input=stdin, capture_output=True, text=True,
                          env=dict(base, **env), timeout=60)


class Configure(unittest.TestCase):
    def test_nothing_set(self):
        env = {}
        self.assertFalse(CP.configure(env))
        self.assertNotIn("EKBASIS_URL", env)

    def test_blank_is_not_set(self):
        self.assertFalse(CP.configure({"EKBASIS_URL": " ", "EKBASIS_API_KEY": ""}))

    def test_key_alone_means_hosted(self):
        env = {"EKBASIS_API_KEY": "ekb_test"}
        self.assertTrue(CP.configure(env))
        self.assertEqual(env["EKBASIS_URL"], CP.HOSTED_URL)

    def test_url_is_kept(self):
        env = {"EKBASIS_URL": "http://10.0.0.5:8000", "EKBASIS_API_KEY": "ekb_test"}
        self.assertTrue(CP.configure(env))
        self.assertEqual(env["EKBASIS_URL"], "http://10.0.0.5:8000")
        self.assertTrue(CP.configure({"EKBASIS_URL": "http://127.0.0.1:8000"}))


class SessionStart(unittest.TestCase):
    def test_not_set_up_says_how(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(CP.session_start({}), 0)
        d = json.loads(out.getvalue())
        self.assertIn(CP.CONSOLE, d["systemMessage"])
        self.assertIn("EKBASIS_API_KEY", d["systemMessage"])
        self.assertEqual(d["hookSpecificOutput"]["hookEventName"], "SessionStart")

    def test_set_up_says_nothing(self):
        out = io.StringIO()
        with redirect_stdout(out):
            CP.session_start({"EKBASIS_API_KEY": "ekb_test"})
        self.assertEqual(out.getvalue(), "")


class Hook(unittest.TestCase):
    def test_not_set_up_does_not_run_the_guard(self):
        with mock.patch("ekbasis.claude_code_hook.main") as guard:
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(CP.hook({}), 0)
        guard.assert_not_called()
        self.assertEqual(out.getvalue(), "")

    def test_set_up_runs_the_guard(self):
        with mock.patch("ekbasis.claude_code_hook.main", return_value=0) as guard:
            self.assertEqual(CP.hook({"EKBASIS_URL": "http://127.0.0.1:1"}), 0)
        guard.assert_called_once()


class Launcher(unittest.TestCase):
    """The plugin's command line, as Claude Code runs it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = self.tmp.name
        env = dict(os.environ, **GIT_ENV)
        for args in (["init", "-q"], ["add", "f"], ["commit", "-qm", "init"]):
            if args[0] == "add":
                with open(os.path.join(self.repo, "f"), "w") as fh:
                    fh.write("a\n")
            subprocess.run(["git", *args], cwd=self.repo, env=env, check=True)
        with open(os.path.join(self.repo, "f"), "a") as fh:
            fh.write("uncommitted\n")
        self.line = json.dumps({"tool_name": "Bash", "tool_input": {"command": "git reset --hard"}, "cwd": self.repo,
                                "session_id": "test"})

    def tearDown(self):
        self.tmp.cleanup()

    def test_not_set_up_lets_the_normal_flow_decide(self):
        r = run_launcher("hook", {}, self.line)
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        r = run_launcher("session-start", {})
        self.assertIn(CP.CONSOLE, json.loads(r.stdout)["systemMessage"])

    def test_set_up_still_fails_closed(self):
        for env in ({"EKBASIS_URL": dead_url()}, {"EKBASIS_URL": dead_url(), "EKBASIS_API_KEY": "ekb_test"}):
            r = run_launcher("hook", env, self.line)
            self.assertEqual(r.returncode, 0)
            d = json.loads(r.stdout)["hookSpecificOutput"]
            self.assertEqual(d["permissionDecision"], "ask")
            self.assertIn("could not foresee", d["permissionDecisionReason"])

    def test_unknown_mode(self):
        self.assertEqual(run_launcher("nope", {}).returncode, 1)


class McpCommand(unittest.TestCase):
    def test_ekbasis_mcp_runs_the_server(self):
        fake = types.ModuleType("ekbasis.mcp_server")
        fake.main = mock.Mock()
        with mock.patch.dict(sys.modules, {"ekbasis.mcp_server": fake}), \
                mock.patch.object(ekbasis, "mcp_server", fake, create=True), \
                mock.patch.dict(os.environ, {"EKBASIS_URL": "http://a"}):
            self.assertEqual(cli.main(["--url", "http://b:8000", "mcp"]), cli.OK)
            self.assertEqual(os.environ["EKBASIS_URL"], "http://b:8000")
        fake.main.assert_called_once()


if __name__ == "__main__":
    unittest.main()
