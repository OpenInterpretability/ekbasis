"""0.1.42: a variable set earlier on the same line to a known value is read with it, by the shell guard and the git
guard (shell.resolve). The lines are real ones from a Claude Code session's hook log (689 commands, 2026-10-16), with
paths, hosts and names replaced. Everything else stays as before: a variable from the environment, set twice, used
before it is set, exported, set in a loop, a condition, a pipeline or a subshell, or by command substitution, is not
guessed ("cannot foresee"). Offline: a fake client."""
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from ekbasis import claude_code_hook as H
from ekbasis import shell as S
from ekbasis.client import Answer

ENV = dict(os.environ, GIT_AUTHOR_NAME="Dev", GIT_AUTHOR_EMAIL="dev@example.invalid", GIT_COMMITTER_NAME="Dev",
           GIT_COMMITTER_EMAIL="dev@example.invalid", GIT_CONFIG_NOSYSTEM="1", LC_ALL="C")


def sh(cmd, cwd):
    subprocess.run(["bash", "-c", cmd], cwd=cwd, env=ENV, check=True, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL)


class Fake:
    """'lost' with p_lost, every other yes/no with p_fail; counts the requests."""

    def __init__(self, p_lost=0.0, p_fail=0.0):
        self.p_lost, self.p_fail, self.requests = p_lost, p_fail, []

    def ask(self, state, questions, read_once=False, images=None):
        self.requests.append(state)
        out = {}
        for k in questions:
            if k == "why":
                out[k] = Answer(value="other", confidence=0.9, probabilities={"other": 0.9})
                continue
            p = self.p_lost if k == "lost" else self.p_fail
            out[k] = Answer(value=p >= 0.5, confidence=max(p, 1 - p), probabilities={"yes": p, "no": 1 - p}, p_yes=p)
        return out


def words(line):
    return [[(w.text, w.dynamic) for w in c.words] for c in S.parse(line).commands]


