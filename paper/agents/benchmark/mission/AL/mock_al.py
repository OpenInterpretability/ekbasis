"""Mock Ekbasis for plumbing tests only (validation): /foresee, /choose and /ask answer with the first option."""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class H(BaseHTTPRequestHandler):
    def _send(self, obj):
        b = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        self._send({"ok": True, "mock": True})

    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        if self.path == "/choose":
            o = req["options"]
            return self._send({"value": o[0], "confidence": 1 / len(o), "probabilities": {x: 1 / len(o) for x in o}, "ms": 1})
        qs = req["questions"]
        items = qs.items() if isinstance(qs, dict) else [(q["key"], q) for q in qs]
        ans = {}
        for k, q in items:
            opts = q.get("options") or ["yes", "no"]
            ans[k] = {"value": str(opts[0]), "confidence": 0.9, "probabilities": {str(opts[0]): 0.9}}
        self._send({"answers": ans, "ms": 1})

    def log_message(self, *a):
        pass


ThreadingHTTPServer(("127.0.0.1", int(os.environ.get("PORT", "8798"))), H).serve_forever()
