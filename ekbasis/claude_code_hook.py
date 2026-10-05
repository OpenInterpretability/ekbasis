"""Claude Code PreToolUse hook: before the Bash tool runs git commands, ask Ekbasis what they will do. If they may
permanently lose uncommitted work, Claude Code asks you to confirm (or blocks, EKBASIS_GUARD_MODE=deny), showing why.

The guard is a warning layer that can be wrong, not a security boundary: keep Claude Code's confirmations, backups and
least privilege (docs/SECURITY.md).

It fails closed (0.1.2): when it cannot judge a line (the server cannot be reached or does not answer in time, the
repository or folder cannot be read, git is pointed at another repository, the line changes folder in a way the hook
does not follow, or it has parts the hook cannot evaluate such as subshells, variables in a git command, nested shells,
git aliases), Claude Code asks you to confirm, saying why. EKBASIS_FAIL_OPEN=1 restores 0.1.1's behaviour (say nothing
and let the command go through Claude Code's normal permission flow). A hook only blocks or asks through its JSON
answer; an exit code other than 2 does not block, so this hook always answers in JSON and exits 0.

Opt-in (a prototype): with EKBASIS_SHELL_GUARD=1, a Bash line that has no git command but can change files (rm, mv,
cp, rsync, find, sed -i, tar, a `>` redirection, ...) goes to the shell guard (ekbasis.shell), with the same threshold,
mode and fail-closed rule. Git lines are checked as before.

Install (after `pip install ./ekbasis`), in .claude/settings.json (one project) or ~/.claude/settings.json (all):
  {"hooks": {"PreToolUse": [{"matcher": "Bash",
                             "hooks": [{"type": "command", "command": "ekbasis-claude-hook", "timeout": 30}]}]}}
env: EKBASIS_URL (server), EKBASIS_LOST_THRESHOLD (0.2), EKBASIS_GUARD_MODE (ask | deny), EKBASIS_FETCH (1: git fetch
first so the state shows the real remote; slower), EKBASIS_SHELL_GUARD (1: also check other lines that change files),
EKBASIS_FAIL_OPEN (1: stay silent when it cannot judge), EKBASIS_HOOK_DEADLINE (seconds, default 25: keep it below the
hook's "timeout", or Claude Code stops the hook first and the command goes through unchecked).
"""
from __future__ import annotations

import json
import os
import re
import shlex
import sys
import threading

from . import git as G
from . import shell as S
from .client import CannotJudge, Ekbasis

QUIET_REDIRECT = re.compile(r"[0-9&]*>>?\s*/dev/null|[0-9]*>&[0-9-]")
CHANGES_FILES = re.compile(r"(^|[\s;&|(])(rm|rmdir|unlink|mv|cp|rsync|shred|truncate|ln|tar|unzip|dd|install|xargs|tee|"
                           r"perl|chmod|chown|find)(\s|$)|(^|[\s;&|(])sed\s+(-[a-zA-Z]*i|--in-place)|>")
GIT_WORD = re.compile(r"(^|[\s;&|(`'\"/])git(\s|$)")
GIT_ENV = re.compile(r"^GIT_(DIR|WORK_TREE|INDEX_FILE|OBJECT_DIRECTORY|COMMON_DIR|NAMESPACE)=")
STRUCTURE = {S.P_SUBSHELL, S.P_GROUP, S.P_PROCSUB, S.P_QUOTE, S.P_HEREDOC_OPEN}


def git_commands(command: str) -> tuple[str | None, list[str]]:
    """The git commands in a shell command line, and a leading `cd DIR` (the 0.1.1 helper, kept for callers)."""
    where, cmds, _ = read_line(command)
    return where, cmds


