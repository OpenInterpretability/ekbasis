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


# ---------------------------------------------------------------- 0.1.3: read-only commands, lost committed work

READ_ONLY_SUBS = {"status", "blame", "annotate", "ls-files", "ls-tree", "ls-remote", "cat-file", "rev-parse",
                  "rev-list", "describe", "name-rev", "merge-base", "for-each-ref", "show-ref", "show-branch",
                  "count-objects", "check-ignore", "check-attr", "check-ref-format", "check-mailmap", "var", "version",
                  "help", "cherry", "verify-commit", "verify-tag", "fsck", "get-tar-commit-id"}
OUTPUT_SUBS = {"log", "show", "diff", "diff-tree", "diff-index", "diff-files", "range-diff", "whatchanged", "shortlog"}
BRANCH_LIST = {"--list", "--all", "--remotes", "--verbose", "--merged", "--no-merged", "--contains", "--no-contains",
               "--points-at", "--show-current", "--format", "--sort", "--column", "--no-column", "--color",
               "--no-color", "--abbrev", "--no-abbrev", "--ignore-case", "--omit-empty"}
BRANCH_CHANGE = {"--delete", "--move", "--copy", "--force", "--set-upstream-to", "--unset-upstream", "--edit-description",
                 "--track", "--no-track", "--create-reflog", "--recurse-submodules"}
TAG_LIST = {"--list", "--contains", "--no-contains", "--points-at", "--merged", "--no-merged", "--sort", "--format",
            "--column", "--no-column", "--color", "--ignore-case", "--omit-empty"}
TAG_CHANGE = {"--delete", "--force", "--annotate", "--sign", "--local-user", "--message", "--file", "--edit",
              "--create-reflog", "--cleanup", "--trailer"}


def _long(args) -> set:
    return {a.split("=", 1)[0] for a in args if a.startswith("--")}


def read_only(command: str) -> bool:
    """Whether a git command only reads (0.1.3: the hook does not ask the model about these). Listing forms of branch,
    tag, stash, worktree, remote, config and reflog count; anything that writes a file (`--output`) or a ref does not."""
    sub, args = P.parse_git(command)
    if sub is None:
        return P.tokens(command)[:1] == ["git"] or os.path.basename((P.tokens(command) or [""])[0]) == "git"
    longs, shorts = _long(args), P.short_flags(args)
    first = next((a for a in args if not a.startswith("-")), None)
    if sub in READ_ONLY_SUBS:
        return True
    if sub in OUTPUT_SUBS:
        return "--output" not in longs
    if sub == "grep":
        return "O" not in shorts and "--open-files-in-pager" not in longs
    if sub == "reflog":
        return first in (None, "show", "exists")
    if sub == "config":
        return bool(longs & {"--get", "--get-all", "--get-regexp", "--get-urlmatch", "--list", "--get-color",
                             "--get-colorbool"}) or "l" in shorts or first in ("get", "list")
    if sub == "branch":
        if shorts & set("dDmMcCfu") or longs & BRANCH_CHANGE:
            return False
        listing = bool(shorts & set("larv") or longs & BRANCH_LIST)
        return listing or not P._positional(args)
    if sub == "tag":
        if shorts & set("dfasumFe") or longs & TAG_CHANGE:
            return False
        listing = bool("l" in shorts or "n" in shorts or longs & TAG_LIST)
        return listing or not P._positional(args)
    if sub in ("stash", "notes"):
        return first in ("list", "show")
    if sub == "worktree":
        return first == "list"
    if sub == "remote":
        return first in (None, "show", "get-url")
    if sub == "submodule":
        return first in ("status", "summary")
    if sub == "bisect":
        return first in ("log", "visualize", "view")
    if sub == "clean":
        return "n" in shorts or "--dry-run" in longs
    return False


BRANCH_NOT_NEW = {"--delete", "--move", "--copy", "--set-upstream-to", "--unset-upstream", "--edit-description"}
REF_SUBS = {"branch", "checkout", "switch", "reset", "tag", "update-ref", "worktree"}


def _value(args, *names):
    """The value of the first of these options (`-b x`, `-bx`, `--orphan=x`, `--orphan x`), or None."""
    for i, a in enumerate(args):
        for n in names:
            if a == n:
                return args[i + 1] if i + 1 < len(args) else None
            if n.startswith("--") and a.startswith(n + "="):
                return a.split("=", 1)[1]
            if not n.startswith("--") and a.startswith(n) and len(a) > len(n) and not a.startswith("--"):
                return a[len(n):]
    return None


