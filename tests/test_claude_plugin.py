"""The Claude Code plugin (plugins/ekbasis/, ekbasis.claude_plugin): not set up, the hook says nothing, the session
starts with one setup line and `ekbasis` says it is not set up; set up, it is the same fail-closed hook as
ekbasis-claude-hook, and a hook that cannot run (python3 missing or too old, an import error, a crash, a bad input, no
answer in time) asks, never lets the command through silently. Also: the plugin's copy of the package is identical to
ekbasis/, and `ekbasis mcp`. Offline: a port nobody listens on, broken copies of the plugin, a fake MCP module."""
import importlib.util
import io
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import types
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

import ekbasis
from ekbasis import claude_plugin as CP
from ekbasis import cli

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = os.path.join(ROOT, "plugins", "ekbasis")
GIT_ENV = dict(GIT_AUTHOR_NAME="Dev", GIT_AUTHOR_EMAIL="dev@example.invalid", GIT_COMMITTER_NAME="Dev",
               GIT_COMMITTER_EMAIL="dev@example.invalid", GIT_CONFIG_NOSYSTEM="1", LC_ALL="C")
PY_DIR = os.path.dirname(sys.executable)


def dead_url():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return f"http://127.0.0.1:{port}"


def run_plugin(mode, env, stdin="", plugin=PLUGIN, path=None):
    """The hook as Claude Code runs it: sh run.sh MODE, with python3 from this interpreter's folder first on PATH."""
    base = {k: v for k, v in os.environ.items() if not k.startswith("EKBASIS_")}
    base["PYTHONDONTWRITEBYTECODE"] = "1"
    base["PATH"] = path if path is not None else PY_DIR + os.pathsep + base.get("PATH", "")
    return subprocess.run(["/bin/sh", os.path.join(plugin, "scripts", "run.sh"), mode], input=stdin,
                          capture_output=True, text=True, env=dict(base, **env), timeout=60)


def decision(r):
    return json.loads(r.stdout)["hookSpecificOutput"]


class InSync(unittest.TestCase):
    def test_plugin_copy_is_the_package(self):
        spec = importlib.util.spec_from_file_location("sync_plugin", os.path.join(ROOT, "scripts", "sync_plugin.py"))
        sp = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sp)
        self.assertEqual(sp.differences(), [], "run: python scripts/sync_plugin.py")


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


class SessionStartAndHook(unittest.TestCase):
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


class Command(unittest.TestCase):
    """bin/ekbasis (ekbasis.claude_plugin.cli)."""

    def test_not_set_up_says_so(self):
        err = io.StringIO()
        with redirect_stderr(err), mock.patch("ekbasis.cli.main") as real:
            self.assertEqual(CP.cli(["git-check", "--", "git reset --hard"], env={}), 3)
        real.assert_not_called()
        self.assertIn("not set up", err.getvalue())
        self.assertIn(CP.CONSOLE, err.getvalue())

    def test_help_and_url_still_work(self):
        with mock.patch("ekbasis.cli.main", return_value=0) as real:
            self.assertEqual(CP.cli(["--help"], env={}), 0)
            self.assertEqual(CP.cli(["--url", "http://h:8000", "health"], env={}), 0)
        self.assertEqual(real.call_count, 2)

    def test_set_up_runs_the_command(self):
        env = {"EKBASIS_API_KEY": "ekb_test"}
        with mock.patch("ekbasis.cli.main", return_value=2) as real:
            self.assertEqual(CP.cli(["git-check", "--", "git reset --hard"], env=env), 2)
        real.assert_called_once_with(["git-check", "--", "git reset --hard"])
        self.assertEqual(env["EKBASIS_URL"], CP.HOSTED_URL)

    def test_bin_ekbasis(self):
        base = {k: v for k, v in os.environ.items() if not k.startswith("EKBASIS_")}
        r = subprocess.run([sys.executable, os.path.join(PLUGIN, "bin", "ekbasis"), "health"], capture_output=True,
                           text=True, env=base, timeout=60)
        self.assertEqual(r.returncode, 3)
        self.assertIn("not set up", r.stderr)


