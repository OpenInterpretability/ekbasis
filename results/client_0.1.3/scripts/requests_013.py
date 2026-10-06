"""Server accounting for the 0.1.3 re-run (written after the freeze; it measures nothing about the guard): how many
vLLM requests my own hook calls sent to :8542. The vLLM counter goes up once per question (the pilot: 20 questions,
20 requests). Each call's before-state is restored at its path and both hooks run in process with a client that
counts questions: arm H's live call (0.1.3), and the offline 0.1.3 and 0.1.2 runs of every call.

usage: python3.12 requests_013.py      (prints the counts and the server's delta; writes results_013/requests.json)
"""
from __future__ import annotations

import importlib
import importlib.util
import io
import json
import os
import shutil
import sys
from contextlib import redirect_stderr, redirect_stdout
from types import SimpleNamespace
from unittest import mock

from common import RESULTS, W, base_env, d, read_jsonl
import replay as RP
import tasks as T

PKG012 = os.path.join(W, "ekbasis_venv/lib/python3.12/site-packages/ekbasis")
PKG013 = os.path.join(W, "ekbasis013_venv/lib/python3.12/site-packages/ekbasis")


def load_hook(name, path):
    spec = importlib.util.spec_from_file_location(name, os.path.join(path, "__init__.py"),
                                                  submodule_search_locations=[path])
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return importlib.import_module(name + ".claude_code_hook")


class Counter:
    def __init__(self):
        self.questions = 0

    def ask(self, state, questions, read_once=False, images=None):
        self.questions += len(questions)
        return {k: SimpleNamespace(value=False if q.get("type") == "noul" else sorted(q.get("criteria") or ["x"])[0],
                                   confidence=0.99, probabilities={}, p_yes=0.0) for k, q in questions.items()}


def count(H, inp, env):
    c = Counter()
    full = {**env, "EKBASIS_SHELL_GUARD": "1", "EKBASIS_URL": "http://127.0.0.1:9", "EKBASIS_HOOK_DEADLINE": "60"}
    with mock.patch.dict(os.environ, full, clear=True), mock.patch.object(H, "Ekbasis", lambda **k: c), \
            mock.patch("sys.stdin", io.StringIO(json.dumps(inp))), redirect_stdout(io.StringIO()), \
            redirect_stderr(io.StringIO()):
        H.main()
    return c.questions


def main():
    H12, H13 = load_hook("ekb012", PKG012), load_hook("ekb013", PKG013)
    tot = {"live013": 0, "shadow013": 0, "shadow012": 0, "calls": 0}
    for sub, prefix in (("sessions", "s"), ("sessions_explore", "y")):
        root = os.path.join(RESULTS, sub)
        for sid in sorted(os.listdir(root)) if os.path.isdir(root) else []:
            if not sid.startswith(prefix):
                continue
            sess = json.load(open(os.path.join(root, sid, "session.json")))
            env = base_env(sid, python=T.BY_ID[sess["task"]].python)
            inputs = {e["tool_use_id"]: e.get("input") for e in read_jsonl(os.path.join(root, sid, "events.jsonl"))
                      if e.get("phase") == "pre"}
            for c in read_jsonl(os.path.join(root, sid, "calls.jsonl")):
                inp = inputs.get(c["tool_use_id"])
                if not inp or not c.get("snap_ok"):
                    continue
                RP.restore(sid, d("snaps", sid, f"{c['tool_use_id']}.pre"))
                try:
                    q13, q12 = count(H13, inp, env), count(H12, inp, env)
                finally:
                    shutil.rmtree(d("s", sid), ignore_errors=True)
                tot["calls"] += 1
                tot["shadow013"] += q13 if c.get("shadow") else 0
                tot["shadow012"] += q12 if c.get("shadow012") else 0
                tot["live013"] += q13 if c["arm"] == "H" and (c.get("ekbasis") or {}).get("decision") not in (None,) else 0
    tot["mine"] = tot["live013"] + tot["shadow013"] + tot["shadow012"]
    srv = read_jsonl(os.path.join(RESULTS, "server_log.jsonl"))
    before = next((r for r in srv if r["label"] == "before_study"), None)
    after = next((r for r in reversed(srv) if r["label"] == "after_study"), None)
    if before and after:
        for port in ("30191", "30193"):
            tot[f"delta_{port}"] = after["servers"].get(port, {}).get("requests", 0) - \
                before["servers"].get(port, {}).get("requests", 0)
        tot["others_on_8542"] = tot["delta_30191"] - tot["mine"]
        tot["window"] = [before["t"], after["t"]]
    with open(os.path.join(RESULTS, "requests.json"), "w") as fh:
        json.dump(tot, fh, indent=1)
    print(json.dumps(tot, indent=1))


if __name__ == "__main__":
    main()
