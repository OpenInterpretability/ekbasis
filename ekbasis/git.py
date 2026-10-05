"""Ekbasis as a git guard: the state of a REAL repository written the way the git training data was, the standard
questions, and a verdict before the commands run.

Only read-only git commands are run to describe the repository (and `git fetch`, when asked, so the state shows the
real remote). The commands being checked are never executed.

What decides a conflict must be in the state, so the description includes, for every other branch and the remote, the
files that differ from the current branch and the files changed on both sides since they split (as
`git diff --name-only` gives them): without that, no model can tell whether a checkout, merge or pull will conflict.
"""
from __future__ import annotations

import hashlib
import os
import shlex
import subprocess
from dataclasses import dataclass, field

from . import prompts as P
from .client import Ekbasis

ENV = {"LC_ALL": "C", "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0"}
ST = {"M": "modified", "A": "added", "D": "deleted", "R": "renamed", "C": "copied", "T": "type changed",
      "?": "untracked", "U": "unmerged (conflict)"}


def _git(repo: str, *args: str, timeout: float = 30) -> tuple[int, str]:
    try:
        p = subprocess.run(["git", *args], cwd=repo, env=dict(os.environ, **ENV), stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL, text=True, errors="replace", timeout=timeout)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return 1, ""
    return p.returncode, p.stdout


def _fingerprint(path: str) -> str:
    """A short fingerprint of the file's content (the state shows contents as fingerprints)."""
    with open(path, "rb") as f:
        return "h" + hashlib.sha1(f.read()).hexdigest()[:6]


def _names(files: list[str], cap: int) -> str:
    return ", ".join(files[:cap]) + (f" and {len(files) - cap} more files" if len(files) > cap else "")


def remote_ref(repo: str) -> str | None:
    """The remote's default branch as a ref (origin/main, origin/master, ...), if any."""
    rc, out = _git(repo, "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD")
    if rc == 0 and out.strip():
        return out.strip()
    for ref in ("origin/main", "origin/master"):
        if _git(repo, "rev-parse", "--verify", "--quiet", ref)[0] == 0:
            return ref
    return None


def repo_state(repo: str = ".", commands=(), fetch: bool = False, max_branches: int = 12, max_files: int = 8,
               max_status: int = 25, commit_text: str = "hash") -> tuple[str, list[str]]:
    """The repository's state in the training layout, and the local branch names.
    commit_text="hash" (default) shows every commit as its short hash instead of its message: commit messages are free
    text that whoever shares a repository controls, so they are a way to inject instructions into the guard. Measured on
    the real-repository scenarios: same accuracy as with the messages, and an instruction planted in a commit message
    (which with messages shown let 1 of 5 work-losing scenarios through) no longer reaches the model.
    commit_text="message" shows the messages, as in the training data."""
    if fetch:
        _git(repo, "fetch", "-q", "origin", timeout=120)
    rc, out = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    branch = out.strip() if rc == 0 and out.strip() else "(none)"
    _, out = _git(repo, "for-each-ref", "--sort=-committerdate", "--format=%(refname:short)|%(contents:subject)", "refs/heads")
    heads = dict(l.split("|", 1) for l in out.splitlines() if "|" in l)
    shown = sorted(list(heads)[:max_branches] + ([branch] if branch in heads and branch not in list(heads)[:max_branches] else []))
    remote = remote_ref(repo)
    if commit_text == "message":
        lines = [f"Current branch: {branch}",
                 "Branches (last commit message): " + ", ".join(f"{b} ({heads[b]})" for b in shown)]
        msg = _git(repo, "log", "-1", "--format=%s", remote)[1].strip() if remote else ""
    else:
        short = lambda ref: _git(repo, "rev-parse", "--short=7", ref)[1].strip()  # noqa: E731
        lines = [f"Current branch: {branch}",
                 "Branches (last commit): " + ", ".join(f"{b} (commit {short('refs/heads/' + b)})" for b in shown)]
        msg = f"commit {short(remote)}" if remote and short(remote) else ""
    lines.append(f"Remote {remote or 'origin/main'} last commit: {msg or '(none)'}")
    parts = []
    for ref in [b for b in shown if b != branch] + ([remote] if remote else []):
        rc, dif = _git(repo, "diff", "--name-only", "HEAD", ref)
        if rc != 0:
            continue
        both = []
        rc, base = _git(repo, "merge-base", "HEAD", ref)
        if rc == 0 and base.strip():
            ours = set(_git(repo, "diff", "--name-only", base.strip(), "HEAD")[1].split())
            theirs = set(_git(repo, "diff", "--name-only", base.strip(), ref)[1].split())
            both = sorted(ours & theirs)
        dl = sorted(dif.split())
        parts.append((f"{ref} differs in {_names(dl, max_files)}" if dl else f"{ref} has the same files")
                     + (f" (changed on both sides since they split: {_names(both, max_files)})" if both else ""))
    if parts:
        lines.append("Compared with the current branch: " + "; ".join(parts))
    _, out = _git(repo, "status", "--porcelain=v1", "--untracked-files=all")
    status = [l for l in out.splitlines() if l.strip()]
    if status:
        def one(l):
            staged = f"staged {ST.get(l[0], l[0])}" if l[0] not in " ?" else ""
            unstaged = f"unstaged {ST.get(l[1], l[1])}" if l[1] not in " ?" else ""
            return f"{l[3:]} ({'untracked' if l[:2] == '??' else ', '.join(x for x in (staged, unstaged) if x)})"
        more = f"; and {len(status) - max_status} more" if len(status) > max_status else ""
        lines.append("git status: " + "; ".join(one(l) for l in status[:max_status]) + more)
    else:
        lines.append("git status: nothing to commit, working tree clean")
    _, out = _git(repo, "stash", "list")
    lines.append(f"Stash entries: {len([l for l in out.splitlines() if l.strip()])}")
    _, gd = _git(repo, "rev-parse", "--git-dir")
    gd = os.path.join(repo, gd.strip()) if gd.strip() and not os.path.isabs(gd.strip()) else gd.strip()
    if gd and os.path.exists(os.path.join(gd, "MERGE_HEAD")):
        lines.append("Operation in progress: merge (unfinished)")
    elif gd and any(os.path.exists(os.path.join(gd, d)) for d in ("rebase-merge", "rebase-apply")):
        lines.append("Operation in progress: rebase (unfinished)")
    words = {w for c in commands for w in shlex.split(c, posix=True) if not w.startswith("-")} if commands else set()
    files = sorted({l[3:].split(" -> ")[-1] for l in status} | {w for w in words if os.path.isfile(os.path.join(repo, w))})
    files = [f for f in files if os.path.isfile(os.path.join(repo, f))][:12]
    lines.append("Files in the working directory (content): " +
                 (", ".join(f"{f} ({_fingerprint(os.path.join(repo, f))})" for f in files) or "(none)"))
    return "\n".join(lines), sorted(heads)


