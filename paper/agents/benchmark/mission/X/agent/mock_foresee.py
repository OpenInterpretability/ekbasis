"""A stand-in for foresee.py used only to test the study's plumbing without the model: it answers every question with
its first option at 0.9. Never used for a scored run.  PORT (default 8799)."""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class H(BaseHTTPRequestHandler):
    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        out = {"answers": {q["key"]: {"value": str(q["options"][0]), "confidence": 0.9,
                                      "probabilities": {str(o): (0.9 if i == 0 else 0.1 / max(1, len(q["options"]) - 1)) for i, o in enumerate(q["options"])}}
                           for q in req["questions"]}, "ms": 1.0}
        body = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"ok": true, "mock": true}')

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", int(os.environ.get("PORT", "8799"))), H).serve_forever()
