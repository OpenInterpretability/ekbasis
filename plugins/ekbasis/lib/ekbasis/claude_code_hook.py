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
mode and fail-closed rule.

0.1.3 (from the real-terminal study, capability/real_terminal): less friction, same prompts where nothing changed.
- Read-only git (status, log, diff, show, branch/tag/stash/worktree listings, ...) does not ask the model.
- `cd DIR` anywhere in the line, `pushd`/`popd`, subshells `( ... )` and `git -C DIR` are followed instead of "cannot
  judge"; a folder that an earlier `git worktree add` (or `git clone`, `mkdir`) of the same line creates is known to
  hold no uncommitted work, so the worktree route (`git worktree add ../wt b && cd ../wt && git cherry-pick X`) passes.
- With EKBASIS_SHELL_GUARD=1, the shell part of a line that also runs git (its other commands, and redirections of the
  git commands) goes to the shell guard too.
- No model call (and no ask) when nothing could be lost for good: a repository with no uncommitted work, or, for the
  shell guard, when every path the line could change is committed in git or ignored and rebuildable (ekbasis.recover).
  EKBASIS_SHORTCUTS=0 turns these code checks off (0.1.2's behaviour: the model is asked).
- Lost committed work, a separate check done by code: branch deletion (-D), forced branch moves, `reset <commit>`,
  tag deletion and the like that leave commits no branch, tag, remote-tracking branch or stash holds (git.committed_loss).

Since 0.1.6: preflight, opt-in with EKBASIS_PREFLIGHT=1 (ekbasis.preflight). A line that runs a multi-step
change (a sqlite3 run of several statements, a shell script, a chain of commands with two or more steps that change
something) is checked before it runs: on a copy when it can be (local files and SQLite; shell steps only inside the
macOS sandbox; EKBASIS_PREFLIGHT_COPY=0 turns that off), otherwise by Ekbasis, and code works out whether the first
failure would leave the change half applied. Only
that case warns; a plan that fails atomically, or a failing check that only reads, does not. In a headless run an "ask"
is a denial, so the warning says so and the same command in the same session goes through the second time
(EKBASIS_PREFLIGHT_REPEAT=0: always warn). When preflight cannot judge a line it says nothing
(EKBASIS_PREFLIGHT_FAIL_CLOSED=1: it warns once, the same way).

Install (after `pip install ./ekbasis`), in .claude/settings.json (one project) or ~/.claude/settings.json (all):
  {"hooks": {"PreToolUse": [{"matcher": "Bash",
                             "hooks": [{"type": "command", "command": "ekbasis-claude-hook", "timeout": 30}]}]}}
env: EKBASIS_URL (server), EKBASIS_LOST_THRESHOLD (0.2), EKBASIS_GUARD_MODE (ask | deny | log: never block, record what it would do in
~/.cache/ekbasis/hook_log.jsonl or EKBASIS_HOOK_LOG), EKBASIS_FETCH (1: git fetch
first so the state shows the real remote; slower), EKBASIS_SHELL_GUARD (1: also check other lines that change files),
EKBASIS_FAIL_OPEN (1: stay silent when it cannot judge), EKBASIS_HOOK_DEADLINE (seconds, default 25, for the whole
line: keep it below the hook's "timeout", or Claude Code stops the hook first and the command goes through unchecked),
EKBASIS_SHORTCUTS (0: always ask the model, as 0.1.2 did), EKBASIS_PREFLIGHT (1: check multi-step changes before they run),
EKBASIS_PREFLIGHT_REPEAT (1, the default: a warned command passes when it is run again in the same session),
EKBASIS_GIT_GUARD (0: no git checks, for preflight alone), EKBASIS_PREFLIGHT_COPY (0: never run on a copy),
EKBASIS_PREFLIGHT_FAIL_CLOSED (1: warn when preflight cannot judge), EKBASIS_SAFER (0: no safer route),
EKBASIS_REMOTE_CHECK (0: do not read the remote with git ls-remote before forced or mirror pushes; 0.1.23),
EKBASIS_REQUEST (1: experimental, give the guards the last message the user typed; 0.1.23),
EKBASIS_GUARD_REPEAT (1: warn once, the same command run again goes through; 0.1.24).

0.1.42: a variable set earlier on the same line to a known value (`G=/repo; git -C "$G" status`, `D=build; rm -rf
"$D"`) is read with that value by the git guard and the shell guard (ekbasis.shell.resolve); any other variable (from the
environment, set twice, exported, read, set in a loop or a condition, or by command substitution) is still not guessed:
"cannot foresee", as before. Preflight never names as failing a step that runs code given inline to an interpreter or
runs on another machine (the other steps are still judged), and says nothing on loops and conditions written on one
line (it cannot judge them).

Safer route: when the hook warns about git commands, it also offers the alternative with the same intent that Ekbasis
checked and found safe (ekbasis.safer), e.g. `git stash push && git reset --hard`, or says that none passed. It is
searched last, in the time the deadline leaves; when the search cannot finish, the warning goes out without a route.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field

from . import git as G
from . import preflight as PF
from . import prompts as P
from . import recover as R
from . import safer as SF
from .redact import redact
from . import shell as S
from .client import CannotJudge, Ekbasis

QUIET_REDIRECT = re.compile(r"[0-9&]*>>?\s*/dev/null|[0-9]*>&[0-9-]")
CHANGES_FILES = re.compile(r"(^|[\s;&|(])(rm|rmdir|unlink|mv|cp|rsync|shred|truncate|ln|tar|unzip|dd|install|xargs|tee|"
                           r"perl|chmod|chown|find)(\s|$)|(^|[\s;&|(])sed\s+(-[a-zA-Z]*i|--in-place)|>")
GIT_WORD = re.compile(r"(^|[\s;&|(`'\"/])git(\s|$)")
GIT_ENV = re.compile(r"^GIT_(DIR|WORK_TREE|INDEX_FILE|OBJECT_DIRECTORY|COMMON_DIR|NAMESPACE)=")
STRUCTURE = {S.P_SUBSHELL, S.P_GROUP, S.P_PROCSUB, S.P_QUOTE, S.P_HEREDOC_OPEN}
STRUCTURE_013 = STRUCTURE - {S.P_SUBSHELL}   # 0.1.3 follows subshells
CLONE_VALUE = ("-b", "--branch", "-o", "--origin", "--depth", "--reference", "-c", "--config", "-u", "--upload-pack",
               "--separate-git-dir", "--template", "-j", "--jobs", "--filter", "--shallow-since", "--shallow-exclude")


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


@dataclass
class Plan:
    steps: list = field(default_factory=list)   # git commands: {"repo", "cmd" (without -C), "fresh"}
    shell_line: str = ""                        # the line for the shell guard: git commands replaced by `true`
    why: list = field(default_factory=list)     # why the line cannot be judged


def _safe_branch_delete(command: str) -> bool:
    """git branch -d (without -D or force): git itself refuses to delete a branch that is not merged."""
    sub, args = P.parse_git(command)
    sf = P.short_flags(args)
    return sub == "branch" and ("d" in sf or "--delete" in args) and not (sf & {"D", "f"} or "--force" in args)


def _scoped(toks):
    """Simple commands and subshell marks from S.lex(line, parens=True): [("cmd", Simple) | ("(",) | (")",)]."""
    items, words, redirs, joined = [], [], [], ""
    i = 0
    while i < len(toks):
        t = toks[i]
        if isinstance(t, tuple):
            _, op, fd = t
            if op in ("(", ")") or op in S.CONTROL:
                if words or redirs:
                    items.append(("cmd", S.Simple(words, redirs, joined)))
                    words, redirs = [], []
                if op in ("(", ")"):
                    items.append((op,))
                    joined = ""
                else:
                    joined = op
            else:
                target = toks[i + 1] if i + 1 < len(toks) and isinstance(toks[i + 1], S.Word) else None
                redirs.append(S.Redirect(op, fd, target))
                if target is not None:
                    i += 1
        else:
            words.append(t)
        i += 1
    if words or redirs:
        items.append(("cmd", S.Simple(words, redirs, joined)))
    return items


def _without(line: str, simples) -> str:
    """The line with each of these simple commands' words replaced by `true` (their redirections stay)."""
    edits = []
    for sc in simples:
        ws = [w for w in sc.words if w.start >= 0]
        if not ws:
            continue
        edits.append((ws[0].start, ws[0].end, "true"))
        edits += [(w.start, w.end, "") for w in ws[1:]]
    for a, b, rep in sorted(edits, reverse=True):
        line = line[:a] + rep + line[b:]
    return line


def _read_only_whatever(args) -> bool:
    """0.1.23: a git command with a variable or substitution that only reads whatever the variable holds: its
    subcommand is a literal read-only one (status, log, show, diff, stash list/show, rev-parse, ...), no variable stands
    where an option could go in a command that has a writing option (log/show/diff --output), and git is not pointed at
    another repository with --git-dir/--work-tree. A variable -C folder is fine: reading changes nothing anywhere."""
    texts = [w.text for w in args]
    i = 0
    while i < len(args) and texts[i].startswith("-"):
        if texts[i].split("=", 1)[0] in ("--git-dir", "--work-tree"):
            return False
        i += 2 if texts[i] in ("-C", "-c") else 1
    if i >= len(args) or args[i].dynamic:
        return False
    rest = args[i:]
    cmd = shlex.join(["git"] + [w.text for w in rest])
    if not G.read_only(cmd):
        return False
    sub, _ = P.parse_git(cmd)
    if sub in G.OUTPUT_SUBS and any(w.dynamic and w.text[:1] in ("$", "`") for w in rest[1:]):
        return False  # the variable could hold --output=FILE
    return True


def plan_line(command: str, cwd: str) -> Plan:
    """0.1.3: the git commands of a line with the folder each runs in (following cd, pushd/popd, subshells and git -C),
    the folders the line itself creates (git worktree add, git clone, mkdir), the line for the shell guard, and why
    the line cannot be judged (structure the hook does not follow, variables in git commands, git in a nested shell,
    git through xargs unless it only lists or safely deletes, a folder it cannot tell)."""
    toks, problems = S.lex(command, parens=True)
    items = _scoped(S.resolve(toks))   # 0.1.42: variables set earlier on the line to a known value are read with it
    gitlike = bool(GIT_WORD.search(command))
    plan = Plan()
    depth, balanced = 0, True
    for it in items:
        depth += {"(": 1, ")": -1}.get(it[0], 0)
        balanced = balanced and depth >= 0
    balanced = balanced and depth == 0
    cur, scopes, dirstack, fresh, replaced = os.path.normpath(cwd), [], [], {}, []

    def at(base, target):
        return os.path.normpath(os.path.join(base, os.path.expanduser(target)))

    def fresh_of(path):
        p = path
        while True:
            if p in fresh:
                return fresh[p]
            parent = os.path.dirname(p)
            if parent == p:
                return None
            p = parent

    for it in items:
        if it[0] == "(":
            scopes.append((cur, list(dirstack)))
            continue
        if it[0] == ")":
            if scopes:
                cur, dirstack = scopes.pop()
            continue
        sc = it[1]
        name, k0, _ = S.command_name(list(sc.words))
        args = sc.words[k0 + 1:]
        if name in ("cd", "pushd"):
            targets = [w for w in args if not (w.text.startswith("-") and w.text != "-")]
            if any(w.dynamic for w in args) or len(targets) > 1 or (targets and targets[0].text == "-"):
                if gitlike:
                    plan.why.append("the line changes folder in a way the hook does not follow")
                cur = None
            elif cur is not None:
                new = at(cur, targets[0].text if targets else "~")
                if name == "pushd":
                    dirstack.append(cur)
                cur = new if (os.path.isdir(new) or fresh_of(new)) else None
            continue
        if name == "popd":
            cur = dirstack.pop() if dirstack else None
            continue
        if name in S.NESTED and gitlike and (name in ("eval", "source", ".") or any(w.text == "-c" for w in args)):
            plan.why.append("git may run inside a nested shell or eval")
        if name == "mkdir" and cur is not None:
            for w in args:
                if not w.text.startswith("-") and not w.dynamic:
                    fresh.setdefault(at(cur, w.text), {"kind": "dir"})
        if name == "xargs" and any(w.text == "git" for w in args):
            j = next(i for i, w in enumerate(args) if w.text == "git")
            inner = shlex.join([w.text for w in args[j:]])
            if any(w.dynamic for w in args[j:]) or not (G.read_only(inner) or _safe_branch_delete(inner)):
                plan.why.append("git runs through xargs")
            else:
                replaced.append(sc)  # it only lists or safely deletes branches: nothing for the shell guard
            continue
        if name != "git":
            continue
        replaced.append(sc)
        if any(GIT_ENV.match(w.text) for w in sc.words[:k0]):
            plan.why.append("a GIT_DIR-like variable points git elsewhere")
        if any(w.dynamic and not (i > 0 and args[i - 1].text in S.MESSAGE_OPTS) for i, w in enumerate(args)):
            if _read_only_whatever(args):
                continue  # 0.1.23: it only reads, whatever the variable holds (git stash show "stash@{$i}" in a loop)
            plan.why.append("a git command has a variable or substitution the hook does not evaluate")
        texts = [w.text for w in args]
        repo, i, keep = cur, 0, []
        while i < len(texts) and texts[i].startswith("-"):
            o = texts[i]
            if o == "-C" and i + 1 < len(texts):
                repo = at(repo, texts[i + 1]) if repo is not None else None
                i += 2
            elif o.split("=", 1)[0] in ("--git-dir", "--work-tree"):
                plan.why.append("git is pointed at another repository with --git-dir or --work-tree")
                i += 1 if "=" in o else 2
            elif o in ("-c", "--namespace") and i + 1 < len(texts):
                keep += texts[i:i + 2]
                i += 2
            else:
                keep.append(o)
                i += 1
        cmd = shlex.join(["git"] + keep + texts[i:])
        if repo is None:
            plan.why.append("git runs in a folder the hook cannot tell (after a cd it could not follow)")
            continue
        fr = fresh_of(repo)
        if not os.path.isdir(repo) and not fr:
            plan.why.append(f"git runs in a folder that does not exist: {repo}")
            continue
        plan.steps.append({"repo": repo, "cmd": cmd, "fresh": fr})
        sub, sargs = P.parse_git(cmd)
        if sub == "worktree" and sargs[:1] == ["add"]:
            rest = sargs[1:]
            pos = P._positional(rest, ("-b", "-B", "--reason"))
            if pos:
                path = at(repo, pos[0])
                b = G._value(rest, "-B") or G._value(rest, "-b")
                base = fr["base"] if fr and fr.get("kind") == "worktree" else repo
                detach = "--detach" in rest or "-d" in rest
                if b:
                    head = ("branch", "refs/heads/" + b)
                elif len(pos) > 1 and not detach and os.path.isdir(base) and \
                        G._git(base, "rev-parse", "--verify", "--quiet", "refs/heads/" + pos[1])[0] == 0:
                    head = ("branch", "refs/heads/" + pos[1])
                elif len(pos) > 1:
                    head = ("rev", pos[1])
                elif detach:
                    head = ("rev", "HEAD")
                else:
                    head = ("branch", "refs/heads/" + os.path.basename(path))
                fresh[path] = {"kind": "worktree", "base": base, "head": head}
        elif sub == "clone":
            pos = P._positional(sargs, CLONE_VALUE)
            if pos:
                dest = pos[1] if len(pos) > 1 else re.sub(r"\.git$", "", os.path.basename(pos[0].rstrip("/")))
                fresh[at(repo, dest)] = {"kind": "clone"}
    if plan.steps or gitlike:
        plan.why += [p for p in problems if p in STRUCTURE_013]
        if not balanced:
            plan.why.append("unbalanced parentheses")
    plan.shell_line = _without(command, replaced) if replaced else command
    plan.why = list(dict.fromkeys(plan.why))
    return plan


_LOG_CTX: dict = {}   # the Bash call being checked, for EKBASIS_GUARD_MODE=log


def _log_mode() -> bool:
    return os.environ.get("EKBASIS_GUARD_MODE") == "log"


def _log_path() -> str:
    if os.environ.get("EKBASIS_HOOK_LOG"):
        return os.environ["EKBASIS_HOOK_LOG"]
    base = os.environ.get("EKBASIS_CACHE_DIR") or os.path.join(os.path.expanduser("~"), ".cache", "ekbasis")
    return os.path.join(base, "hook_log.jsonl")


def _shadow(decision: str, reason: str = "") -> None:
    """EKBASIS_GUARD_MODE=log: never block; append what the hook would have done to a local JSONL file (this machine
    only; nothing is sent anywhere) so a trial period shows what it would have stopped before it may stop anything."""
    reason = redact(reason)[0]   # 0.1.42: no credential typed on the line in the log (main redacts the command; "redacted":
    rec = {"t": round(time.time(), 3), "decision": decision, "reason": reason, **_LOG_CTX}   # how many values it replaced)
    try:
        path = _log_path()
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a") as f:
            f.write(json.dumps(rec) + "\n")
    except OSError as e:
        print(f"ekbasis hook (log mode): could not write {_log_path()}: {e}", file=sys.stderr)
    if decision != "pass":
        print(f"ekbasis hook (log mode, not blocking): would {decision.replace('_', ' ')}: {reason}", file=sys.stderr)


def _repeat_on() -> bool:
    """EKBASIS_GUARD_REPEAT=1 (0.1.24, opt-in): warn once. A line the guard warned about in this session goes through
    when it is run again unchanged, in the same folder: the agent (or the person) has read the facts and decides."""
    return os.environ.get("EKBASIS_GUARD_REPEAT") == "1"


REPEAT_NOTE = (" If this loss is what the user asked for, or the work is already kept elsewhere, run exactly the same "
               "command again to go ahead; otherwise take another route. Work named above as found nowhere else is "
               "not covered by a general request (\"clean up\", \"the old ones\"): keep it unless the user named it.")


def _decide(reason: str) -> None:
    if _log_mode():
        return _shadow("ask", reason)
    reason = redact(reason)[0]
    mode = "deny" if os.environ.get("EKBASIS_GUARD_MODE") == "deny" else "ask"
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": mode,
                                             "permissionDecisionReason": reason}}))


