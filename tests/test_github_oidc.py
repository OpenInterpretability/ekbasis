"""The migration guard Action's OIDC step (actions/migration-guard/github_oidc.py): with no API key, a public
repository's workflow requests a GitHub OIDC token for the audience openinterp.org and sends it instead. Offline: a
local fake of GitHub's token endpoint. Checks the audience and bearer sent, that the token goes only to the hosted API,
and that every failure exits 1 without printing a token."""
import http.server
import importlib.util
import io
import json
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

_spec = importlib.util.spec_from_file_location(
    "github_oidc", Path(__file__).resolve().parents[1] / "actions" / "migration-guard" / "github_oidc.py")
oidc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(oidc)

TOKEN = "eyJhbGciOiJSUzI1NiJ9.eyJpc3MiOiJ4In0.c2ln"


class GitHub(http.server.BaseHTTPRequestHandler):
    seen: list = []
    status = 200
    body: dict = {"value": TOKEN}

    def do_GET(self):  # noqa: N802
        GitHub.seen.append((self.path, self.headers.get("Authorization")))
        b = json.dumps(GitHub.body).encode()
        self.send_response(GitHub.status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b)

    def log_message(self, *a):
        pass


class OidcTest(unittest.TestCase):
    def setUp(self):
        GitHub.seen, GitHub.status, GitHub.body = [], 200, {"value": TOKEN}
        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), GitHub)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.env = {
            "ACTIONS_ID_TOKEN_REQUEST_URL": f"http://127.0.0.1:{self.srv.server_address[1]}/token?api-version=2.0",
            "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "runner-secret",
        }

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()

    def run_main(self, api_url="https://openinterp.org/api/v1", env=None):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict("os.environ", self.env if env is None else env, clear=True), \
                redirect_stdout(out), redirect_stderr(err):
            rc = oidc.main(["--api-url", api_url])
        return rc, out.getvalue(), err.getvalue()

    def test_token_for_the_hosted_api(self):
        rc, out, err = self.run_main()
        self.assertEqual((rc, out), (0, TOKEN))
        self.assertEqual(err, "")
        path, auth = GitHub.seen[0]
        self.assertEqual(path, "/token?api-version=2.0&audience=openinterp.org")
        self.assertEqual(auth, "bearer runner-secret")

    def test_never_sent_to_another_server(self):
        for url in ("https://example.com/api/v1", "http://openinterp.org/api/v1", "https://openinterp.org.evil.io/v1",
                    "http://127.0.0.1:8000"):
            rc, out, err = self.run_main(url)
            self.assertEqual((rc, out), (1, ""), url)
            self.assertIn("not the hosted API", err)
        self.assertEqual(GitHub.seen, [])

    def test_no_id_token_permission(self):
        rc, out, err = self.run_main(env={})
        self.assertEqual((rc, out), (1, ""))
        self.assertIn("id-token: write", err)

    def test_failures_exit_1_without_a_token(self):
        for status, body in ((403, {"message": "no"}), (200, {}), (200, {"value": "not-a-jwt"})):
            GitHub.status, GitHub.body = status, body
            rc, out, err = self.run_main()
            self.assertEqual((rc, out), (1, ""), (status, body))
            self.assertNotIn("runner-secret", err)
        self.srv.shutdown()
        self.srv.server_close()
        rc, out, err = self.run_main()
        self.assertEqual((rc, out), (1, ""))
        self.assertIn("could not request", err)
        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), GitHub)  # for tearDown
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def test_action_uses_it_only_without_a_key(self):
        y = (Path(__file__).resolve().parents[1] / "actions" / "migration-guard" / "action.yml").read_text()
        self.assertIn('if [ -z "$API_KEY" ]', y)
        self.assertIn("github_oidc.py\" --api-url \"$EKBASIS_URL\"", y)
        self.assertIn("::add-mask::$API_KEY", y)
        self.assertIn("required: false", y.split("api-url:")[0])


if __name__ == "__main__":
    unittest.main()
