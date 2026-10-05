"""Ekbasis as a git guard: the state of a REAL repository written the way the git training data was, the standard
questions, and a verdict before the commands run.

Only read-only git commands are run to describe the repository (and `git fetch`, when asked, so the state shows the
real remote). The commands being checked are never executed.

What decides a conflict must be in the state, so the description includes, for every other branch and the remote, the
files that differ from the current branch and the files changed on both sides since they split (as
`git diff --name-only` gives them): without that, no model can tell whether a checkout, merge or pull will conflict.

Facts (facts=True, the default since 0.1.1) add what `git status` does not show but some commands depend on, only when
it exists or when the commands could touch it: ignored files (for `clean -x/-X`, `stash -a`, `sparse-checkout`, or a
target ref that tracks them), untracked files a target ref tracks, linked worktrees and submodules with their changes,
whether a conflicted file still has conflict markers, cherry-pick/revert/am sessions, and ahead/behind the upstream
for `pull`/`push`. Notes (notes=True) add a few plain-text git rules, only for the commands being checked and only for
command forms the training data did not cover (see prompts.git_notes).
"""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
from dataclasses import dataclass, field

from . import prompts as P
from .client import CannotJudge, Ekbasis

ENV = {"LC_ALL": "C", "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0"}
ST = {"M": "modified", "A": "added", "D": "deleted", "R": "renamed", "C": "copied", "T": "type changed",
      "?": "untracked", "U": "unmerged (conflict)"}
UNMERGED = {"DD", "AU", "UD", "UA", "DU", "AA", "UU"}
TARGET_SUBS = {"checkout", "switch", "merge", "reset", "rebase", "cherry-pick", "pull", "restore", "read-tree"}


def _git(repo: str, *args: str, timeout: float = 30) -> tuple[int, str]:
    try:
        p = subprocess.run(["git", *args], cwd=repo, env=dict(os.environ, **ENV), stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL, text=True, errors="replace", timeout=timeout)
    except (subprocess.TimeoutExpired, FileNotFoundError, NotADirectoryError):
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


def _status_entry(l: str, extra: str = "") -> str:
    staged = f"staged {ST.get(l[0], l[0])}" if l[0] not in " ?" else ""
    unstaged = f"unstaged {ST.get(l[1], l[1])}" if l[1] not in " ?" else ""
    inner = "untracked" if l[:2] == "??" else ", ".join(x for x in (staged, unstaged) if x)
    return f"{l[3:]} ({inner}{extra})"


def _status_lines(repo: str) -> list[str]:
    _, out = _git(repo, "status", "--porcelain=v1", "--untracked-files=all")
    return [l for l in out.splitlines() if l.strip()]


