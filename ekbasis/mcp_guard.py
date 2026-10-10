"""A guard in front of any MCP server (stdio), standard library only (a prototype in 0.1.10).

    python3 -m ekbasis.mcp_guard [--mode block|warn] [--threshold 0.5] [--no-repeat] [--fail-open] -- <server command>

Register this command in the MCP client instead of the server's own command. It starts the server and relays every
message both ways unchanged, and it keeps what it relays as context: the tools' descriptions and annotations (from
tools/list) and each tool call with its result. Before a tools/call that may change something (ekbasis.toolguard:
read-only names, readOnlyHint and SELECT-only SQL pass without a check) it asks Ekbasis, with a state built from the
results it relayed earlier. The MCP traffic does not carry the user's request, so that question is not asked here.

- mode block (the default): a risky or cannot-foresee call is not sent to the server; the agent gets a tool result
  with isError and the forecast, so it can tell the user. The same call (same tool, same arguments) made again in the
  session goes through (--no-repeat: never), so a user who confirms can have the agent call it again.
- mode warn: the call goes through and the forecast is put before the result.

Fails closed: when the server of Ekbasis cannot be reached or does not answer in time (EKBASIS_TOOL_DEADLINE seconds,
default 25), the call counts as cannot foresee (--fail-open: it goes through). Messages are newline-delimited JSON-RPC,
as the MCP stdio transport sends them; a line that is not JSON is relayed as it is.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import threading

from . import toolguard as TG
from .client import CannotJudge, Ekbasis

MAX_EVENTS = 40     # tool calls kept as context


class Guard:
    """The relay's decisions, without the pipes (send_client/send_server write one message each way)."""

    def __init__(self, send_client, send_server, client=None, mode: str = "block", risky_at: float = 0.5,
                 repeat: bool = True, fail_open: bool = False, log=None):
        self.send_client, self.send_server = send_client, send_server
        self.client = client or Ekbasis(timeout=float(os.environ.get("EKBASIS_TOOL_DEADLINE", "25")), surface="mcp-guard")
        self.mode, self.risky_at, self.repeat, self.fail_open = mode, risky_at, repeat, fail_open
        self.log = log or (lambda m: print(f"ekbasis-mcp-guard: {m}", file=sys.stderr, flush=True))
        self.tools: dict = {}        # name -> {"description", "annotations"}
        self.events: list = []       # {"kind": "tool", "name", "input", "result"}
        self.pending: dict = {}      # request id -> ("list", None) | ("call", event, warning)
        self.warned: set = set()     # calls blocked once (their keys)
        self.lock = threading.Lock()

    # ---- client -> server
    def from_client(self, msg) -> None:
        if not isinstance(msg, dict) or "method" not in msg or "id" not in msg:
            self.send_server(msg)
            return
        if msg["method"] == "tools/list":
            with self.lock:
                self.pending[msg["id"]] = ("list", None, None)
            self.send_server(msg)
        elif msg["method"] == "tools/call":
            threading.Thread(target=self._call, args=(msg,), daemon=True).start()
        else:
            self.send_server(msg)

    def _call(self, msg: dict) -> None:
        params = msg.get("params") or {}
        name, args = str(params.get("name", "")), params.get("arguments") or {}
        meta = self.tools.get(name, {})
        key = hashlib.sha256(json.dumps([name, args], sort_keys=True, default=str).encode()).hexdigest()
        warning = None
        if not TG.read_only(name, args, meta.get("annotations")):
            with self.lock:
                events = list(self.events)
            try:
                v = TG.check(name, args, events, description=meta.get("description"),
                             annotations=meta.get("annotations"), client=self.client, risky_at=self.risky_at)
            except CannotJudge as e:
                v = TG.ToolVerdict(tool=name, verdict="cannot_foresee", reasons=[str(e)])
            except Exception as e:  # noqa: BLE001  (anything else: cannot foresee)
                v = TG.ToolVerdict(tool=name, verdict="cannot_foresee", reasons=[f"{type(e).__name__}: {e}"])
            if v.verdict == "cannot_foresee" and self.fail_open:
                self.log(f"{v.message()} (--fail-open: calling it)")
            elif v.risky:
                warning = v.message()
                self.log(f"{name}: {v.verdict}: {'; '.join(v.reasons)}")
                if self.mode == "block":
                    with self.lock:
                        again = self.repeat and key in self.warned
                        self.warned.add(key)
                    if not again:
                        note = " Calling it again with the same arguments will go through." if self.repeat else ""
                        self.send_client({"jsonrpc": "2.0", "id": msg["id"], "result": {
                            "content": [{"type": "text", "text": f"Not called. {warning}{note}"}], "isError": True}})
                        return
                    warning = None
        event = {"kind": "tool", "name": name, "input": args, "result": ""}
        with self.lock:
            self.pending[msg["id"]] = ("call", event, warning)
        self.send_server(msg)

    # ---- server -> client
    def from_server(self, msg) -> None:
        if isinstance(msg, dict) and "id" in msg and "method" not in msg:
            with self.lock:
                kind, event, warning = self.pending.pop(msg["id"], (None, None, None))
            result = msg.get("result") if isinstance(msg.get("result"), dict) else None
            if kind == "list" and result:
                for t in result.get("tools") or []:
                    if isinstance(t, dict) and t.get("name"):
                        self.tools[t["name"]] = {"description": t.get("description"),
                                                 "annotations": t.get("annotations") or {}}
            elif kind == "call":
                text = TG.content_text((result or {}).get("content")) if result else json.dumps(msg.get("error"))
                if result and result.get("structuredContent") is not None and not text.strip():
                    text = json.dumps(result["structuredContent"], ensure_ascii=False)
                event["result"] = text
                with self.lock:
                    self.events = (self.events + [event])[-MAX_EVENTS:]
                if warning and result is not None:
                    content = [{"type": "text", "text": warning}] + list(result.get("content") or [])
                    msg = {**msg, "result": {**result, "content": content}}
        self.send_client(msg)


