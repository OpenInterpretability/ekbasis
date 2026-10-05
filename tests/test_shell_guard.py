"""Offline tests of the shell guard prototype (0.1.2): reading lines, the state (never file contents), the notes, the
verdict and the CLI's exit codes, with a fake client (no server)."""
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from ekbasis import cli
from ekbasis import shell as S
from ekbasis.client import Answer

SECRET = "SECRET-TOKEN-do-not-copy-91c2"
WHERE = "a Linux machine (test)"


class FakeClient:
    """Answers 'lost' with p_lost and every 'fails_k' with p_fail; records the prompts."""

    def __init__(self, p_lost=0.0, p_fail=0.0):
        self.p_lost, self.p_fail, self.prompts = p_lost, p_fail, []

    def ask(self, state, questions, read_once=False, images=None):
        self.prompts.append(state)
        out = {}
        for k in questions:
            p = self.p_lost if k == "lost" else self.p_fail
            out[k] = Answer(value=p >= 0.5, confidence=max(p, 1 - p), probabilities={"yes": p, "no": 1 - p}, p_yes=p)
        return out


def make_box(root):
    """A folder with a secret, a copy, a hidden file, a name with a space, a link to a folder and an archive."""
    os.makedirs(os.path.join(root, "docs"))
    os.makedirs(os.path.join(root, "releases", "v1"))
    files = {".env": SECRET, "notes.txt": "meeting notes", "docs/notes.txt": "meeting notes", "old notes.txt": "old",
             "a.tmp": "a", "b.tmp": "b", "releases/v1/app.txt": "app v1", "names.txt": "zoe\nadam"}
    for p, c in files.items():
        with open(os.path.join(root, p), "w") as f:
            f.write(c + "\n")
    os.symlink("releases/v1", os.path.join(root, "current"))
    return root


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.box = make_box(os.path.join(self.tmp.name, "box"))

    def tearDown(self):
        self.tmp.cleanup()

    def view(self, *cmds, shell="bash"):
        return S.inspect(list(cmds), self.box, shell=shell, salt="fixed", where=WHERE, coreutils="")  # no machine detection

    def notes(self, *cmds, shell="bash"):
        return S.shell_notes(self.view(*cmds, shell=shell))


class TestParse(unittest.TestCase):
    def test_quotes_operators_and_redirects(self):
        ps = S.parse('rm "old notes.txt" && sort f > f 2>/dev/null; echo \'a b\' | tee -a log')
        words = [[w.text for w in c.words] for c in ps.commands]
        self.assertEqual(words, [["rm", "old notes.txt"], ["sort", "f"], ["echo", "a b"], ["tee", "-a", "log"]])
        self.assertEqual([c.joined_by for c in ps.commands], ["", "&&", ";", "|"])
        self.assertEqual([(r.op, r.fd, r.target.text) for r in ps.commands[1].redirects], [(">", "", "f"), (">", "2", "/dev/null")])
        self.assertEqual(ps.problems, [])

    def test_globs_dynamic_words_and_problems(self):
        ps = S.parse('rm *.log "$DIR"/x \\*.txt')
        w = ps.commands[0].words
        self.assertTrue(w[1].glob and not w[1].quoted)
        self.assertTrue(w[2].dynamic)
        self.assertFalse(w[3].glob)
        self.assertIn(S.P_SUBSHELL, S.parse("(cd x && rm -rf *)").problems)
        self.assertIn(S.P_QUOTE, S.parse("rm 'unclosed").problems)

    def test_heredoc_bodies_are_data(self):
        ps = S.parse("cat <<'EOF' > out.txt\nrm -rf / ; echo \"half\nEOF\nrm old.txt")
        self.assertEqual([[w.text for w in c.words] for c in ps.commands], [["cat"], ["rm", "old.txt"]])
        self.assertEqual(ps.problems, [])
        self.assertIn(S.P_HEREDOC_OPEN, S.parse("cat << EOF").problems)