class TestResolve(unittest.TestCase):
    def test_literal_assignments_are_read(self):
        self.assertEqual(words('D=/tmp/x; rm -rf "$D"')[1], [("rm", False), ("-rf", False), ("/tmp/x", False)])
        self.assertEqual(words('G=/a; T="$G/b"; ls ${T}/c $G')[2], [("ls", False), ("/a/b/c", False), ("/a", False)])
        self.assertEqual(words("D='/a b'; rm \"$D\"")[1][1], ("/a b", False))
        w = S.parse('D=/a; rm "$D/x"').commands[1].words[1]
        self.assertEqual(w.values, (("D", "/a"),))

    def test_quoting_is_kept(self):
        self.assertEqual(words("D=/a; echo '$D' \\$D")[1][1:], [("$D", False), ("$D", False)])
        self.assertEqual(words('D="a b"; rm $D')[1][1], ("$D", True))      # unquoted: it would split
        self.assertEqual(words('D="*.log"; rm $D')[1][1], ("$D", True))    # unquoted: it would be a pattern
        self.assertEqual(words('D=x; rm $D.*')[1][1], ("x.*", False))
        self.assertTrue(S.parse('D=x; rm $D.*').commands[1].words[1].glob)

    def test_what_stays_unknown(self):
        for line in ['rm -rf "$HOME_X/build"',                    # not set on the line
                     'rm "$D"; D=/a',                              # used before it is set
                     'D=/a; rm "$D"; D=/b; rm "$D"',               # set twice
                     'export D=/a; rm "$D"',                       # exported
                     'D=/a rm "$D"',                               # an assignment for that command only
                     'false && D=/a; rm "$D"',                     # set only if the command before succeeds
                     'D=/a | cat; rm "$D"',                        # in a pipeline: a subshell
                     '(D=/a); rm "$D"',                            # in a subshell
                     'if x; then D=/a; fi; rm "$D"',               # in a condition
                     'for D in a b; do rm "$D"; done',             # a loop variable
                     'D=$(pwd); rm "$D"',                          # command substitution
                     'D=`pwd`; rm "$D"',
                     'D=/a; read D; rm "$D"',
                     'D=/a; eval "$X"; rm "$D"',                   # eval or source could set anything
                     'D=/a; source env.sh; rm "$D"',
                     'f() { D=/x; }; D=/a; f; rm "$D"',
                     'D=~/x; rm "$D"',                             # ~ in a value
                     'D=/a; rm "${D:-/b}"',
                     'IFS=/; D=/a; rm $D']:
            rms = [c for c in S.parse(line).commands if S.command_name(c.words)[0] == "rm"]
            self.assertTrue(rms and all(any(w.dynamic for w in c.words[1:]) for c in rms), line)

    def test_here_document_body_and_delimiter_are_untouched(self):
        ps = S.parse("D=/a; cat <<EOF > \"$D/f\"\n$D\nEOF")
        rd = ps.commands[1].redirects
        self.assertEqual([(r.op, r.target.text) for r in rd], [("<<", "EOF"), (">", "/a/f")])


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.repo = os.path.join(self.tmp, "release skopos")
        os.makedirs(self.repo)
        for c in ("git init -q -b main", "git config commit.gpgsign false", "printf 'tracked\\n' > results.json",
                  "mkdir -p work && printf 'v1\\n' > work/kept.txt", "git add -A", "git commit -qm init",
                  "printf 'v2\\n' > work/kept.txt", "printf 'draft\\n' > work/untracked.txt"):
            sh(c, self.repo)
        self.env = mock.patch.dict(os.environ, {"TMPDIR": tempfile.mkdtemp(), "WORK_DIR": self.repo}, clear=False)
        self.env.start()
        for k in ("EKBASIS_GUARD_MODE", "EKBASIS_FAIL_OPEN", "EKBASIS_SHELL_GUARD", "EKBASIS_PREFLIGHT",
                  "EKBASIS_GIT_GUARD", "EKBASIS_GUARD_REPEAT", "EKBASIS_PREFLIGHT_FAIL_CLOSED"):
            os.environ.pop(k, None)
        tempfile.tempdir = None

    def tearDown(self):
        self.env.stop()
        tempfile.tempdir = None

    def hook(self, line, fake, env=None, session="s1"):
        data = {"tool_name": "Bash", "tool_input": {"command": line}, "cwd": self.tmp, "session_id": session}
        out = io.StringIO()
        with mock.patch.dict(os.environ, env or {}), mock.patch.object(H, "Ekbasis", return_value=fake), \
                mock.patch.object(sys, "stdin", io.StringIO(json.dumps(data))), redirect_stdout(out):
            self.assertEqual(H.main(), 0)
        return json.loads(out.getvalue())["hookSpecificOutput"] if out.getvalue().strip() else None


class TestLogLines(Base):
    """Lines of the hook log that the guards could not foresee in 0.1.41, now read."""

    def test_shell_guard_reads_a_folder_set_on_the_line(self):
        line = f'RS="{self.repo}"; mkdir -p "$RS/prelaunch_out" && cp results.json "$RS/prelaunch_out/"'
        v = S.inspect([line], self.tmp)
        self.assertEqual(v.unread, [])
        self.assertIn(os.path.join(self.repo, "prelaunch_out"), v.touched)
        self.assertIn(f'$RS is "{self.repo}" (set earlier on the line)', v.state)

    def test_two_names_one_built_from_the_other(self):
        line = f'SPD={self.tmp}/scratch; T="$SPD/tools"; rm -rf $SPD/dryrun && mkdir -p $SPD/dryrun "$T"'
        self.assertEqual(S.inspect([line], self.tmp).unread, [])

    def test_git_guard_follows_cd_and_git_c_with_a_variable(self):
        for line in (f'G="{self.repo}"; cd "$G"; git status --short; git log --oneline -3',
                     f'G="{self.repo}"; git -C "$G" diff --stat; git -C "$G" log -1 --format=%H'):
            p = H.plan_line(line, self.tmp)
            self.assertEqual(p.why, [], line)
            self.assertEqual({s["repo"] for s in p.steps}, {self.repo}, line)
        self.assertIsNone(self.hook(f'G="{self.repo}"; cd "$G"; git status --short', Fake()))


