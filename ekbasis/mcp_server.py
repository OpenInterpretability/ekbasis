"""MCP server (stdio) that lets any MCP-capable agent ask Ekbasis before acting.

Install: pip install "./ekbasis[mcp]"; register the command `ekbasis-mcp` in your MCP client (server URL from
EKBASIS_URL). Tools:
- check_git_commands: before running git commands, the probability that they lose uncommitted work, that each fails,
  that a merge or rebase is left unfinished, and the branch at the end; when risky, the safer route with the same
  intent that Ekbasis checked;
- predict_consequences: typed questions about the state after some actions, given the rules and the current state;
- preflight_command (since 0.1.6): before a multi-step change runs (a sqlite3 run of several statements, a shell
  script, a chain of commands), which step fails first and whether the failure would leave the change half applied.
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
from . import preflight as PF
from . import safer as SF
from .client import Ekbasis
from .prompts import world_state

mcp = _Server("ekbasis")


@mcp.tool()
def check_git_commands(commands: list[str], repo: str = ".", fetch: bool = False, safer: bool = True) -> dict:
    """Before running git commands in a repository: what they will do. Returns p_lost (uncommitted work lost for good),
    p_fail per command, p_in_progress (a merge or rebase left unfinished), the predicted branch at the end, and risky
    (p_lost >= 0.2) with the reasons. When risky, safer is the alternative with the same intent that Ekbasis checked
    and found safe ({commands: run them in order, p_lost, keeps: what it keeps recoverable}); prefer running it. It is
    null when none passed the check (safer_note says why) or when safer is false. Nothing is executed; only read-only
    git commands describe the repository (and git fetch when fetch is true)."""
    client = Ekbasis(surface="mcp")
    v = G.check(commands, repo=repo, fetch=fetch, client=client)
    route = SF.search(v.commands, repo=repo, client=client) if v.risky and safer else None
    return {"risky": v.risky, "reasons": v.reasons, "p_lost": round(v.p_lost, 4), "p_fail": [round(p, 4) for p in v.p_fail],
            "p_in_progress": round(v.p_in_progress, 4), "branch": list(v.branch) if v.branch else None,
            "safer": route.as_json() if route else None, "safer_note": route.note if route and not route.route else None}


@mcp.tool()
def predict_consequences(rules: str, state: str, actions: list[str], questions: dict) -> dict:
    """What will the state be after these actions? rules: how the world works, in words. state: how things stand now.
    actions: what will be done, in order. questions: {name: {"type": "noul", "instructions": "Is X on?"}} for yes/no,
    or {name: {"type": "choice", "instructions": "...?", "criteria": {"label": "description", ...}}}. Returns, per
    question, the answer, its confidence and every option's probability. For long sequences, ask one action at a time
    and carry the state forward."""
    ans = Ekbasis(surface="mcp").ask(world_state(rules, state, actions), questions)
    return {k: {"answer": a.value, "confidence": round(a.confidence, 4),
                "probabilities": {o: round(p, 4) for o, p in a.probabilities.items()}} for k, a in ans.items()}


@mcp.tool()
def preflight_command(command: str, cwd: str = ".") -> dict:
    """Before running a multi-step change (e.g. "sqlite3 app.db < migrations/0012.sql", "bash scripts/reorg.sh", or
    "mkdir -p a && mv x a/ && rm -r old"): which step fails first and why, which steps would already have run and which
    would still run, and risky (a failure would leave the change half applied). Local files and SQLite are checked by
    running the plan on a copy (by="copy"; shell steps only inside the macOS sandbox, SQL where the sqlite3 tool is
    installed); anything else is asked to the model (by="model"); by="code" when the sqlite3 tool is not installed, so
    the line fails before any statement runs (note says why). The real files are never touched. multi_step is false
    when the line has fewer than two steps that change something."""
    v = PF.check_line(command, cwd)
    if v is None:
        return {"multi_step": False}
    return {"multi_step": True, "risky": v.risky, "cannot_judge": v.cannot_judge, "cannot_foresee": v.cannot_judge, "by": v.by, "first": v.first,
            "p_fail": [round(p, 4) for p in v.p_fail], "steps": [s.text for s in v.plan.steps],
            "applied_before": v.applied_before, "runs_after": v.runs_after, "atomic": v.atomic, "error": v.error,
            "reason": v.reason, "note": v.copy_note or None, "message": v.message() if v.risky else None}


def main():
    mcp.run()


if __name__ == "__main__":
    main()
