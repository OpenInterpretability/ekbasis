# Tool guard (prototype)

The git and shell guards read the repository or the folder themselves. Any other tool call (send an email, delete a
folder, move money, drop a table, delete a namespace, change who can open a file) has no such state, and almost nobody
writes one by hand. The tool guard builds it from what the agent has already seen, and asks Ekbasis before the call.

**A warning layer that can be wrong, not a security boundary**, and a prototype: measured only on scenarios we wrote
([results/toolguard_pilot](../results/toolguard_pilot/RESULTS.md)).

## What it does

1. **Read-only calls are not asked about** (`toolguard.read_only`): built-in reading tools (Read, Grep, Glob,
   WebFetch, ...), names with a reading verb and no changing word (`list_files`, `get_issue`; `get_or_create_user` is
   asked about), MCP tools annotated `readOnlyHint`, SQL that only selects. Unknown verbs are asked about.
2. **The state is quoted, never written** (`toolguard.build_state`): the user's last request, the tool's description
   when known, and the earlier tool results that mention what the call touches (ids, names, paths, addresses,
   amounts) — the matching JSON object whole, or the matching lines with their neighbours and the header — plus the
   latest short results whole. About 2,000 tokens at most, newest first. It ends with
   `About to: <tool>(<arguments>)`.
3. **Fixed yes/no questions with written criteria**, one request: content someone may still need destroyed for good;
   money beyond what was asked or covered; information sent outside the intended audience; more access than asked;
   something in production use stopped; and, when a user request is known, whether the call does what was asked.
4. **Verdict**: `risky` (a harm ≥ 0.5, or likely not what was asked), `cannot_foresee` (a harm from 0.2), `ok`. A
   caller treats `cannot_foresee` like `risky`; a server that cannot be reached raises `CannotJudge` (fail closed).

```python
from ekbasis import toolguard
v = toolguard.check("mcp__drive__delete_folder", {"folder_id": "fld_201"}, events)
# events: [{"kind": "user", "text": ...}, {"kind": "tool", "name": ..., "input": {...}, "result": "..."}, ...]
print(v.verdict, v.p, v.message())
```

## Claude Code

Opt-in in the existing hook: `EKBASIS_TOOL_GUARD=1`, and give the hook the tools to guard. The hook reads the tail of
the session's transcript (`transcript_path`) for the user's request and earlier tool results. Bash keeps the git and
shell checks; local file edits (Write, Edit) are left to Claude Code's checkpoints and the git guard.

```json
{"hooks": {"PreToolUse": [
  {"matcher": "Bash", "hooks": [{"type": "command", "command": "ekbasis-claude-hook", "timeout": 30}]},
  {"matcher": "mcp__.*", "hooks": [{"type": "command", "command": "EKBASIS_TOOL_GUARD=1 ekbasis-claude-hook", "timeout": 30}]}
]}}
```

`"matcher": "*"` also works (read-only calls cost nothing: no request). A risky or cannot-foresee forecast answers
`permissionDecision: "ask"` with a one-line reason (`deny` with `EKBASIS_GUARD_MODE=deny`); otherwise the hook stays
silent. `EKBASIS_TOOL_THRESHOLD` (0.5), `EKBASIS_FAIL_OPEN`, `EKBASIS_HOOK_DEADLINE` as for the other checks. Claude
Code documents that the transcript may lag the current turn: a result that arrived just before the call can be missing.

## Any MCP client

```bash
python3 -m ekbasis.mcp_guard [--mode block|warn] [--threshold 0.5] [--no-repeat] [--fail-open] -- <server command>
```

Register this instead of the server's own command. It relays MCP stdio traffic unchanged (standard library only),
keeps the tool descriptions and the results it relays as context, and checks each side-effecting `tools/call` first.
`block` (default) returns a tool result with `isError` and the forecast instead of calling; the same call repeated
goes through (so a user who confirms can have the agent retry; `--no-repeat` turns that off). `warn` calls the tool
and puts the forecast before the result. MCP traffic does not carry the user's request, so "does what was asked" is
not asked there.

## Known limits (measured on our scenarios)

- **A missing fact is not "cannot tell".** When the session never showed the deciding fact, the forecast falls back
  to a prior: cautious for deletions (flagged), permissive for sends, transfers and cancellations (let through: 4 of 4
  such cases in the pilot under the current rule).
- **Tool results are untrusted text** and go into the state; planted instructions there were not measured.
- **Cost:** ~2,400 input tokens and ~4.7 s per side-effecting call on the hosted API (p50).
- Bash lines that act on services (`curl -X DELETE`, `kubectl delete`, `psql -c "DROP ..."`) are not routed here yet.
