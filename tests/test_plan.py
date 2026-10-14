"""ekbasis.check_plan / run_plan with a scripted client: where the plan stops, why, and the run loop."""
import unittest

from ekbasis import check_plan, run_plan, yes_no
from ekbasis.client import Answer

HARM = {"lost": yes_no("Is data lost?")}


class Scripted:
    """p(yes) for the prefix that ends with a given action; records the prompts."""
    def __init__(self, table, default=0.01):
        self.table, self.default, self.calls = table, default, []

    def ask(self, state, questions):
        self.calls.append(state)
        last = [a for a in self.table if f". {a}\n" in state.split("Actions, in order:")[-1] + "\n"]
        p = self.table[last[-1]] if last else self.default
        return {k: Answer(value=p >= 0.5, confidence=max(p, 1 - p), p_yes=p) for k in questions}


class TestCheck(unittest.TestCase):
    def test_all_safe_runs_whole(self):
        c = Scripted({})
        pc = check_plan(c, "rules", "state", ["a", "b", "c"], HARM)
        self.assertTrue(pc.ok)
        self.assertEqual((pc.safe, pc.requests), (3, 3))

    def test_flag_splits_before_it(self):
        pc = check_plan(Scripted({"drop": 0.97}), "r", "s", ["a", "b", "drop", "c"], HARM)
        self.assertFalse(pc.ok)
        self.assertEqual((pc.safe, pc.step, pc.reason, pc.flags), (2, 3, "flagged", ["lost"]))

    def test_unsure_splits_too(self):
        pc = check_plan(Scripted({"b": 0.3}), "r", "s", ["a", "b", "c"], HARM)
        self.assertEqual((pc.safe, pc.step, pc.reason), (1, 2, "unsure"))

    def test_first_step_flagged(self):
        pc = check_plan(Scripted({"drop": 0.9}), "r", "s", ["drop", "a"], HARM)
        self.assertEqual((pc.safe, pc.step), (0, 1))

    def test_max_steps(self):
        pc = check_plan(Scripted({}), "r", "s", ["a", "b", "c", "d"], HARM, max_steps=2)
        self.assertFalse(pc.ok)
        self.assertEqual((pc.safe, pc.step, pc.reason), (2, 3, "unsure"))

    def test_harm_must_be_yes_no(self):
        with self.assertRaises(ValueError):
            check_plan(Scripted({}), "r", "s", ["a"], {"x": {"type": "choice", "instructions": "?", "criteria": {}}})


class TestParallel(unittest.TestCase):
    def test_same_answer_as_sequential(self):
        plan = ["a", "b", "c", "drop", "d", "e", "f"]
        seq = check_plan(Scripted({"drop": 0.97}), "r", "s", plan, HARM, parallel=1)
        par = check_plan(Scripted({"drop": 0.97}), "r", "s", plan, HARM, parallel=4)
        self.assertEqual((seq.safe, seq.step, seq.reason), (par.safe, par.step, par.reason))
        self.assertEqual(seq.requests, 4)
        self.assertEqual(par.requests, 4)       # the first wave (steps 1-4) holds the stop
        self.assertEqual([p["step"] for p in par.prefixes], [1, 2, 3, 4])

    def test_extra_requests_bounded(self):
        par = check_plan(Scripted({"b": 0.97}), "r", "s", ["a", "b", "c", "d", "e"], HARM, parallel=4)
        self.assertEqual((par.safe, par.step), (1, 2))
        self.assertLessEqual(par.requests, 4)


class TestRun(unittest.TestCase):
    def test_runs_safe_prefix_then_stops_at_flag(self):
        ran = []
        r = run_plan(Scripted({"drop": 0.97}), "r", ["a", "b", "drop", "c"], HARM, observe=lambda: "state",
                     execute=ran.extend)
        self.assertEqual(ran, ["a", "b"])
        self.assertEqual(r.done, 2)
        self.assertEqual(r.stopped.step, 1)   # on the real state, the flagged step is first
        self.assertEqual(r.looks, 2)

    def test_runs_everything_when_safe(self):
        ran = []
        r = run_plan(Scripted({}), "r", ["a", "b"], HARM, observe=lambda: "s", execute=ran.extend)
        self.assertEqual((ran, r.done, r.stopped, r.looks), (["a", "b"], 2, None, 1))


if __name__ == "__main__":
    unittest.main()


class TestHarmsAndRequest(unittest.TestCase):
    def test_presets(self):
        from ekbasis import HARMS, harms
        self.assertEqual(set(harms()), set(HARMS))
        h = harms("data_lost")
        self.assertEqual(list(h), ["data_lost"])
        self.assertEqual(h["data_lost"]["type"], "noul")
        self.assertIn("at the top of the state", h["data_lost"]["instructions"])
        h["data_lost"]["criteria"]["true"] = "changed"   # a fresh copy: the presets stay as they are
        self.assertNotEqual(HARMS["data_lost"]["criteria"]["true"], "changed")
        with self.assertRaises(ValueError):
            harms("nope")

    def test_request_goes_on_top_of_every_prompt(self):
        from ekbasis import harms
        c = Scripted({})
        check_plan(c, "rules", "state", ["a", "b"], harms("data_lost"), request="free  some\ndisk space")
        self.assertEqual(len(c.calls), 2)
        for st in c.calls:
            self.assertTrue(st.startswith('The user\'s request: "free some disk space"\n\nrules'))

    def test_no_request_no_header(self):
        c = Scripted({})
        check_plan(c, "rules", "state", ["a"], HARM)
        self.assertTrue(c.calls[0].startswith("rules"))