def read_line(command: str) -> tuple[str | None, list[str], list[str]]:
    """(a leading `cd DIR`, the git commands as strings, why the line cannot be judged). Reasons: structure the hook
    does not follow (subshells, grouping, an unclosed quote), a cd/pushd/popd other than a leading cd, a variable or
    substitution in a git command (a commit message's value is fine), GIT_DIR-like variables, git run inside a nested
    shell, eval or xargs."""
    ps = S.parse(command)
    where, cmds, why = None, [], []
    gitlike = bool(GIT_WORD.search(command))
    for j, s in enumerate(ps.commands):
        name, at, _ = S.command_name(list(s.words))
        args = s.words[at + 1:]
        if name == "cd" and j == 0 and len(args) <= 1 and not any(w.dynamic for w in args):
            where = args[0].text if args else "~"
            continue
        if name in ("cd", "pushd", "popd") and gitlike:
            why.append("the line changes folder in a way the hook does not follow")
        if name in S.NESTED and gitlike and (name in ("eval", "source", ".") or any(w.text == "-c" for w in args)):
            why.append("git may run inside a nested shell or eval")
        if name == "xargs" and any(w.text == "git" for w in args):
            why.append("git runs through xargs")
        if name != "git":
            continue
        if any(GIT_ENV.match(w.text) for w in s.words[:at]):
            why.append("a GIT_DIR-like variable points git elsewhere")
        if any(w.dynamic and not (i > 0 and args[i - 1].text in S.MESSAGE_OPTS) for i, w in enumerate(args)):
            why.append("a git command has a variable or substitution the hook does not evaluate")
        cmds.append(shlex.join(["git"] + [w.text for w in args]))
    if cmds or gitlike:
        why += [p for p in ps.problems if p in STRUCTURE]
    return where, cmds, list(dict.fromkeys(why))


def changes_files(command: str) -> bool:
    """Whether a line has a command that can change files (redirections to /dev/null do not count)."""
    return bool(CHANGES_FILES.search(QUIET_REDIRECT.sub(" ", command)))


def _decide(reason: str) -> None:
    mode = "deny" if os.environ.get("EKBASIS_GUARD_MODE") == "deny" else "ask"
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": mode,
                                             "permissionDecisionReason": reason}}))


def _cannot_judge(why: str) -> int:
    if os.environ.get("EKBASIS_FAIL_OPEN") == "1":
        print(f"ekbasis hook: cannot judge ({why}); EKBASIS_FAIL_OPEN=1: letting it through", file=sys.stderr)
        return 0
    _decide(f"Ekbasis could not judge this command ({why}). Confirm it only if you know it is safe.")
    return 0


def _with_deadline(fn, seconds: float):
    """fn() in a thread; CannotJudge if it does not finish in time (the thread is abandoned)."""
    out = {}

    def run():
        try:
            out["v"] = fn()
        except BaseException as e:  # noqa: BLE001  (re-raised below)
            out["e"] = e

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(seconds)
    if t.is_alive():
        raise CannotJudge(f"the check did not finish within {seconds:g} s")
    if "e" in out:
        raise out["e"]
    return out["v"]


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except (ValueError, OSError) as e:
        return _cannot_judge(f"could not read the hook input: {e}")
    try:
        if data.get("tool_name") != "Bash":
            return 0
        line = (data.get("tool_input") or {}).get("command", "")
        cwd = data.get("cwd") or os.getcwd()
        threshold = float(os.environ.get("EKBASIS_LOST_THRESHOLD", "0.2"))
        deadline = float(os.environ.get("EKBASIS_HOOK_DEADLINE", "25"))
        client = Ekbasis(timeout=deadline)
        where, cmds, why = read_line(line)
        if why:
            return _cannot_judge("; ".join(why))
        if not cmds:
            if os.environ.get("EKBASIS_SHELL_GUARD") != "1" or not changes_files(line):
                return 0
            v = _with_deadline(lambda: S.check([line], cwd=cwd, client=client, lost_threshold=threshold), deadline)
            if v.risky:
                what = "could not judge every part of the line" if not v.lost_risky else "; ".join(v.reasons)
                _decide(f"Ekbasis (shell guard): {what}. Line: {line}. Consider keeping a copy of the files first.")
            return 0
        repo = os.path.normpath(os.path.join(cwd, os.path.expanduser(where))) if where else cwd
        problem = G.readable(repo)
        if problem:
            if "not a git repository" in problem.lower() and not any(G.other_repo(c) for c in cmds):
                return 0  # outside a repository the git commands fail or create one: nothing uncommitted to lose
            return _cannot_judge(f"cannot read a git repository at {repo}: {problem}")
        v = _with_deadline(lambda: G.check(cmds, repo=repo, client=client, fetch=os.environ.get("EKBASIS_FETCH") == "1",
                                           lost_threshold=threshold), deadline)
    except CannotJudge as e:
        return _cannot_judge(str(e))
    except Exception as e:  # noqa: BLE001  (anything else: cannot judge)
        return _cannot_judge(f"{type(e).__name__}: {e}")
    if v.risky:
        _decide(f"Ekbasis: {'; '.join(v.reasons)}. Commands: {' ; '.join(cmds)}. "
                "Consider saving the work first (commit, or git stash -u).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
