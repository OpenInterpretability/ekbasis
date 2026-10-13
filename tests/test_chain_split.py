"""Chain mode of the hook (0.1.29): which lines are cut, how, and the advice added to a flagged line's message."""
import unittest
from unittest import mock

from ekbasis import claude_code_hook as H
from ekbasis import shell as S


class TestSequenceParts(unittest.TestCase):
    def test_cut_at_and_semicolon_newline(self):
        self.assertEqual([t for _, t in S.sequence_parts("du -sh * && rm -rf cache/*; df -h")],
                         ["du -sh *", "rm -rf cache/*", "df -h"])
        self.assertEqual([t for _, t in S.sequence_parts("ls\nrm -rf build\ndf")], ["ls", "rm -rf build", "df"])

    def test_operators_inside_quotes_are_not_cuts(self):
        self.assertEqual([t for _, t in S.sequence_parts('rm -rf "a b" && echo "x && y"')], ['rm -rf "a b"', 'echo "x && y"'])

    def test_not_cut(self):
        for line in ["rm a", "a | b && c", "a || b", "a & b", "if x; then rm y; fi", "cat <<EOF > f\nhi\nEOF\nrm f",
                     "bash -c 'rm x' && ls", "cd sub && rm -rf x", "export A=1 && rm x", "X=1 rm a && ls",
                     "source env.sh && rm x"]:
            self.assertIsNone(S.sequence_parts(line), line)

    def test_join_keeps_operators(self):
        parts = S.sequence_parts("a && b; c\nd")
        self.assertEqual(S.join_parts(parts), "a && b ; c\nd")


class TestChainSplit(unittest.TestCase):
    def advice(self, line, k):
        with mock.patch.object(S, "first_risky", return_value=k):
            return H._chain_split(line, ".", None, 0.2, None, lambda: 10)

    def test_advice_names_the_safe_prefix_and_the_rest(self):
        msg = self.advice("du -sh . && rm -rf cache && rm -rf photos; ls", 3)
        self.assertIn("before command 3 are predicted safe", msg)
        self.assertIn("run `du -sh . && rm -rf cache` on its own", msg)
        self.assertIn("then `rm -rf photos ; ls` as a separate call", msg)

    def test_no_risky_prefix_means_the_last_command(self):
        self.assertIn("before command 2", self.advice("ls && rm -rf photos", None))

    def test_first_command_risky_or_uncuttable_line_adds_nothing(self):
        self.assertEqual(self.advice("rm -rf photos && ls", 1), "")
        self.assertEqual(self.advice("rm a | tee log", 2), "")
