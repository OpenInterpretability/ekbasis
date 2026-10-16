"""Shared pieces of the WS-F factory: the row schema the trainer reads (train_conseq.py), typed questions as the client
builds them (ekbasis.prompts), the two prompt layouts, the sandbox runner, and small helpers."""
from __future__ import annotations

import hashlib
import json
import os
import pwd
import random
import shutil
import subprocess

WORLD_NOTE = "The questions are about the state after all these actions."
CMD_NOTE = "The questions are about the state after all these commands."
NOBODY = 65534
BOX_ROOT = "/tmp/rxF/boxes"


def yes_no(instructions: str) -> dict:
    return {"type": "noul", "instructions": instructions}


def choice(instructions: str, options) -> dict:
    return {"type": "choice", "instructions": instructions, "criteria": {str(o): str(o) for o in options}}


def numbered(lines) -> str:
    out = []
    for i, x in enumerate(lines):
        body = str(x).replace("\n", "\n   ")
        out.append(f"{i + 1}. {body}")
    return "\n".join(out)


def world_floor(rules: str, state: str, actions) -> str:
    return f"{rules}\n\nCurrent state:\n{state}\n\nActions, in order:\n{numbered(actions)}\n\n{WORLD_NOTE}"


def world_ceiling(rules: str, after: str, what: str) -> str:
    return f"{rules}\n\nState after the actions:\n{after}\n\nThis is the state after all the actions.\nWhat happened: {what}"


def cmd_floor(rules: str, state: str, cmds) -> str:
    return f"{rules}\n\nState before:\n{state}\n\nCommands, in order:\n{numbered(cmds)}\n\n{CMD_NOTE}"


def cmd_ceiling(rules: str, cmds, after: str, what: str) -> str:
    return f"{rules}\n\nCommands that were run:\n{numbered(cmds)}\n\nState after the commands:\n{after}\nWhat happened: {what}"


def row(*, world, family, template, qtype, steps, question, gold, gold0, known0, floor, ceiling, rid, twin=None,
        layout=None, face=None, struct=None) -> dict:
    """One training row in the V44 schema (+ factory metadata the trainer ignores)."""
    if question["type"] == "choice":
        assert str(gold) in question["criteria"], (rid, gold, list(question["criteria"]))
        gold = str(gold)
    else:
        gold = bool(gold)
    r = {"kind": "floorRX", "world": world, "family": family, "template": template, "qtype": qtype, "steps": steps,
         "question": question, "gold": gold, "gold0": gold0, "known0": bool(known0), "floor": floor, "ceiling": ceiling,
         "id": rid}
    if twin is not None:
        r["twin"] = twin
    if layout is not None:
        r["layout"] = layout
    if face is not None:
        r["face"] = face  # the face-value predictor's answer (quality metric only)
    if struct is not None:
        r["struct"] = struct
    return r


def stable_seed(*parts) -> int:
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:12], 16)


def make_box(tag: str) -> str:
    """A fresh throwaway folder the unprivileged user owns."""
    os.makedirs(BOX_ROOT, mode=0o711, exist_ok=True)
    os.chmod("/tmp/rxF", 0o711) if os.path.isdir("/tmp/rxF") else None
    path = os.path.join(BOX_ROOT, tag)
    if os.path.exists(path):
        shutil.rmtree(path)
    os.makedirs(path)
    return path


def chown_tree(path: str, uid: int = NOBODY):
    for root, dirs, files in os.walk(path):
        os.lchown(root, uid, uid)
        for n in dirs + files:
            os.lchown(os.path.join(root, n), uid, uid)


def remove_box(path: str):
    if path.startswith(BOX_ROOT + "/") and os.path.isdir(path):
        subprocess.run(["chmod", "-R", "u+rwx", path], check=False)
        shutil.rmtree(path, ignore_errors=True)


def run_unprivileged(argv, cwd: str, env_extra=None, timeout: int = 8, stdin_text: str | None = None,
                     cpu: int = 5, fsize: int = 10_000_000, nproc: int = 400):
    """Run argv as `nobody` with an empty environment, HOME = cwd, CPU/file/process limits and a wall timeout."""
    env = {"HOME": cwd, "PATH": "/usr/bin:/bin", "LC_ALL": "C.UTF-8", "LANG": "C.UTF-8", "PYTHONHASHSEED": "0"}
    if env_extra:
        env.update(env_extra)
    pre = ["prlimit", f"--cpu={cpu}", f"--fsize={fsize}", f"--nproc={nproc}", "--",
           "setpriv", f"--reuid={NOBODY}", f"--regid={NOBODY}", "--clear-groups", "--"]
    envargs = ["env", "-i"] + [f"{k}={v}" for k, v in env.items()]
    try:
        p = subprocess.run(["timeout", "-k", "2", str(timeout)] + pre + envargs + list(argv), cwd=cwd,
                           input=stdin_text, capture_output=True, text=True, errors="replace")
        return p.returncode, p.stdout, p.stderr
    except Exception as e:  # noqa: BLE001
        return -1, "", repr(e)


def write_jsonl(path: str, rows):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def pick(rng: random.Random, seq, k=None):
    seq = list(seq)
    if k is None:
        return rng.choice(seq)
    return rng.sample(seq, min(k, len(seq)))