@dataclass
class Verdict:
    commands: list
    p_lost: float                       # probability that uncommitted work is lost for good
    p_fail: list                        # per command: probability that it fails
    p_in_progress: float                # probability that a merge or rebase is left unfinished
    branch: tuple | None = None         # (predicted branch at the end, its probability)
    risky: bool = False                 # p_lost >= the threshold
    reasons: list = field(default_factory=list)
    state: str = ""                     # the exact state the model read

    def summary(self) -> str:
        out = [f"Ekbasis: {'RISKY' if self.risky else 'ok'}  (lose uncommitted work: {100 * self.p_lost:.0f}%)"]
        for c, p in zip(self.commands, self.p_fail):
            out.append(f"  {100 * p:3.0f}% fails  {c}")
        if self.p_in_progress >= 0.5:
            out.append(f"  {100 * self.p_in_progress:.0f}%: a merge or rebase is left unfinished")
        if self.branch:
            out.append(f"  ends on branch {self.branch[0]} ({100 * self.branch[1]:.0f}%)")
        out += [f"  - {r}" for r in self.reasons]
        return "\n".join(out)


def check(commands, repo: str = ".", client: Ekbasis | None = None, fetch: bool = False, lost_threshold: float = 0.2,
          fail_threshold: float = 0.5, commit_text: str = "hash") -> Verdict:
    """What these git commands will do, before they run: lost work, failures, unfinished merge/rebase, final branch."""
    commands = [c.strip() for c in commands]
    if not commands or any(not c for c in commands):
        raise ValueError("empty command: pass each command as one non-empty string")
    client = client or Ekbasis()
    state, branches = repo_state(repo, commands, fetch=fetch, commit_text=commit_text)
    qs = {"lost": P.GIT_LOST, "in_progress": P.GIT_IN_PROGRESS}
    qs.update({f"fails_{k}": P.git_fails(k) for k in range(1, len(commands) + 1)})
    if len(branches) >= 2:
        qs["branch"] = P.git_branch(branches)
    prompt = P.git_state(state, commands)
    ans = client.ask(prompt, qs)
    v = Verdict(commands=commands, p_lost=ans["lost"].p_yes, p_fail=[ans[f"fails_{k}"].p_yes for k in range(1, len(commands) + 1)],
                p_in_progress=ans["in_progress"].p_yes, state=prompt,
                branch=(ans["branch"].value, ans["branch"].confidence) if "branch" in ans else None)
    if v.p_lost >= lost_threshold:
        v.risky = True
        v.reasons.append(f"may permanently lose uncommitted work ({100 * v.p_lost:.0f}%)")
    v.reasons += [f"command {k} likely fails: {c}" for k, (c, p) in enumerate(zip(commands, v.p_fail), 1) if p >= fail_threshold]
    return v
