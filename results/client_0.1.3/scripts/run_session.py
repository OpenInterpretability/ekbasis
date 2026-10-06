"""One agent session (see ../SPEC.md): fresh APFS clone of the task's template, claude -p in the sandbox with the
wrapper hook (arm H calls ekbasis, arm C does not), ledger entry, completion check on a copy, preservation.

usage: python3 run_session.py <task> <H|C> <sid> [cap] [model]
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time

from common import (CLAUDE, EKB013_PY as EKB_PY, HOME, SESSION_CAP, W, base_env, clone_tree, d, git, ledger_add,
                    read_jsonl)
import prepare
import tasks as T
import truth

SESSION_TIMEOUT = 1500
TOOLS = "Bash,Read,Edit,Write"   # the core coding tools; the rest of this build's tools stay off
PROJECT_KEY = os.environ.get("RT_PRIVATE_DIR", "/private/tmp/claude-coordinator")  # the coordinating session's own task outputs

DENY_READ = ["/Volumes", f"{HOME}/.ssh", f"{HOME}/.config", f"{HOME}/.aws", f"{HOME}/.gnupg", f"{HOME}/.docker",
             f"{HOME}/.kube", f"{HOME}/Documents", f"{HOME}/Desktop", f"{HOME}/Downloads", f"{HOME}/Library/Mail",
             f"{HOME}/Library/Messages", f"{HOME}/Library/Safari", f"{HOME}/Library/Application Support/BraveSoftware",
             f"{HOME}/Library/Application Support/Google", f"{HOME}/Library/Application Support/Firefox",
             f"{HOME}/.claude/projects", f"{HOME}/.claude/jobs", PROJECT_KEY]
DENY_READ_FILES = [f"{HOME}/.netrc", f"{HOME}/.zshrc", f"{HOME}/.zshenv", f"{HOME}/.zprofile", f"{HOME}/.zsh_history",
                   f"{HOME}/.bash_history", f"{HOME}/.bashrc", f"{HOME}/.bash_profile", f"{HOME}/.profile",
                   f"{HOME}/.gitconfig", f"{HOME}/.git-credentials", f"{HOME}/.npmrc", f"{HOME}/.pypirc"]


def q(p):
    return '"' + p.replace("\\", "\\\\").replace('"', '\\"') + '"'


def agent_profile() -> str:
    path = d("bin", "agent.sb")
    rules = ["(version 1)", "(allow default)", "(deny file-write*)",
             "(allow file-write*", f"  (subpath {q(W)})", '  (subpath "/private/tmp")',
             '  (subpath "/private/var/folders")', '  (subpath "/dev")', f"  (subpath {q(HOME + '/.claude')})",
             f'  (regex #"^{HOME}/\\.claude\\.json")', f"  (subpath {q(HOME + '/Library/Caches')}))",
             "(deny file-read* file-write*"]
    rules += [f"  (subpath {q(p)})" for p in DENY_READ] + [f"  (literal {q(p)})" for p in DENY_READ_FILES]
    rules[-1] += ")"
    with open(path, "w") as fh:
        fh.write("\n".join(rules) + "\n")
    return path


def install_bin():
    here = os.path.dirname(os.path.abspath(__file__))
    shutil.copy(os.path.join(here, "wrapper.py"), d("bin", "wrapper_013.py"))


def settings(sid, arm) -> str:
    cmd = lambda phase: f"'{EKB_PY}' '{d('bin', 'wrapper_013.py')}' {phase} {sid} {arm}"
    s = {"hooks": {
        "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": cmd("pre"), "timeout": 90}]}],
        "PostToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": cmd("post"), "timeout": 90}]}],
        "PostToolUseFailure": [{"matcher": "Bash", "hooks": [{"type": "command", "command": cmd("post"),
                                                              "timeout": 90}]}]}}
    path = d("cfg", f"{sid}.json")
    with open(path, "w") as fh:
        json.dump(s, fh)
    return path


def result_event(stream_path):
    res, model = None, None
    for ev in read_jsonl_safe(stream_path):
        if ev.get("type") == "result":
            res = ev
        if ev.get("type") == "system" and ev.get("subtype") == "init":
            model = ev.get("model")
    return res, model


def read_jsonl_safe(path):
    out = []
    if os.path.exists(path):
        with open(path) as fh:
            for line in fh:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    pass
    return out


def run_session(task_id, arm, sid, cap=SESSION_CAP, model="sonnet") -> dict:
    task = T.BY_ID[task_id]
    start = json.load(open(d("templates", f"{task_id}.start.json")))
    sdir, logs = d("s", sid), d("logs", sid)
    for p in (sdir, logs, d("snaps", sid)):
        if os.path.exists(p):
            raise RuntimeError(f"{p} exists: a session id is used once")
    clone_tree(d("templates", task_id), sdir)
    os.makedirs(logs)
    os.makedirs(d("snaps", sid))
    env = base_env(sid, python=task.python)
    git(os.path.join(sdir, "repo"), "remote", "set-url", "origin", os.path.join(sdir, "remote.git"), env=env)
    if task.python:
        prepare.make_venv(sid, env)
    cfg = settings(sid, arm)
    cmd = ["timeout", str(SESSION_TIMEOUT), "sandbox-exec", "-f", d("bin", "agent.sb"), CLAUDE, "-p", task.prompt,
           "--model", model, "--permission-mode", "bypassPermissions", "--setting-sources", "project,local",
           "--settings", cfg, "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
           "--tools", TOOLS, "--no-session-persistence", "--output-format", "stream-json", "--verbose",
           "--max-budget-usd", f"{cap:.2f}"]
    t0 = time.time()
    with open(os.path.join(logs, "stream.jsonl"), "w") as out, open(os.path.join(logs, "claude.err"), "w") as err:
        p = subprocess.run(cmd, cwd=os.path.join(sdir, "repo"), env=env, stdin=subprocess.DEVNULL, stdout=out,
                           stderr=err)
    wall = time.time() - t0
    res, model_id = result_event(os.path.join(logs, "stream.jsonl"))
    cost = float(res["total_cost_usd"]) if res and res.get("total_cost_usd") is not None else cap
    ledger_add({"kind": "session", "sid": sid, "task": task_id, "arm": arm, "usd": cost,
                "from_result": res is not None, "cap": cap, "model": model_id, "exit": p.returncode,
                "wall": round(wall, 1)})
    wc = T.work_copy(sdir)
    try:
        chk = task.check(wc, env, sid, start)
    except Exception as e:  # noqa: BLE001 — a crashed check is a fact to report, not a crash of the study
        chk = {"done": False, "check_error": f"{type(e).__name__}: {e}"}
    shutil.rmtree(wc, ignore_errors=True)
    pres = truth.preserved(sdir, start["U0"], extra_dirs=[d("tmp", sid)])
    c0_left = set(start["C0"]) - (truth.reachable(os.path.join(sdir, "repo")) |
                                  truth.reachable(os.path.join(sdir, "remote.git")))
    events = read_jsonl(os.path.join(logs, "events.jsonl"))
    out = {"sid": sid, "task": task_id, "arm": arm, "model": model_id, "exit": p.returncode, "wall": round(wall, 1),
           "usd": cost, "cost_from_result": res is not None,
           "result": {k: res.get(k) for k in ("subtype", "is_error", "num_turns", "duration_ms", "duration_api_ms",
                                              "total_cost_usd", "usage", "modelUsage", "permission_denials", "result")}
           if res else None,
           "check": chk, "preserved": pres, "c0_commits_lost": sorted(c0_left),
           "bash_calls": sum(1 for e in events if e.get("phase") == "pre"),
           "asks": sum(1 for e in events if (e.get("ekbasis") or {}).get("decision") in ("ask", "deny"))}
    with open(os.path.join(logs, "session.json"), "w") as fh:
        json.dump(out, fh, indent=1)
    return out


def main():
    task_id, arm, sid = sys.argv[1], sys.argv[2], sys.argv[3]
    cap = float(sys.argv[4]) if len(sys.argv) > 4 else SESSION_CAP
    model = sys.argv[5] if len(sys.argv) > 5 else "sonnet"
    install_bin()
    agent_profile()
    out = run_session(task_id, arm, sid, cap, model)
    print(json.dumps({k: out[k] for k in ("sid", "task", "arm", "model", "usd", "wall", "bash_calls", "asks")}))
    print(json.dumps(out["check"])[:600])
    print("preserved:", json.dumps(out["preserved"])[:300])


if __name__ == "__main__":
    main()
