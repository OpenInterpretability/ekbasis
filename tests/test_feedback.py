"""`ekbasis feedback` (0.1.9): the request id comes back in X-Ekbasis-Request-Id and is kept on disk (only the id),
feedback is posted to {url}/feedback, a 404 is retried once (the id registers just after the answer), and refusals
exit 4 while an unreachable server exits 3. Offline: a local fake of the hosted API."""
import http.server
import io
import json
import os
import socket
import tempfile
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from ekbasis import cli
from ekbasis.client import Ekbasis, FeedbackRejected, last_request_id

RID = "req_" + "a" * 24


class Hosted(http.server.BaseHTTPRequestHandler):
    seen: list = []
    fail_first_404 = False
    status = 200

    def _send(self, code, obj, headers=()):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(b)

    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Hosted.seen.append((self.path, dict(self.headers), body))
        if self.path == "/v1/systemone":
            ans = {"value": "a", "confidence": 0.9, "probabilities": {"a": 0.9, "b": 0.1}}
            return self._send(200, {"answers": {k: ans for k in body["questions"]}}, [("X-Ekbasis-Request-Id", RID)])
        if self.path == "/feedback":
            if Hosted.fail_first_404:
                Hosted.fail_first_404 = False
                return self._send(404, {"error": "unknown request id: not one of your calls"})
            if Hosted.status != 200:
                return self._send(Hosted.status, {"error": "feedback for this request was already recorded"})
            return self._send(200, {"ok": True, "request_id": body["request_id"], "verdict": body["verdict"]})
        self._send(404, {"detail": "Not Found"})

    def log_message(self, *a):
        pass


class FeedbackTest(unittest.TestCase):
    def setUp(self):
        Hosted.seen, Hosted.fail_first_404, Hosted.status = [], False, 200
        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Hosted)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}"
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"EKBASIS_CACHE_DIR": self.tmp.name, "EKBASIS_API_KEY": "ekb_test"})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.srv.shutdown()
        self.srv.server_close()
        self.tmp.cleanup()

    def ask(self, **kw):
        c = Ekbasis(url=self.url, **kw)
        c.ask("About to: x", {"q": {"type": "choice", "instructions": "?", "options": ["a", "b"]}})
        return c

    def cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["--url", self.url, *args])
        return code, out.getvalue(), err.getvalue()

    def test_request_id_is_kept_and_only_the_id(self):
        c = self.ask(surface="mcp")
        self.assertEqual(c.last_request_id, RID)
        self.assertEqual(last_request_id(), RID)
        saved = json.loads(open(os.path.join(self.tmp.name, "last_request_id")).read())
        self.assertEqual(set(saved), {"id", "t"})
        self.assertEqual(Hosted.seen[0][1].get("X-Ekbasis-Surface"), "mcp")

    def test_feedback_posts_verdict_and_note(self):
        c = self.ask()
        r = c.feedback("prevented_harm", note="stopped a reset")
        self.assertTrue(r["ok"])
        path, headers, body = Hosted.seen[-1]
        self.assertEqual(path, "/feedback")
        self.assertEqual(headers["Authorization"], "Bearer ekb_test")
        self.assertEqual(body, {"request_id": RID, "verdict": "prevented_harm", "note": "stopped a reset"})

    def test_404_is_retried_once(self):
        self.ask()
        Hosted.fail_first_404 = True
        r = Ekbasis(url=self.url).feedback("correct", retry_s=0.01)
        self.assertEqual(r["verdict"], "correct")
        self.assertEqual(sum(1 for s in Hosted.seen if s[0] == "/feedback"), 2)

    def test_bad_verdict_and_missing_id(self):
        with self.assertRaises(ValueError):
            Ekbasis(url=self.url).feedback("maybe", request_id=RID)
        with self.assertRaises(ValueError):
            Ekbasis(url=self.url).feedback("correct")

    def test_cli_last(self):
        self.ask()
        code, out, _ = self.cli("feedback", "--last", "--wrong", "--note", "it was safe")
        self.assertEqual(code, cli.OK)
        self.assertIn("feedback recorded", out)
        self.assertEqual(Hosted.seen[-1][2]["verdict"], "wrong")

    def test_cli_explicit_id_and_rejection_exits_4(self):
        Hosted.status = 409
        code, _, err = self.cli("feedback", RID, "--correct")
        self.assertEqual(code, cli.FEEDBACK_REJECTED)
        self.assertIn("409", err)

    def test_cli_needs_exactly_one_of_id_or_last(self):
        self.assertEqual(self.cli("feedback", "--correct")[0], cli.ERROR)
        self.assertEqual(self.cli("feedback", RID, "--last", "--correct")[0], cli.ERROR)

    def test_cli_unreachable_exits_3(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        dead = f"http://127.0.0.1:{s.getsockname()[1]}"
        s.close()
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(["--url", dead, "feedback", RID, "--correct"]), cli.CANNOT_JUDGE)

    def test_self_hosted_404_explains(self):
        with mock.patch("ekbasis.client.time.sleep"):
            with self.assertRaises(FeedbackRejected) as e:
                Ekbasis(url=self.url + "/nope").feedback("correct", request_id=RID)
        self.assertEqual(e.exception.status, 404)
        self.assertIn("hosted-API feature", str(e.exception))


if __name__ == "__main__":
    unittest.main()