def _has_markers(path: str) -> bool | None:
    try:
        with open(path, "rb") as f:
            c = f.read(2_000_000)
    except OSError:
        return None
    return bool(re.search(rb"^<<<<<<< ", c, re.M) and re.search(rb"^>>>>>>> ", c, re.M))


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _targets(repo: str, commands, heads: set) -> dict:
    """Refs the commands name as a target (a checkout/switch/merge/reset/rebase/cherry-pick/pull/restore source):
    token -> (commit, is a local branch). Paths after `--` and options are skipped."""
    out = {}
    for c in commands:
        sub, args = P.parse_git(c)
        if sub not in TARGET_SUBS:
            continue
        cands = []
        for a in args:
            if a == "--":
                break
            if a.startswith("--source="):
                cands.append(a.split("=", 1)[1])
            elif not a.startswith("-"):
                cands.append(a)
        if sub == "pull":
            up = _git(repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")[1].strip()
            cands = [up or remote_ref(repo) or ""]
        for tok in cands:
            if not tok or tok in out or tok == ".":
                continue
            rc, sha = _git(repo, "rev-parse", "--verify", "--quiet", tok + "^{commit}")
            if rc == 0 and sha.strip():
                out[tok] = (sha.strip(), tok in heads)
    return out


def _tree(repo: str, rev: str) -> set:
    _, out = _git(repo, "ls-tree", "-r", "--name-only", "-z", rev, timeout=60)
    return {p for p in out.split("\0") if p}


@dataclass
class RepoView:
    state: str
    branches: list
    info: dict = field(default_factory=dict)   # what the notes need: see prompts.git_notes


def inspect(repo: str = ".", commands=(), fetch: bool = False, max_branches: int = 12, max_files: int = 8,
            max_status: int = 25, commit_text: str = "hash", facts: bool = True) -> RepoView:
    """The repository's state in the training layout (plus the facts, when facts=True), the local branch names and
    what the notes need. See repo_state."""
    commands = list(commands or ())
    parsed = [P.parse_git(c) for c in commands]
    subs = {s for s, _ in parsed if s}
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
    remote_line = f"Remote {remote or 'origin/main'} last commit: {msg or '(none)'}"
    info = {"branches": sorted(heads), "nonbranch_targets": [], "path_args": [], "pull_config": {},
            "ignored_overwrite": False, "untracked_collision": False, "stash_count": 0}
    if facts and subs & {"pull", "push"} and remote and branch not in ("(none)", "HEAD"):
        up = _git(repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")[1].strip() or remote
        rc, cnt = _git(repo, "rev-list", "--left-right", "--count", f"HEAD...{up}")
        if rc == 0 and len(cnt.split()) == 2:
            a, b = (int(x) for x in cnt.split())
            pos = "up to date with it" if a == b == 0 else f"{_plural(a, 'commit')} ahead of it and {b} behind"
            remote_line += (f" (the current branch is {pos})" if up == remote
                            else f" (the current branch tracks {up}: {_plural(a, 'commit')} ahead, {b} behind)")
    if "pull" in subs:
        for k in ("pull.rebase", "pull.ff"):
            rc, v = _git(repo, "config", "--get", k)
            if rc == 0 and v.strip():
                info["pull_config"][k] = v.strip()
        if facts and info["pull_config"]:
            remote_line += " (this repository sets " + ", ".join(f"{k}={v}" for k, v in sorted(info["pull_config"].items())) + ")"
    lines.append(remote_line)
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

    status = _status_lines(repo)
    rc, top = _git(repo, "rev-parse", "--show-toplevel")
    top = top.strip() if rc == 0 and top.strip() else os.path.abspath(repo)
    targets = _targets(repo, commands, set(heads)) if commands else {}
    info["nonbranch_targets"] = sorted(t for t, (_, is_branch) in targets.items() if not is_branch)
    trees = {}

    def tracked_on(path: str) -> list[str]:
        """The target refs whose tree has this path (or, for a directory, files under it)."""
        hits = []
        for t in targets:
            if t not in trees:
                trees[t] = _tree(repo, targets[t][0])
            tr = trees[t]
            if path in tr or (path.endswith("/") and any(p.startswith(path) for p in tr)):
                hits.append(t)
        return hits

    def committed_on(path: str, hits: list[str]) -> str:
        """'also committed on dev, with different content' (or the same content; directories: no content)."""
        if path.endswith("/"):
            return f"also committed on {', '.join(hits)}"
        rc, mine = _git(repo, "hash-object", "--", path)
        parts = []
        for t in hits:
            rc2, theirs = _git(repo, "rev-parse", f"{targets[t][0]}:{path}")
            same = rc == 0 and rc2 == 0 and mine.strip() == theirs.strip()
            parts.append(f"{t}, with {'the same' if same else 'different'} content")
        return "also committed on " + "; ".join(parts)

    # ignored files: only when a command could delete or overwrite them
    ignored_shown = []
    want_all = any((s == "clean" and P.short_flags(a, stop="e") & {"x", "X"})
                   or (s == "stash" and ("--all" in a or "a" in P.short_flags(a, stop="m")))
                   or s == "sparse-checkout" for s, a in parsed)
    if want_all or targets:
        _, ig = _git(repo, "ls-files", "-z", "--others", "--ignored", "--exclude-standard", "--directory", "--no-empty-directory")
        ignored = sorted(p for p in ig.split("\0") if p)
        for p in ignored:
            hits = tracked_on(p) if targets else []
            if hits:
                info["ignored_overwrite"] = True
                ignored_shown.append(f"{p} (ignored; {committed_on(p, hits)})")
            elif want_all:
                ignored_shown.append(f"{p} (ignored)")
    entries = []
    for l in status:
        extra = ""
        if facts and l[:2] in UNMERGED:
            m = _has_markers(os.path.join(top, l[3:]))
            if m is True:
                extra = "; conflict markers still in the file"
            elif m is False:
                extra = "; resolved by hand (no conflict markers left), not added yet"
        if l[:2] == "??" and targets:
            hits = tracked_on(l[3:])
            if hits:
                info["untracked_collision"] = True
                extra = f"; {committed_on(l[3:], hits)}" if facts else ""
        entries.append(_status_entry(l, extra))
    more = f"; and {len(status) - max_status} more" if len(status) > max_status else ""
    ign = ""
    if facts and ignored_shown:
        ign = "; ".join(ignored_shown[:8]) + (f"; and {len(ignored_shown) - 8} more ignored" if len(ignored_shown) > 8 else "")
    if entries:
        lines.append("git status: " + "; ".join(entries[:max_status]) + more + (f"; {ign}" if ign else ""))
    else:
        lines.append("git status: nothing to commit, working tree clean" + (f"; {ign}" if ign else ""))
    _, out = _git(repo, "stash", "list")
    info["stash_count"] = len([l for l in out.splitlines() if l.strip()])
    lines.append(f"Stash entries: {info['stash_count']}")

    if facts:
        wts = _worktrees(repo, top)
        if wts:
            lines.append("Linked worktrees: " + "; ".join(wts))
        subm = _submodules(repo, top)
        if subm:
            lines.append("Submodules: " + "; ".join(subm))
    _, gd = _git(repo, "rev-parse", "--git-dir")
    gd = os.path.join(repo, gd.strip()) if gd.strip() and not os.path.isabs(gd.strip()) else gd.strip()
    ex = lambda *p: bool(gd) and os.path.exists(os.path.join(gd, *p))  # noqa: E731
    if ex("MERGE_HEAD"):
        lines.append("Operation in progress: merge (unfinished)")
    elif ex("rebase-merge") or ex("rebase-apply"):
        lines.append(f"Operation in progress: {'am' if facts and ex('rebase-apply', 'applying') else 'rebase'} (unfinished)")
    elif facts and ex("CHERRY_PICK_HEAD"):
        lines.append("Operation in progress: cherry-pick (unfinished)")
    elif facts and ex("REVERT_HEAD"):
        lines.append("Operation in progress: revert (unfinished)")

    words = {w for c in commands for w in P.tokens(c) if not w.startswith("-")} if commands else set()
    info["path_args"] = sorted(w for w in words if w not in targets and os.path.exists(os.path.join(repo, w)) and w not in (".", ".."))
    files = {l[3:].split(" -> ")[-1] for l in status} | {w for w in words if os.path.isfile(os.path.join(repo, w))}
    if facts:
        files |= {s.split(" (", 1)[0] for s in ignored_shown}
    files = [f for f in sorted(files) if os.path.isfile(os.path.join(repo, f))][:12]
    lines.append("Files in the working directory (content): " +
                 (", ".join(f"{f} ({_fingerprint(os.path.join(repo, f))})" for f in files) or "(none)"))
    return RepoView("\n".join(lines), sorted(heads), info)


def _worktrees(repo: str, top: str, cap: int = 4) -> list[str]:
    rc, out = _git(repo, "worktree", "list", "--porcelain")
    if rc != 0:
        return []
    blocks, cur = [], {}
    for l in out.splitlines() + [""]:
        if not l.strip():
            if cur:
                blocks.append(cur)
            cur = {}
            continue
        k, _, v = l.partition(" ")
        cur[k] = v
    here = os.path.realpath(top)
    res = []
    for i, b in enumerate(blocks):
        path = b.get("worktree", "")
        if not path or "bare" in b or os.path.realpath(path) == here:
            continue
        where = os.path.relpath(path, top)
        head = (f"branch {b['branch'][len('refs/heads/'):]}" if b.get("branch", "").startswith("refs/heads/")
                else f"detached at commit {b.get('HEAD', '')[:7]}")
        role = "main worktree, " if i == 0 else ""
        if not os.path.isdir(path):
            res.append(f"{where} ({role}{head}; missing)")
            continue
        st = _status_lines(path)
        desc = ("git status: " + "; ".join(_status_entry(l) for l in st[:8]) + (f"; and {len(st) - 8} more" if len(st) > 8 else "")
                if st else "working tree clean")
        res.append(f"{where} ({role}{head}; {desc})")
        if len(res) == cap:
            break
    return res


def _submodules(repo: str, top: str, cap: int = 4) -> list[str]:
    if not os.path.exists(os.path.join(top, ".gitmodules")):
        return []
    rc, out = _git(top, "submodule", "status")
    if rc != 0:
        return []
    res = []
    for l in out.splitlines():
        if len(l) < 42:
            continue
        flag, sha, rest = l[0], l[1:41], l[42:]
        path = rest.split(" (", 1)[0].strip()
        rc, ls = _git(top, "ls-files", "-s", "--", path)
        recorded = ls.split()[1][:7] if rc == 0 and len(ls.split()) > 1 else "?"
        if flag == "-":
            res.append(f"{path} (not checked out; the superproject records commit {recorded})")
        else:
            at = (f"at the recorded commit {recorded}" if sha[:7] == recorded
                  else f"checked out at commit {sha[:7]}, the superproject records commit {recorded}")
            st = _status_lines(os.path.join(top, path))
            desc = ("git status inside: " + "; ".join(_status_entry(x) for x in st[:8]) + (f"; and {len(st) - 8} more" if len(st) > 8 else "")
                    if st else "working tree clean")
            res.append(f"{path} ({at}; {desc}{'; merge conflict' if flag == 'U' else ''})")
        if len(res) == cap:
            break
    return res


def repo_state(repo: str = ".", commands=(), fetch: bool = False, max_branches: int = 12, max_files: int = 8,
               max_status: int = 25, commit_text: str = "hash", facts: bool = True) -> tuple[str, list[str]]:
    """The repository's state in the training layout, and the local branch names.
    commit_text="hash" (default) shows every commit as its short hash instead of its message: commit messages are free
    text that whoever shares a repository controls, so they are a way to inject instructions into the guard. Measured on
    the real-repository scenarios: same accuracy as with the messages, and an instruction planted in a commit message
    (which with messages shown let 1 of 5 work-losing scenarios through) no longer reaches the model.
    commit_text="message" shows the messages, as in the training data.
    facts=False gives the 0.1.0 description exactly."""
    v = inspect(repo, commands, fetch=fetch, max_branches=max_branches, max_files=max_files, max_status=max_status,
                commit_text=commit_text, facts=facts)
    return v.state, v.branches


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


OTHER_REPO = {"-C", "--git-dir", "--work-tree"}


def readable(repo: str) -> str | None:
    """None if git can read a work tree at `repo`; else why not."""
    if not os.path.isdir(repo):
        return "the folder does not exist"
    try:
        p = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=repo, env=dict(os.environ, **ENV),
                           capture_output=True, text=True, errors="replace", timeout=30)
    except FileNotFoundError:
        return "git is not installed"
    except (subprocess.TimeoutExpired, OSError) as e:
        return f"git did not answer ({e})"
    if p.returncode != 0 or p.stdout.strip() != "true":
        return (p.stderr.strip().splitlines() or ["not inside a git work tree"])[-1]
    return None


def other_repo(command: str) -> bool:
    """Whether a git command points git at another repository (-C, --git-dir, --work-tree before the subcommand)."""
    t = P.tokens(command)
    if not t or os.path.basename(t[0]) != "git":
        return False
    for a in t[1:]:
        if not a.startswith("-"):
            return False
        if a.split("=", 1)[0] in OTHER_REPO:
            return True
    return False


def check(commands, repo: str = ".", client: Ekbasis | None = None, fetch: bool = False, lost_threshold: float = 0.2,
          fail_threshold: float = 0.5, commit_text: str = "hash", facts: bool = True, notes: bool = True,
          notes_at: str | None = None, fail_closed: bool = True) -> Verdict:
    """What these git commands will do, before they run: lost work, failures, unfinished merge/rebase, final branch.
    facts / notes: see the module docstring (facts=False, notes=False reproduce client 0.1.0).

    Fails closed: if git cannot read a work tree at `repo`, if a command points git at another repository (-C,
    --git-dir, --work-tree) or uses a git alias, or if the server cannot be reached or does not answer in time, it
    raises CannotJudge,
    which callers treat as risky. fail_closed=False checks such commands against `repo` as 0.1.1 did (server errors
    still raise)."""
    commands = [c.strip() for c in commands]
    if not commands or any(not c for c in commands):
        raise ValueError("empty command: pass each command as one non-empty string")
    if fail_closed:
        why = readable(repo)
        if why:
            raise CannotJudge(f"cannot read a git repository at {repo!r}: {why}")
        elsewhere = [c for c in commands if other_repo(c)]
        if elsewhere:
            raise CannotJudge("a command points git at another repository (-C, --git-dir or --work-tree): "
                              + " ; ".join(elsewhere))
        aliases = sorted({sub for sub, _ in map(P.parse_git, commands)
                          if sub and _git(repo, "config", "--get", f"alias.{sub}")[0] == 0})
        if aliases:
            raise CannotJudge("a command uses a git alias the guard does not expand: " + ", ".join(aliases))
    client = client or Ekbasis()
    view = inspect(repo, commands, fetch=fetch, commit_text=commit_text, facts=facts)
    qs = {"lost": P.GIT_LOST, "in_progress": P.GIT_IN_PROGRESS}
    qs.update({f"fails_{k}": P.git_fails(k) for k in range(1, len(commands) + 1)})
    if len(view.branches) >= 2:
        qs["branch"] = P.git_branch(view.branches)
    prompt = P.git_state(view.state, commands, notes=P.git_notes(commands, view.info) if notes else None, notes_at=notes_at)
    ans = client.ask(prompt, qs)
    v = Verdict(commands=commands, p_lost=ans["lost"].p_yes, p_fail=[ans[f"fails_{k}"].p_yes for k in range(1, len(commands) + 1)],
                p_in_progress=ans["in_progress"].p_yes, state=prompt,
                branch=(ans["branch"].value, ans["branch"].confidence) if "branch" in ans else None)
    if v.p_lost >= lost_threshold:
        v.risky = True
        v.reasons.append(f"may permanently lose uncommitted work ({100 * v.p_lost:.0f}%)")
    v.reasons += [f"command {k} likely fails: {c}" for k, (c, p) in enumerate(zip(commands, v.p_fail), 1) if p >= fail_threshold]
    return v