def _after(args, value, skip=()):
    """Positional arguments after the option value `value` (and not the values of the options in `skip`)."""
    out, seen, nxt = [], value is None, False
    for a in args:
        if nxt:
            nxt = False
            continue
        if a == "--":
            break
        if a in skip:
            nxt = True
            continue
        if not seen:
            if a == value or a.endswith(value or "\0"):
                seen = True
            continue
        if not a.startswith("-"):
            out.append(a)
    return out


def remote_loss(repo: str, cmds: list) -> list:
    """Remote commits that a force-push in cmds would overwrite: refs where the remote holds commits the
    local branch does not (plain --force/-f only; --force-with-lease fails safely instead of overwriting).
    Returns [{"ref", "commits"}]."""
    out = []
    for cmd in cmds:
        parsed = P.parse_git(cmd)
        if not parsed or parsed[0] != "push":
            continue
        flags = [a for a in parsed[1] if a.startswith("-")]
        rest = [a for a in parsed[1] if not a.startswith("-")]
        force = any(a in ("-f", "--force") or (a.startswith("--force") and not a.startswith("--force-with-lease")) for a in flags)
        if not force:
            continue
        up = _git(repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
        if up[0] != 0 or not up[1].strip():
            rr = remote_ref(repo)
            up = (0, rr) if rr else up
        if rest:  # push [remote] [refspec]: map the pushed ref to its remote-tracking counterpart
            spec = rest[-1] if ":" in rest[-1] or len(rest) > 1 else None
            if spec:
                src_ref = spec.split(":")[0] if ":" in spec else spec
                rc, cur = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
                if src_ref in ("HEAD", cur.strip()) and ":" not in spec:
                    dst = up[1].strip() if up[0] == 0 and up[1].strip() else None
                elif ":" in spec:
                    dst = "origin/" + spec.split(":")[1]
                else:
                    dst = "origin/" + src_ref
            else:
                dst = up[1].strip() if up[0] == 0 and up[1].strip() else None
        else:
            dst = up[1].strip() if up[0] == 0 and up[1].strip() else None
        if not dst:
            continue
        rc, cnt = _git(repo, "rev-list", "--left-right", "--count", f"HEAD...{dst}")
        if rc == 0:
            behind = int(cnt.split()[1])
            if behind > 0:
                out.append({"ref": dst, "commits": behind})
    return out


def committed_loss(steps) -> list:
    """Commits that a line's git commands would make unreachable from every branch, tag, remote-tracking branch and
    stash entry: lost committed work (0.1.3), kept apart from the model's question about uncommitted work. Computed by
    simulating the refs: branch deletion (-D, -d -f, -r), forced branch moves and renames (-f, -M, -C, checkout -B,
    switch -C, worktree add -B), `git reset --hard/--keep/--merge <commit>` on the checked-out branch (--soft and
    --mixed keep the changes in the work tree), tag deletion and moves, update-ref.
    Rewrites that keep the changes (rebase, commit --amend, cherry-pick), stash commands (the model's question) and
    remote updates (push) are not counted.

    steps: [{"repo": folder the command runs in, "cmd": the git command without -C, "fresh": None or
    {"kind": "worktree", "base": repo that created it, "head": ("branch", ref) | ("rev", rev)} for a worktree an
    earlier command of the same line creates}]. Returns [{"repo", "commits", "refs": [{"ref", "commits", "deleted"}]}]."""
    groups: dict = {}
    for st in steps:
        fr = st.get("fresh")
        if fr and fr.get("kind") != "worktree":
            continue
        base = fr["base"] if fr else st["repo"]
        if not os.path.isdir(base):
            continue
        rc, common = _git(base, "rev-parse", "--path-format=absolute", "--git-common-dir")
        if rc != 0 or not common.strip():
            continue
        groups.setdefault(common.strip(), {"base": base, "steps": []})["steps"].append(st)
    out = []
    for g in groups.values():
        if any(P.parse_git(st["cmd"])[0] in REF_SUBS for st in g["steps"]):
            out += _simulate_refs(g["base"], g["steps"])
    return out


def _simulate_refs(base: str, steps) -> list:
    rc, txt = _git(base, "for-each-ref", "--format=%(refname) %(objecttype) %(objectname) %(*objectname)")
    refs = {}
    for line in txt.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[0] != "refs/stash":
            if parts[1] == "commit":
                refs[parts[0]] = parts[2]
            elif parts[1] == "tag" and len(parts) == 4:
                refs[parts[0]] = parts[3]
    stash = _git(base, "log", "-g", "--format=%H", "refs/stash")[1].split()
    orig = dict(refs)
    heads: dict = {}   # work tree -> ("branch", ref) | ("detached", commit), as the line changes them
    rc, wl = _git(base, "worktree", "list", "--porcelain")
    for block in wl.split("\n\n"):
        kv = dict(l.split(" ", 1) for l in block.splitlines() if " " in l)
        if "worktree" in kv and "bare" not in block.split():
            heads[os.path.realpath(kv["worktree"])] = (("branch", kv["branch"]) if "branch" in kv
                                                       else ("detached", kv.get("HEAD", "")))
    tops: dict = {}

    def key(st):
        if st.get("fresh"):
            return ("fresh", os.path.normpath(st["repo"]))
        if st["repo"] not in tops:
            rc2, top = _git(st["repo"], "rev-parse", "--show-toplevel")
            tops[st["repo"]] = os.path.realpath(top.strip() if rc2 == 0 and top.strip() else st["repo"])
        return tops[st["repo"]]

    def checked_out(other_than=None):
        return {h[1] for kk, h in heads.items() if h[0] == "branch" and kk != other_than}

    def head_of(st):
        k = key(st)
        if k not in heads:
            fr = st.get("fresh")
            if fr:
                h = fr.get("head") or ("rev", "HEAD")
                heads[k] = ("branch", h[1]) if h[0] == "branch" else ("detached", resolve(h[1], None))
            else:
                rc2, sym = _git(st["repo"], "symbolic-ref", "-q", "HEAD")
                heads[k] = (("branch", sym.strip()) if rc2 == 0 and sym.strip()
                            else ("detached", _git(st["repo"], "rev-parse", "HEAD")[1].strip()))
        return heads[k]

    def resolve(rev, st):
        if not rev:
            return None
        m = re.match(r"^(HEAD|@)(?![A-Za-z0-9_/{-])(.*)$", rev)
        if m and st is not None:
            h = head_of(st)
            cur = refs.get(h[1]) if h[0] == "branch" else h[1]
            if not cur:
                return None
            rev = cur + m.group(2)
        where = st["repo"] if st is not None and not st.get("fresh") and os.path.isdir(st["repo"]) else base
        rc2, sha = _git(where, "rev-parse", "--verify", "--quiet", rev + "^{commit}")
        return sha.strip() if rc2 == 0 and sha.strip() else None

    for st in steps:
        sub, args = P.parse_git(st["cmd"])
        if sub not in REF_SUBS:
            continue
        sf, longs = P.short_flags(args), _long(args)
        k = key(st)
        if sub == "branch":
            pos = P._positional(args, ("-u", "--set-upstream-to", "--contains", "--no-contains", "--points-at",
                                       "--format", "--sort"))
            force = "f" in sf or "--force" in longs
            space = "refs/remotes/" if ("r" in sf or "--remotes" in longs) else "refs/heads/"
            if "D" in sf or (("d" in sf or "--delete" in longs) and force):
                for n in pos:
                    refs.pop(space + n, None)
            elif sf & {"M", "C"} or ((sf & {"m", "c"} or longs & {"--move", "--copy"}) and force):
                h = head_of(st)
                cur = h[1][len("refs/heads/"):] if h[0] == "branch" else None
                old, new = (cur, pos[0]) if len(pos) == 1 else ((pos[0], pos[1]) if len(pos) >= 2 else (None, None))
                if old and new and "refs/heads/" + old in refs:
                    refs["refs/heads/" + new] = refs["refs/heads/" + old]
                    if sf & {"M", "m"} or "--move" in longs:
                        refs.pop("refs/heads/" + old)
                        for kk, hv in list(heads.items()):
                            if hv == ("branch", "refs/heads/" + old):
                                heads[kk] = ("branch", "refs/heads/" + new)
            elif pos and not sf & set("dDmMcCu") and not longs & BRANCH_NOT_NEW and not read_only(st["cmd"]):
                ref = "refs/heads/" + pos[0]   # a new branch (also without -f: a backup branch keeps commits)
                head_of(st)
                if (force or ref not in refs) and ref not in checked_out():
                    sha = resolve(pos[1] if len(pos) > 1 else "HEAD", st)
                    if sha:
                        refs[ref] = sha
        elif sub in ("checkout", "switch"):
            if sub == "checkout":
                fname, cname = _value(args, "-B"), _value(args, "-b")
            else:
                fname, cname = _value(args, "-C", "--force-create"), _value(args, "-c", "--create")
            orphan = _value(args, "--orphan")
            name = fname or cname
            if name:
                rest = _after(args, name, skip=("--conflict",))
                ref = "refs/heads/" + name
                if fname or ref not in refs:
                    sha = resolve(rest[0] if rest else "HEAD", st)
                    if sha and not (fname and ref in checked_out(other_than=k)):
                        refs[ref] = sha
                heads[k] = ("branch", ref)
            elif orphan:
                heads[k] = ("branch", "refs/heads/" + orphan)
            else:
                pos = P._positional(args, ("--conflict", "--pathspec-from-file"))
                if len(pos) == 1 and "--" not in args:
                    if "refs/heads/" + pos[0] in refs and "--detach" not in longs:
                        heads[k] = ("branch", "refs/heads/" + pos[0])
                    else:
                        sha = resolve(pos[0], st)
                        if sha:
                            heads[k] = ("detached", sha)
                elif not pos and "--detach" in longs:
                    heads[k] = ("detached", resolve("HEAD", st))
        elif sub == "reset":
            if not longs & {"--hard", "--keep", "--merge"}:
                continue  # --soft and --mixed (the default) keep the dropped commits' changes in the work tree
            if "--" in args:
                i = args.index("--")
                before, paths = P._positional(args[:i], ("--pathspec-from-file",)), list(args[i + 1:])
            else:
                before, paths = P._positional(args, ("--pathspec-from-file",)), []
            commit = None
            if before:
                commit = resolve(before[0], st)
                paths += before[1:] if commit else before
            if paths or "--pathspec-from-file" in longs or not commit:
                continue
            h = head_of(st)
            if h[0] == "branch":
                refs[h[1]] = commit
            else:
                heads[k] = ("detached", commit)
        elif sub == "tag":
            pos = P._positional(args, ("-m", "-F", "-u", "--message", "--file", "--local-user", "--contains",
                                       "--points-at", "--sort", "--format", "--cleanup"))
            if "d" in sf or "--delete" in longs:
                for n in pos:
                    refs.pop("refs/tags/" + n, None)
            elif pos and not read_only(st["cmd"]) and ("f" in sf or "--force" in longs or "refs/tags/" + pos[0] not in refs):
                sha = resolve(pos[1] if len(pos) > 1 else "HEAD", st)
                if sha:
                    refs["refs/tags/" + pos[0]] = sha
        elif sub == "update-ref":
            pos = P._positional(args, ("-m",))
            full = lambda r: r if r.startswith("refs/") else "refs/heads/" + r  # noqa: E731
            if "-d" in args and pos:
                refs.pop(full(pos[0]), None)
            elif len(pos) >= 2 and "--stdin" not in longs:
                sha = resolve(pos[1], st)
                if sha:
                    refs[full(pos[0])] = sha
        elif sub == "worktree" and args and args[0] == "add":
            rest = args[1:]
            fname, cname = _value(rest, "-B"), _value(rest, "-b")
            pos = P._positional(rest, ("-b", "-B", "--reason"))
            if fname or cname:
                ref = "refs/heads/" + (fname or cname)
                if fname or ref not in refs:
                    sha = resolve(pos[1] if len(pos) > 1 else "HEAD", st)
                    if sha and not (fname and ref in checked_out()):
                        refs[ref] = sha
            elif len(pos) == 1 and "--detach" not in longs and "-d" not in args:
                ref = "refs/heads/" + os.path.basename(os.path.normpath(pos[0]))
                if ref not in refs:
                    sha = resolve("HEAD", st)
                    if sha:
                        refs[ref] = sha

    old_tips, new_tips = set(orig.values()) | set(stash), set(refs.values()) | set(stash)
    gone = sorted(old_tips - new_tips)
    if not gone:
        return []
    keep = ["--not", *sorted(new_tips)] if new_tips else []
    rc, lost = _git(base, "rev-list", *gone, *keep)
    lost = lost.split()
    if not lost:
        return []
    details = []
    for ref, sha in sorted(orig.items()):
        if refs.get(ref) != sha:
            n = len(_git(base, "rev-list", sha, *keep)[1].split())
            if n:
                details.append({"ref": ref, "commits": n, "deleted": ref not in refs})
    return [{"repo": base, "commits": len(lost), "refs": details}]


def describe_loss(loss: dict) -> str:
    """'deletes branch wip/help-text (1 commit that no other branch, tag or remote holds)'."""
    parts = []
    for d in loss["refs"]:
        kind, name = ("branch", d["ref"][len("refs/heads/"):]) if d["ref"].startswith("refs/heads/") else \
            (("remote-tracking branch", d["ref"][len("refs/remotes/"):]) if d["ref"].startswith("refs/remotes/") else
             (("tag", d["ref"][len("refs/tags/"):]) if d["ref"].startswith("refs/tags/") else ("ref", d["ref"])))
        verb = "deletes" if d["deleted"] else "moves"
        parts.append(f"{verb} {kind} {name} ({_plural(d['commits'], 'commit')} that no other branch, tag or remote "
                     "holds)")
    return "; ".join(parts) or f"leaves {_plural(loss['commits'], 'commit')} unreachable"
