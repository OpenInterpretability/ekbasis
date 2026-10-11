"""Claude Code transcripts (JSONL): what the user typed and each tool call with its result, from the tail of the file.
Standard library only."""
from __future__ import annotations

import json

TAIL_BYTES = 768 << 10     # read at most the last 768 KiB of a transcript


def content_text(content) -> str:
    """The text of a message or tool-result content (a string, or a list of blocks of which the text ones count)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ""


def events(path: str, tail_bytes: int = TAIL_BYTES, skip_tool_use: str | None = None) -> list:
    """[{"kind": "user", "text"} | {"kind": "tool", "name", "input", "result"}], oldest first, from the last
    `tail_bytes` of the transcript. Lines that do not parse (the first one, cut by the tail), meta messages, sidechains
    and calls without a result yet (skip_tool_use: the call being checked) are left out. The agent's own text is left
    out. Raises OSError when the file cannot be read."""
    with open(path, "rb") as fh:
        fh.seek(0, 2)
        end = fh.tell()
        fh.seek(max(0, end - tail_bytes))
        raw = fh.read().decode("utf-8", errors="replace")
    out, calls = [], {}
    for line in raw.splitlines():
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if not isinstance(d, dict) or d.get("isSidechain") or d.get("isMeta"):
            continue
        msg = d.get("message") if isinstance(d.get("message"), dict) else {}
        content = msg.get("content")
        if d.get("type") == "assistant" and isinstance(content, list):
            for b in content:
                if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("id") != skip_tool_use:
                    e = {"kind": "tool", "name": str(b.get("name", "")), "input": b.get("input") or {}, "result": ""}
                    calls[b.get("id")] = e
                    out.append(e)
        elif d.get("type") == "user":
            results = [b for b in content if isinstance(b, dict) and b.get("type") == "tool_result"] \
                if isinstance(content, list) else []
            for b in results:
                e = calls.get(b.get("tool_use_id"))
                if e is not None:
                    e["result"] = content_text(b.get("content"))
            if not results:
                text = content_text(content)
                if text.strip() and not text.lstrip().startswith(("<command-", "<local-command", "<system-reminder")):
                    out.append({"kind": "user", "text": text})
    return [e for e in out if e["kind"] == "user" or e["result"]]
