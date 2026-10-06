"""WS-AL service between the stage and Ekbasis (released client and prompts, shared API through the AL tunnel).
POST /foresee {"rules", "state", "action", "questions": [{"key", "text", "options"}]} -> answers, as WS-X's foresee_x.py
POST /choose  {"rules", "state", "goal", "options": [label]} -> {"value", "confidence", "probabilities": {label: p}, "ms"}
     one typed choice: "The user's task: ... Which of these should be clicked next to accomplish the task?" over the
     actions on the screen (groups of 20, winners compared again, for longer lists)
POST /ask     {"prompt_rules", "state", "actions": [..], "questions": {key: question}} -> raw answers (the ledger tracker)
GET /health
env: EKBASIS_URL (default http://127.0.0.1:18551), PORT (default 8771), LOG (calls log)."""
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path[:0] = [p for p in [os.environ.get("EKBASIS_CLIENT_SRC")] if p]
from ekbasis import prompts as P  # noqa: E402
from ekbasis.client import Ekbasis  # noqa: E402

client = Ekbasis(url=os.environ.get("EKBASIS_URL", "http://127.0.0.1:18551"))
HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.environ.get("LOG", os.path.join(HERE, "calls.jsonl"))
CLICK = "Click one of the items on this screen."


def log(kind, req, out):
    with open(LOG, "a") as f:
        f.write(json.dumps({"time": time.time(), "kind": kind, "request": req, "response": out}) + "\n")


def foresee(req):
    qs = {q["key"]: P.choice(q["text"], [str(o) for o in q["options"]]) for q in req["questions"]}
    t0 = time.time()
    ans = client.ask(P.world_state(req["rules"], req["state"], [req["action"]]), qs)
    out = {"answers": {k: {"value": str(a.value), "confidence": round(a.confidence, 4),
                           "probabilities": {o: round(p, 4) for o, p in a.probabilities.items()}} for k, a in ans.items()},
           "ms": round(1000 * (time.time() - t0), 1)}
    log("foresee", req, out)
    return out


def choose_group(rules, state, goal, options):
    q = P.choice(f"The user's task: \"{goal}\". Which of these should be clicked next to accomplish the task?", options)
    a = client.ask(P.world_state(rules, state, [CLICK]), {"pick": q})["pick"]
    return a


def choose(req):
    """One choice over up to 20 options; more: groups of 20, then one choice over the group winners (the final
    probabilities are the final round's; options that lost in a group keep 0)."""
    t0 = time.time()
    opts = list(dict.fromkeys(req["options"]))
    if len(opts) == 1:
        probs = {opts[0]: 1.0}
    elif len(opts) <= 20:
        probs = dict(choose_group(req["rules"], req["state"], req["goal"], opts).probabilities)
    else:
        winners = [str(choose_group(req["rules"], req["state"], req["goal"], opts[i:i + 20]).value) if len(opts[i:i + 20]) > 1
                   else opts[i] for i in range(0, len(opts), 20)]
        probs = {o: 0.0 for o in opts}
        probs.update(choose_group(req["rules"], req["state"], req["goal"], winners).probabilities if len(winners) > 1 else {winners[0]: 1.0})
    top = max(probs, key=probs.get)
    out = {"value": top, "confidence": round(probs[top], 4), "probabilities": {o: round(p, 4) for o, p in probs.items()},
           "ms": round(1000 * (time.time() - t0), 1)}
    log("choose", req, out)
    return out


def ask(req):
    t0 = time.time()
    qs = {k: (P.choice(q["text"], q["options"]) if q.get("options") else P.yes_no(q["text"])) for k, q in req["questions"].items()}
    ans = client.ask(P.world_state(req["rules"], req["state"], req["actions"]), qs)
    out = {"answers": {k: {"value": str(a.value), "confidence": round(a.confidence, 4),
                           "probabilities": {o: round(p, 4) for o, p in a.probabilities.items()}} for k, a in ans.items()},
           "ms": round(1000 * (time.time() - t0), 1)}
    log("ask", req, out)
    return out


ROUTES = {"/foresee": foresee, "/choose": choose, "/ask": ask}


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
        fn = ROUTES.get(self.path)
        if not fn:
            return self._send(404, {"error": "not found"})
        try:
            req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            self._send(200, fn(req))
        except Exception as e:  # noqa: BLE001
            self._send(500, {"error": f"{type(e).__name__}: {e}"})

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8771"))
    print(f"foresee_al on 127.0.0.1:{port} -> {os.environ.get('EKBASIS_URL', 'http://127.0.0.1:18551')}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