class TestStillFlagged(Base):
    def test_git_reset_hard_with_uncommitted_work(self):
        for line in ("git -C 'release skopos' reset --hard", f'G="{self.repo}"; cd "$G" && git reset --hard'):
            f = Fake(p_lost=0.9)
            a = self.hook(line, f)
            self.assertEqual(a["permissionDecision"], "ask", line)
            self.assertIn("may permanently lose uncommitted work", a["permissionDecisionReason"], line)
            self.assertTrue(f.requests, line)

    def test_rm_of_a_folder_set_on_the_line_with_uncommitted_files(self):
        f = Fake(p_lost=0.9)
        a = self.hook(f'D="{self.repo}/work"; rm -rf "$D"', f, {"EKBASIS_SHELL_GUARD": "1"})
        self.assertEqual(a["permissionDecision"], "ask")
        self.assertIn("may permanently lose file content", a["permissionDecisionReason"])
        self.assertNotIn("could not foresee", a["permissionDecisionReason"])
        self.assertIn("untracked.txt", a["permissionDecisionReason"])
        self.assertTrue(any(f'$D is "{self.repo}/work"' in s for s in f.requests))

    def test_a_pattern_after_a_variable_still_expands(self):
        # the log's line: S=<scratch>; rm -rf $S/hooktest.* (a test repository with uncommitted work)
        os.makedirs(os.path.join(self.tmp, "hooktest.a1"))
        with open(os.path.join(self.tmp, "hooktest.a1", "draft.txt"), "w") as fh:
            fh.write("work\n")
        line = f"S={self.tmp}; rm -rf $S/hooktest.*; ls"
        v = S.inspect([line], self.tmp)
        self.assertEqual(v.unread, [])
        self.assertEqual([how for t, how in v.touched.items() if t.endswith("hooktest.a1")], ["tree"])   # expanded
        f = Fake(p_lost=0.9)
        a = self.hook(line, f, {"EKBASIS_SHELL_GUARD": "1"})
        self.assertIn("may permanently lose file content", a["permissionDecisionReason"])
        self.assertIn("draft.txt", a["permissionDecisionReason"])

    def test_a_variable_from_the_environment_is_not_guessed(self):
        f = Fake(p_lost=0.0)
        a = self.hook('rm -rf "$WORK_DIR/work"', f, {"EKBASIS_SHELL_GUARD": "1"})   # set in the environment only
        self.assertEqual(a["permissionDecision"], "ask")
        self.assertIn("could not foresee every part of the line", a["permissionDecisionReason"])

    def test_a_reassigned_variable_is_not_guessed(self):
        for line in (f'D="{self.repo}/work"; rm -rf "$D"; D=/nonexistent; rm -rf "$D"',
                     f'rm -rf "$D"; D="{self.repo}/work"',
                     f'export D="{self.repo}/work"; rm -rf "$D"'):
            a = self.hook(line, Fake(p_lost=0.0), {"EKBASIS_SHELL_GUARD": "1"})
            self.assertEqual(a["permissionDecision"], "ask", line)
            self.assertIn("could not foresee every part of the line", a["permissionDecisionReason"], line)

    def test_git_with_an_unknown_variable_still_cannot_be_judged(self):
        a = self.hook('git -C "$WORK_DIR" reset --hard', Fake(p_lost=0.0))
        self.assertEqual(a["permissionDecision"], "ask")
        self.assertIn("variable", a["permissionDecisionReason"])

    def test_inline_code_does_not_hide_an_rm_outside_it(self):
        line = "cd 'release skopos' && python3 - <<'EOF'\nprint('cleanup')\nEOF\nrm -rf work"
        f = Fake(p_lost=0.9, p_fail=0.99)
        a = self.hook(line, f, {"EKBASIS_SHELL_GUARD": "1", "EKBASIS_PREFLIGHT": "1"})
        self.assertEqual(a["permissionDecision"], "ask")
        self.assertIn("Ekbasis (shell guard): may permanently lose file content", a["permissionDecisionReason"])
        self.assertNotIn("`python3 -`", a["permissionDecisionReason"])   # preflight never names the inline code


if __name__ == "__main__":
    unittest.main()
