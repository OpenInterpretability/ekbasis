"""0.1.42: preflight says nothing on what it cannot judge, as its docstring says. From a Claude Code session's hook log
(689 commands, 2026-10-16; paths, hosts and names replaced): steps that run code given inline to an interpreter
(`python3 - <<'EOF'`, `python3 -c`, `node -e`), steps that run on another machine (ssh, scp/rsync with host:) and loops
written on one line came out "step N is likely to fail". Loops were cut at their `;` into commands named for, do, done,
case, esac, which code then found "not installed" and decided as failing (checked in code). A redirection into a folder
an earlier step creates (`mkdir -p out; ... > out/log`) was also decided as failing. Offline: a fake client."""
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from ekbasis import claude_code_hook as H
from ekbasis import preflight as PF
from ekbasis.client import Answer


class Fake:
    """Step k fails with fails.get(k, p_fail) (the walk's question `f` too); nothing is lost; counts the requests."""

    def __init__(self, p_fail=0.99, fails=None):
        self.p_fail, self.fails, self.requests = p_fail, fails or {}, []

    def ask(self, state, questions, read_once=False, images=None):
        self.requests.append(state)
        out = {}
        for k in questions:
            if k == "why":
                out[k] = Answer(value="other", confidence=0.9, probabilities={"other": 0.9})
                continue
            if k == "lost":
                p = 0.0
            elif k == "f":
                n = len([x for x in state.split("Actions, in order:")[1].split("\n\n")[0].splitlines()
                         if x.strip()[:1].isdigit()])
                p = self.fails.get(n, self.p_fail)
            else:
                p = self.fails.get(int(k[1:]), self.p_fail)
            out[k] = Answer(value=p >= 0.5, confidence=max(p, 1 - p), probabilities={"yes": p, "no": 1 - p}, p_yes=p)
        return out


def box(root):
    for d in ("compare", "dry", "notes", "public", "tools"):
        os.makedirs(os.path.join(root, d), exist_ok=True)
    for p in ("analyze.py", "chart.png", "chart.tmp", "sanity10.jsonl", "compare/P8.json", "compare/P8_same.json",
              "notes/pin.txt", "dry/old.json", "build.py", "a.json", "tools/release.sh"):
        with open(os.path.join(root, p), "w") as fh:
            fh.write("x\n")
    return root


# the log's lines, as typed (with {box} for the folder)
INLINE = ["cd {box} && python3 - <<'EOF'\np = 'analyze.py'\ns = open(p).read()\nopen(p, 'w').write(s.replace('a', 'b'))\n"
          "EOF\ncp chart.png public/chart.png; rm -f chart.tmp",
          "head -1 sanity10.jsonl | python3 -I -c \"import json,sys; r=json.loads(sys.stdin.read()); print(sorted(r))\"; "
          "cp analyze.py dry/; rm -f dry/old.json",
          "timeout 300 python3 - <<'EOF' 2>&1 | grep -v NotOpenSSL\nprint(1)\nEOF\nmv a.json dry/a.json; rm -f chart.tmp",
          "node -e \"require('fs').rmSync('chart.tmp')\"; cp chart.png public/; rm -f a.json"]
REMOTE = ["timeout 60 scp -q -P 2222 notes/pin.txt root@host.example:/root/pin.txt && mv notes/pin.txt notes/pin.sent; "
          "rm -f chart.tmp",
          "timeout 90 ssh -o ConnectTimeout=15 -p 2222 root@host.example 'P=2577534; kill $P'; sleep 1; "
          "mv a.json dry/; rm -f chart.tmp",
          "rsync -a dry/ root@host.example:/root/dry/; rm -rf dry; mv a.json notes/"]
LOOPS = ["cd {box}/compare && for f in P8.json P8_same.json; do echo \"=== $f\"; cat $f; echo; done",
         "for p in $(pgrep -f driver2.sh); do a=$(ps -o args= -p $p); case \"$a\" in *driver2.sh*) kill $p;; esac; "
         "done; sleep 1; rm -f chart.tmp",
         "find compare -type f | head -50 | while read f; do cp \"$f\" dry/; done; rm -f a.json"]


