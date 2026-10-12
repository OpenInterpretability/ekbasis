"""0.1.23: commands after shell reserved words reach the guards (before, `do git ...`, `then git ...` and `! git ...`
were not seen at all), and read-only git commands with a variable do not make the hook give up."""
import unittest

from ekbasis import claude_code_hook as H
from ekbasis import shell as S


def cmds(line):
    p = H.plan_line(line, "/tmp")
    return p.why, [s["cmd"] for s in p.steps]


class TestReservedWords(unittest.TestCase):
    def test_git_after_reserved_words_is_checked(self):
        for line, want in [("while true; do git clean -fdx; done", ["git clean -fdx"]),
                           ("if true; then git reset --hard; fi", ["git reset --hard"]),
                           ("if x; then git stash clear; else git reset --hard; fi", ["git stash clear", "git reset --hard"]),
                           ("! git reset --hard", ["git reset --hard"])]:
            self.assertEqual(cmds(line)[1], want, line)

    def test_variable_in_a_writing_loop_cannot_be_judged(self):
        why, _ = cmds("for b in x y; do git branch -D $b; done")
        self.assertTrue(any("variable" in w for w in why))

    def test_words_as_arguments_are_not_skipped(self):
        name, _, _ = S.command_name(S.parse("echo do then").commands[0].words)
        self.assertEqual(name, "echo")


class TestReadOnlyWithVariables(unittest.TestCase):
    def test_reads_pass(self):
        for line in ['for i in 0 1 2; do echo "$i"; git stash show --stat "stash@{$i}"; done',
                     'for d in a b; do git -C $d status --short; done',
                     'git log -1 --format=%s "stash@{$i}"']:
            self.assertEqual(cmds(line), ([], []), line)

    def test_writes_or_unknowns_do_not(self):
        for line in ["git log --oneline $OPTS", "git $SUB main", "git --git-dir=$G status", "git stash drop $s",
                     "git checkout $b"]:
            self.assertTrue(cmds(line)[0], line)

    def test_shell_reads_with_variables(self):
        self.assertEqual(S.inspect(['for f in a b; do cmp "$f" "x/$f"; cat "$f"; done'], "/tmp").unread, [])
        for line in ['rm "$f"', 'sed -i s/a/b/ "$f"', 'cat a > "$out"', 'find "$d" -delete']:
            self.assertTrue(S.inspect([line], "/tmp").unread, line)


if __name__ == "__main__":
    unittest.main()
