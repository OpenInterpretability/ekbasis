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
