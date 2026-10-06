"""The README's steps, run end to end in a clean virtualenv against a real Ekbasis server: every step prints PASS or
FAILED, and the exit code is the number of FAILED steps.

Not run: step 1 of the quick start (downloading and serving the 55 GB model; the server is given), and
`claude mcp add` (it changes the user's Claude Code configuration); the MCP server itself is exercised over stdio.

usage: EKBASIS_URL=http://127.0.0.1:18642 python3.12 readme_run_013.py <what pip installs>
       (<what pip installs>: the candidate folder before publishing, or "git+https://github.com/OpenInterpretability/ekbasis")
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
README = os.path.join(os.path.dirname(HERE), "ekbasis", "README.md")
TARGET = sys.argv[1]
URL = os.environ["EKBASIS_URL"]
GENV = dict(os.environ, GIT_AUTHOR_NAME="Dev", GIT_AUTHOR_EMAIL="dev@example.invalid", GIT_COMMITTER_NAME="Dev",
            GIT_COMMITTER_EMAIL="dev@example.invalid", GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL="/dev/null")
RESULTS = []


def step(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS  ' if ok else 'FAILED'} {name}" + (f"  [{detail}]" if detail else ""), flush=True)


def run(cmd, cwd=None, env=None, input=None, timeout=600):
    p = subprocess.run(cmd, cwd=cwd, env=env or dict(os.environ), input=input, capture_output=True, text=True,
                       timeout=timeout)
    return p.returncode, p.stdout + p.stderr


def block(heading, lang="python", index=0):
    """The index-th code block of a language under a README heading."""
    text = open(README).read()
    sec = text[text.index(heading):]
    nxt = re.search(r"\n## ", sec[3:])
    sec = sec[:nxt.start() + 3] if nxt else sec
    blocks = re.findall(r"```" + lang + r"\n(.*?)```", sec, re.S)
    return blocks[index]


def main():
    tmp = tempfile.mkdtemp(prefix="ekb_readme_")
    venv = os.path.join(tmp, "venv")
    bin_ = os.path.join(venv, "bin")
    env = dict(os.environ, EKBASIS_URL=URL, PATH=bin_ + ":" + os.environ["PATH"])
    # Quick start 2: install, health
    rc, out = run([sys.executable, "-m", "venv", venv])
    rc, out = run([os.path.join(bin_, "pip"), "install", "-q", TARGET], timeout=900)
    step("pip install the client (" + ("GitHub" if TARGET.startswith("git+") else "candidate folder") + ")", rc == 0,
         out[-300:] if rc else "")
    rc, out = run([os.path.join(bin_, "python"), "-c", "import ekbasis; print(ekbasis.__version__)"])
    step("version is 0.1.3", rc == 0 and out.strip() == "0.1.3", out.strip())
    rc, out = run(["ekbasis", "health"], env=env)
    step("ekbasis health", rc == 0, out.strip()[:120])
    # Quick start 3: git-check in a repository with a changed app.py
    repo = os.path.join(tmp, "repo")
    os.makedirs(repo)
    for c in ("git init -q -b main", "echo v1 > app.py", "git add -A", "git commit -qm init", "git branch feature",
              "echo v2 > app.py"):
        subprocess.run(["bash", "-c", c], cwd=repo, env=GENV, check=True, capture_output=True)
    rc, out = run(["ekbasis", "git-check", "--", "git checkout -- app.py"], cwd=repo, env={**env, **{
        k: GENV[k] for k in ("GIT_CONFIG_NOSYSTEM", "GIT_CONFIG_GLOBAL")}})
    step("ekbasis git-check -- \"git checkout -- app.py\" is RISKY (exit 2)", rc == 2 and "RISKY" in out,
         out.strip().splitlines()[0] if out.strip() else "")
    # Python: the README's block, verbatim, run in the repository
    code = block("## Python")
    rc, out = run([os.path.join(bin_, "python"), "-c", code], cwd=repo, env=env)
    step("README Python block runs", rc == 0, out.strip().replace("\n", " | ")[:300])
    # Look when unsure: the README's block with the names it leaves to the reader defined first (a card ordering)
    prelude = textwrap.dedent('''
        from ekbasis import Ekbasis, choice, simulate
        client = Ekbasis()
        rules = ("World: three cards in a row, positions 1, 2 and 3. 'swap X and Y' exchanges the cards at positions "
                 "X and Y; nothing else moves.")
        cards = ["7", "Q", "K"]
        state = {"p1": "7", "p2": "Q", "p3": "K"}
        actions = ["swap 1 and 2", "swap 2 and 3", "swap 1 and 3", "swap 1 and 2"]
        questions = {f"p{i}": choice(f"Which card is at position {i}?", cards) for i in (1, 2, 3)}
        render = lambda s: ", ".join(f"position {i}: {s[f'p{i}']}" for i in (1, 2, 3))
        truth = [dict(state)]
        for a in actions:
            x, y = a.split()[1], a.split()[3]
            s = dict(truth[-1]); s[f"p{x}"], s[f"p{y}"] = s[f"p{y}"], s[f"p{x}"]; truth.append(s)
        def read_real_state(k=None, *args, **kw):
            k = len(truth) - 1 if k is None else k
            return truth[min(k, len(truth) - 1)]
    ''')
    rc, out = run([os.path.join(bin_, "python"), "-c", prelude + block("## Look when unsure")], cwd=repo, env=env)
    step("README Look-when-unsure block runs", rc == 0, out.strip().replace("\n", " | ")[:300])
    # Recap on the command line
    rc, out = run(["ekbasis", "predict", "--rules", "A disk can never be placed on a smaller disk.",
                   "--state", "Peg A: small disk on top of big disk. Peg B: empty.", "--action", "move big disk to B",
                   "--question", "Is the big disk on peg B?", "--recap"], env=env)
    step("ekbasis predict --recap", rc == 0, out.strip()[:120])
    # Read-once
    rc, out = run([os.path.join(bin_, "python"), "-c", textwrap.dedent('''
        from ekbasis import Ekbasis, world_state, yes_no
        c = Ekbasis()
        a = c.ask(world_state("A lamp is on or off; 'toggle' flips it.", "The lamp is off.", ["toggle"]),
                  {"on": yes_no("Is the lamp on?"), "off": yes_no("Is the lamp off?")}, read_once=True)
        print(a["on"].value, a["off"].value)
    ''')], env=env)
    step("client.ask(..., read_once=True)", rc == 0, out.strip()[:120])
    # Claude Code hook: the JSON Claude Code sends, through the installed command
    def hook(line, cwd, extra=None):
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": line}, "cwd": cwd})
        rc, out = run(["ekbasis-claude-hook"], env={**env, **(extra or {}), "GIT_CONFIG_NOSYSTEM": "1",
                                                     "GIT_CONFIG_GLOBAL": "/dev/null"}, input=payload)
        d = json.loads(out)["hookSpecificOutput"]["permissionDecision"] if out.strip().startswith("{") else None
        return rc, d
    rc, d = hook("git reset --hard", repo)
    step("hook asks before `git reset --hard` with a changed file", rc == 0 and d == "ask", str(d))
    rc, d = hook("ls -la && git status", repo)
    step("hook stays silent on `ls -la && git status`", rc == 0 and d is None, str(d))
    rc, d = hook("git worktree add -q ../wt feature && cd ../wt && git log -1", repo)
    step("hook lets the worktree route through (0.1.3)", rc == 0 and d is None, str(d))
    open(os.path.join(repo, "notes.md"), "w").write("mine\n")
    rc, d = hook("rm notes.md", repo, {"EKBASIS_SHELL_GUARD": "1"})
    step("hook (EKBASIS_SHELL_GUARD=1) asks before deleting an untracked file", rc == 0 and d == "ask", str(d))
    # Shell guard on the command line
    box = os.path.join(tmp, "box")
    os.makedirs(os.path.join(box, "build"))
    open(os.path.join(box, "build", "out.txt"), "w").write("x\n")
    rc, out = run(["ekbasis", "shell-check", "--", "rm -r build/"], cwd=box, env=env)
    step("ekbasis shell-check -- \"rm -r build/\" answers", rc in (0, 2) and "Ekbasis:" in out,
         out.strip().splitlines()[0] if out.strip() else "")
    # MCP server (Python >= 3.10): install the extra, then talk to it over stdio
    rc, out = run([os.path.join(bin_, "pip"), "install", "-q", TARGET + ("[mcp]" if not TARGET.startswith("git+")
                                                                         else "")] if not TARGET.startswith("git+") else
                  [os.path.join(bin_, "pip"), "install", "-q", "ekbasis[mcp] @ " + TARGET], timeout=900)
    step("pip install the [mcp] extra", rc == 0, out[-200:] if rc else "")
    mcp_code = textwrap.dedent(f'''
        import asyncio, json, os
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        async def main():
            params = StdioServerParameters(command="ekbasis-mcp", env=dict(os.environ))
            async with stdio_client(params) as (r, w):
                async with ClientSession(r, w) as s:
                    await s.initialize()
                    tools = sorted(t.name for t in (await s.list_tools()).tools)
                    res = await s.call_tool("check_git_commands", {{"commands": ["git checkout -- app.py"], "repo": {repo!r}}})
                    print(json.dumps({{"tools": tools, "text": res.content[0].text[:200]}}))
        asyncio.run(main())
    ''')
    rc, out = run([os.path.join(bin_, "python"), "-c", mcp_code], env={**env, "GIT_CONFIG_NOSYSTEM": "1",
                                                                       "GIT_CONFIG_GLOBAL": "/dev/null"})
    ok = rc == 0 and "check_git_commands" in out and "predict_consequences" in out
    step("ekbasis-mcp lists its tools and answers check_git_commands", ok, out.strip()[-300:])
    shutil.rmtree(tmp, ignore_errors=True)
    failed = sum(1 for _, ok in RESULTS if not ok)
    print(json.dumps({"steps": len(RESULTS), "failed": failed, "target": "GitHub" if TARGET.startswith("git+") else
                      "candidate folder", "server": URL}))
    return failed


if __name__ == "__main__":
    sys.exit(main())
