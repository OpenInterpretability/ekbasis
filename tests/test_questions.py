"""A malformed question is refused before it is sent: the server reads only `instructions` and would answer a question
in `question` (or with no text) with one same probability, whatever it asked."""
import unittest
import unittest.mock

from ekbasis.client import Ekbasis


class TestQuestionCheck(unittest.TestCase):
    def setUp(self):
        self.c = Ekbasis(url="http://127.0.0.1:9")
        self.sent = unittest.mock.patch.object(Ekbasis, "_call", return_value={"answers": {}}).start()
        self.addCleanup(unittest.mock.patch.stopall)

    def test_question_field_is_refused_with_a_hint(self):
        with self.assertRaises(ValueError) as e:
            self.c.ask("About to: x", {"q": {"type": "noul", "question": "Will it fail?"}})
        self.assertIn("instructions", str(e.exception))
        self.assertIn("'question'", str(e.exception))
        self.sent.assert_not_called()

    def test_missing_text_type_or_empty(self):
        for qs in ({"q": {"type": "noul"}}, {"q": {"type": "noul", "instructions": "  "}},
                   {"q": {"type": "yesno", "instructions": "Will it?"}}, {"q": "Will it?"}, {}):
            with self.assertRaises(ValueError):
                self.c.ask("About to: x", qs)
        self.sent.assert_not_called()

    def test_valid_questions_are_sent(self):
        self.c.ask("About to: x", {"a": {"type": "noul", "instructions": "Will it fail?"},
                                   "b": {"type": "choice", "instructions": "Which?", "criteria": {"x": "x", "y": "y"}}})
        self.sent.assert_called_once()


if __name__ == "__main__":
    unittest.main()
