"""The safer route: when git commands are risky, the safest concrete alternative that does what they were meant to do,
chosen by Ekbasis. A warning alone often does not make a smaller agent change course; a command it can run instead does.

Candidates come from rules (no model): the risky command and the repository's facts give a few alternatives with the
same intent that keep the work recoverable. Each candidate is then checked by Ekbasis with the same state builder as
the original (git.check on the candidate commands), and by the same code checks as the Claude Code hook (commits no
ref would hold, remote commits a push would overwrite). Only a candidate that passes every check is offered: lose
uncommitted work below the RISKY threshold, no command likely to fail, no merge or rebase left unfinished. Among those,
the lowest probability of losing work wins (compared at the shown precision, 1 point), then the fewest extra steps,
then the order below. If none passes, there is no suggestion: an unchecked command is never offered.

Intent of the risky command                        Candidates, in order
- `reset --hard [X]` (discard the changes, move     `git stash push` first (`-u` too when there are untracked files);
  the branch to X)                                  plus `git branch backup/<branch>` first when X drops commits
- `checkout [X] -- <paths>`, `restore <paths>`      `git stash push -- <paths>` first (the whole tree for `.`)
  (put files back as in HEAD or X)
- `checkout -f B`, `switch -f/--discard-changes B`  `git stash push [-u]` then the same switch without the force;
  (switch, dropping the changes)                    or `git stash push [-u]` then the command as written
- `clean -f[d]` (delete untracked files)            `git stash push -u -- <what git clean -n lists>` (`-a` with
                                                    -x/-X); the whole tree with -u when it lists more than 20 paths
- `branch -D N`, `branch -d -f N` (remove N)        `git branch -m N backup/N` (the name goes, the commits stay);
                                                    `git branch -d N` first when N is merged (when it is not, git
                                                    would refuse, so it would not do what was asked)
- `stash drop [S]`, `stash clear` (discard          `git branch backup/stash-K stash@{K}` first, for each entry
  stash entries)
- `push --force`/`-f` (replace the remote branch)   `--force-with-lease` instead; with `git branch backup/<remote ref>
                                                    <remote ref>` first when the remote-tracking ref has commits the
                                                    local branch does not (--force-with-lease does not protect those:
                                                    they are already fetched, so the lease matches)
- any other checkout, switch, merge, pull, rebase,  `git stash push [-u]` first
  reset or restore

`git clean -n` alone (a dry run) is not offered for `clean -f`: it does not do what was asked, and a dry run followed by
the same delete loses the same files. Candidates are checked in parallel, one request each (the states differ, so
they cannot share a request), so a search costs about one extra round trip; read_once is not used (it costs 0.9-3.1
points of accuracy, see README). A server that cannot be reached, or a deadline, means no suggestion.
"""
from __future__ import annotations

import itertools
import os
import shlex
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from . import git as G
from . import prompts as P
from .client import CannotJudge, Ekbasis

MAX_CANDIDATES = 4
MAX_CLEAN_PATHS = 20
MAX_STASH_BACKUPS = 5
GENERIC = {"checkout", "switch", "merge", "pull", "rebase", "reset", "restore", "cherry-pick", "revert", "am"}

KEEP_STASH = "the discarded changes stay in a stash (git stash list; git stash pop brings them back)"
KEEP_BACKUP = "the commits stay on branch {}"
KEEP_BRANCH_D = "git refuses to delete a branch that is not merged"
KEEP_RENAME = "the branch is renamed to {} instead of deleted, so its commits stay"
KEEP_STASH_BACKUP = "the stash entries stay on branch {}"
KEEP_LEASE = "the push fails instead of overwriting remote commits you have not fetched"
KEEP_REMOTE = "the remote commits it overwrites stay on branch {}"


@dataclass
class Candidate:
    commands: list                              # the commands to run instead, in order
    keeps: list = field(default_factory=list)   # what each rule keeps, in words
    extra: int = 0                              # steps added to the original


