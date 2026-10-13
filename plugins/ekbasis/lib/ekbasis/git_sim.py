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


def _tree(cwd, env, ref) -> dict:
    """{path: blob id} of a commit's tree (one `git ls-tree -r`)."""
    rc, out = _g(cwd, env, "ls-tree", "-r", "-z", "--full-tree", ref)
    tree = {}
    for item in (out.decode(errors="replace").split("\0") if rc == 0 else []):
        meta, _, path = item.partition("\t")
        parts = meta.split()
        if path and len(parts) == 3 and parts[1] == "blob":
            tree[path] = parts[2]
    return tree


def _index(cwd, env) -> dict:
    """{path: {blob ids}} in the index (every stage: a conflict keeps both sides)."""
    rc, out = _g(cwd, env, "ls-files", "-s", "-z")
    idx = {}
    for item in (out.decode(errors="replace").split("\0") if rc == 0 else []):
        meta, _, path = item.partition("\t")
        parts = meta.split()
        if path and len(parts) == 3:
            idx.setdefault(path, set()).add(parts[1])
    return idx


def _worktree_blobs(cwd, env, paths) -> dict:
    """{path: blob id} of the files in the work tree (one `git hash-object --stdin-paths`)."""
    files = [p for p in sorted(paths) if os.path.isfile(os.path.join(cwd, p)) and not os.path.islink(os.path.join(cwd, p))]
    if not files:
        return {}
    r = subprocess.run(["git", *SAFE_CONFIG, "hash-object", "--no-filters", "--stdin-paths"], cwd=cwd, env=env,
                       input="\n".join(files).encode(), capture_output=True, timeout=TIME_LIMIT)
    ids = r.stdout.decode().split()
    return dict(zip(files, ids)) if r.returncode == 0 and len(ids) == len(files) else {}


def _stash_commits(cwd, env) -> list:
    rc, hs = _g(cwd, env, "stash", "list", "--format=%H")
    out = []
    for h in hs.decode().split()[:50]:
        for ref in (h, h + "^2", h + "^3"):
            rc, sha = _g(cwd, env, "rev-parse", "--verify", "-q", ref)
            if rc == 0:
                out.append(sha.decode().strip())
    return out


def _uncommitted(cwd, env) -> dict | None:
    """{path: {blob id}}: versions in the work tree (tracked and changed, untracked or ignored files), in the index, or
    only in a stash entry, that HEAD does not have. None when there are too many files to compare. Works on blob ids:
    a handful of git calls, whatever the number of files."""
    rc, out = _g(cwd, env, "ls-files", "-z", "--modified", "--others", "--deleted")
    rc2, ign = _g(cwd, env, "ls-files", "-z", "--others", "--ignored", "--exclude-standard")
    paths = {p for blob in (out, ign) for p in blob.decode(errors="replace").split("\0") if p}
    head = _tree(cwd, env, "HEAD")
    idx = _index(cwd, env)
    paths |= {p for p, ids in idx.items() if ids != {head.get(p)}}
    if len(paths) > MAX_FILES:
        return None
    total = sum(os.path.getsize(os.path.join(cwd, p)) for p in paths
                if os.path.isfile(os.path.join(cwd, p)) and not os.path.islink(os.path.join(cwd, p)))
    if total > MAX_BYTES:
        return None
    vers = {}
    for p, b in _worktree_blobs(cwd, env, paths).items():
        if b != head.get(p):
            vers.setdefault(p, set()).add(b)
    for p in paths:
        for b in idx.get(p, ()):
            if b != head.get(p):
                vers.setdefault(p, set()).add(b)
    for c in _stash_commits(cwd, env):
        for p, b in _tree(cwd, env, c).items():
            if b != head.get(p):
                vers.setdefault(p, set()).add(b)
    # keep the content of work-tree versions now: the commands may delete the files (their blobs are not in .git)
    store = {}
    for p, ids in vers.items():
        full = os.path.join(cwd, p)
        if os.path.isfile(full) and not os.path.islink(full):
            store[p] = open(full, "rb").read()
    return {"vers": vers, "files": store}


def _cat(cwd, env, ids) -> dict:
    """{blob id: content} (one `git cat-file --batch`)."""
    ids = sorted(set(ids))
    if not ids:
        return {}
    r = subprocess.run(["git", *SAFE_CONFIG, "cat-file", "--batch"], cwd=cwd, env=env, input="\n".join(ids).encode() + b"\n",
                       capture_output=True, timeout=TIME_LIMIT)
    out, data, at = {}, r.stdout, 0
    for i in ids:
        nl = data.find(b"\n", at)
        if nl < 0:
            break
        head = data[at:nl].split()
        if len(head) == 2 and head[1] == b"missing":
            at = nl + 1
            continue
        size = int(head[2])
        out[i] = data[nl + 1: nl + 1 + size]
        at = nl + 1 + size + 1
    return out


