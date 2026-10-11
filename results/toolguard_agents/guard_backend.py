"""Condition D (the ceiling): the guard reads the app's backend for the state — the app's rules and the facts its own
foresight uses (the `backend_spec` tool, hidden from the agent) — and asks the same generic questions as B and C.
A click the app says changes nothing that matters is not asked about (as in the earlier studies' foresee)."""
import json
import sys

from ekbasis import mcp_guard as MG
from ekbasis import prompts as P


class BackendGuard(MG.Guard):
    def backend_state(self, name, args, events):
        if name != "click":
            return None
        resp = self._ask_server("tools/call", {"name": "backend_spec", "arguments": {"element": args.get("element", "")}},
                                self.probe_seconds)
        result = (resp or {}).get("result") or {}
        if result.get("isError"):
            return ""   # the element is not on the screen: the click fails and changes nothing
        text = MG.TG.content_text(result.get("content"))
        spec = json.loads(text) if text.strip() else None
        if not spec:
            return ""   # nothing that matters changes: not asked
        state = (f'The user asked: "{self.request}". ' if self.request else "") + spec["state"]
        return P.world_state(spec["rules"], state, [spec["action"]])


if __name__ == "__main__":
    sys.exit(MG.main(guard_class=BackendGuard))
