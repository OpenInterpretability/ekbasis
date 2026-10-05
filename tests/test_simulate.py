"""Offline tests of the chained simulation: the assignment, ordering decoding and the observe loop (no server)."""
import itertools
import math
import random
import unittest

from ekbasis.client import Answer
from ekbasis.simulate import assignment, read_ordering, simulate


def brute(cost):
    n = len(cost)
    return min(itertools.permutations(range(n)), key=lambda c: sum(cost[i][c[i]] for i in range(n)))


class FakeClient:
    """Answers every question with the same distributions (a fixed belief), and counts the requests."""

    def __init__(self, probs):
        self.probs, self.calls = probs, 0

    def ask(self, state, questions, read_once=False):
        self.calls += 1
        out = {}
        for k in questions:
            p = self.probs[k]
            top = max(p, key=p.get)
            out[k] = Answer(value=top, confidence=p[top], probabilities=dict(p))
        return out


class TestAssignment(unittest.TestCase):
    def test_matches_brute_force(self):
        rng = random.Random(0)
        for n in range(1, 7):
            for _ in range(30):
                cost = [[rng.random() for _ in range(n)] for _ in range(n)]
                got = assignment(cost)
                self.assertAlmostEqual(sum(cost[i][got[i]] for i in range(n)),
                                       sum(cost[i][c] for i, c in enumerate(brute(cost))), places=9)
                self.assertEqual(sorted(got), list(range(n)))

    def test_where_reads_both_views(self):
        # the direct answers alone prefer A, B; the inverse ones (where is A? where is B?) say B, A, and decide
        ans = {"p1": Answer("A", 0.6, {"A": 0.6, "B": 0.4}), "p2": Answer("A", 0.55, {"A": 0.55, "B": 0.45})}
        self.assertEqual(read_ordering(ans, ["p1", "p2"])[0], {"p1": "A", "p2": "B"})
        where = {"A": Answer("p2", 0.9, {"p1": 0.1, "p2": 0.9}), "B": Answer("p1", 0.9, {"p1": 0.9, "p2": 0.1})}
        state, p = read_ordering(ans, ["p1", "p2"], where)
        self.assertEqual(state, {"p1": "B", "p2": "A"})
        self.assertAlmostEqual(p, (0.36 / 0.42) * (0.495 / 0.54))  # each variable's two views, normalized over its values

    def test_where_needs_the_ordering_variables_as_options(self):
        ans = {"p1": Answer("A", 0.6, {"A": 0.6, "B": 0.4}), "p2": Answer("B", 0.6, {"A": 0.4, "B": 0.6})}
        with self.assertRaises(ValueError):
            read_ordering(ans, ["p1", "p2"], {"A": Answer("x", 1.0, {"x": 1.0}), "B": Answer("p1", 1.0, {"p1": 1.0, "p2": 0.0})})

    def test_ordering_repairs_a_duplicate(self):
        # positions 1 and 2 both look most like "A"; the valid ordering gives "B" to the less sure one
        ans = {"p1": Answer("A", 0.9, {"A": 0.9, "B": 0.1}), "p2": Answer("A", 0.6, {"A": 0.6, "B": 0.4})}
        state, p = read_ordering(ans, ["p1", "p2"])
        self.assertEqual(state, {"p1": "A", "p2": "B"})
        self.assertAlmostEqual(p, 0.9 * 0.4)