def _cannot_judge(why: str, session: str | None = None, rkey: str | None = None) -> int:
    if _log_mode():
        _shadow("ask_cannot_foresee", why)
        return 0
    if os.environ.get("EKBASIS_FAIL_OPEN") == "1":
        print(f"ekbasis hook: cannot foresee ({redact(why)[0]}); EKBASIS_FAIL_OPEN=1: letting it through", file=sys.stderr)
        return 0
    again = ""
    if _repeat_on() and session and rkey:
        _remember(session, rkey)
        again = " Run exactly the same command again to go ahead if you have checked it."
    _decide(f"Ekbasis could not foresee what this command will do ({why}). Confirm it only if you know it is safe."
            + again)
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


def _seen_path(session: str) -> str:
    return os.path.join(tempfile.gettempdir(), "ekbasis-preflight", re.sub(r"[^A-Za-z0-9_.-]", "_", session) + ".json")


def _preflight_key(line: str, cwd: str) -> str:
    """The command and what it would run: a script or SQL file edited since the warning is checked again."""
    content = ""
    try:
        plan = PF.plan_line(line, cwd)
        if plan is not None:
            content = "\n".join(s.text + "".join("\n" + x.text for x in (s.sql or [])) for s in plan.steps)
    except Exception:  # noqa: BLE001 — the line alone is the key then
        pass
    return hashlib.sha256(f"{os.path.realpath(cwd)}\0{line}\0{content}".encode()).hexdigest()[:32]


