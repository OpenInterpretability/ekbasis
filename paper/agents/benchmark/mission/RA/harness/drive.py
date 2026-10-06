"""Scripted driver for stage_real.mjs (no agent): start a stage for a run context, call its ops, find elements by a pattern
in `look`, and stop it. Used to test the adapters and to execute every task's harm and safe paths on the real app.
    from drive import Stage
    with Stage(run_ctx_path, mode="model") as st: st.click(r'button "Create Repository"')"""
import json
import os
import re
import socket
import subprocess
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))


def free_port():
    for _ in range(200):
        s = socket.socket()
        try:
            s.bind(("127.0.0.1", 0))
            p = s.getsockname()[1]
        finally:
            s.close()
        if 47100 <= p <= 47900:
            continue
        return p
    raise RuntimeError("no free port")


class Stage:
    def __init__(self, run_path, mode="none", port=None, log=None, env=None):
        self.port = port or free_port()
        self.log = log or os.path.join(HERE, "..", "logs", "drive_stage.log")
        self.proc = subprocess.Popen(["node", os.path.join(HERE, "stage_real.mjs"), "--run", run_path, "--port", str(self.port), "--mode", mode],
                                     cwd=os.path.join(HERE, ".."), stdout=open(self.log, "a"), stderr=subprocess.STDOUT,
                                     env=dict(os.environ, **(env or {})))
        for _ in range(120):
            try:
                self.op("look")
                break
            except Exception:  # noqa: BLE001
                time.sleep(0.5)
        else:
            raise RuntimeError("stage did not start")
        self.last = ""

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.quit()

    def op(self, name, timeout=120, **params):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/{name}", data=json.dumps(params).encode(),
                                     headers={"Content-Type": "application/json"})
        j = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
        if "error" in j:
            raise RuntimeError(j["error"])
        return j.get("result")

    def look(self):
        self.last = self.op("look")
        return self.last

    def ref(self, pattern, text=None, nth=0, after=None):
        """The [n] of the nth line of `look` matching `pattern` (regex), optionally only after a line matching `after`."""
        t = text if text is not None else self.look()
        lines = t.splitlines()
        if after:
            idx = next((i for i, l in enumerate(lines) if re.search(after, l)), None)
            if idx is None:
                raise LookupError(f"no line matches {after!r}")
            lines = lines[idx:]
        hits = [l for l in lines if re.search(pattern, l) and re.match(r"\[\d+\]", l)]
        if len(hits) <= nth:
            raise LookupError(f"no element matches {pattern!r}:\n" + t[:3000])
        return re.match(r"\[(\d+)\]", hits[nth]).group(1)

    def click(self, pattern, **kw):
        self.last = self.op("click", element=self.ref(pattern, **kw))
        return self.last

    def type(self, pattern, text, **kw):
        return self.op("type_text", element=self.ref(pattern, **kw), text=text)

    def foresee(self, pattern, **kw):
        return self.op("foresee", element=self.ref(pattern, **kw))

    def goto(self, url):
        self.last = self.op("goto", url=url)
        return self.last

    def press(self, key):
        self.last = self.op("press_key", key=key)
        return self.last

    def select(self, pattern, option, **kw):
        self.last = self.op("select_option", element=self.ref(pattern, **kw), option=option)
        return self.last

    def save(self, out):
        u = f"http://127.0.0.1:{self.port}/save?out={urllib.parse.quote(out)}"
        return json.loads(urllib.request.urlopen(urllib.request.Request(u, data=b"{}", headers={"Content-Type": "application/json"}), timeout=60).read())

    def quit(self):
        try:
            urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{self.port}/quit", data=b"{}"), timeout=10)
        except Exception:  # noqa: BLE001
            pass
        try:
            self.proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self.proc.kill()


import urllib.parse  # noqa: E402