@dataclass
class Route:
    commands: list
    p_lost: float
    p_fail: list
    keeps: list
    extra: int

    def line(self) -> str:
        return " && ".join(self.commands)

    def text(self) -> str:
        return f"Safer: {self.line()}  (lose uncommitted work: {100 * self.p_lost:.0f}%)"


@dataclass
class Search:
    route: Route | None
    tried: int = 0          # candidates checked by Ekbasis
    note: str = ""          # why there is no route
    seconds: float = 0.0

    def summary(self) -> str:
        if self.route:
            return self.route.text() + "".join(f"\n  keeps: {k}" for k in self.route.keeps)
        return f"Safer: none ({self.note})"

    def as_json(self) -> dict | None:
        r = self.route
        return {"commands": r.commands, "p_lost": round(r.p_lost, 4), "keeps": r.keeps} if r else None


class _Facts:
    """What the rules need from the repository, read once (read-only git)."""

    def __init__(self, repo: str):
        self.repo = repo
        rc, out = G._git(repo, "rev-parse", "--abbrev-ref", "HEAD")
        self.branch = out.strip() if rc == 0 and out.strip() not in ("", "HEAD") else None
        _, out = G._git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads")
        self.taken = set(out.split())
        self.untracked = any(l.startswith("??") for l in G._status_lines(repo))
        _, out = G._git(repo, "stash", "list")
        self.stashes = len([l for l in out.splitlines() if l.strip()])

    def name(self, base: str) -> str:
        """A branch name nobody uses yet: backup/x, backup/x-2, ..."""
        n, k = base, 2
        while n in self.taken:
            n, k = f"{base}-{k}", k + 1
        self.taken.add(n)
        return n

    def stash(self, untracked: bool | None = None) -> str:
        return "git stash push -u" if (self.untracked if untracked is None else untracked) else "git stash push"


def _join(*toks) -> str:
    return shlex.join(["git", *toks])


def _without(args, letter: str, longs=(), stop: str = "") -> list:
    """args without the short flag `letter` (also inside clusters: -fd -> -d) and without the long options in `longs`;
    a letter in `stop` takes the rest of its cluster as its value, which is kept as written; after `--` nothing
    changes."""
    out, rest = [], False
    for a in args:
        if rest or a == "--":
            rest = True
            out.append(a)
        elif a in longs:
            continue
        elif a.startswith("-") and not a.startswith("--") and len(a) > 1:
            kept = ""
            for k, ch in enumerate(a[1:]):
                if ch in stop:
                    kept += a[1 + k:]
                    break
                if ch != letter:
                    kept += ch
            if kept:
                out.append("-" + kept)
        else:
            out.append(a)
    return out


def _paths(repo: str, sub: str, args: list) -> list:
    """The paths of a `checkout ... -- paths`, `checkout paths` or `restore paths` (empty: not a path form)."""
    if "--" in args:
        return args[args.index("--") + 1:]
    pos = P._positional(args, ("-s", "--source", "--conflict", "--pathspec-from-file"))
    if sub == "restore":
        return pos
    return [p for p in pos if os.path.exists(os.path.join(repo, p))]


