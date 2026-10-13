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


def run_on_copy(repo: str, commands) -> dict | None:
    """{"exit": [code per command run], "stderr": [first line per command], "ran": n, "stopped": why or None}, or None
    when the repository cannot be copied safely. commands: git command lines, as the user wrote them."""
    from .preflight import _copy_tree   # the copy that preflight uses (clonefile / reflink / capped)
    top = _toplevel(repo)
    if not top or not os.path.isdir(os.path.join(top, ".git")):
        return None   # not a work tree, or .git is a file (linked worktree, submodule)
    rel = os.path.relpath(os.path.realpath(repo), os.path.realpath(top))
    work = tempfile.mkdtemp(prefix="ekbasis-git-")
    dst = os.path.join(work, "repo")
    out = {"exit": [], "stderr": [], "ran": 0, "stopped": None}
    try:
        try:
            _copy_tree(top, dst)
        except Exception:  # noqa: BLE001 — too big, no clonefile or reflink: leave it to the model
            return None
        cwd = os.path.normpath(os.path.join(dst, rel))
        env = {**os.environ, **ENV}
        start = time.time()
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
        return out
    finally:
        shutil.rmtree(work, ignore_errors=True)
