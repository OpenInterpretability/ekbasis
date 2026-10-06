"""Truth for every Bash call of a session (see ../SPEC.md, "Truth"), the replay check, and the shadow runs.

For each call: observed truth from the snapshots before/after when it ran; replay truth when it did not run (the hook
stopped it) and for a seeded 25% of the calls that ran. Shadow: the published hook run offline on each call against
its before-snapshot restored at the original path (arm C: the guard's verdict on calls no guard influenced; arm H:
agreement with the live verdict).

usage: python3 replay.py <sid> [<sid> ...]     (after the session; writes W/logs/<sid>/calls.jsonl)
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

from common import (EKB013_HOOK, EKB_HOOK, REPLAY_SEED, REPLAY_SHARE, W, base_env, clone_tree, d, ekbasis_env,
                    read_jsonl)
from run_session import DENY_READ, DENY_READ_FILES, q
import tasks as T
import truth

REPLAY_TIMEOUT = 300


def replay_profile(sid) -> str:
    path = d("bin", f"replay_{sid}.sb")
    rules = ["(version 1)", "(allow default)", "(deny file-write*)", "(allow file-write*",
             f"  (subpath {q(d('s', sid))})", f"  (subpath {q(d('tmp', sid))})", f"  (subpath {q(d('cache'))})",
             '  (subpath "/private/var/folders")', '  (subpath "/dev"))', "(deny file-read* file-write*"]
    rules += [f"  (subpath {q(p)})" for p in DENY_READ] + [f"  (literal {q(p)})" for p in DENY_READ_FILES]
    rules[-1] += ")"
    with open(path, "w") as fh:
        fh.write("\n".join(rules) + "\n")
    return path


def sampled(sid, tid) -> bool:
    h = hashlib.sha256(f"{REPLAY_SEED}:{sid}:{tid}".encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF < REPLAY_SHARE


def calls(sid):
    events = read_jsonl(d("logs", sid, "events.jsonl"))
    sess = json.load(open(d("logs", sid, "session.json")))
    denied = {x.get("tool_use_id") for x in ((sess.get("result") or {}).get("permission_denials") or [])}
    pre = [e for e in events if e.get("phase") == "pre" and "snapshot" in e]
    post = {e["tool_use_id"]: e for e in events if e.get("phase") == "post"}
    out = []
    for e in sorted(pre, key=lambda x: x["t"]):
        tid = e["tool_use_id"]
        out.append({"sid": sid, "arm": e["arm"], "tool_use_id": tid, "t": e["t"], "command": e["command"],
                    "cwd": e["cwd"], "input": e.get("input"), "ekbasis": e.get("ekbasis"),
                    "snap_ok": e["snapshot"]["ok"] and (tid not in post or
                                                        post[tid].get("snapshot", {}).get("ok", False)),
                    "executed": tid in post and tid not in denied, "denied": tid in denied, "t_post": post.get(tid, {}).get("t"),
                    "response": post.get(tid, {}).get("response")})
    # calls whose before/after windows overlap another call's (parallel tool calls) are flagged for the report
    for c in out:
        c["overlap"] = any(o is not c and o["t"] < (c["t_post"] or c["t"]) and (o["t_post"] or o["t"]) > c["t"]
                           for o in out if c["executed"] and o["executed"])
    return out


def restore(sid, snap):
    sdir = d("s", sid)
    if os.path.exists(sdir):
        shutil.rmtree(sdir)
    clone_tree(snap, sdir)
    return sdir


def prelude() -> str:
    return d("bin", "cc_prelude.zsh")


def replay_call(sid, c, env, start):
    snap = d("snaps", sid, f"{c['tool_use_id']}.pre")
    sdir = restore(sid, snap)
    cwd = c["cwd"] if c["cwd"] and os.path.isdir(c["cwd"]) else os.path.join(sdir, "repo")
    t = time.monotonic()
    try:
        p = subprocess.run(["sandbox-exec", "-f", replay_profile(sid), "/bin/zsh", "-c",
                            'source "$RT_PRELUDE" >/dev/null 2>&1; eval "$RT_CMD"'],
                           cwd=cwd, env={**env, "RT_CMD": c["command"], "RT_PRELUDE": prelude()},
                           stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=REPLAY_TIMEOUT)
        code, tail = p.returncode, (p.stdout + p.stderr)[-600:]
    except subprocess.TimeoutExpired:
        code, tail = None, "replay timed out"
    secs = time.monotonic() - t
    tr = truth.transition(snap, sdir, start["U0"], start["C0"])
    shutil.rmtree(sdir, ignore_errors=True)
    return {**tr, "exit": code, "tail": tail, "secs": round(secs, 2)}


def shadow_call(sid, c, env, hook=EKB_HOOK):
    snap = d("snaps", sid, f"{c['tool_use_id']}.pre")
    sdir = restore(sid, snap)
    t = time.monotonic()
    try:
        p = subprocess.run(["sandbox-exec", "-f", replay_profile(sid), hook], input=json.dumps(c["input"]),
                           env=ekbasis_env(env), capture_output=True, text=True, timeout=60)
        out, code = p.stdout, p.returncode
    except subprocess.TimeoutExpired:
        out, code = "", None
    wall = time.monotonic() - t
    shutil.rmtree(sdir, ignore_errors=True)
    decision, reason = "allow", None
    if code is None:
        decision = "timeout"
    elif out.strip():
        try:
            h = json.loads(out)["hookSpecificOutput"]
            decision, reason = h.get("permissionDecision"), h.get("permissionDecisionReason")
        except (ValueError, KeyError, TypeError):
            decision = "unparsed"
    return {"decision": decision, "reason": reason, "wall": round(wall, 3), "exit": code}


def process(sid):
    sess = json.load(open(d("logs", sid, "session.json")))
    task = T.BY_ID[sess["task"]]
    start = json.load(open(d("templates", f"{sess['task']}.start.json")))
    env = base_env(sid, python=task.python)
    final = d("final", sid)
    if os.path.exists(d("s", sid)) and not os.path.exists(final):
        shutil.move(d("s", sid), final)
    out = []
    for c in calls(sid):
        rec = {k: c[k] for k in ("sid", "arm", "tool_use_id", "t", "command", "cwd", "executed", "denied", "snap_ok",
                                 "overlap")}
        rec["ekbasis"] = c["ekbasis"]
        if not c["snap_ok"]:
            rec["truth"] = None
        elif c["executed"]:
            rec["truth"] = truth.transition(d("snaps", sid, f"{c['tool_use_id']}.pre"),
                                            d("snaps", sid, f"{c['tool_use_id']}.post"), start["U0"], start["C0"])
            rec["truth_source"] = "observed"
            if sampled(sid, c["tool_use_id"]):
                rec["replay_check"] = replay_call(sid, c, env, start)
        else:
            rec["truth"] = replay_call(sid, c, env, start)
            rec["truth_source"] = "replay"
        if c["snap_ok"] and c["input"]:
            # both versions offline on the same before-state; the order is a seeded coin per call, so that the
            # server's prefix cache favours neither (latency is compared on each version's first-run calls)
            first013 = int(hashlib.sha256(f"order:{REPLAY_SEED}:{sid}:{c['tool_use_id']}".encode()).hexdigest()[:8],
                           16) % 2 == 0
            order = [("shadow", EKB013_HOOK), ("shadow012", EKB_HOOK)]
            for i, (key, hook) in enumerate(order if first013 else order[::-1]):
                rec[key] = {**shadow_call(sid, c, env, hook), "ran_first": i == 0}
        out.append(rec)
        print(f"{sid} {rec['tool_use_id'][-6:]} {rec.get('truth_source')} "
              f"{(rec['truth'] or {}).get('class')} live={(c['ekbasis'] or {}).get('decision')} "
              f"shadow013={(rec.get('shadow') or {}).get('decision')} shadow012={(rec.get('shadow012') or {}).get('decision')}"
              f" :: {(c['command'] or '')[:90]!r}", flush=True)
    with open(d("logs", sid, "calls.jsonl"), "w") as fh:
        for r in out:
            fh.write(json.dumps(r) + "\n")
    return out


if __name__ == "__main__":
    for s in sys.argv[1:]:
        process(s)
