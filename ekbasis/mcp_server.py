"""MCP server (stdio) that lets any MCP-capable agent ask Ekbasis before acting.

Install: pip install "./ekbasis[mcp]"; register the command `ekbasis-mcp` in your MCP client (server URL from
EKBASIS_URL). Tools:
- check_git_commands: before running git commands, the probability that they lose uncommitted work, that each fails,
  that a merge or rebase is left unfinished, and the branch at the end;
- predict_consequences: typed questions about the state after some actions, given the rules and the current state.
"""
from __future__ import annotations

try:  # MCP Python SDK 2.x
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:
    try:  # 1.x
        from mcp.server.fastmcp import FastMCP as _Server
    except ImportError:
        raise SystemExit('ekbasis-mcp needs the MCP Python SDK (Python >= 3.10): pip install "ekbasis[mcp]"') from None

from . import git as G
from .client import Ekbasis
from .prompts import world_state

mcp = _Server("ekbasis")


@mcp.tool()
def check_git_commands(commands: list[str], repo: str = ".", fetch: bool = False) -> dict:
    """Before running git commands in a repository: what they will do. Returns p_lost (uncommitted work lost for good),
    p_fail per command, p_in_progress (a merge or rebase left unfinished), the predicted branch at the end, and risky
    (p_lost >= 0.2) with the reasons. Nothing is executed; only read-only git commands describe the repository
    (and git fetch when fetch is true)."""
    v = G.check(commands, repo=repo, fetch=fetch)
    return {"risky": v.risky, "reasons": v.reasons, "p_lost": round(v.p_lost, 4), "p_fail": [round(p, 4) for p in v.p_fail],
            "p_in_progress": round(v.p_in_progress, 4), "branch": list(v.branch) if v.branch else None}


@mcp.tool()
def predict_consequences(rules: str, state: str, actions: list[str], questions: dict) -> dict:
    """What will the state be after these actions? rules: how the world works, in words. state: how things stand now.
    actions: what will be done, in order. questions: {name: {"type": "noul", "instructions": "Is X on?"}} for yes/no,
    or {name: {"type": "choice", "instructions": "...?", "criteria": {"label": "description", ...}}}. Returns, per
    question, the answer, its confidence and every option's probability. For long sequences, ask one action at a time
    and carry the state forward."""
    ans = Ekbasis().ask(world_state(rules, state, actions), questions)
    return {k: {"answer": a.value, "confidence": round(a.confidence, 4),
                "probabilities": {o: round(p, 4) for o, p in a.probabilities.items()}} for k, a in ans.items()}


def main():
    mcp.run()


if __name__ == "__main__":
    main()