def _rules(cmd: str, facts: _Facts) -> list:
    """Alternatives for one command, each a Candidate; [] when no rule applies (the command stays as it is)."""
    toks = P.tokens(cmd)
    sub, args = P.parse_git(cmd)
    if not sub or len(toks) < 2 or toks[1].startswith("-"):
        return []   # not git, or global options before the subcommand: no rule
    longs, sf, a = G._long(args), P.short_flags(args), set(args)
    stash = facts.stash()
    if sub == "reset" and "--hard" in longs:
        pre, keeps = [], [KEEP_STASH]
        if facts.branch and G.committed_loss([{"repo": facts.repo, "cmd": cmd, "fresh": None}]):
            name = facts.name(f"backup/{facts.branch}")
            pre, keeps = [_join("branch", name)], keeps + [KEEP_BACKUP.format(name)]
        out = [Candidate(["git stash push", *pre, cmd], keeps, 1 + len(pre))]
        if facts.untracked:
            out.append(Candidate(["git stash push -u", *pre, cmd], keeps, 1 + len(pre)))
        return out
    forced = "f" in P.short_flags(args, stop="bBcC") or longs & {"--force", "--discard-changes"}
    worktree = sub == "checkout" and not a & {"--ours", "--theirs"} or \
        sub == "restore" and ("W" in sf or "--worktree" in longs or not ("S" in sf or "--staged" in longs))
    if worktree and not forced:
        paths = _paths(facts.repo, sub, args)
        if paths:
            save = "git stash push" if paths == ["."] else _join("stash", "push", "--", *paths)
            return [Candidate([save, cmd], [KEEP_STASH], 1)]
    if sub in ("checkout", "switch") and forced:
        plain = _without(args, "f", ("--force", "--discard-changes"), stop="bBcC")
        out = [Candidate([stash, _join(sub, *plain)], [KEEP_STASH], 1)] if "--" not in args else []
        return out + [Candidate([stash, cmd], [KEEP_STASH], 1)]
    if sub == "clean" and not G.read_only(cmd):
        rc, out = G._git(facts.repo, "clean", "-n", *_without(args, "f", ("--force",), stop="e"))
        listed = [l[len("Would remove "):] for l in out.splitlines() if l.startswith("Would remove ")] if rc == 0 else []
        if not listed:
            return []
        flag = "-a" if P.short_flags(args, stop="e") & {"x", "X"} else "-u"
        save = _join("stash", "push", flag, "--", *listed) if len(listed) <= MAX_CLEAN_PATHS else f"git stash push {flag}"
        return [Candidate([save], [KEEP_STASH], 0)]
    if sub == "branch" and ("D" in sf or (("d" in sf or "--delete" in longs) and ("f" in sf or "--force" in longs))) \
            and not ("r" in sf or "--remotes" in longs):
        names = P._positional(args)
        if not names:
            return []
        renames = [(n, facts.name(f"backup/{n}")) for n in names]
        rename = Candidate([_join("branch", "-m", n, b) for n, b in renames],
                           [KEEP_RENAME.format(", ".join(b for _, b in renames))], len(names) - 1)
        if G.committed_loss([{"repo": facts.repo, "cmd": cmd, "fresh": None}]):
            return [rename]   # not merged anywhere: git branch -d would refuse, so it would not do what was asked
        return [Candidate([_join("branch", "-d", *names)], [KEEP_BRANCH_D], 0), rename]
    if sub == "stash" and args[:1] in (["drop"], ["clear"]):
        if args[0] == "clear":
            nums = [str(k) for k in range(facts.stashes)]
        else:
            ref = next((x for x in args[1:] if not x.startswith("-")), "0")
            nums = [ref[len("stash@{"):-1] if ref.startswith("stash@{") and ref.endswith("}") else ref]
        if not nums or len(nums) > MAX_STASH_BACKUPS or not all(n.isdigit() for n in nums):
            return []
        names = [facts.name(f"backup/stash-{n}") for n in nums]
        return [Candidate([*(f"git branch {b} stash@{{{n}}}" for b, n in zip(names, nums)), cmd],   # written unquoted
                          [KEEP_STASH_BACKUP.format(", ".join(names))], len(nums))]
    if sub == "push" and ("f" in sf or "--force" in longs):
        lease = _join("push", "--force-with-lease", *_without(args, "f", ("--force",)))
        out = [Candidate([lease], [KEEP_LEASE], 0)]
        names = [(facts.name("backup/" + l["ref"].replace("/", "-")), l["ref"]) for l in G.remote_loss(facts.repo, [cmd])]
        if names:
            out.append(Candidate([*(_join("branch", b, r) for b, r in names), lease],
                                 [KEEP_REMOTE.format(", ".join(b for b, _ in names)), KEEP_LEASE], len(names)))
        return out
    if sub in GENERIC:
        return [Candidate([stash, cmd], [KEEP_STASH], 1)]
    return []


