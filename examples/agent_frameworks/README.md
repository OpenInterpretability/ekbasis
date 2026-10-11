# Intent check in agent frameworks (drafts)

Drafts, not part of the `ekbasis` package (they import the framework). Each puts `ekbasis.intent_check`
(experimental, [docs/INTENT_CHECK.md](../../docs/INTENT_CHECK.md)) in front of tool calls as a **request for human
approval**, never an automatic refusal:

- `openai_agents_intent.py`: OpenAI Agents SDK (checked against openai-agents 0.23): a `needs_approval` function per
  tool, with `RunHooks` keeping the tool outputs as context; the run pauses with a ToolApprovalItem.
- `langgraph_intent.py`: LangGraph (checked against langgraph 1.2): a gate node before the ToolNode that calls
  `interrupt()`; a declined call gets a ToolMessage instead of running.

Both: the action is the tool call only (name and arguments); the context is the tool outputs already returned,
quoted as untrusted data; a server error asks (fail closed). Not measured inside these frameworks.