def _seen_any(session: str | None, key: str) -> bool:
    """Whether this session already recorded the key (no env switch; _seen adds preflight's own)."""
    if not session:
        return False
    try:
        with open(_seen_path(session)) as fh:
            return key in json.load(fh)
    except (OSError, ValueError):
        return False


def _seen(session: str | None, key: str) -> bool:
    if not session or os.environ.get("EKBASIS_PREFLIGHT_REPEAT", "1") == "0":
        return False
    try:
        with open(_seen_path(session)) as fh:
            return key in json.load(fh)
    except (OSError, ValueError):
        return False


def _remember(session: str | None, key: str) -> None:
    if not session:
        return
    path = _seen_path(session)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            with open(path) as fh:
                keys = json.load(fh)
        except (OSError, ValueError):
            keys = []
        with open(path, "w") as fh:
            json.dump(keys + [key], fh)
    except OSError:
        pass


def _preflight(line: str, cwd: str, session: str | None, client, left) -> str | None:
    """The preflight warning for this line, or None (since 0.1.6). Silent when it cannot judge, unless
    EKBASIS_PREFLIGHT_FAIL_CLOSED=1: preflight is an extra check, not the guard against lost work."""
    key = _preflight_key(line, cwd)
    if _seen(session, key):
        return None   # warned before in this session: the second run goes through
    again = "" if os.environ.get("EKBASIS_PREFLIGHT_REPEAT", "1") == "0" or not session else \
        " Fix the plan first, or run the same command again to go ahead anyway."
    fail_closed = os.environ.get("EKBASIS_PREFLIGHT_FAIL_CLOSED") == "1"
    copy = os.environ.get("EKBASIS_PREFLIGHT_COPY", "1") != "0"
    try:
        v = _with_deadline(lambda: PF.check_line(line, cwd, client=client, fail_closed=fail_closed, copy=copy), left())
    except CannotJudge as e:
        if not fail_closed:
            print(f"ekbasis preflight: cannot foresee ({e}); saying nothing", file=sys.stderr)
            return None
        _remember(session, key)
        return f"Ekbasis preflight could not check this multi-step change ({e}).{again}"
    if v is None or not v.risky:
        if v is not None and v.cannot_judge:
            print("ekbasis preflight: cannot foresee (" + "; ".join(v.plan.unread) + "); saying nothing", file=sys.stderr)
        return None
    _remember(session, key)
    return v.message() + again