class TestCannotJudge(unittest.TestCase):
    def setUp(self):
        self.box = box(tempfile.mkdtemp())

    def lines(self, group):
        return [x.replace("{box}", self.box) for x in group]

    def test_inline_and_remote_steps_are_never_named(self):
        for group, why in ((INLINE, PF.U_INLINE), (REMOTE, PF.U_REMOTE)):
            for line in self.lines(group):
                plan = PF.plan_line(line, self.box)
                self.assertEqual(plan.unread, [], line)
                opaque = [k for k, st in enumerate(plan.steps, 1) if st.opaque]
                self.assertTrue(opaque and all(plan.steps[k - 1].opaque == why for k in opaque), line)
                # the model says only those steps fail: nothing is named, and the line is "cannot judge" (silent)
                f = Fake(p_fail=0.01, fails={k: 0.99 for k in opaque})
                v = PF.check_line(line, self.box, client=f, copy=False)
                self.assertIsNone(v.first, line)
                self.assertTrue(v.cannot_judge and not v.risky, line)
                self.assertTrue(PF.check_line(line, self.box, client=Fake(p_fail=0.01, fails={k: 0.99 for k in opaque}),
                                              copy=False, fail_closed=True).risky, line)
                # every step fails: the first one named is one it judges
                v = PF.check_line(line, self.box, client=Fake(p_fail=0.99), copy=False)
                self.assertNotIn(v.first, opaque, line)

    def test_loops_on_one_line_are_not_judged(self):
        for line in self.lines(LOOPS):
            f = Fake()
            v = PF.check_line(line, self.box, client=f, copy=False)
            self.assertTrue(v.cannot_judge and not v.risky, line)
            self.assertIn(PF.U_CONTROL, v.plan.unread, line)
            self.assertEqual(f.requests, [], line)

    def test_a_step_after_inline_code_is_still_judged(self):
        # the log's line: an inline edit of a script, then the script; the script failed, after the edit was applied
        line = ("cd {box} && python3 - <<'EOF'\np = 'build.py'\ns = open(p).read()\nopen(p, 'w').write(s)\nEOF\n"
                "python3 build.py").replace("{box}", self.box)
        v = PF.check_line(line, self.box, client=Fake(p_fail=0.01, fails={3: 0.6}), copy=False, walk=False)
        self.assertEqual((v.first, v.risky), (3, True))
        self.assertIn("Step 2 was not judged", v.message())

    def test_no_reserved_word_is_a_missing_command(self):
        for line in self.lines(LOOPS):
            plan = PF.plan_line(line, self.box)
            facts = PF.shell_facts(plan)[1]
            self.assertFalse([x for x in facts if "is not installed" in x], line)

    def test_a_script_file_and_a_local_chain_are_still_judged(self):
        line = "cp a.json dry/a.json; python3 build.py; rm -f a.json"
        plan = PF.plan_line(line, self.box)
        self.assertEqual(plan.unread, [])

        class Second(Fake):
            def ask(self, state, questions, read_once=False, images=None):
                out = super().ask(state, questions, read_once, images)
                for k in questions:
                    if k not in ("why", "lost"):
                        p = 0.95 if k in ("f2",) else 0.01
                        out[k] = Answer(value=p >= 0.5, confidence=max(p, 1 - p), probabilities={"yes": p, "no": 1 - p},
                                        p_yes=p)
                return out
        v = PF.check_line(line, self.box, client=Second(), copy=False, walk=False)
        self.assertEqual(v.first, 2)
        self.assertTrue(v.risky)                             # rm still runs after the failing step
        self.assertIn("would still run", v.message())

    def test_a_command_given_by_its_path_is_not_a_missing_command(self):
        os.makedirs(os.path.join(self.box, "node_modules", ".bin"))
        plan = PF.plan_line("cp a.json dry/; ./node_modules/.bin/tsc --noEmit -p .; rm -f chart.tmp", self.box)
        self.assertEqual(PF.shell_facts(plan)[0], {})

    def test_a_folder_an_earlier_step_creates(self):
        line = (f"rm -rf {self.box}/dryrun && mkdir -p {self.box}/dryrun; DRY_RUN=1 bash tools/release.sh > "
                f"{self.box}/dryrun/rel.log 2>&1; echo \"exit=$?\"")
        plan = PF.plan_line(line, self.box)
        self.assertEqual(PF.shell_facts(plan)[0], {})
        line = "echo x > nope/rel.log; cp a.json b.json; rm -f chart.tmp"     # nothing creates nope/: still a fact
        self.assertIn("nope is not a folder", PF.shell_facts(PF.plan_line(line, self.box))[0].get(1, ""))


class TestHook(unittest.TestCase):
    def setUp(self):
        self.box = box(tempfile.mkdtemp())
        self.env = mock.patch.dict(os.environ, {"EKBASIS_PREFLIGHT": "1", "EKBASIS_GIT_GUARD": "0",
                                                "TMPDIR": tempfile.mkdtemp()})
        self.env.start()
        for k in ("EKBASIS_GUARD_MODE", "EKBASIS_SHELL_GUARD", "EKBASIS_PREFLIGHT_FAIL_CLOSED", "EKBASIS_FAIL_OPEN"):
            os.environ.pop(k, None)
        tempfile.tempdir = None

    def tearDown(self):
        self.env.stop()
        tempfile.tempdir = None

    def hook(self, line, env=None, session="s1"):
        data = {"tool_name": "Bash", "tool_input": {"command": line}, "cwd": self.box, "session_id": session}
        out = io.StringIO()
        with mock.patch.dict(os.environ, env or {}), mock.patch.object(H, "Ekbasis", return_value=Fake(p_fail=0.01)), \
                mock.patch.object(sys, "stdin", io.StringIO(json.dumps(data))), redirect_stdout(out):
            self.assertEqual(H.main(), 0)
        return json.loads(out.getvalue())["hookSpecificOutput"] if out.getvalue().strip() else None

    def test_silent_by_default_and_warns_once_when_fail_closed(self):
        line = INLINE[1]
        self.assertIsNone(self.hook(line))
        on = {"EKBASIS_PREFLIGHT_FAIL_CLOSED": "1"}
        a = self.hook(line, on, session="s2")
        self.assertEqual(a["permissionDecision"], "ask")
        self.assertIn("could not check this multi-step change", a["permissionDecisionReason"])
        self.assertIn("code given inline", a["permissionDecisionReason"])
        self.assertIsNone(self.hook(line, on, session="s2"))   # once


if __name__ == "__main__":
    unittest.main()
