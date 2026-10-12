"""0.1.24 opt-in warn once (EKBASIS_GUARD_REPEAT=1): the same line in the same session and folder goes through the
second time; another line, folder or session is checked again; off by default."""
import io
import json
import os
import sys
import tempfile
import unittest
import uuid
from unittest import mock

from ekbasis import claude_code_hook as H


def run(line, cwd, session, env):
    data = json.dumps({"tool_name": "Bash", "tool_input": {"command": line}, "cwd": cwd, "session_id": session})
    out = io.StringIO()
    with mock.patch.dict(os.environ, env, clear=False), mock.patch.object(sys, "stdin", io.StringIO(data)), \
            mock.patch.object(sys, "stdout", out):
        for k in ("EKBASIS_GUARD_MODE", "EKBASIS_FAIL_OPEN"):
            os.environ.pop(k, None)
        H.main()
    return json.loads(out.getvalue())["hookSpecificOutput"] if out.getvalue().strip() else None


class TestWarnOnce(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.line = "git $SUB main"   # cannot be judged: no model or repository needed

    def test_second_run_passes_when_on(self):
        s = str(uuid.uuid4())
        env = {"EKBASIS_GUARD_REPEAT": "1"}
        first = run(self.line, self.d, s, env)
        self.assertEqual(first["permissionDecision"], "ask")
        self.assertIn("same command again", first["permissionDecisionReason"])
        self.assertIsNone(run(self.line, self.d, s, env))
        self.assertIsNotNone(run(self.line, self.d, str(uuid.uuid4()), env))      # other session
        self.assertIsNotNone(run(self.line + " ", self.d, s, env))               # other line
        self.assertIsNotNone(run(self.line, tempfile.mkdtemp(), s, env))         # other folder

    def test_off_by_default(self):
        s = str(uuid.uuid4())
        env = {"EKBASIS_GUARD_REPEAT": "0"}
        self.assertIsNotNone(run(self.line, self.d, s, env))
        self.assertIsNotNone(run(self.line, self.d, s, env))


if __name__ == "__main__":
    unittest.main()