class TestState(Base):
    def test_never_file_contents(self):
        for cmds in (["rm .env"], ["cat .env > copy.txt"], ["find . -type f -delete"], ["rm -rf * .*"],
                     ["tar czf all.tgz . && rm -rf docs"]):
            prompt = S.shell_prompt(self.view(*cmds))
            self.assertNotIn(SECRET, prompt, cmds)
            self.assertNotIn("meeting notes", prompt, cmds)

    def test_fingerprints_compare_contents_and_change_with_the_key(self):
        v = self.view("rm notes.txt docs/notes.txt")
        fp = [l.rsplit("fingerprint ", 1)[1] for l in v.state.splitlines() if "notes.txt: file" in l]
        self.assertEqual(len(fp), 2)
        self.assertEqual(fp[0], fp[1])
        other = S.inspect(["rm notes.txt"], self.box, shell="bash", salt="another", where=WHERE)
        self.assertNotIn(fp[0], other.state)
        self.assertEqual(self.view("rm notes.txt").state, self.view("rm notes.txt").state)  # deterministic with a key

    def test_listing_facts(self):
        st = self.view("rm notes.txt").state
        self.assertIn("Same content elsewhere (not listed above): docs/notes.txt (same content as notes.txt)", st)
        self.assertIn("- build: does not exist", self.view("cd build; rm -rf *").state)
        st = self.view("rm -rf *").state
        self.assertIn("* expands to a.tmp b.tmp current docs names.txt notes.txt \"old notes.txt\" releases", st)
        self.assertNotIn("- .env:", st)  # * skips hidden names, and the listing only has what the line could touch
        self.assertIn("- .env: hidden file", self.view("rm .env").state)
        self.assertIn("current: symbolic link to releases/v1 (points to a folder)", self.view("rm -r current/").state)
        self.assertIn("releases/v1/app.txt", self.view("rm -r current/").state)
        self.assertIn('the unquoted words old notes.txt are passed as 2 separate names', self.view("rm old notes.txt").state)
        self.assertIn("Not evaluated by the guard: command 1: " + S.P_DYNAMIC_PATH, self.view('rm -rf "$DIR"/*').state)
        self.assertEqual(self.view('echo "$(date)" > stamp.txt').unread, [])  # echo's words are not paths


