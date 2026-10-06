"""ORACLE-LLM for the WS-X controls: the same foresee request (rules, state, action, typed questions with options) answered by
Claude Sonnet via `claude -p` (no tools, no user settings), one call per foresee, priced and timed (wall time includes the
CLI start). Same response shape as foresee_x.py. Every call is appended to oracle_calls.jsonl.
    PORT=8762 python3 oracle_llm.py"""
import json
import os
import subprocess
import tempfile
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.environ.get("ORACLE_LOG", os.path.join(HERE, "oracle_calls.jsonl"))


def ask_claude(req):
    qs = "\n".join(f"- {q['key']}: {q['text']} Options: {json.dumps([str(o) for o in q['options']])}" for q in req["questions"])
    prompt = ("Predict what an action does in an app. Read the app's rules, the current state and the action.\n"
              f"Rules: {req['rules']}\nState: {req['state']}\nAction: {req['action']}\n"
              "For each question choose exactly one of its options, copied verbatim, and give your confidence (0-100) that it is "
              "right. Reply with only a JSON object, no other text: {\"<key>\": {\"option\": \"<option>\", \"confidence\": <0-100>}}.\n"
              f"Questions:\n{qs}")
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")}
    t0 = time.time()
    with tempfile.TemporaryDirectory() as d:
        p = subprocess.run(["claude", "-p", prompt, "--model", "sonnet", "--tools", "", "--setting-sources", "project,local",
                            "--output-format", "json", "--no-session-persistence"], cwd=d, env=env, capture_output=True, text=True, timeout=300)
    ms = 1000 * (time.time() - t0)
    j = json.loads(p.stdout)
    txt = j.get("result", "")
    a, b = txt.find("{"), txt.rfind("}")
    got = json.loads(txt[a:b + 1]) if a >= 0 else {}
    answers = {}
    for q in req["questions"]:
        g = got.get(q["key"], {})
        opt = str(g.get("option", ""))
        opts = [str(o) for o in q["options"]]
        if opt not in opts:  # tolerate case and spacing, never invent an option
            low = {o.lower().strip(): o for o in opts}
            opt = low.get(opt.lower().strip(), opts[0])
        conf = max(0.0, min(1.0, float(g.get("confidence", 50)) / 100))
        answers[q["key"]] = {"value": opt, "confidence": round(conf, 4), "probabilities": {opt: round(conf, 4)}}
    return {"answers": answers, "ms": round(ms, 1), "cost_usd": j.get("total_cost_usd") or 0.0}


class H(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._send(200, {"ok": True, "oracle": "claude sonnet via claude -p"})

    def do_POST(self):
        try:
            req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            out = ask_claude(req)
            with open(LOG, "a") as f:
                f.write(json.dumps({"time": time.time(), "request": req, "response": out}) + "\n")
            self._send(200, out)
        except Exception as e:  # noqa: BLE001
            self._send(500, {"error": f"{type(e).__name__}: {e}"})

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", int(os.environ.get("PORT", "8762"))), H).serve_forever()
