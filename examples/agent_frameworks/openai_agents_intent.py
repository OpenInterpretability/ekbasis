"""Draft: Ekbasis's intent check as a human-approval gate in the OpenAI Agents SDK (openai-agents 0.23).

Before a guarded tool runs, the gate asks ekbasis.intent_check whether the call serves the user's request or follows
instructions found in earlier tool output. When it may follow them, the tool's `needs_approval` returns True and the
run pauses with a ToolApprovalItem: a person approves (RunState.approve) or rejects (RunState.reject). It never
rejects on its own. Experimental, like intent_check (docs/INTENT_CHECK.md): measured on AgentDojo steps, not in this
SDK; adaptive attacks were not tested.

    log = IntentLog()
    tools = guard_tools([send_email, read_inbox], log, user_request)
    result = await Runner.run(agent_with(tools), user_request, hooks=log)
    for item in result.interruptions:     # the gate asked: show item, then
        state = result.to_state(); state.approve(item)  # or state.reject(item); then Runner.run(agent, state)
"""
from __future__ import annotations

import asyncio
import json

from agents import RunHooks

from ekbasis import intent_check
from ekbasis.client import CannotJudge


class IntentLog(RunHooks):
    """Keeps every tool call of the run and its output, as intent_check's context (untrusted data)."""

    def __init__(self):
        self.events: list = []
        self._args: dict = {}

    async def on_tool_start(self, context, agent, tool):
        self._args[id(tool)] = getattr(context, "tool_arguments", None)

    async def on_tool_end(self, context, agent, tool, result):
        raw = self._args.pop(id(tool), None)
        try:
            args = json.loads(raw) if isinstance(raw, str) else (raw or {})
        except ValueError:
            args = {"arguments": raw}
        self.events.append({"kind": "tool", "name": tool.name, "input": args, "result": str(result)})


def intent_approval(log: IntentLog, user_request: str, tool_name: str, client=None):
    """A `needs_approval` function for one tool: True (ask a person) when the call may follow a third party's
    instructions, or when Ekbasis cannot be reached (fail closed)."""
    async def needs_approval(run_context, params: dict, call_id: str) -> bool:
        if not log.events:
            return False    # no tool output yet: nothing that could carry someone else's instructions
        try:
            v = await asyncio.to_thread(intent_check, user_request, list(log.events),
                                        {"name": tool_name, "input": params}, client)
        except CannotJudge:
            return True
        return v.verdict == "follows_third_party"
    return needs_approval


def guard_tools(tools, log: IntentLog, user_request: str, client=None):
    """Sets the gate on every function tool given (in place) and returns them."""
    for t in tools:
        t.needs_approval = intent_approval(log, user_request, t.name, client)
    return tools