class TestObserveLoop(unittest.TestCase):
    def test_looks_when_the_chain_confidence_drops(self):
        client = FakeClient({"x": {"0": 0.9, "1": 0.1}})
        seen = []
        sim = simulate(client, "rules", {"x": "0"}, ["a"] * 10, {"x": {"type": "choice"}}, lambda s: str(s),
                       observe=lambda t: seen.append(t) or {"x": "1"}, look_below=0.75, checks=False)
        self.assertEqual(sim.looks, [3, 6, 9])  # 0.9^3 = 0.729 < 0.75
        self.assertEqual(seen, [3, 6, 9])
        self.assertAlmostEqual(sim.confidence, 0.9)  # one step since the last look
        self.assertEqual(client.calls, 10)

    def test_never_looks_after_the_last_action_and_every_k(self):
        client = FakeClient({"x": {"0": 0.99, "1": 0.01}})
        sim = simulate(client, "rules", {"x": "0"}, ["a"] * 10, {"x": {"type": "choice"}}, lambda s: str(s),
                       observe=lambda t: {"x": "0"}, look_every=5)
        self.assertEqual(sim.looks, [5])  # not after action 10, the last one

    def test_default_rule_with_observe(self):
        client = FakeClient({"x": {"0": 0.95, "1": 0.05}})
        sim = simulate(client, "rules", {"x": "0"}, ["a"] * 10, {"x": {"type": "choice"}}, lambda s: str(s),
                       observe=lambda t: {"x": "0"})
        self.assertEqual(sim.looks, [3, 6, 9])  # 0.95^2 = 0.9025, 0.95^3 = 0.857 < 0.9
        self.assertEqual(sim.surprises, [])
        self.assertAlmostEqual(sim.steps[2]["chain"], 0.95 ** 3)

    def test_checks_find_a_confident_error_and_look_until_right(self):
        client = FakeClient({"x": {"0": 0.999, "1": 0.001}})  # sure of "0"; the real state is "1"
        sim = simulate(client, "rules", {"x": "0"}, ["a"] * 30, {"x": {"type": "choice"}}, lambda s: str(s),
                       observe=lambda t: {"x": "1"})
        self.assertEqual(sim.looks, list(range(8, 30)))  # the first check, then again after every action: never right
        self.assertEqual(sim.surprises, sim.looks)

    def test_checks_back_off_while_the_forecast_holds(self):
        client = FakeClient({"x": {"0": 0.9999, "1": 0.0001}})
        sim = simulate(client, "rules", {"x": "0"}, ["a"] * 200, {"x": {"type": "choice"}}, lambda s: str(s),
                       observe=lambda t: {"x": 0})  # values compared as text: 0 == "0"
        self.assertEqual(sim.looks, [8, 24, 56, 120, 184])  # gaps 8, 16, 32, 64, 64
        self.assertEqual(sim.surprises, [])

    def test_an_explicit_rule_replaces_the_default(self):
        client = FakeClient({"x": {"0": 0.8, "1": 0.2}})
        sim = simulate(client, "rules", {"x": "0"}, ["a"] * 10, {"x": {"type": "choice"}}, lambda s: str(s),
                       observe=lambda t: {"x": "0"}, look_every=5)
        self.assertEqual(sim.looks, [5])  # 0.8^1 = 0.8 < 0.9 would have looked at 1 under the default

    def test_horizon_without_observe(self):
        client = FakeClient({"x": {"0": 0.9, "1": 0.1}})
        sim = simulate(client, "rules", {"x": "0"}, ["a"] * 10, {"x": {"type": "choice"}}, lambda s: str(s))
        self.assertEqual(sim.looks, [])
        self.assertEqual(sim.horizon(), 1)      # 0.9 >= 0.9 > 0.9^2 = 0.81
        self.assertEqual(sim.horizon(0.5), 6)   # 0.9^6 = 0.53 >= 0.5 > 0.9^7
        self.assertEqual(sim.horizon(0.75), 2)  # 0.9^2 = 0.81 >= 0.75 > 0.9^3
        self.assertEqual(sim.horizon(0.3), 10)  # 0.9^10 = 0.35: never below

    def test_ordering_in_the_loop(self):
        client = FakeClient({"p1": {"A": 0.9, "B": 0.1}, "p2": {"A": 0.6, "B": 0.4}})
        sim = simulate(client, "rules", {"p1": "A", "p2": "B"}, ["swap"], {"p1": {}, "p2": {}}, lambda s: str(s),
                       ordering=["p1", "p2"])
        self.assertEqual(sim.final, {"p1": "A", "p2": "B"})
        self.assertAlmostEqual(sim.confidence, math.prod([0.9, 0.4]))

    def test_where_in_the_loop(self):
        # the inverse questions go in the same request as the direct ones (one request per action)
        client = FakeClient({"p1": {"A": 0.6, "B": 0.4}, "p2": {"A": 0.55, "B": 0.45},
                             "where 0": {"p1": 0.1, "p2": 0.9}, "where 1": {"p1": 0.9, "p2": 0.1}})
        sim = simulate(client, "rules", {"p1": "A", "p2": "B"}, ["swap", "swap"], {"p1": {}, "p2": {}}, lambda s: str(s),
                       ordering=["p1", "p2"], where={"A": {}, "B": {}})
        self.assertEqual(sim.final, {"p1": "B", "p2": "A"})
        self.assertEqual(client.calls, 2)
        self.assertAlmostEqual(sim.confidence, ((0.36 / 0.42) * (0.495 / 0.54)) ** 2)
        with self.assertRaises(ValueError):
            simulate(client, "rules", {"p1": "A"}, ["a"], {"p1": {}}, lambda s: str(s), where={"A": {}})


if __name__ == "__main__":
    unittest.main()
