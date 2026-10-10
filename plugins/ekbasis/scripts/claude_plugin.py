#!/usr/bin/env python3
"""Claude Code plugin launcher (run by run.sh): the hooks and the MCP server from the plugin's own copy of the ekbasis
package in ../lib (no install, no network). See ekbasis/claude_plugin.py.

The PreToolUse hook must never let a command through silently when Ekbasis is set up: Claude Code does not block on
a hook that crashes, exits with an error or is stopped by its timeout. So, once EKBASIS_URL or EKBASIS_API_KEY is set,
this launcher answers "ask" (or "deny", EKBASIS_GUARD_MODE=deny) with the reason when the hook cannot run: a Python older
than 3.9, an import error, any exception, or no answer within WATCHDOG seconds (below the hook's "timeout" of 30 in
plugin.json; the hook's own deadline, EKBASIS_HOOK_DEADLINE, is 25). run.sh does the same when python3 itself is
missing or dies. Only the standard library is used before the package is imported, and no f-strings, so that an old
Python still reaches the answer below."""
import io
import json
import os
import sys
import threading

LIB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib")
WATCHDOG = float(os.environ.get("EKBASIS_PLUGIN_WATCHDOG", "27"))


def configured():
    return bool(os.environ.get("EKBASIS_URL", "").strip() or os.environ.get("EKBASIS_API_KEY", "").strip())


def cannot_run(why):
    """The hook's own fail-closed answer, for a hook that could not run (EKBASIS_FAIL_OPEN=1: let it through, on stderr)."""
    if os.environ.get("EKBASIS_FAIL_OPEN") == "1":
        sys.stderr.write("ekbasis hook: cannot foresee ({0}); EKBASIS_FAIL_OPEN=1: letting it through\n".format(why))
        return ""
    mode = "deny" if os.environ.get("EKBASIS_GUARD_MODE") == "deny" else "ask"
    return json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": mode,
        "permissionDecisionReason": "Ekbasis could not foresee what this command will do (the Ekbasis hook could not "
                                    "run: {0}). Confirm it only if you know it is safe.".format(why)}})


def run_hook():
    out = sys.stdout
    lock, done = threading.Lock(), []

    def answer(text):
        with lock:
            if done:
                return
            done.append(True)
            if text:
                out.write(text if text.endswith("\n") else text + "\n")
            out.flush()

    def too_late():
        answer(cannot_run("it did not finish within {0:g} s".format(WATCHDOG)))
        os._exit(0)

    timer = threading.Timer(WATCHDOG, too_late)
    timer.daemon = True
    timer.start()
    captured = io.StringIO()
    try:
        if sys.version_info < (3, 9):
            raise RuntimeError("it needs Python 3.9 or later as python3, found {0}".format(sys.version.split()[0]))
        sys.path.insert(0, LIB)
        sys.stdout = captured
        from ekbasis.claude_plugin import hook
        rc = hook()
        sys.stdout = out
        if rc not in (0, None):
            raise RuntimeError("it exited with {0}".format(rc))
        answer(captured.getvalue())
    except BaseException as e:  # noqa: BLE001 — anything, including SystemExit and KeyboardInterrupt
        sys.stdout = out
        answer(cannot_run("{0}: {1}".format(type(e).__name__, e)))
    timer.cancel()
    return 0


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "hook":
        if not configured():
            return 0   # not set up: the SessionStart line says how; Claude Code's normal permission flow applies
        return run_hook()
    if sys.version_info < (3, 9):
        sys.exit("ekbasis plugin: needs Python 3.9 or later as python3, found {0}".format(sys.version.split()[0]))
    sys.path.insert(0, LIB)
    from ekbasis.claude_plugin import main as plugin_main
    return plugin_main([mode])


if __name__ == "__main__":
    sys.exit(main())
