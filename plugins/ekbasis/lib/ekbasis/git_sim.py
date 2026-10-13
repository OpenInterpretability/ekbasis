"""Which git commands fail, found by running them on a copy of the repository (0.1.33, check when sure).

The model forecasts failures well on states it has seen; on held-out command kinds it can be confidently wrong (a
`git rebase` after a `git rm` that leaves staged changes: it answered "succeeds", git refuses). git itself knows: so
the commands are run, in order, on a copy of the repository, and the exit code of each one is the answer.

Safety: the real repository is never touched. The work tree with its .git is copied (APFS clonefile on macOS, a reflink
or a size-capped copy elsewhere: preflight's copy); every command runs in the copy with hooks disabled
(core.hooksPath), no editor, no credential prompt and no signing, under a time limit. Only local subcommands run; at the
first command that could reach a remote (push, pull, fetch, clone, remote, submodule, ...) or that is not on the list,
the run stops and the remaining commands are left to the model. A work tree whose .git is a file (a linked worktree or
a submodule) is not copied. The copy is removed afterwards.

Used by ekbasis.git.check(..., simulate=True), which sets each simulated command's failure to 0 or 1 by the exit code
and leaves the prompt the model reads unchanged (the lesson of 0.1.30: a rule in the prompt leaked into other
answers)."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time

from . import prompts as P

LOCAL_SUBS = {"add", "rm", "mv", "commit", "stash", "reset", "checkout", "switch", "restore", "rebase", "merge",
              "cherry-pick", "revert", "branch", "tag", "clean", "status", "log", "diff", "show", "rev-parse"}
TIME_LIMIT = 15.0   # seconds for the whole run
SAFE_CONFIG = ["-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false",
               "-c", "core.fsmonitor=false", "-c", "gc.auto=0", "-c", "maintenance.auto=false"]
ENV = {"GIT_EDITOR": "true", "GIT_SEQUENCE_EDITOR": "true", "GIT_TERMINAL_PROMPT": "0", "GIT_MERGE_AUTOEDIT": "no",
       "GIT_ASKPASS": "true", "SSH_ASKPASS": "true", "GIT_PAGER": "cat", "PAGER": "cat", "LC_ALL": "C"}


def _toplevel(repo: str) -> str | None:
    r = subprocess.run(["git", "-C", repo, "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=10)
    return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else None


MAX_FILES = 2000          # files in the work tree (tracked changes, untracked and ignored) compared for lost work
MAX_BYTES = 64 << 20


def _g(cwd, env, *args):
    r = subprocess.run(["git", *SAFE_CONFIG, *args], cwd=cwd, env=env, capture_output=True, timeout=TIME_LIMIT,
                       stdin=subprocess.DEVNULL)
    return r.returncode, r.stdout


def _uncommitted(cwd, env) -> dict | None:
    """{path: {content bytes}}: versions in the work tree (tracked and changed, untracked or ignored files), in the
    index, or only in stash entries, that HEAD does not have. None when there are too many files to compare."""
    rc, out = _g(cwd, env, "ls-files", "-z", "--modified", "--others", "--deleted")
    rc2, ign = _g(cwd, env, "ls-files", "-z", "--others", "--ignored", "--exclude-standard")
    rc3, staged = _g(cwd, env, "diff", "--cached", "--name-only", "-z")
    paths = {p for blob in (out, ign, staged) for p in blob.decode(errors="replace").split("\0") if p}
    if len(paths) > MAX_FILES:
        return None
    vers, total = {}, 0
    for p in paths:
        rc, head = _g(cwd, env, "show", f"HEAD:{p}")
        head = head if rc == 0 else None
        full = os.path.join(cwd, p)
        if os.path.isfile(full) and not os.path.islink(full):
            data = open(full, "rb").read()
            total += len(data)
            if data != head:
                vers.setdefault(p, set()).add(data)
        rc, idx = _g(cwd, env, "show", f":{p}")
        if rc == 0 and idx != head:
            vers.setdefault(p, set()).add(idx)
        if total > MAX_BYTES:
            return None
    rc, hs = _g(cwd, env, "stash", "list", "--format=%H")
    for h in hs.decode().split()[:50]:
        for ref in (h, h + "^2", h + "^3"):
            rc, names = _g(cwd, env, "ls-tree", "-r", "-z", "--name-only", ref)
            for p in (names.decode(errors="replace").split("\0") if rc == 0 else []):
                if not p:
                    continue
                rc, c = _g(cwd, env, "show", f"{ref}:{p}")
                rc2, head = _g(cwd, env, "show", f"HEAD:{p}")
                if rc == 0 and (rc2 != 0 or c != head):
                    vers.setdefault(p, set()).add(c)
    return vers


def _survives(cwd, env, path, content) -> bool:
    """Whether this content of `path` still exists anywhere: work tree, index, any branch or remote-tracking tip, any
    stash entry; or inside another version of the same file (a merge result with conflict markers keeps both sides)."""
    found = []
    full = os.path.join(cwd, path)
    if os.path.isfile(full) and not os.path.islink(full):
        found.append(open(full, "rb").read())
    rc, out = _g(cwd, env, "for-each-ref", "--format=%(refname)", "refs/heads", "refs/remotes", "refs/tags")
    refs = out.decode().split()[:500]
    rc, hs = _g(cwd, env, "stash", "list", "--format=%H")
    for h in hs.decode().split()[:50]:
        refs += [h, h + "^2", h + "^3"]
    for ref in [""] + refs:   # "" = the index
        rc, c = _g(cwd, env, "show", f"{ref}:{path}")
        if rc == 0:
            found.append(c)
    want = content.strip()
    return any(c == content or (want and want in c) for c in found)


def run_on_copy(repo: str, commands) -> dict | None:
    """{"exit": [code per command run], "stderr": [first line per command], "ran": n, "stopped": why or None, "lost":
    [paths whose uncommitted content survives nowhere] or None (not every command ran, or too many files)}, or None
    when the repository cannot be copied safely. commands: git command lines, as the user wrote them."""
    from .preflight import _copy_tree   # the copy that preflight uses (clonefile / reflink / capped)
    top = _toplevel(repo)
    if not top or not os.path.isdir(os.path.join(top, ".git")):
        return None   # not a work tree, or .git is a file (linked worktree, submodule)
    rel = os.path.relpath(os.path.realpath(repo), os.path.realpath(top))
    work = tempfile.mkdtemp(prefix="ekbasis-git-")
    dst = os.path.join(work, "repo")
    out = {"exit": [], "stderr": [], "ran": 0, "stopped": None, "lost": None}
    try:
        try:
            _copy_tree(top, dst)
        except Exception:  # noqa: BLE001 — too big, no clonefile or reflink: leave it to the model
            return None
        cwd = os.path.normpath(os.path.join(dst, rel))
        env = {**os.environ, **ENV}
        start = time.time()
        before = _uncommitted(cwd, env)   # taken on the copy, before any command
        # a copy has new file times and inodes: refresh the index's stat cache, or git sees every file as possibly
        # modified ("Entry ... not uptodate") where the real repository would not (contents are unchanged)
        subprocess.run(["git", *SAFE_CONFIG, "update-index", "-q", "--refresh"], cwd=cwd, env=env, capture_output=True,
                       timeout=TIME_LIMIT, stdin=subprocess.DEVNULL)
        for c in commands:
            sub, args = P.parse_git(c)
            if sub is None or sub not in LOCAL_SUBS:
                out["stopped"] = f"`git {sub or '?'}` is not run on a copy"
                break
            left = TIME_LIMIT - (time.time() - start)
            if left <= 0:
                out["stopped"] = "time limit"
                break
            try:
                r = subprocess.run(["git", *SAFE_CONFIG, sub, *args], cwd=cwd, env=env, capture_output=True, text=True,
                                   timeout=left, stdin=subprocess.DEVNULL)
            except subprocess.TimeoutExpired:
                out["stopped"] = "time limit"
                break
            out["exit"].append(r.returncode)
            err = (r.stderr or r.stdout or "").strip().splitlines()
            out["stderr"].append(err[0][:200] if err else "")
            out["ran"] += 1
        # lost work, only when every command ran here and the work tree was small enough to compare
        if out["ran"] == len(list(commands)) and before is not None:
            lost = sorted(p for p, vs in before.items() for c in vs if not _survives(cwd, env, p, c))
            out["lost"] = sorted(set(lost))
        return out
    finally:
        shutil.rmtree(work, ignore_errors=True)
