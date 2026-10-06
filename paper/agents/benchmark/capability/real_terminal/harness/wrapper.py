"""Claude Code hook used in both arms (see ../SPEC.md, "Logging").

usage (from the session's --settings): python wrapper.py pre|post <sid> <arm>
  pre:  log the Bash call, APFS-clone the session folder (before), and in arm H run the published
        ekbasis-claude-hook on the same input and pass its answer through unchanged.
  post: APFS-clone the session folder (after) and log what the call returned.
Never blocks by itself: any error of the wrapper is logged and the call goes on as with no hook.
Self-contained on purpose: it runs inside the agent's sandbox, from the work root.
"""
import ctypes
import json
import os
import subprocess
import sys
import time

W = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))  # the work root: this file runs as <work root>/bin/wrapper*.py
EKB_HOOK = os.path.join(W, "ekbasis_venv/bin/ekbasis-claude-hook")
TUNNEL_URL = "http://127.0.0.1:18642"
HOOK_TIMEOUT = 30          # the timeout of the install snippet: past it Claude Code lets the call through


def log(sid, rec):
    with open(os.path.join(W, "logs", sid, "events.jsonl"), "a") as fh:
        fh.write(json.dumps(rec) + "\n")


def snapshot(sid, name):
    """clonefile(2) of the whole session folder: an APFS copy-on-write clone of the tree in one call."""
    src, dst = os.path.join(W, "s", sid), os.path.join(W, "snaps", sid, name)
    t = time.monotonic()
    r = ctypes.CDLL("libc.dylib", use_errno=True).clonefile(src.encode(), dst.encode(), 0)
    err = "" if r == 0 else os.strerror(ctypes.get_errno())
    if r != 0:   # fall back to a per-file clone
        p = subprocess.run(["cp", "-c", "-R", src, dst], capture_output=True, text=True)
        r, err = p.returncode, err + " | " + p.stderr[-300:]
    return {"path": dst, "secs": round(time.monotonic() - t, 4), "ok": r == 0, "err": err}


def main():
    phase, sid, arm = sys.argv[1], sys.argv[2], sys.argv[3]
    raw = sys.stdin.buffer.read()
    t_in = time.time()
    try:
        data = json.loads(raw)
    except ValueError as e:
        log(sid, {"phase": phase, "t": t_in, "error": f"unreadable hook input: {e}"})
        return 0
    tid = data.get("tool_use_id") or f"noid-{t_in}"
    rec = {"phase": phase, "sid": sid, "arm": arm, "tool_use_id": tid, "t": t_in,
           "command": (data.get("tool_input") or {}).get("command"), "cwd": data.get("cwd"),
           "permission_mode": data.get("permission_mode")}
    try:
        if phase == "post":
            rec["snapshot"] = snapshot(sid, f"{tid}.post")
            resp = data.get("tool_response")
            if isinstance(resp, dict):
                rec["response"] = {k: (v[-1500:] if isinstance(v, str) else v) for k, v in resp.items()}
            else:
                rec["response"] = str(resp)[-1500:]
            rec["t_done"] = time.time()
            log(sid, rec)
            return 0
        rec["snapshot"] = snapshot(sid, f"{tid}.pre")
        rec["input"] = data
        if arm == "H":
            env = {**os.environ, "EKBASIS_URL": TUNNEL_URL, "EKBASIS_SHELL_GUARD": "1"}
            t = time.monotonic()
            try:
                p = subprocess.run([EKB_HOOK], input=raw, capture_output=True, env=env, timeout=HOOK_TIMEOUT)
                out, err, code, timed_out = p.stdout, p.stderr, p.returncode, False
            except subprocess.TimeoutExpired as e:
                out, err, code, timed_out = b"", (e.stderr or b""), None, True
            wall = time.monotonic() - t
            decision, reason = "allow", None
            if timed_out:
                out = b""                     # Claude Code would kill the hook and let the call through
                decision = "timeout"
            elif out.strip():
                try:
                    hso = json.loads(out)["hookSpecificOutput"]
                    decision, reason = hso.get("permissionDecision"), hso.get("permissionDecisionReason")
                except (ValueError, KeyError, TypeError):
                    decision = "unparsed"
            rec["ekbasis"] = {"wall": round(wall, 4), "exit": code, "timed_out": timed_out, "decision": decision,
                              "reason": reason, "stdout": out.decode(errors="replace")[-3000:],
                              "stderr": err.decode(errors="replace")[-1500:]}
            rec["t_done"] = time.time()
            log(sid, rec)
            if code == 2 and not timed_out:   # exit 2 blocks in Claude Code (0.1.2 never uses it): pass it on as is
                sys.stderr.buffer.write(err)
                return 2
            if out:
                sys.stdout.buffer.write(out)
                sys.stdout.flush()
            return 0
        rec["t_done"] = time.time()
        log(sid, rec)
        return 0
    except Exception as e:  # noqa: BLE001 — the wrapper must never stop a session
        rec["error"] = f"{type(e).__name__}: {e}"
        try:
            log(sid, rec)
        except OSError:
            pass
        return 0


if __name__ == "__main__":
    sys.exit(main())