def _safer_routes(groups: dict, flagged: set, client, threshold: float, left, request=None) -> list:
    """One sentence per flagged repository: the safer route Ekbasis checked (ekbasis.safer), or that none passed.
    Searched last, in the time left; a search that cannot finish leaves the warning without a route (never an unchecked
    one). EKBASIS_SAFER=0 turns it off."""
    if os.environ.get("EKBASIS_SAFER", "1") == "0":
        return []
    out = []
    for (repo, is_fresh), cmds in groups.items():
        if is_fresh or (repo not in flagged and not SF.code_problems(cmds, repo)):
            continue
        try:
            s = _with_deadline(lambda: SF.search(cmds, repo=repo, client=client, lost_threshold=threshold,
                                                  request=request), left())
        except Exception as e:  # noqa: BLE001  (the deadline, or anything else: the warning goes out without a route)
            print(f"ekbasis hook: no safer route ({e})", file=sys.stderr)
            continue
        if s.route:
            out.append(f"Safer route, checked by Ekbasis: `{s.route.line()}` (lose uncommitted work: "
                       f"{100 * s.route.p_lost:.0f}%; {'; '.join(s.route.keeps)}).")
        else:
            out.append(f"No safer route passed Ekbasis's check ({s.note}).")
    return out


def user_request(transcript_path: str | None) -> str | None:
    """The user's last typed message in the Claude Code transcript (a JSONL file): what the guard's loss question
    leaves out (0.1.23). Tool results, which Claude Code also records as user turns, are skipped. None when the file
    cannot be read or has no such message."""
    if not transcript_path:
        return None
    last = None
    try:
        with open(transcript_path, encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                try:
                    ev = json.loads(raw)
                except ValueError:
                    continue
                if not isinstance(ev, dict) or ev.get("type") != "user" or ev.get("isMeta"):
                    continue
                c = (ev.get("message") or {}).get("content")
                if isinstance(c, str):
                    text = c
                elif isinstance(c, list):
                    text = " ".join(x.get("text", "") for x in c if isinstance(x, dict) and x.get("type") == "text")
                else:
                    text = ""
                if text.strip():
                    last = text
    except OSError:
        return None
    return last


def _chain_split(line: str, cwd: str, client, threshold: float, request, left) -> str:
    """Chain mode (EKBASIS_CHAIN=1, 0.1.29): for a flagged line of several commands joined by ;, && or new lines, the
    first command whose prefix is risky, and the advice to run the commands before it on their own, so the rest is
    checked on the state after them (look when unsure, as in the chain studies). Only adds to the message: the
    decision is the same. "" when the line cannot be cut safely, the first command is already the risky one, or the
    check does not finish in time."""
    parts = S.sequence_parts(line)
    if not parts or len(parts) > 12:
        return ""
    try:
        k = _with_deadline(lambda: S.first_risky(parts, cwd=cwd, client=client, lost_threshold=threshold,
                                                 request=request), left())
    except Exception:  # noqa: BLE001 — the warning goes out without the split
        return ""
    k = k or len(parts)
    if k <= 1:
        return ""
    return (f" The commands before command {k} are predicted safe: run `{S.join_parts(parts[:k - 1])}` on its own "
            f"first, then `{S.join_parts([('', parts[k - 1][1])] + parts[k:])}` as a separate call, so it is checked "
            "on the state after them.")


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
        logged, n = redact(line)
        _LOG_CTX.update(command=logged, cwd=cwd, session=data.get("session_id"), redacted=n)
        session = data.get("session_id")
        rkey = "guard:" + hashlib.sha256(f"{os.path.realpath(cwd)}\0{line}".encode()).hexdigest()[:32]
        if _repeat_on() and session and _seen_any(session, rkey):
            if _log_mode():
                _shadow("pass_repeat")
            return 0
        threshold = float(os.environ.get("EKBASIS_LOST_THRESHOLD", "0.2"))
        deadline = float(os.environ.get("EKBASIS_HOOK_DEADLINE", "25"))
        shortcuts = os.environ.get("EKBASIS_SHORTCUTS", "1") != "0"
        t0 = time.monotonic()

        def left() -> float:
            r = deadline - (time.monotonic() - t0)
            if r <= 0:
                raise CannotJudge(f"the check did not finish within {deadline:g} s")
            return r

        client = Ekbasis(timeout=deadline, surface="claude-hook")
        request = user_request(data.get("transcript_path")) if os.environ.get("EKBASIS_REQUEST") == "1" else None
        plan = plan_line(line, cwd)
        if plan.why and os.environ.get("EKBASIS_GIT_GUARD", "1") != "0":
            return _cannot_judge("; ".join(plan.why), session, rkey)
        found = []
        if os.environ.get("EKBASIS_GIT_GUARD", "1") == "0":
            plan.steps = []   # preflight only: no git checks
        for loss in G.committed_loss(plan.steps) if plan.steps else []:
            found.append(f"Ekbasis (committed work, checked by code): this line {G.describe_loss(loss)}. Keep a branch "
                         "or tag on those commits first if you need them.")
        for st in plan.steps:
            for loss in G.remote_loss(st["repo"], [st["cmd"]]):
                if loss["deleted"]:
                    found.append(f"Ekbasis (remote work, checked by code): this line deletes the remote branch "
                                 f"{loss['ref']}, whose {loss['commits']} commit(s) no other branch, tag or remote "
                                 f"branch holds. Keep them on a branch first (git branch backup {loss['ref']}).")
                    continue
                found.append(f"Ekbasis (remote work, checked by code): this line force-pushes over {loss['commits']} "
                             f"commit(s) that {loss['ref']} holds and the pushed commit does not. Integrate them first "
                             "(git rebase), or push with --force-with-lease --force-if-includes, which refuses while "
                             "they are not integrated; --force-with-lease alone does not protect commits that were "
                             "already fetched.")
        for st in plan.steps:
            sk = G.skip_loss(st["repo"], st["cmd"])
            if sk:
                found.append(f"Ekbasis (committed work, checked by code): `{st['cmd']}` drops commit {sk['commit']} "
                             f"(\"{sk['subject']}\"), which no other branch, tag or remote branch holds: after the "
                             "rebase it is only in the reflog. Resolve the conflict and continue instead, or keep a "
                             f"branch on it first (git branch keep {sk['commit']}).")
        if os.environ.get("EKBASIS_REMOTE_CHECK", "1") != "0":
            for st in plan.steps:
                for loss in G.remote_unseen(st["repo"], [st["cmd"]], timeout=min(10.0, left())):
                    found.append(f"Ekbasis (remote work, read from the remote): this line "
                                 + (f"deletes the remote branch {loss['ref']}, which has no local branch here"
                                    if loss["deleted"] else
                                    f"force-pushes over commits on {loss['ref']} that this clone has never fetched")
                                 + ". Fetch and look at them first (git fetch, then git log for that branch).")
        groups: dict = {}
        flagged = set()   # repositories whose git commands the model found risky
        for st in plan.steps:
            groups.setdefault((st["repo"], st["fresh"] is not None), []).append(st["cmd"])
        for (repo, is_fresh), cmds in groups.items():
            if is_fresh:
                continue  # created earlier in this line: nothing uncommitted there yet
            if shortcuts and all(G.read_only(c) or R.clean_recoverable(repo, c) for c in cmds):
                continue  # only reads, or a git clean that removes only rebuildable ignored files
            problem = G.readable(repo)
            if problem:
                if "not a git repository" in problem.lower():
                    continue  # outside a repository the git commands fail or create one: nothing uncommitted to lose
                return _cannot_judge(f"cannot read a git repository at {repo}: {problem}", session, rkey)
            if shortcuts and R.no_uncommitted_work(repo):
                continue
            # run on a copy only when nothing else in the line writes: the shell part has every git command replaced by
            # `true`, so a line of git commands only leaves `true`s and separators (0.1.37: 0.1.33-0.1.36 saw "true" as
            # other commands and never ran the copy from the hook)
            only_git = not re.sub(r"\btrue\b|&&|\|\||;|\s", "", plan.shell_line)
            v = _with_deadline(lambda: G.check(cmds, repo=repo, client=client,
                                               fetch=os.environ.get("EKBASIS_FETCH") == "1",
                                               lost_threshold=threshold, request=request,
                                               simulate=None if only_git else False), left())
            if v.risky:
                flagged.add(repo)
                stake = G.at_stake(repo, cmds)
                found.append(f"Ekbasis: {'; '.join(v.reasons)}. Commands: {' ; '.join(cmds)}. "
                             + (f"At stake ({stake}). " if stake else "")
                             + "Consider saving the work first (commit, or git stash -u).")
        if os.environ.get("EKBASIS_SHELL_GUARD") == "1" and plan.shell_line.strip() and changes_files(plan.shell_line):
            skip = (lambda view: R.touched_recoverable(view, cwd)) if shortcuts else None
            v = _with_deadline(lambda: S.check([plan.shell_line], cwd=cwd, client=client, lost_threshold=threshold,
                                               skip=skip, request=request), left())
            if v.risky:
                what = "could not foresee every part of the line" if not v.lost_risky else "; ".join(v.reasons)
                stake = ""
                try:  # 0.1.24: name what the line could change, so whoever reads the warning can decide
                    touched, _ = R.write_touched(S.inspect([plan.shell_line], cwd), cwd)
                    names = []
                    for t, how in sorted(touched.items()):
                        full = os.path.join(cwd, t)
                        if how == "tree" and os.path.isdir(full) and not os.path.islink(full):
                            for dp, dns, fns in os.walk(full):
                                dns[:] = [x for x in dns if x != ".git"]
                                names += [os.path.relpath(os.path.join(dp, f), cwd) for f in sorted(fns)]
                                if len(names) > 50:
                                    break
                        elif os.path.lexists(full):
                            names.append(t)
                    if names:
                        stake = (" It changes or removes: " + ", ".join(names[:8])
                                 + (f" and {len(names) - 8} more" if len(names) > 8 else "") + ".")
                except Exception:  # noqa: BLE001 — the warning goes out without the list
                    pass
                split = ""
                if os.environ.get("EKBASIS_CHAIN", "1") != "0" and v.lost_risky:   # 0.1.37: on by default
                    split = _chain_split(plan.shell_line, cwd, client, threshold, request, left)
                found.append(f"Ekbasis (shell guard): {what}. Line: {line}.{stake}{split} Consider keeping a copy of "
                             "the files first.")
        if os.environ.get("EKBASIS_PREFLIGHT") == "1":
            warn = _preflight(line, cwd, data.get("session_id"), client, left)
            if warn:
                found.append(warn)
        routes = _safer_routes(groups, flagged, client, threshold, left, request) if found else []
    except CannotJudge as e:
        return _cannot_judge(str(e), session, rkey)
    except Exception as e:  # noqa: BLE001  (anything else: cannot judge)
        return _cannot_judge(f"{type(e).__name__}: {e}", session, rkey)
    if found:
        if _repeat_on() and session:
            _remember(session, rkey)
        _decide(" Also: ".join(found) + "".join(" " + r for r in routes) + (REPEAT_NOTE if _repeat_on() and session else ""))
    elif _log_mode():
        _shadow("pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