def _writer(stream):
    lock = threading.Lock()

    def send(msg) -> None:
        line = msg if isinstance(msg, str) else json.dumps(msg, ensure_ascii=False)
        with lock:
            stream.write(line.rstrip("\n") + "\n")
            stream.flush()
    return send


def _pump(src, handle) -> None:
    for line in src:
        if not line.strip():
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            handle(line)
            continue
        for m in (msg if isinstance(msg, list) else [msg]):
            handle(m)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m ekbasis.mcp_guard",
                                 description="Relay an MCP server (stdio) and check its tool calls with Ekbasis first.")
    ap.add_argument("--mode", choices=("block", "warn"), default="block")
    ap.add_argument("--threshold", type=float, default=0.5, help="a harm this likely is risky (default 0.5)")
    ap.add_argument("--no-repeat", action="store_true", help="a blocked call never goes through when repeated")
    ap.add_argument("--fail-open", action="store_true", help="call the tool when Ekbasis cannot foresee")
    ap.add_argument("command", nargs=argparse.REMAINDER, help="-- the MCP server command and its arguments")
    a = ap.parse_args(argv)
    cmd = a.command[1:] if a.command[:1] == ["--"] else a.command
    if not cmd:
        ap.error("give the MCP server command after --")
    try:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding="utf-8",
                                bufsize=1)
    except OSError as e:
        print(f"ekbasis-mcp-guard: cannot start {cmd[0]}: {e}", file=sys.stderr)
        return 1
    guard = Guard(_writer(sys.stdout), _writer(proc.stdin), mode=a.mode, risky_at=a.threshold,
                  repeat=not a.no_repeat, fail_open=a.fail_open)
    t = threading.Thread(target=_pump, args=(proc.stdout, guard.from_server), daemon=True)
    t.start()
    try:
        _pump(sys.stdin, guard.from_client)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            proc.stdin.close()
        except OSError:
            pass
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.terminate()
    t.join(timeout=2)
    return proc.returncode or 0


if __name__ == "__main__":
    sys.exit(main())