def candidates(commands, repo: str = ".", limit: int = MAX_CANDIDATES) -> list:
    """The alternatives for these commands, in order of preference (at most `limit`): every command with a rule is
    replaced by one of its alternatives, the others stay. Only read-only git runs here."""
    facts = _Facts(repo)
    per = []
    for c in commands:
        alts = _rules(c, facts)
        per.append(alts or [Candidate([c])])
    if all(len(a) == 1 and a[0].commands == [c] for a, c in zip(per, commands)):
        return []
    out, seen = [], set()
    for combo in itertools.product(*per):
        cmds = [x for cand in combo for x in cand.commands]
        if tuple(cmds) in seen or cmds == list(commands):
            continue
        seen.add(tuple(cmds))
        keeps = list(dict.fromkeys(k for cand in combo for k in cand.keeps))
        out.append(Candidate(cmds, keeps, sum(cand.extra for cand in combo)))
        if len(out) == limit:
            break
    return out


def _lease_as_force(cmd: str) -> str:
    sub, args = P.parse_git(cmd)
    if sub != "push":
        return cmd
    return _join("push", *["--force" if a.startswith("--force-with-lease") else a for a in args])


def code_problems(commands, repo: str) -> list:
    """What the hook's code checks find in a line: commits no ref would hold, and remote commits a push would
    overwrite that no earlier `git branch <name> <remote ref>` of the line keeps. --force-with-lease counts as a force
    here: it only protects commits that were not fetched, and these were."""
    out = [G.describe_loss(l) for l in G.committed_loss([{"repo": repo, "cmd": c, "fresh": None} for c in commands])]
    for k, c in enumerate(commands):
        kept = set()
        for prev in commands[:k]:
            sub, args = P.parse_git(prev)
            pos = P._positional(args) if sub == "branch" else []
            if len(pos) == 2 and not P.short_flags(args) & set("dDmMcC"):
                kept.add(pos[1])
        for l in G.remote_loss(repo, [_lease_as_force(c)]):
            if l["ref"] not in kept:
                out.append(f"overwrites {l['commits']} commit(s) that {l['ref']} holds")
    return out


def search(commands, repo: str = ".", client: Ekbasis | None = None, lost_threshold: float = 0.2,
           fail_threshold: float = 0.5, limit: int = MAX_CANDIDATES, **check_kw) -> Search:
    """The safest checked alternative to these commands (Search.route), or why there is none (Search.note). Each
    candidate is asked with git.check (same state builder, same thresholds as the original; check_kw goes through, e.g.
    commit_text, facts, notes) and checked by code_problems. Never raises CannotJudge: a candidate that cannot be
    checked is not offered."""
    t0 = time.monotonic()
    commands = [c.strip() for c in commands]
    cands = candidates(commands, repo, limit=limit)
    if not cands:
        return Search(None, 0, "no rule gives an alternative for these commands", time.monotonic() - t0)
    client = client or Ekbasis()
    check_kw.pop("fetch", None)   # the original check fetched already, if asked to

    def one(c: Candidate):
        try:
            v = G.check(c.commands, repo=repo, client=client, lost_threshold=lost_threshold,
                        fail_threshold=fail_threshold, **check_kw)
        except CannotJudge as e:
            return c, None, str(e)
        return c, v, None

    with ThreadPoolExecutor(max_workers=len(cands)) as ex:
        results = list(ex.map(one, cands))
    passed, errors = [], []
    for i, (c, v, err) in enumerate(results):
        if v is None:
            errors.append(err)
            continue
        if v.risky or any(p >= fail_threshold for p in v.p_fail) or v.p_in_progress >= 0.5 or code_problems(c.commands, repo):
            continue
        passed.append((round(v.p_lost, 2), c.extra, i, Route(c.commands, v.p_lost, v.p_fail, c.keeps, c.extra)))
    took = time.monotonic() - t0
    if passed:
        return Search(min(passed, key=lambda x: x[:3])[3], len(cands), "", took)
    if errors and len(errors) == len(cands):
        return Search(None, len(cands), f"cannot foresee the alternatives: {errors[0]}", took)
    return Search(None, len(cands), f"{G._plural(len(cands), 'alternative')} checked, none passed", took)