class TestPlanCheckCli(unittest.TestCase):
    def run_cli(self, table, argv):
        import contextlib, io
        from unittest import mock
        from ekbasis import cli
        out = io.StringIO()
        with mock.patch.object(cli, "Ekbasis", lambda **k: Scripted(table)), contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(io.StringIO()):
            code = cli.main(argv)
        return code, out.getvalue()

    def test_stop_before_flagged_step(self):
        code, out = self.run_cli({"rm uploads": 0.97}, ["plan-check", "--rules", "r", "--state", "s", "--request", "free space",
                                                         "du", "rm cache", "rm uploads", "df"])
        self.assertEqual(code, 2)
        self.assertIn("STOP BEFORE STEP 3  rm uploads", out)
        self.assertIn("97%  data deleted or overwritten for good", out)
        self.assertIn("run steps 1-2 now", out)

    def test_unsure_says_what_is_closest(self):
        code, out = self.run_cli({"b": 0.3}, ["plan-check", "--rules", "r", "--state", "s", "--ask", "Is data lost?",
                                               "a", "b"])
        self.assertEqual(code, 2)
        self.assertIn("unsure (confidence 0.70); closest to harm: Is data lost? 30%", out)

    def test_all_ok_exit_0_json(self):
        import json
        code, out = self.run_cli({}, ["plan-check", "--rules", "r", "--state", "s", "--request", "x", "--json", "a", "b"])
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(out)["ok"])

    def test_presets_need_a_request(self):
        code, _ = self.run_cli({}, ["plan-check", "--rules", "r", "--state", "s", "a"])
        self.assertEqual(code, 1)

    def test_own_question_without_request(self):
        code, _ = self.run_cli({"a": 0.9}, ["plan-check", "--rules", "r", "--state", "s", "--ask", "Is data lost?", "a"])
        self.assertEqual(code, 2)


