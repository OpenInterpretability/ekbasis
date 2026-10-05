"""Offline tests of 0.1.2's rule recap, numeric questions and compare-in-code helper (no server)."""
import unittest

from ekbasis import prompts as P
from ekbasis.client import Answer
from ekbasis.simulate import simulate, threshold


class RecordingClient:
    """Answers each question with fixed probabilities, or with a scripted value per call; records every request."""

    def __init__(self, probs=None, script=None, conf=0.9):
        self.probs, self.script, self.conf, self.requests = probs or {}, script or {}, conf, []

    def ask(self, state, questions, read_once=False, images=None):
        self.requests.append((state, questions))
        out = {}
        for k, q in questions.items():
            if k in self.script:
                v = self.script[k][len(self.requests) - 1]
                out[k] = Answer(value=v, confidence=self.conf, probabilities={v: self.conf})
            else:
                p = self.probs[k]
                top = max(p, key=p.get)
                out[k] = Answer(value=top, confidence=p[top], probabilities=dict(p))
        return out


class TestDefaultsUnchanged(unittest.TestCase):
    def test_world_state_is_the_training_layout(self):
        got = P.world_state("R.", "S.", ["a", "b"])
        self.assertEqual(got, "R.\n\nCurrent state:\nS.\n\nActions, in order:\n1. a\n2. b\n\n"
                              "The questions are about the state after all these actions.")

    def test_notes_go_after_the_actions(self):
        got = P.world_state("R.", "S.", ["a"], notes=["N1.", "N2."], notes_label="Shell rules for these commands")
        self.assertIn("1. a\n\nShell rules for these commands: N1. N2.\n\nThe questions are about", got)

    def test_questions_unchanged_without_recap(self):
        self.assertEqual(P.yes_no("Q?"), {"type": "noul", "instructions": "Q?"})
        self.assertEqual(P.choice("Q?", ["a", "b"]), {"type": "choice", "instructions": "Q?", "criteria": {"a": "a", "b": "b"}})


class TestRecap(unittest.TestCase):
    def test_one_rule_in_the_measured_wording(self):
        q = P.yes_no("Did it move?")
        r = P.recap(q, "A bigger disk never goes on a smaller one.")
        self.assertEqual(r["instructions"], "Remember this rule: A bigger disk never goes on a smaller one.\nDid it move?")
        self.assertEqual(q["instructions"], "Did it move?")  # the original is not changed

    def test_several_rules_and_a_rules_text(self):
        q = P.choice("Color?", ["red", "blue"])
        self.assertTrue(P.recap(q, ["R1.", "R2."])["instructions"].startswith("Remember these rules: R1. R2.\n"))
        text = "Rules:\n- Pull A turns B red.\n- Lift C turns C blue.\n"
        self.assertEqual(P.rule_lines(text), ["Rules:", "Pull A turns B red.", "Lift C turns C blue."])
        self.assertEqual(P.recap(q, []), q)

    def test_recap_all(self):
        qs = {"a": P.yes_no("A?"), "b": P.yes_no("B?")}
        out = P.recap_all(qs, "R.")
        self.assertTrue(all(v["instructions"].startswith("Remember this rule: R.\n") for v in out.values()))

    def test_simulate_recap_none_is_unchanged_and_true_repeats_the_rules(self):
        probs = {"x": {"0": 0.9, "1": 0.1}}
        a, b, c = RecordingClient(probs), RecordingClient(probs), RecordingClient(probs)
        qs = {"x": P.choice("What is x?", ["0", "1"])}
        render = lambda s: f"x is {s['x']}"  # noqa: E731
        simulate(a, "R.", {"x": "0"}, ["act"], qs, render)
        simulate(b, "R.", {"x": "0"}, ["act"], qs, render, recap=None)
        simulate(c, "R.", {"x": "0"}, ["act"], qs, render, recap=True)
        self.assertEqual(a.requests, b.requests)
        self.assertEqual(c.requests[0][0], a.requests[0][0])  # the state is the same
        self.assertEqual(c.requests[0][1]["x"]["instructions"], "Remember this rule: R.\nWhat is x?")

    def test_number_labels(self):
        self.assertEqual(list(P.number("How many?", [0, 1, 2.5, 3.0])["criteria"]), ["0", "1", "2.5", "3"])


class TestThreshold(unittest.TestCase):
    def setUp(self):
        self.qs = {"spent": P.number("How much has been spent?", range(0, 200, 10))}
        self.render = lambda s: f"Spent so far: {s['spent']} dollars."  # noqa: E731

    def run_with(self, values, **kw):
        client = RecordingClient(script={"spent": values}, conf=0.95)
        return threshold(client, "Each purchase adds its price.", {"spent": "0"}, ["buy"] * len(values), self.qs,
                         self.render, quantity="spent", **kw)

    def test_end_ever_and_before_last(self):
        t = self.run_with(["40", "90", "100"], op=">=", limit=100)
        self.assertEqual(t.trace, [0.0, 40.0, 90.0, 100.0])
        self.assertTrue(t.holds)
        self.assertEqual(t.first, 3)
        self.assertAlmostEqual(t.confidence, 0.95 ** 3)
        self.assertFalse(self.run_with(["40", "90", "100"], op=">=", limit=100, when="before_last").holds)
        self.assertTrue(self.run_with(["120", "90"], op=">", limit=100, when="ever").holds)
        self.assertFalse(self.run_with(["120", "90"], op=">", limit=100, when="end").holds)

    def test_errors(self):
        with self.assertRaises(ValueError):
            self.run_with(["40"], op="=>", limit=1)
        with self.assertRaises(ValueError):
            self.run_with(["40"], op=">=", limit=1, when="sometimes")
        with self.assertRaises(ValueError):
            self.run_with(["forty"], op=">=", limit=1)


if __name__ == "__main__":
    unittest.main()
