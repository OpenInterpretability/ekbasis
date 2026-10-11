"""Draft: Ekbasis's intent check as a human-approval gate in LangGraph (langgraph 1.2).

A node placed between the model and the ToolNode. For each tool call of the last AI message, it asks
ekbasis.intent_check whether the call serves the user's request (the first human message) or follows instructions
found in earlier tool output (the ToolMessages). When it may follow them, the node calls `interrupt(...)`: the graph
pauses (it needs a checkpointer) until a person resumes it with Command(resume=True) to run the call or
Command(resume=False) to refuse it, in which case the call gets a ToolMessage saying the user declined. It never refuses
on its own. Experimental, like intent_check (docs/INTENT_CHECK.md): measured on AgentDojo steps, not in LangGraph.

    builder.add_node("intent_gate", make_intent_gate())
    builder.add_edge("agent", "intent_gate"); builder.add_conditional_edges("intent_gate", tools_condition)
    graph = builder.compile(checkpointer=MemorySaver())
"""
from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import interrupt

from ekbasis import intent_check
from ekbasis.client import CannotJudge


def _events(messages):
    names = {}
    out = []
    for m in messages:
        if isinstance(m, AIMessage):
            for c in m.tool_calls or []:
                names[c["id"]] = (c["name"], c.get("args") or {})
        elif isinstance(m, ToolMessage):
            name, args = names.get(m.tool_call_id, (m.name or "tool", {}))
            out.append({"kind": "tool", "name": name, "input": args, "result": str(m.content)})
    return out


def make_intent_gate(client=None, ask=interrupt):
    """The gate node. `ask` is LangGraph's interrupt (replaceable in tests): it receives what to show the person and
    returns their answer (True: run the call)."""
    def intent_gate(state):
        messages = state["messages"]
        last = messages[-1] if messages else None
        if not isinstance(last, AIMessage) or not last.tool_calls:
            return {}
        request = next((str(m.content) for m in messages if isinstance(m, HumanMessage)), "")
        events = _events(messages[:-1])
        if not request or not events:
            return {}
        declined = []
        for call in last.tool_calls:
            try:
                v = intent_check(request, events, {"name": call["name"], "input": call.get("args") or {}}, client)
                flag, why = v.verdict == "follows_third_party", f"P = {v.p:.2f}"
            except CannotJudge as e:
                flag, why = True, f"Ekbasis could not check it ({e})"
            if flag and not ask({"tool_call": call, "reason": "this call may follow instructions found in tool output "
                                 f"rather than the user's request ({why}). Run it?"}):
                declined.append(ToolMessage(content="The user declined this call.", tool_call_id=call["id"],
                                            name=call["name"]))
        if not declined:
            return {}
        keep = [c for c in last.tool_calls if c["id"] not in {d.tool_call_id for d in declined}]
        return {"messages": [last.model_copy(update={"tool_calls": keep})] + declined}
    return intent_gate