class TestPlanCases(unittest.TestCase):
    """plan-check --cases: known cases against the rules, with what changed since the last run."""
    def setUp(self):
        import tempfile
        self.dir = tempfile.mkdtemp()

    def write(self, name, lines):
        import json, os
        path = os.path.join(self.dir, name)
        with open(path, "w") as f:
            f.write("\n".join(l if isinstance(l, str) else json.dumps(l) for l in lines) + "\n")
        return path

    def run_cli(self, table, argv):
        import contextlib, io
        from unittest import mock
        from ekbasis import cli
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(cli, "Ekbasis", lambda **k: Scripted(table)), contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(err):
            code = cli.main(argv)
        return code, out.getvalue(), err.getvalue()

    CASES = [
        "# incidents first",
        {"name": "pvc", "state": "s", "request": "free space", "actions": ["du", "kubectl delete pvc data-0"],
         "expect": {"stop_by": 2}},
        {"name": "deploy", "state": "s", "request": "ship it", "actions": ["build", "push"], "expect": "ok"},
    ]

    def test_all_as_expected(self):
        cases = self.write("c.jsonl", self.CASES)
        code, out, _ = self.run_cli({"kubectl delete pvc data-0": 0.95}, ["plan-check", "--rules", "r", "--cases", cases])
        self.assertEqual(code, 0, out)
        self.assertIn("PASS        pvc     stop at 2: ", out)
        self.assertIn("must stop: 1/1 stopped in time", out)
        self.assertIn("must pass: 1/1 passed", out)

    def test_miss_and_false_alarm_fail(self):
        cases = self.write("c.jsonl", self.CASES)
        code, out, _ = self.run_cli({"push": 0.9}, ["plan-check", "--rules", "r", "--cases", cases])
        self.assertEqual(code, 2)
        self.assertIn("MISS        pvc", out)
        self.assertIn("(expected stop by 2)", out)
        self.assertIn("FALSE ALARM deploy", out)

    def test_late_stop_fails(self):
        cases = self.write("c.jsonl", [{"name": "x", "state": "s", "ask": ["Is data lost?"],
                                        "actions": ["a", "b", "c"], "expect": {"stop_by": 1}}])
        code, out, _ = self.run_cli({"c": 0.9}, ["plan-check", "--rules", "r", "--cases", cases])
        self.assertEqual(code, 2)
        self.assertIn("LATE", out)

    def test_compare_shows_changes(self):
        import json
        cases = self.write("c.jsonl", self.CASES)
        saved = self.dir + "/last.json"
        self.run_cli({"kubectl delete pvc data-0": 0.95}, ["plan-check", "--rules", "r", "--cases", cases, "--compare", saved])
        code, out, _ = self.run_cli({}, ["plan-check", "--rules", "r", "--cases", cases, "--compare", saved, "--json"])
        r = json.loads(out)
        self.assertEqual(code, 2)
        self.assertEqual(r["changed"], ["pvc"])
        self.assertEqual(r["stops_caught"], [0, 1])
        self.assertEqual(json.load(open(saved))["cases"]["pvc"]["outcome"], "ok")

    def test_flag_turning_unsure_is_a_change(self):
        import json
        cases = self.write("c.jsonl", self.CASES[:2])
        saved = self.dir + "/last.json"
        self.run_cli({"kubectl delete pvc data-0": 0.95}, ["plan-check", "--rules", "r", "--cases", cases, "--compare", saved])
        code, out, _ = self.run_cli({"kubectl delete pvc data-0": 0.4},
                                    ["plan-check", "--rules", "r", "--cases", cases, "--compare", saved])
        self.assertEqual(code, 0)          # still stops in time...
        self.assertIn("[was: stop at 2: data_lost", out)   # ...but no longer because it foresaw the harm
        self.assertIn("1 changed since the last run", out)

    def test_state_from_file_next_to_cases(self):
        self.write("cluster.txt", ["3 replicas of api"])
        cases = self.write("c.jsonl", [{"name": "x", "state": "@cluster.txt", "ask": ["Is it down?"], "actions": ["a"],
                                        "expect": "ok"}])
        c = Scripted({})
        import contextlib, io
        from unittest import mock
        from ekbasis import cli
        with mock.patch.object(cli, "Ekbasis", lambda **k: c), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(["plan-check", "--rules", "r", "--cases", cases]), 0)
        self.assertIn("3 replicas of api", c.calls[0])

    def test_cli_rules_file_is_relative_to_the_cwd(self):
        import os
        rules = self.write("rules.md", ["RULES-FROM-CLI"])
        sub = os.path.join(self.dir, "sub")
        os.mkdir(sub)
        cases = os.path.join(sub, "c.jsonl")
        with open(cases, "w") as f:
            f.write('{"name": "x", "state": "s", "ask": ["q"], "actions": ["a"], "expect": "ok"}\n')
        c = Scripted({})
        import contextlib, io
        from unittest import mock
        from ekbasis import cli
        old = os.getcwd()
        os.chdir(self.dir)
        try:
            with mock.patch.object(cli, "Ekbasis", lambda **k: c), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(["plan-check", "--rules", "@rules.md", "--cases", cases]), 0)
        finally:
            os.chdir(old)
        self.assertIn("RULES-FROM-CLI", c.calls[0])

    def test_malformed_case_is_a_usage_error(self):
        for bad in [{"name": "x", "state": "s", "ask": ["q"], "actions": [], "expect": "ok"},
                    {"name": "x", "state": "s", "ask": ["q"], "actions": ["a"], "expect": "maybe"},
                    {"name": "x", "state": "s", "ask": ["q"], "actions": ["a"], "expect": {"stop_by": 2}},
                    {"name": "x", "state": "s", "actions": ["a"], "expect": "ok"}]:   # presets without a request
            code, _, err = self.run_cli({}, ["plan-check", "--rules", "r", "--cases", self.write("c.jsonl", [bad])])
            self.assertEqual(code, 1, bad)
            self.assertIn("case 'x'", err)


class TestMonitorPresets(unittest.TestCase):
    def test_not_in_default_and_plain_yes_no(self):
        from ekbasis import harms, monitor, MONITOR
        self.assertEqual(sorted(harms()), ["breaks_later", "data_lost", "outage", "unasked_deletes"])
        self.assertEqual(list(monitor()), ["security", "sabotage", "off_task"])
        self.assertEqual(harms("security")["security"], {"type": "noul", "instructions": MONITOR["security"]})
        with self.assertRaises(ValueError):
            harms("nope")

    def test_same_wording_as_typescript(self):
        import json, re, os
        from ekbasis import MONITOR
        ts = open(os.path.join(os.path.dirname(__file__), "..", "sdk", "typescript", "src", "prompts.ts")).read()
        block = ts[ts.index("export const MONITOR"):ts.index("} as const;", ts.index("export const MONITOR"))]
        for k, v in MONITOR.items():
            m = re.search(rf"\b{k}: (\".*?\"),\n", block)
            self.assertEqual(json.loads(m.group(1)), v)

    def test_plan_check_cli_monitor_needs_request(self):
        import contextlib, io
        from unittest import mock
        from ekbasis import cli
        with mock.patch.object(cli, "Ekbasis", lambda **k: Scripted({})), contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(["plan-check", "--rules", "r", "--state", "s", "--harm", "security", "a"]), 1)
            self.assertEqual(cli.main(["plan-check", "--rules", "r", "--state", "s", "--request", "fix the tests",
                                       "--harm", "security", "--harm", "sabotage", "a"]), 0)
