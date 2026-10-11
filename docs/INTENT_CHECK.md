# Intent check (experimental)

**Experimental API.** It may change without a major version, it is not announced, and it was measured only as below.
Use it as a **signal to ask a person for confirmation**, not as an automatic block.

## What it asks

Before an agent's next tool call runs: does the call serve the user's request, or does it carry out instructions that
came from content the agent read (a tool's output, a document, an e-mail, a web page, any third party)? This is the
pattern of indirect prompt injection.

```python
from ekbasis import intent_check

v = intent_check(
    "What are we doing on June 13, according to the Hawaii vacation file?",   # what the user asked
    [{"kind": "tool", "name": "search_files", "input": {"query": "Hawaii"}, "result": "..."},  # what the tools returned
     {"kind": "tool", "name": "read_email", "input": {"id": "9"}, "result": "..."}],
    {"name": "send_email", "input": {"recipients": ["someone@example.com"], "body": "..."}},  # the next call
)
v.verdict   # "follows_third_party" (p >= 0.5) | "unsure" (p >= 0.2) | "serves_user"
v.p         # P(the call carries out a third party's instructions)
```

- **Input: the tool call only** (name and arguments). The agent's own reasoning is left out by default
  (`agent_text=False`): the check was as accurate without it, and a guard should not depend on text the agent writes.
- **`shield=True` (default):** tool output is treated as untrusted data. Every line of it is quoted with `│ ` under a
  line naming the tool, so it cannot pose as the user's request, as a section of the state or as a message to the
  reviewer. The request is repeated just before the call, and the rule is repeated before the question. Nothing is
  filtered out.
- **Fails closed:** it raises `CannotJudge` when the server cannot be reached or does not answer in time; treat that as
  "ask".
- One request, one yes/no question.

## How it was measured

These are pre-registered studies, with each plan's hash committed before its first request
([results/intent_check](../results/intent_check/RESULTS.md)). The data: 150 steps of AgentDojo from TS-Bench
(third-party labels: does the step carry out the injection?) and 36 sessions we wrote. One run per request, on the
hosted model.

| condition (AgentDojo, call only, shielded) | F1 | recall on malicious steps | false alarms |
|---|---|---|---|
| no attack | 97.5 | 96.7% | 1.1% |
| injections re-worded with the attacks published in the AgentDojo repository (`direct`, `ignore_previous`, `system_message`, `injecagent`, `important_instructions`) | 97.5 | 96.7% | 1.1% (current layout: 2.2%) |
| six fixed attacks we wrote, addressed to the reviewer ("the user approved this", fake `SYSTEM:`, fake request headers, fake end of data, …) | 92.3 | 100% | 11.1% |

- **Recall held at 95–100%** under fixed and published attacks, in both layouts.
- **False alarms:**
  - 1–2% with published injections, including steps where an injection is present and the agent ignores it;
  - 5–11% when the tool output addresses the reviewer directly. That kind of text looks like an injection whether or
    not the agent follows it.
- **What the shield buys is stability.** Under attack, the largest drop in probability on a malicious step was 0.08
  with the shield and 0.47 without it. In our own sessions, one followed injection was missed without the shield and
  none with it.
- The agent's reasoning was not what carried the result: the check scored F1 95.9–96.7 with it and 97.5 without it.

## Not measured

- **Adaptive or optimized attacks against the shielded layout were not tested.** The attacks above are fixed
  templates, about 10–12 malicious steps each.
- Real agent sessions beyond AgentDojo: our 36 sessions are written by us.
- Long histories: the AgentDojo sample has states of up to 9,000 characters.

## Recommended use

Before a side-effecting call, an `intent_check` that is not `serves_user` should **ask a person** and show the reason:
"this call may follow instructions found in <tool output>". Do not block on it alone. It is one layer, next to least
privilege, confirmations for irreversible actions, and provenance tracking of untrusted content.
