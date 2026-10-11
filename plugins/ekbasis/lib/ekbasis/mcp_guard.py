"""A guard in front of any MCP server (stdio), standard library only (a prototype in 0.1.10).

    ekbasis-mcp-guard [--mode block|warn] [--threshold 0.5] [--no-repeat] [--fail-open] [--no-probe]
                      [--request TEXT] [--no-request-flags] [--allow a,b] [--probe-only c,d] [--log FILE]
                      -- <server command>

Register this command in the MCP client instead of the server's own command. It starts the server and relays every
message both ways unchanged, and it keeps what it relays as context: the tools' descriptions, annotations and input
schemas (from tools/list) and each tool call with its result. Before a tools/call that may change something
(ekbasis.toolguard: read-only names, readOnlyHint and SELECT-only SQL pass without a check; --allow names tools the
operator declares harmless) it asks Ekbasis, with a state built from the results it relayed earlier.

The read-only probe (on by default; --no-probe turns it off): before asking, the guard itself calls up to three of the
server's read-only tools whose arguments it can fill from the call (toolguard.plan_probes), so facts the agent never
looked at (who a folder is shared with, a balance, what uses a key) can reach the state, quoted like any result. It
never calls a tool that is not classed as read-only, and gives the probe at most EKBASIS_PROBE_SECONDS (default 8) in
all. --probe-only names tools kept for the probe: they are removed from the tool list the agent sees.

The MCP traffic does not carry the user's request; --request (or EKBASIS_GUARD_REQUEST) gives it, so the guard can
also ask whether the call does what was asked. With --intent-check (experimental, docs/INTENT_CHECK.md) it also runs
ekbasis.intent_check on the call alone, with the tool results it relayed as quoted context: a call that may follow
instructions found in them is refused once with the reason, and goes through if made again (the agent's way to ask
its user; keep the default repeat). --intent-only runs that check without the harm questions.

- mode block (the default): a risky or cannot-foresee call is not sent to the server; the agent gets a tool result
  with isError and the forecast, so it can tell the user. The same call (same tool, same arguments) made again in the
  session goes through (--no-repeat: never), so a user who confirms can have the agent call it again.
- mode warn: the call goes through and the forecast is put before the result.

Fails closed: when the server of Ekbasis cannot be reached or does not answer in time (EKBASIS_TOOL_DEADLINE seconds,
default 25), the call counts as cannot foresee (--fail-open: it goes through). Messages are newline-delimited JSON-RPC,
as the MCP stdio transport sends them; a line that is not JSON is relayed as it is. --log (or EKBASIS_GUARD_LOG)
appends one JSON line per checked call: the verdict, its probabilities, the probes, the time and the tokens.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
import subprocess
import sys
import threading
import time

from . import intent as INTENT
from . import toolguard as TG
from .client import CannotJudge, Ekbasis

MAX_EVENTS = 40     # tool calls kept as context


class Guard:
    """The relay's decisions, without the pipes (send_client/send_server write one message each way)."""

    def __init__(self, send_client, send_server, client=None, mode: str = "block", risky_at: float = 0.5,
                 repeat: bool = True, fail_open: bool = False, log=None, probe: bool = True, request: str | None = None,
                 allow=(), probe_only=(), audit: str | None = None, probe_seconds: float | None = None,
                 request_flags: bool = True, intent: bool = False, harm: bool = True):
        self.send_client, self.send_server = send_client, send_server
        self.client = client or Ekbasis(timeout=float(os.environ.get("EKBASIS_TOOL_DEADLINE", "25")), surface="mcp-guard")
        self.mode, self.risky_at, self.repeat, self.fail_open = mode, risky_at, repeat, fail_open
        self.log = log or (lambda m: print(f"ekbasis-mcp-guard: {m}", file=sys.stderr, flush=True))
        self.probe, self.request, self.request_flags = probe, request, request_flags
        self.intent, self.harm = intent, harm
        self.allow, self.probe_only = set(allow), set(probe_only)
        self.audit = audit
        self.probe_seconds = probe_seconds if probe_seconds is not None else \
            float(os.environ.get("EKBASIS_PROBE_SECONDS", "8"))
        self.tools: dict = {}        # name -> {"description", "annotations", "inputSchema"}
        self.events: list = [{"kind": "user", "text": request}] if request else []
        self.pending: dict = {}      # request id -> ("list" | "call", event, warning)
        self.waiting: dict = {}      # the guard's own request id -> [threading.Event, response]
        self.warned: set = set()     # calls blocked once (their keys)
        self.ids = itertools.count(1)
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

    def _ask_server(self, method: str, params: dict, timeout: float):
        """A request of the guard's own to the server (a probe); its answer is not relayed. None on timeout."""
        rid = f"ekbasis-guard-{next(self.ids)}"
        slot = [threading.Event(), None]
        with self.lock:
            self.waiting[rid] = slot
        self.send_server({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        slot[0].wait(max(0.0, timeout))
        with self.lock:
            self.waiting.pop(rid, None)
        return slot[1]

    def run_probes(self, name: str, args, events) -> list:
        """The read-only calls planned for this call, made now: their events (kind tool, probe True)."""
        out, t0 = [], time.monotonic()
        for tool, targs in TG.plan_probes(name, args, self.tools, events):
            left = self.probe_seconds - (time.monotonic() - t0)
            if left <= 0:
                break
            resp = self._ask_server("tools/call", {"name": tool, "arguments": targs}, left)
            result = (resp or {}).get("result") if isinstance(resp, dict) else None
            if not isinstance(result, dict) or result.get("isError"):
                continue
            text = TG.content_text(result.get("content"))
            if not text.strip() and result.get("structuredContent") is not None:
                text = json.dumps(result["structuredContent"], ensure_ascii=False)
            if text.strip():
                out.append({"kind": "tool", "name": tool, "input": targs, "result": text, "probe": True})
        return out

    def backend_state(self, name: str, args, events) -> str | None:
        """A state written from another source than the session (a subclass may read the app's backend); None: build
        it from the session; "": the source says the call changes nothing that matters (not asked)."""
        return None

    def _call(self, msg: dict) -> None:
        params = msg.get("params") or {}
        name, args = str(params.get("name", "")), params.get("arguments") or {}
        meta = self.tools.get(name, {})
        key = hashlib.sha256(json.dumps([name, args], sort_keys=True, default=str).encode()).hexdigest()
        warning, row = None, None
        with self.lock:
            refused = not self.repeat and key in self.warned
        if refused:   # blocked before and --no-repeat: blocked again without asking the model
            self._audit({"t": time.time(), "tool": name, "input": args, "verdict": "repeat", "p": {}, "reasons": [],
                         "skipped": None, "probes": [], "backend": False, "seconds": 0.0, "usage": None,
                         "state_chars": 0, "action": "blocked again"})
            self.send_client({"jsonrpc": "2.0", "id": msg["id"], "result": {"content": [{"type": "text", "text":
                              "Not called: this exact call was blocked before in this session."}], "isError": True}})
            return
        if name not in self.allow and not TG.read_only(name, args, meta.get("annotations")):
            t0 = time.monotonic()
            with self.lock:
                events = list(self.events)
            probes, state = [], None
            for attr, empty in (("last_usage", None), ("last_timing", {}), ("last_status", None)):
                if hasattr(self.client, attr):
                    setattr(self.client, attr, empty)   # this check's values only, never the previous one's
            try:
                state = self.backend_state(name, args, events)
                if state is None and self.probe:
                    probes = self.run_probes(name, args, events)
                if state == "":
                    v = TG.ToolVerdict(tool=name, skipped="the backend says it changes nothing that matters")
                elif not self.harm:
                    v = TG.ToolVerdict(tool=name, skipped="harm questions off (--intent-only)")
                else:
                    v = TG.check(name, args, events + probes, description=meta.get("description"),
                                 annotations=meta.get("annotations"), client=self.client, risky_at=self.risky_at,
                                 state=state, request_flags=self.request_flags)
            except CannotJudge as e:
                v = TG.ToolVerdict(tool=name, verdict="cannot_foresee", reasons=[str(e)])
            except Exception as e:  # noqa: BLE001  (anything else: cannot foresee)
                v = TG.ToolVerdict(tool=name, verdict="cannot_foresee", reasons=[f"{type(e).__name__}: {e}"])
            if self.intent and not v.risky:
                v = self._intent(name, args, events, v)
            row = {"t": time.time(), "tool": name, "input": args, "verdict": v.verdict, "p": v.p, "reasons": v.reasons,
                   "skipped": v.skipped, "probes": [p["name"] for p in probes], "backend": state is not None,
                   "seconds": round(time.monotonic() - t0, 3), "usage": getattr(self.client, "last_usage", None),
                   "server_timing": dict(getattr(self.client, "last_timing", None) or {}),
                   "http_status": getattr(self.client, "last_status", None),
                   "error": v.verdict == "cannot_foresee" and not v.p,
                   "state_chars": len(v.state), "action": "called"}
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
                        self._audit({**row, "action": "blocked"})
                        self.send_client({"jsonrpc": "2.0", "id": msg["id"], "result": {
                            "content": [{"type": "text", "text": f"Not called. {warning}{note}"}], "isError": True}})
                        return
                    row["action"] = "called after a warning"
                    warning = None
                else:
                    row["action"] = "called with a warning"
            self._audit(row)
        event = {"kind": "tool", "name": name, "input": args, "result": ""}
        with self.lock:
            self.pending[msg["id"]] = ("call", event, warning)
        self.send_server(msg)

    def _intent(self, name: str, args, events, v):
        """--intent-check: does the call serve the request (--request) or instructions found in tool output? A call
        that may follow them is flagged like a risky one (block mode: refused once, with the reason; the same call
        made again goes through, so a user who confirms can have the agent call it again)."""
        tools = [e for e in events if e.get("kind") == "tool"]
        if not self.request or not tools:
            return v
        try:
            iv = INTENT.intent_check(self.request, tools, {"name": name, "input": args}, client=self.client)
        except CannotJudge as e:
            return TG.ToolVerdict(tool=name, verdict="cannot_foresee", p=dict(v.p), reasons=[str(e)])
        p = {**v.p, "intent_third_party": iv.p}
        if iv.verdict != "follows_third_party":
            return TG.ToolVerdict(tool=name, verdict=v.verdict, p=p, reasons=v.reasons, skipped=v.skipped)
        seen = ", ".join(dict.fromkeys(e["name"] for e in tools[-5:]))
        return TG.ToolVerdict(tool=name, verdict="risky", p=p, reasons=[
            f"may follow instructions found in tool output ({seen}) rather than the user's request ({100 * iv.p:.0f}%)"])

    def _audit(self, row: dict) -> None:
        if not self.audit:
            return
        try:
            with self.lock, open(self.audit, "a") as fh:
                fh.write(json.dumps(row, default=str) + "\n")
        except OSError as e:
            self.log(f"cannot write the log {self.audit}: {e}")

    # ---- server -> client
    def from_server(self, msg) -> None:
        if isinstance(msg, dict) and "id" in msg and "method" not in msg:
            with self.lock:
                slot = self.waiting.get(msg["id"])
            if slot is not None:   # the answer to one of the guard's own requests: not relayed
                slot[1] = msg
                slot[0].set()
                return
            with self.lock:
                kind, event, warning = self.pending.pop(msg["id"], (None, None, None))
            result = msg.get("result") if isinstance(msg.get("result"), dict) else None
            if kind == "list" and result:
                for t in result.get("tools") or []:
                    if isinstance(t, dict) and t.get("name"):
                        self.tools[t["name"]] = {"description": t.get("description"),
                                                 "annotations": t.get("annotations") or {},
                                                 "inputSchema": t.get("inputSchema") or {}}
                if self.probe_only:
                    msg = {**msg, "result": {**result, "tools": [t for t in result.get("tools") or []
                                                                 if not (isinstance(t, dict) and t.get("name") in self.probe_only)]}}
            elif kind == "call":
                text = TG.content_text((result or {}).get("content")) if result else json.dumps(msg.get("error"))
                if result and result.get("structuredContent") is not None and not text.strip():
                    text = json.dumps(result["structuredContent"], ensure_ascii=False)
                event["result"] = text
                with self.lock:
                    keep = [e for e in self.events if e.get("kind") == "user"]
                    tools = [e for e in self.events if e.get("kind") != "user"]
                    self.events = keep + (tools + [event])[-MAX_EVENTS:]
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


def _names(text: str | None) -> list:
    return [x.strip() for x in (text or "").split(",") if x.strip()]


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="ekbasis-mcp-guard",
                                 description="Relay an MCP server (stdio) and check its tool calls with Ekbasis first.")
    ap.add_argument("--mode", choices=("block", "warn"), default="block")
    ap.add_argument("--threshold", type=float, default=0.5, help="a harm this likely is risky (default 0.5)")
    ap.add_argument("--no-repeat", action="store_true", help="a blocked call never goes through when repeated")
    ap.add_argument("--fail-open", action="store_true", help="call the tool when Ekbasis cannot foresee")
    ap.add_argument("--no-probe", action="store_true", help="do not call the server's read-only tools before a check")
    ap.add_argument("--request", default=os.environ.get("EKBASIS_GUARD_REQUEST"), help="what the user asked for")
    ap.add_argument("--no-request-flags", action="store_true",
                    help="ask whether the call goes against the request, but do not let that answer flag it")
    ap.add_argument("--intent-check", action="store_true",
                    help="also ask whether the call follows instructions found in tool output (needs --request)")
    ap.add_argument("--intent-only", action="store_true", help="the intent check alone, without the harm questions")
    ap.add_argument("--allow", default=os.environ.get("EKBASIS_GUARD_ALLOW"), help="tools never checked (a,b)")
    ap.add_argument("--probe-only", default=None, help="tools only the probe may call, hidden from the agent (a,b)")
    ap.add_argument("--log", default=os.environ.get("EKBASIS_GUARD_LOG"), help="append one JSON line per check here")
    ap.add_argument("command", nargs=argparse.REMAINDER, help="-- the MCP server command and its arguments")
    return ap


def main(argv=None, guard_class=Guard) -> int:
    ap = parser()
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
    guard = guard_class(_writer(sys.stdout), _writer(proc.stdin), mode=a.mode, risky_at=a.threshold,
                        repeat=not a.no_repeat, fail_open=a.fail_open, probe=not a.no_probe, request=a.request,
                        allow=_names(a.allow), probe_only=_names(a.probe_only), audit=a.log,
                        request_flags=not a.no_request_flags, intent=a.intent_check or a.intent_only,
                        harm=not a.intent_only)
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