class Launcher(unittest.TestCase):
    """The plugin's hooks as Claude Code runs them, including hooks that cannot run."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = os.path.join(self.tmp.name, "repo")
        os.makedirs(self.repo)
        env = dict(os.environ, **GIT_ENV)
        with open(os.path.join(self.repo, "f"), "w") as fh:
            fh.write("a\n")
        for args in (["init", "-q"], ["add", "f"], ["commit", "-qm", "init"]):
            subprocess.run(["git", *args], cwd=self.repo, env=env, check=True)
        with open(os.path.join(self.repo, "f"), "a") as fh:
            fh.write("uncommitted\n")
        self.line = json.dumps({"tool_name": "Bash", "tool_input": {"command": "git reset --hard"}, "cwd": self.repo,
                                "session_id": "test"})
        self.set_up = {"EKBASIS_URL": dead_url(), "EKBASIS_API_KEY": "ekb_test"}

    def tearDown(self):
        self.tmp.cleanup()

    def broken_plugin(self, module_source):
        """A copy of the plugin whose claude_code_hook module is replaced."""
        dst = os.path.join(self.tmp.name, "plugin")
        shutil.copytree(PLUGIN, dst, ignore=shutil.ignore_patterns("__pycache__"))
        with open(os.path.join(dst, "lib", "ekbasis", "claude_code_hook.py"), "w") as fh:
            fh.write(module_source)
        return dst

    def assertAsks(self, r, *words):
        self.assertEqual(r.returncode, 0, r.stderr)
        d = decision(r)
        self.assertEqual(d["permissionDecision"], "ask")
        self.assertIn("could not foresee", d["permissionDecisionReason"])
        for w in words:
            self.assertIn(w, d["permissionDecisionReason"])

    def test_not_set_up_lets_the_normal_flow_decide(self):
        r = run_plugin("hook", {}, self.line)
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        self.assertIn(CP.CONSOLE, json.loads(run_plugin("session-start", {}).stdout)["systemMessage"])

    def test_set_up_still_fails_closed(self):
        self.assertAsks(run_plugin("hook", self.set_up, self.line), "cannot reach")
        self.assertAsks(run_plugin("hook", {"EKBASIS_URL": dead_url()}, self.line))
        r = run_plugin("hook", dict(self.set_up, EKBASIS_GUARD_MODE="deny"), self.line)
        self.assertEqual(decision(r)["permissionDecision"], "deny")

    def test_other_tools_and_reads_stay_silent(self):
        for tool, cmd in (("Read", ""), ("Bash", "git status")):
            line = json.dumps({"tool_name": tool, "tool_input": {"command": cmd}, "cwd": self.repo})
            r = run_plugin("hook", self.set_up, line)
            self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_bad_input_asks(self):
        self.assertAsks(run_plugin("hook", self.set_up, "not json"), "hook input")

    def test_import_error_asks(self):
        plugin = self.broken_plugin("raise ImportError('broken on purpose')\n")
        self.assertAsks(run_plugin("hook", self.set_up, self.line, plugin=plugin), "ImportError", "broken on purpose")

    def test_crash_and_exit_ask(self):
        for src, word in (("def main():\n    raise KeyError('boom')\n", "KeyError"),
                          ("import sys\ndef main():\n    sys.exit(5)\n", "SystemExit"),
                          ("def main():\n    print('half an answer')\n    return 1\n", "exited with 1")):
            with self.subTest(word=word):
                plugin = self.broken_plugin(src)
                self.assertAsks(run_plugin("hook", self.set_up, self.line, plugin=plugin), word)
                shutil.rmtree(plugin)

    def test_no_answer_in_time_asks(self):
        plugin = self.broken_plugin("import time\ndef main():\n    time.sleep(60)\n    return 0\n")
        t0 = time.monotonic()
        r = run_plugin("hook", dict(self.set_up, EKBASIS_PLUGIN_WATCHDOG="1"), self.line, plugin=plugin)
        self.assertLess(time.monotonic() - t0, 20)
        self.assertAsks(r, "did not finish within 1 s")

    def test_python3_missing_asks(self):
        r = run_plugin("hook", self.set_up, self.line, path=os.path.join(self.tmp.name, "empty"))
        self.assertAsks(r, "python3 was not found")
        r = run_plugin("session-start", self.set_up, path=os.path.join(self.tmp.name, "empty"))
        self.assertIn("python3 was not found", json.loads(r.stdout)["systemMessage"])
        r = run_plugin("hook", {}, self.line, path=os.path.join(self.tmp.name, "empty"))
        self.assertEqual((r.returncode, r.stdout), (0, ""))   # not set up: nothing to guard

    def fake_python3(self, body):
        folder = os.path.join(self.tmp.name, "fakebin")
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, "python3")
        with open(path, "w") as fh:
            fh.write("#!/bin/sh\n" + body)
        os.chmod(path, 0o755)
        return folder + os.pathsep + os.environ.get("PATH", "")

    def test_python3_that_dies_asks(self):
        r = run_plugin("hook", self.set_up, self.line, path=self.fake_python3("exit 1\n"))
        self.assertAsks(r, "exit code 1")

    def test_python3_too_old_asks(self):
        old = ('exec "%s" -c "import sys; sys.version_info = (3, 8, 0, \'final\', 0); sys.argv = sys.argv[1:]; '
               'exec(compile(open(sys.argv[0]).read(), sys.argv[0], \'exec\'), '
               '{\'__name__\': \'__main__\', \'__file__\': sys.argv[0]})" "$@"\n' % sys.executable)
        r = run_plugin("hook", self.set_up, self.line, path=self.fake_python3(old))
        self.assertAsks(r, "Python 3.9 or later")

    def test_log_mode_never_blocks_when_the_hook_cannot_run(self):
        env = dict(self.set_up, EKBASIS_GUARD_MODE="log")
        r = run_plugin("hook", env, self.line, path=self.fake_python3("exit 1\n"))
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        self.assertIn("log mode, not blocking", r.stderr)
        plugin = self.broken_plugin("raise ImportError('broken on purpose')\n")
        r = run_plugin("hook", env, self.line, plugin=plugin)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, ""))

    def test_fail_open_is_explicit(self):
        plugin = self.broken_plugin("raise ImportError('broken on purpose')\n")
        r = run_plugin("hook", dict(self.set_up, EKBASIS_FAIL_OPEN="1"), self.line, plugin=plugin)
        self.assertEqual(r.stdout, "")
        self.assertIn("EKBASIS_FAIL_OPEN=1", r.stderr)

    def test_unknown_mode(self):
        r = run_plugin("nope", {})
        self.assertIn("exit code 1", json.loads(r.stdout)["systemMessage"])


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