class TestNotes(Base):
    def test_each_note_and_none_for_plain_commands(self):
        self.assertEqual(self.notes("rm notes.txt"), [])
        self.assertEqual(self.notes("cp notes.txt notes.bak"), [])
        cases = {S.NOTE_TRUNCATE: ["sort names.txt > names.txt"], S.NOTE_SEQUENCE: ["cd build; rm -rf *"],
                 S.NOTE_RSYNC: ["rsync -a docs/ out/"], S.NOTE_CP_MERGE: ["cp -r docs/. out"],
                 S.NOTE_LINK_SLASH: ["rm -r current/"], S.NOTE_SPLIT: ["rm old notes.txt"],
                 S.NOTE_GLOB_FIND: ["find . -name *.tmp -delete"], S.NOTE_XARGS: ['find . -name "*.tmp" | xargs rm'],
                 S.NOTE_REFUSE: ["rm docs"], S.NOTE_NOCLOBBER: ["set -o noclobber; echo x > notes.txt"],
                 S.NOTE_NO_CLOBBER_FLAG: ["mv -n notes.txt names.txt"]}
        for note, cmds in cases.items():
            self.assertIn(note, self.notes(*cmds), cmds)
        self.assertNotIn(S.NOTE_GLOB_FIND, self.notes('find . -name "*.tmp" -delete'))
        self.assertNotIn(S.NOTE_LINK_SLASH, self.notes("rm -r current"))
        self.assertIn(S.NOTE_ZSH_NOMATCH, self.notes("rm *.nothing", shell="zsh"))
        self.assertNotIn(S.NOTE_ZSH_NOMATCH, self.notes("rm *.nothing", shell="bash"))

    def test_notes_added_after_the_dev_pass(self):
        self.assertIn(S.NOTE_RM_F, self.notes("rm -f nothing.txt"))
        self.assertNotIn(S.NOTE_RM_F, self.notes("rm -f notes.txt"))
        self.assertIn(S.NOTE_CP_U, self.notes("cp -u notes.txt docs/notes.txt"))
        self.assertIn(S.NOTE_TRUNCATE, self.notes("cat names.txt >> names.txt"))
        for line in ("mv docs notes.txt", "cp -r docs notes.txt", "mv notes.txt names.txt nowhere", "ln -s notes.txt names.txt"):
            self.assertIn(S.NOTE_REFUSE, self.notes(line), line)
        for line in ("mv notes.txt names.txt docs", "ln -sf notes.txt names.txt", "mv -t docs notes.txt names.txt"):
            self.assertNotIn(S.NOTE_REFUSE, self.notes(line), line)

    def test_no_clobber_note_names_exit_codes_only_for_the_measured_version(self):
        v = S.inspect(["mv -n notes.txt names.txt"], self.box, shell="bash", salt="k", where=WHERE, coreutils="9.4")
        self.assertEqual(S.shell_notes(v), [S.NOTE_NO_CLOBBER_94])
        v = S.inspect(["mv -n notes.txt names.txt"], self.box, shell="bash", salt="k", where=WHERE, coreutils="9.1")
        self.assertEqual(S.shell_notes(v), [S.NOTE_NO_CLOBBER_FLAG])

    def test_facts_about_arguments(self):
        st = self.view("rsync -a --delete docs out/").state
        self.assertIn("rsync copies the folder docs itself into out/docs/", st)
        self.assertIn("--delete deletes the files in out/docs/ that docs does not have", st)
        self.assertIn("rsync copies the contents of docs/ into out/", self.view("rsync -an docs/ out/").state)
        self.assertIn("dry run", self.view("rsync -an docs/ out/").state)
        self.assertIn("sed's pattern \"meeting\" matches 1 line of notes.txt", self.view("sed -i 's/meeting/call/' notes.txt").state)
        self.assertIn("sed's pattern \"^zz\" matches no line of names.txt", self.view("sed -i '/^zz/d' names.txt").state)
        self.assertIn("grep's pattern \"notes\" matches 2 lines in 2 of the", self.view("grep -r notes .").state)
        self.assertIn("find lists 2 names here (./a.tmp, ./b.tmp)", self.view('find . -name "*.tmp" | xargs rm').state)
        st = self.view('find . -name "* notes.txt" | xargs rm').state
        self.assertIn('xargs passes them split at spaces (./old, notes.txt)', st)
        st = self.view('find . -name "*.bak" -print0 | xargs -0 rm').state
        self.assertIn("find lists no name here, so xargs runs the command once with no arguments", st)
        self.assertNotIn("find lists", self.view('find . -mtime +3 | xargs rm').state)  # not followed: no claim
        for cmds in (["sed -i 's/meeting/x/' notes.txt"], ["grep -r SECRET ."]):
            self.assertNotIn(SECRET, S.shell_prompt(self.view(*cmds)), cmds)

    def test_notes_go_after_the_commands(self):
        p = S.shell_prompt(self.view("sort names.txt > names.txt"))
        self.assertIn("1. sort names.txt > names.txt\n\nShell rules for these commands: `>` empties", p)
        self.assertNotIn("Shell rules", S.shell_prompt(self.view("sort names.txt > names.txt"), notes=False))


class TestVerdictAndCli(Base):
    def test_verdict(self):
        v = S.check(["rm notes.txt"], cwd=self.box, client=FakeClient(p_lost=0.9), salt="k", where=WHERE)
        self.assertTrue(v.risky and v.lost_risky and v.judged)
        v = S.check("ls", cwd=self.box, client=FakeClient(p_lost=0.01), salt="k", where=WHERE)
        self.assertFalse(v.risky)
        with self.assertRaises(ValueError):
            S.check([""], cwd=self.box, client=FakeClient())

    def cli(self, *args, p_lost=0.0):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(cli, "Ekbasis", lambda url=None, timeout=None: FakeClient(p_lost=p_lost)), \
                redirect_stdout(out), redirect_stderr(err):
            code = cli.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def test_exit_codes(self):
        self.assertEqual(self.cli("shell-check", "--cwd", self.box, "ls")[0], 0)
        self.assertEqual(self.cli("shell-check", "--cwd", self.box, "rm notes.txt", p_lost=0.9)[0], 2)
        code, out, _ = self.cli("shell-check", "--cwd", self.box, "--json", "rm -rf \"$DIR\"/*")
        self.assertEqual(code, 3)
        self.assertEqual(json.loads(out)["cannot_judge"], True)
        self.assertEqual(self.cli("shell-check", "--cwd", self.box, "--fail-open", "rm -rf \"$DIR\"/*")[0], 0)
        self.assertEqual(self.cli("shell-check", "--cwd", self.box, "")[0], 1)
        code, out, _ = self.cli("shell-check", "--cwd", self.box, "--show-state", "rm .env")
        self.assertIn("--- what the model read ---", out)
        self.assertNotIn(SECRET, out)


if __name__ == "__main__":
    unittest.main()