def _lost(cwd, env, before) -> list:
    """Paths with an uncommitted version (from _uncommitted) that survives nowhere after the commands: work tree, index,
    any branch, remote-tracking or tag tip, any stash entry; or inside another version of the same file."""
    vers, files = before["vers"], before["files"]
    paths = set(vers)
    after = {p: set() for p in paths}
    for p, b in _worktree_blobs(cwd, env, paths).items():
        after[p].add(b)
    for p, ids in _index(cwd, env).items():
        if p in after:
            after[p] |= ids
    rc, out = _g(cwd, env, "for-each-ref", "--format=%(objectname)", "refs/heads", "refs/remotes", "refs/tags")
    commits = out.decode().split()[:300] + _stash_commits(cwd, env)
    for c in commits:
        for p, b in _tree(cwd, env, c).items():
            if p in after:
                after[p].add(b)
    missing = {p: {b for b in ids if b not in after[p]} for p, ids in vers.items()}
    missing = {p: ids for p, ids in missing.items() if ids}
    if not missing:
        return []
    # not found as such: is the content inside another version of the same file (a merge with conflict markers)?
    contents = _cat(cwd, env, [b for ids in missing.values() for b in ids] + [b for p in missing for b in after[p]])
    now = {p: [contents.get(b, b"") for b in after[p]] + ([open(os.path.join(cwd, p), "rb").read()]
                                                           if os.path.isfile(os.path.join(cwd, p)) else []) for p in missing}
    lost = set()
    for p, ids in missing.items():
        for b in ids:
            c = contents.get(b)
            if c is None and p in files:
                c = files[p]     # a work-tree version: its content was kept before the commands ran
            want = (c or b"").strip()
            if not want or not any(want in x for x in now[p]):
                lost.add(p)
    return sorted(lost)


AUTO_BUDGET = 8.0          # seconds for the whole run when it is on by default (0.1.37): past it, the model decides
AUTO_MAX_BYTES = 128 << 20  # without clonefile or reflinks, larger work trees are not copied by default


AUTO_MAX_FILES = 20000      # entries in the work tree (ignored folders such as node_modules included)


def _few_files(top: str, limit: int = AUTO_MAX_FILES, seconds: float = 1.0) -> bool:
    """Whether the work tree has at most `limit` entries, counted for at most `seconds` (a clone copies every file, and
    a tree with a large node_modules takes longer to copy and remove than the whole check may)."""
    n, t0 = 0, time.time()
    for _root, dirs, files in os.walk(top):
        n += len(dirs) + len(files)
        if n > limit or time.time() - t0 > seconds:
            return False
    return True


def _remove_later(path: str) -> None:
    """Remove a copy without waiting for it (a large tree takes seconds to delete)."""
    try:
        subprocess.Popen(["rm", "-rf", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except Exception:  # noqa: BLE001
        shutil.rmtree(path, ignore_errors=True)


def _cheap_to_copy(top: str) -> bool:
    """On by default only where a copy is cheap: macOS (APFS clonefile), or a work tree under AUTO_MAX_BYTES
    (a reflink is tried first anyway, and a full copy of a small tree takes well under a second)."""
    import platform
    return _few_files(top) and (platform.system() == "Darwin" or _small(top))


def _copy(top: str, copy_tree):
    """(work folder, copy path) or (None, None). A clone (clonefile, reflink) only works within one file system, so:
    the system's temporary folder first; then a hidden folder next to the repository, on its own disk (repositories on
    an external drive); then, for a small work tree, a plain copy. The caller removes the work folder."""
    tries = [tempfile.gettempdir()]
    parent = os.path.dirname(top)
    if os.access(parent, os.W_OK):
        tries.append(parent)
    for base in tries:
        work = tempfile.mkdtemp(prefix=".ekbasis-sim-", dir=base)
        dst = os.path.join(work, "repo")
        try:
            copy_tree(top, dst)
            return work, dst
        except Exception:  # noqa: BLE001 — another file system, or too big without clones
            shutil.rmtree(work, ignore_errors=True)
    if _small(top):
        work = tempfile.mkdtemp(prefix=".ekbasis-sim-")
        dst = os.path.join(work, "repo")
        try:
            subprocess.run(["cp", "-R", "-p", top, dst], check=True, capture_output=True, timeout=TIME_LIMIT)
            return work, dst
        except Exception:  # noqa: BLE001
            shutil.rmtree(work, ignore_errors=True)
    return None, None


def _small(top: str) -> bool:
    try:
        r = subprocess.run(["du", "-sk", top], capture_output=True, text=True, timeout=3)
        return r.returncode == 0 and int(r.stdout.split()[0]) * 1024 <= AUTO_MAX_BYTES
    except Exception:  # noqa: BLE001
        return False


def run_on_copy(repo: str, commands, budget: float | None = None) -> dict | None:
    """{"exit": [code per command run], "stderr": [first line per command], "ran": n, "stopped": why or None, "lost":
    [paths whose uncommitted content survives nowhere] or None (not every command ran, or too many files)}, or None
    when the repository cannot be copied safely. commands: git command lines, as the user wrote them."""
    from .preflight import _copy_tree   # the copy that preflight uses (clonefile / reflink / capped)
    t0 = time.time()
    top = _toplevel(repo)
    if not top or not os.path.isdir(os.path.join(top, ".git")):
        return None   # not a work tree, or .git is a file (linked worktree, submodule)
    if budget is not None and not _cheap_to_copy(top):
        return None
    over = lambda: budget is not None and time.time() - t0 > budget   # noqa: E731
    rel = os.path.relpath(os.path.realpath(repo), os.path.realpath(top))
    work, dst = _copy(top, _copy_tree)
    if not work:
        return None
    out = {"exit": [], "stderr": [], "ran": 0, "stopped": None, "lost": None}
    try:
        cwd = os.path.normpath(os.path.join(dst, rel))
        env = {**os.environ, **ENV}
        start = time.time()
        if over():
            return None
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
            if over():
                return None   # on by default: never slower than the budget; the model decides
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
            out["lost"] = None if over() else _lost(cwd, env, before)
        if over():
            return None
        return out
    finally:
        _remove_later(work)
