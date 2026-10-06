"""Foresight for the demo apps: an app's rules, its current state and the action an agent is about to take go to Ekbasis
through the released client and prompts, the same code path as `ekbasis predict --options ...` (the path the app trials
used). Nothing here decides anything; it only asks the model and returns its answers with their confidence.

POST /foresee {"rules": str, "state": str, "action": str, "questions": [{"key": str, "text": str, "options": [str]}]}
  -> {"answers": {key: {"value": str, "confidence": float, "probabilities": {option: p}}}, "ms": float}
GET /health -> the model server's health.
env: EKBASIS_URL (default http://127.0.0.1:18541, the tunnel to the demo replica), PORT (default 8760)."""
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path[:0] = [p for p in [os.environ.get("EKBASIS_CLIENT_SRC")] if p]
from ekbasis import prompts as P  # noqa: E402
from ekbasis.client import Ekbasis  # noqa: E402

client = Ekbasis(url=os.environ.get("EKBASIS_URL", "http://127.0.0.1:18541"))
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sessions", "foresee_calls.jsonl")


def foresee(req: dict) -> dict:
    qs = {q["key"]: P.choice(q["text"], [str(o) for o in q["options"]]) for q in req["questions"]}
    t0 = time.time()
    ans = client.ask(P.world_state(req["rules"], req["state"], [req["action"]]), qs)
    ms = 1000 * (time.time() - t0)
    out = {"answers": {k: {"value": str(a.value), "confidence": round(a.confidence, 4),
                           "probabilities": {o: round(p, 4) for o, p in a.probabilities.items()}} for k, a in ans.items()},
           "ms": round(ms, 1)}
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a") as f:  # every call, so any frame of any video can be traced to the model's own answer
        f.write(json.dumps({"time": time.time(), "request": req, "response": out}) + "\n")
    return out


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            try:
                self._send(200, client.health())
            except Exception as e:  # noqa: BLE001
                self._send(502, {"error": str(e)})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/foresee":
            return self._send(404, {"error": "not found"})
        try:
            req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            self._send(200, foresee(req))
        except Exception as e:  # noqa: BLE001
            self._send(500, {"error": f"{type(e).__name__}: {e}"})

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8760"))
    print(f"foresee on 127.0.0.1:{port} -> {client.url if hasattr(client, 'url') else ''}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
