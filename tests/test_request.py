"""0.1.23: the user's request. With one, the state shows it just before the closing note and the loss question leaves
out what was asked for; without one, prompts and questions are exactly as before. The hook reads it from the Claude
Code transcript (the last message the user typed, never a tool result)."""
import json
import os
import subprocess
import tempfile
import unittest

from ekbasis import claude_code_hook as H
from ekbasis import git as G
from ekbasis import prompts as P
from ekbasis import shell as S
from ekbasis.client import Answer


class Recorder:
    def __init__(self):
        self.calls = []

    def ask(self, state, questions):
        self.calls.append((state, questions))
        return {k: Answer(value=False, confidence=0.9, p_yes=0.1) for k in questions}


def git(repo, *a):
    subprocess.run(["git", "-C", repo, *a], check=True, capture_output=True,
                   env=dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1",
                            GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@x", GIT_COMMITTER_NAME="t",
                            GIT_COMMITTER_EMAIL="t@x"))


class TestPrompt(unittest.TestCase):
    def test_with_request_goes_before_the_note(self):
        p = P.git_state("Current branch: main", ["git stash clear"])
        q = P.with_request(p, "  clear the\nold stashes ")
        self.assertTrue(q.endswith("\n\n" + P.GIT_NOTE))
        self.assertIn(f"{P.REQUEST_LABEL}: clear the old stashes\n\n{P.GIT_NOTE}", q)
        self.assertEqual(P.with_request(p, None), p)
        self.assertEqual(P.with_request(p, "   "), p)

    def test_long_request_keeps_its_end(self):
        r = P.request_text("x" * 5000 + " the user's words")
        self.assertLessEqual(len(r), P.REQUEST_MAX + 3)
        self.assertTrue(r.endswith("the user's words"))


class TestChecks(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        git(self.d, "init", "-q", "-b", "main")
        open(os.path.join(self.d, "a.txt"), "w").write("a\n")
        git(self.d, "add", "a.txt")
        git(self.d, "commit", "-q", "-m", "a")

    def test_git_without_request_is_unchanged(self):
        r = Recorder()
        G.check(["git stash clear"], repo=self.d, client=r)
        state, qs = r.calls[0]
        self.assertEqual(qs["lost"], P.GIT_LOST)
        self.assertNotIn(P.REQUEST_LABEL, state)

    def test_git_with_request(self):
        r = Recorder()
        G.check(["git stash clear"], repo=self.d, client=r, request="clear my stash list")
        state, qs = r.calls[0]
        self.assertEqual(qs["lost"], P.GIT_LOST_REQUEST)
        self.assertIn(f"{P.REQUEST_LABEL}: clear my stash list", state)

    def test_shell_with_and_without_request(self):
        r = Recorder()
        S.check(["rm a.txt"], cwd=self.d, client=r)
        S.check(["rm a.txt"], cwd=self.d, client=r, request="remove a.txt")
        (s0, q0), (s1, q1) = r.calls
        self.assertEqual(q0["lost"], S.shell_lost_question())
        self.assertEqual(q1["lost"], S.SHELL_LOST_REQUEST)
        self.assertNotIn(P.REQUEST_LABEL, s0)
        self.assertIn(f"{P.REQUEST_LABEL}: remove a.txt", s1)


class TestNotes(unittest.TestCase):
    def test_add_on_a_conflict_gets_the_note(self):
        self.assertIn(P.NOTE_ADD_CONFLICT, P.git_notes(["git add src/a.py"], {"unmerged": True}))
        self.assertNotIn(P.NOTE_ADD_CONFLICT, P.git_notes(["git add src/a.py"], {}))


class TestTranscript(unittest.TestCase):
    def write(self, events):
        f = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False)
        for e in events:
            f.write(json.dumps(e) + "\n")
        f.close()
        return f.name

    def test_last_typed_message_not_tool_results(self):
        p = self.write([
            {"type": "user", "message": {"role": "user", "content": "first ask"}},
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "ok"}]}},
            {"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": "clear the cache"}]}},
            {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "content": "done"}]}},
            {"type": "user", "isMeta": True, "message": {"role": "user", "content": "<meta>"}},
        ])
        self.assertEqual(H.user_request(p), "clear the cache")

    def test_unreadable_or_missing(self):
        self.assertIsNone(H.user_request(None))
        self.assertIsNone(H.user_request("/nonexistent/t.jsonl"))
        self.assertIsNone(H.user_request(self.write([{"type": "summary"}, "not json"])))


if __name__ == "__main__":
    unittest.main()
