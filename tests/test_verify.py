"""Tests of ekbasis.verify against a mock System One server (a real HTTP server on 127.0.0.1, no model): the exact
requests the policy sends, its scores against the frozen policy of the confirmatory test, the decisions, the family
tracker (observed outcomes only, blocked actions reported apart), the step-by-step check, the git wrapper, and failing
closed."""
import http.server
import json
import os
import tempfile
import threading
import unittest

from ekbasis import prompts as P
from ekbasis import verify as V
from ekbasis.client import Answer, Ekbasis
from ekbasis.git import Verdict


class MockServer:
    """POST /v1/systemone: every question is answered by `rule(state, name, question) -> {label: probability}`; every
    request body is recorded. status: an HTTP status to return instead (to test failures)."""

    def __init__(self, rule, status=200):
        self.rule, self.status, self.requests = rule, status, []
        mock = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):  # quiet
                pass

            def do_POST(self):  # noqa: N802
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                mock.requests.append(body)
                if mock.status != 200:
                    self.send_response(mock.status)
                    self.end_headers()
                    self.wfile.write(b"mock failure")
                    return
                answers = {}
                for name, q in body["questions"].items():
                    probs = mock.rule(body["state"], name, q)
                    if q["type"] == "noul":
                        p = probs["yes"]
                        answers[name] = {"type": "noul", "value": p >= 0.5, "probability": p, "confidence": max(p, 1 - p)}
                    else:
                        top = max(probs, key=probs.get)
                        answers[name] = {"type": "choice", "choice": top, "confidence": probs[top], "probabilities": probs}
                out = json.dumps({"answers": answers}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

        self.srv = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.client = Ekbasis(url=f"http://127.0.0.1:{self.srv.server_address[1]}", timeout=10)

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


def rule_from(p_reorder, p_prefixed, p_no_self):
    """Answers: the self-check gets P(no) = p_no_self; the prefixed question gives the first option... see below."""
    def rule(state, name, q):
        text = q["instructions"]
        if text.startswith("Consider this question:"):
            return {"yes": 1 - p_no_self, "no": p_no_self}
        labels = list(q["criteria"]) if q["type"] == "choice" else ["yes", "no"]
        target = "A" if "A" in labels else "yes"
        p = p_prefixed if text.startswith(V.PREFIX) else p_reorder
        rest = [lab for lab in labels if lab != target]
        return {target: p, **{lab: (1 - p) / len(rest) for lab in rest}}
    return rule


STATE = "Rules: the lamp turns red when pressed.\n\nCurrent state:\nlamp: blue\n\nActions, in order:\n1. press"
CHOICE = P.choice("What colour is the lamp?", {"A": "a red light", "B": "B"})
YESNO = P.yes_no("Is the lamp red?")


class TestFrozenPolicy(unittest.TestCase):
    def test_scores_match_the_confirmatory_policy(self):
        # golden values from results/client_0.1.4/confirm/policy.py (Policy().score), the policy that was confirmed
        golden = [((0.0123, 0.031, 0.02), 0.5731157937242165), ((0.31, 0.42, 0.66), 0.9237160241617732),
                  ((0.12, 0.0005, 0.9), 0.5379346044436563), ((0.5, 0.0, 0.0), 0.32616609193307833)]
        for (fam, stab, doubt), want in golden:
            self.assertEqual(V.score(fam, stab, doubt), want)
        # git and shell: no self-check (policy.py ignores the third signal for git_wild and shell_wild)
        self.assertEqual(V.score(0.08, 0.2), 0.7664088734366982)
        self.assertEqual(V.score(0.5, 0.01), 0.801243301374547)
        self.assertEqual(V.policy()["tau"], 0.6413503412121874)
        self.assertEqual(V.policy()["no_selfcheck_domains"], ["git", "shell"])


class TestThresholds(unittest.TestCase):
    """The per-domain thresholds (default) and the conformal option, exactly as fitted on dev and confirmed on fresh
    items (results/client_0.1.4/confirm2/params_confirm2.json)."""

    def test_domain_thresholds_are_the_confirmed_ones(self):
        want = {"rules": 0.6055848106528391, "sql": 0.4836054561014753, "shell": 0.6570531088924103,
                "git": 0.7675364241656271, "totals": 0.7360748425001905}
        for d, t in want.items():
            self.assertEqual(V.threshold(d), t)
        self.assertEqual(V.threshold("git_wild"), want["git"])      # the evaluation suite names are accepted
        self.assertEqual(V.threshold("Accumulation"), want["totals"])
        self.assertEqual(V.threshold(None), V.policy()["tau"])       # any other domain: the global threshold
        self.assertEqual(V.threshold("terraform"), V.policy()["tau"])
        self.assertEqual(V.threshold("git", rule="global"), V.policy()["tau"])

    def test_conformal_groups_and_fallbacks(self):
        self.assertEqual(V.policy()["conformal"]["alpha"], 0.15)
        self.assertEqual(len(V.policy()["conformal"]["groups"]), 17)
        self.assertEqual(V.threshold("rules", "kind|delay", rule="conformal"), 0.7746812586564135)
        self.assertEqual(V.threshold("rules", "kind|plain", rule="conformal"), 0.5211290808268627)  # the rules rest group
        self.assertEqual(V.threshold("sql", "where|where_null", rule="conformal"), 0.4290206279330199)
        self.assertEqual(V.threshold("git", "git:checkout|lost", rule="conformal"), 0.7488905697934353)  # git rest
        self.assertEqual(V.threshold(None, "x", rule="conformal"), V.policy()["tau"])
        with self.assertRaises(ValueError):
            V.threshold("git", rule="strict")

    def test_the_domain_changes_the_decision(self):
        # stability 0.02 and P(no) 0.03 in a family never wrong in 60 observations: a score of about 0.58, between the
        # sql threshold (0.48) and the global one (0.64), so sql verifies and the default for an unnamed domain does not
        tr = V.FamilyTracker()
        for _ in range(60):
            tr.observe("f", correct=True)
        decisions = {}
        for domain in ("sql", None):
            m = MockServer(rule_from(0.98, 0.99, 0.03))
            try:
                decisions[domain] = V.check(m.client, STATE, CHOICE, Answer("A", 0.97, {"A": 0.97, "B": 0.03}), family="f",
                                            domain=domain, tracker=tr)
            finally:
                m.close()
        sql, other = decisions["sql"], decisions[None]
        self.assertAlmostEqual(sql.score, other.score, places=12)
        self.assertTrue(V.threshold("sql") <= sql.score < V.threshold(None), sql.score)
        self.assertTrue(sql.verify)
        self.assertFalse(other.verify)
        self.assertEqual((sql.rule, sql.threshold), ("domain", V.threshold("sql")))


class TestRequests(unittest.TestCase):
    def test_unsure_answer_needs_no_call(self):
        m = MockServer(rule_from(0.9, 0.9, 0.1))
        try:
            d = V.check(m.client, STATE, CHOICE, Answer("A", 0.8, {"A": 0.8, "B": 0.2}))
            self.assertTrue(d.verify)
            self.assertEqual((d.requests, len(m.requests)), (0, 0))
            self.assertIn("unsure", d.reasons[0])
        finally:
            m.close()

    def test_choice_question_sends_the_two_variants_then_the_self_check(self):
        m = MockServer(rule_from(0.99, 0.99, 0.02))
        try:
            V.check(m.client, STATE, CHOICE, Answer("A", 0.97, {"A": 0.97, "B": 0.03}))
            self.assertEqual(len(m.requests), 2)
            first, second = m.requests
            self.assertEqual(first["state"], STATE)
            self.assertEqual(list(first["questions"]["reorder"]["criteria"].items()), [("B", "B"), ("A", "a red light")])
            self.assertEqual(first["questions"]["para"]["instructions"],
                             "Answer from the rules and the state above. What colour is the lamp?")
            self.assertEqual(first["questions"]["para"]["criteria"], {"A": "a red light", "B": "B"})
            self.assertEqual(second["state"], STATE)
            self.assertEqual(second["questions"]["q"]["instructions"],
                             'Consider this question: "What colour is the lamp?" Is "A (a red light)" the correct answer?')
            self.assertEqual(second["questions"]["q"]["criteria"], {"yes": "yes", "no": "no"})
        finally:
            m.close()

    def test_yes_no_question_variants(self):
        m = MockServer(rule_from(0.99, 0.99, 0.02))
        try:
            V.check(m.client, STATE, YESNO, Answer(True, 0.98, {"yes": 0.98, "no": 0.02}, p_yes=0.98))
            first, second = m.requests
            self.assertEqual(first["questions"]["reorder"], {"type": "choice", "instructions": "Is the lamp red?",
                                                             "criteria": {"no": "no", "yes": "yes"}})
            self.assertEqual(first["questions"]["para"], {"type": "noul",
                                                          "instructions": "Answer from the rules and the state above. Is the lamp red?"})
            self.assertEqual(second["questions"]["q"]["instructions"],
                             'Consider this question: "Is the lamp red?" Is "yes" the correct answer?')
        finally:
            m.close()

    def test_git_and_shell_skip_the_self_check(self):
        for domain in ("git", "shell", "GIT"):
            m = MockServer(rule_from(0.99, 0.99, 0.9))
            try:
                d = V.check(m.client, STATE, YESNO, Answer(True, 0.98, {"yes": 0.98, "no": 0.02}, p_yes=0.98), domain=domain)
                self.assertEqual((d.requests, len(m.requests)), (1, 1))
                self.assertNotIn("self_check", d.signals)
            finally:
                m.close()


class TestDecisions(unittest.TestCase):
    def test_unstable_doubted_answer_in_a_failing_family_is_verified(self):
        tr = V.FamilyTracker()
        for k in range(20):
            tr.observe("rules|negation", correct=k % 3 != 0)  # 7 errors in 20
        m = MockServer(rule_from(0.55, 0.6, 0.7))
        try:
            d = V.check(m.client, STATE, CHOICE, Answer("A", 0.97, {"A": 0.97, "B": 0.03}), family="rules|negation", tracker=tr)
            self.assertTrue(d.verify)
            self.assertGreaterEqual(d.score, V.policy()["tau"])
            self.assertTrue(any("wrong 7 of 20" in r for r in d.reasons), d.reasons)
            self.assertAlmostEqual(d.signals["stability"]["value"], 0.45, places=6)
            self.assertAlmostEqual(d.signals["self_check"]["value"], 0.7, places=6)
        finally:
            m.close()

    def test_stable_answer_in_a_reliable_family_is_not_verified(self):
        tr = V.FamilyTracker()
        for _ in range(300):
            tr.observe("rules|plain", correct=True)
        m = MockServer(rule_from(0.995, 0.995, 0.01))
        try:
            d = V.check(m.client, STATE, CHOICE, Answer("A", 0.99, {"A": 0.99, "B": 0.01}), family="rules|plain", tracker=tr)
            self.assertFalse(d.verify)
            self.assertLess(d.score, V.policy()["tau"])
            self.assertEqual(d.requests, 2)
        finally:
            m.close()

    def test_failing_server_means_verify(self):
        m = MockServer(rule_from(0.99, 0.99, 0.01), status=500)
        try:
            d = V.check(m.client, STATE, CHOICE, Answer("A", 0.99, {"A": 0.99, "B": 0.01}))
            self.assertTrue(d.verify)
            self.assertIn("could not run", d.reasons[0])
        finally:
            m.close()


class TestTracker(unittest.TestCase):
    def test_only_observed_outcomes_count(self):
        tr = V.FamilyTracker()
        self.assertEqual(tr.rate("x"), 0.5)
        tr.observe("x", correct=False)
        tr.observe("x", correct=True)
        tr.unobserved("x")  # a blocked action: reported, never counted
        tr.unobserved("x")
        self.assertEqual(tr.counts("x"), {"observed": 2, "errors": 1, "unobserved": 2})
        self.assertEqual(tr.rate("x"), (1 + 1) / (2 + 2))

    def test_blocked_actions_are_named_in_the_reasons(self):
        tr = V.FamilyTracker()
        tr.observe("git:reset|lost", correct=False)
        tr.unobserved("git:reset|lost")
        m = MockServer(rule_from(0.6, 0.6, 0.5))
        try:
            d = V.check(m.client, STATE, YESNO, Answer(True, 0.97, {"yes": 0.97, "no": 0.03}, p_yes=0.97),
                        family="git:reset|lost", domain="git", tracker=tr)
            self.assertTrue(any("never observed" in r for r in d.reasons), d.reasons)
        finally:
            m.close()

    def test_saved_and_loaded(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "sub", "families.json")
            tr = V.FamilyTracker(path)
            tr.observe("a", correct=False)
            tr.unobserved("a")
            again = V.FamilyTracker(path)
            self.assertEqual(again.counts("a"), {"observed": 1, "errors": 1, "unobserved": 1})
            self.assertEqual(again.rate("a"), tr.rate("a"))


class TestAudit(unittest.TestCase):
    def test_audit_picks_the_requested_share(self):
        import random
        rng = random.Random(7)
        picks = sum(V.audit(0.05, rng) for _ in range(20000))
        self.assertTrue(800 < picks < 1200, picks)  # about 5%
        self.assertFalse(any(V.audit(0.0, rng) for _ in range(1000)))


class TestSteps(unittest.TestCase):
    """A counter: each press adds one; the question asks whether the counter reached 3 after the presses."""

    RULES = "Each press adds one to the counter. The alarm rings when the counter reaches 3."
    QS = {"count": P.choice("What is the counter?", ["0", "1", "2", "3", "4"]), "alarm": P.yes_no("Does the alarm ring?")}

    @staticmethod
    def render(st):
        return f"counter: {st['count']}\nalarm: {'ringing' if st['alarm'] in (True, 'yes') else 'silent'}"

    def make_rule(self, p_direct, p_last):
        def rule(state, name, q):
            if name == "alarm":
                many = state.count("\n1. ") and "\n2. press" in state  # the direct question lists every action
                n = state.split("counter: ")[1].split("\n")[0]
                p = p_direct if many else (p_last if n == "2" else 0.02)
                return {"yes": p, "no": 1 - p}
            n = int(state.split("counter: ")[1].split("\n")[0])
            return {str(v): (0.96 if v == n + 1 else 0.01) for v in range(5)}
        return rule

    def run_case(self, p_direct, p_last):
        m = MockServer(self.make_rule(p_direct, p_last))
        try:
            d = V.check_steps(m.client, self.RULES, {"count": "0", "alarm": "no"}, ["press", "press", "press"], self.QS,
                              self.render, target="alarm")
            return d, len(m.requests)
        finally:
            m.close()

    def test_disagreement_is_verified(self):
        d, n = self.run_case(0.97, 0.40)
        self.assertTrue(d.verify)
        self.assertEqual(d.answer, "yes")
        self.assertAlmostEqual(d.score, 0.57, places=6)
        self.assertEqual((d.requests, n), (4, 4))  # the direct question, then one per action

    def test_agreement_is_not_verified(self):
        d, n = self.run_case(0.97, 0.96)
        self.assertFalse(d.verify)
        self.assertAlmostEqual(d.score, 0.01, places=6)


class TestGit(unittest.TestCase):
    def test_family_keys(self):
        self.assertEqual(V.git_family(["git stash", "git checkout main"], "lost"), "git:checkout+stash|lost")
        self.assertEqual(V.git_family(["git -C sub reset --hard"], "fails"), "git:reset|fails")
        self.assertEqual(V.shell_family(["rm -rf build", "/bin/mv a b"], "lost"), "shell:mv+rm|lost")

    def test_verdict_questions_without_self_check(self):
        v = Verdict(commands=["git stash", "git checkout main"], p_lost=0.03, p_fail=[0.02, 0.95], p_in_progress=0.01,
                    state="State before:\nclean")
        m = MockServer(rule_from(0.99, 0.99, 0.5))
        try:
            out = V.git(v, m.client, tracker=V.FamilyTracker())
            self.assertEqual(sorted(out), ["fails_1", "fails_2", "in_progress", "lost"])
            self.assertEqual(out["lost"].family, "git:checkout+stash|lost")
            self.assertEqual(out["fails_2"].family, "git:checkout|fails")
            self.assertEqual(out["lost"].answer, "no")
            self.assertEqual(len(m.requests), 4)  # one perturbation request per confident answer, no self-check
            self.assertTrue(all(set(r["questions"]) == {"reorder", "para"} for r in m.requests))
            self.assertTrue(all(r["state"] == "State before:\nclean" for r in m.requests))
        finally:
            m.close()


if __name__ == "__main__":
    unittest.main()
