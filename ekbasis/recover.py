"""What git or a rebuild can give back (0.1.3): the checks that let the hook skip the model when nothing at risk could be
lost for good.

A file is recoverable when git holds its content (a tracked file with no change against HEAD, staged or not) or when it
is ignored and rebuildable (build outputs, caches and dependency folders, by name: see REBUILDABLE). Untracked files
that are not ignored, changed tracked files, other ignored files (.env, editor settings, virtual environments) and
anything inside .git are not. These checks only read: git status, rev-parse, stash list.
"""
from __future__ import annotations

import fnmatch
import os
import subprocess

ENV = {"LC_ALL": "C", "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0"}

REBUILDABLE_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", ".nox", ".hypothesis",
                    ".eggs", "node_modules", ".next", ".nuxt", ".parcel-cache", ".turbo", ".svelte-kit", ".angular",
                    ".gradle", ".sass-cache", "bower_components", "build", "dist", "target", "out", "_build", "coverage",
                    "htmlcov", ".nyc_output", ".cache"}
REBUILDABLE_FILES = ("*.pyc", "*.pyo", "*.o", "*.obj", "*.class", ".coverage", ".coverage.*", ".DS_Store",
                     "*.egg-info", "*.tsbuildinfo")


def rebuildable(rel: str) -> bool:
    """Whether a path (relative to the repository) is a build output, cache or dependency folder, by its name."""
    parts = [p for p in rel.replace(os.sep, "/").strip("/").split("/") if p]
    if not parts:
        return False
    if any(p in REBUILDABLE_DIRS or p.endswith(".egg-info") for p in parts):
        return True
    return any(fnmatch.fnmatch(parts[-1], pat) for pat in REBUILDABLE_FILES)


def _git(repo: str, *args: str, timeout: float = 30) -> tuple[int, str]:
    try:
        p = subprocess.run(["git", *args], cwd=repo, env=dict(os.environ, **ENV), stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL, text=True, errors="replace", timeout=timeout)
    except (subprocess.TimeoutExpired, FileNotFoundError, NotADirectoryError, PermissionError):
        return 1, ""
    return p.returncode, p.stdout


def toplevel(path: str) -> str | None:
    """The work tree that holds a path (a folder, or a file's folder), or None outside git."""
    d = path if os.path.isdir(path) else os.path.dirname(path)
    while d and not os.path.isdir(d):
        d = os.path.dirname(d)
    if not d:
        return None
    rc, out = _git(d, "rev-parse", "--show-toplevel")
    return out.strip() if rc == 0 and out.strip() else None


def _entries(top: str, paths=None) -> list | None:
    """git status entries (XY, path) with untracked and ignored files listed one by one; None if git fails."""
    args = ["status", "--porcelain=v1", "-z", "--untracked-files=all", "--ignored=matching"]
    if paths is not None:
        args += ["--"] + list(paths)
    rc, out = _git(top, *args, timeout=60)
    if rc != 0:
        return None
    toks, res, i = out.split("\0"), [], 0
    while i < len(toks):
        t = toks[i]
        if len(t) >= 4:
            res.append((t[:2], t[3:]))
            if t[0] in "RC":  # a rename's or copy's source follows as its own field
                i += 1
        i += 1
    return res


def _clean(entries) -> bool:
    """Every entry is an ignored, rebuildable path (a clean tracked file gives no entry)."""
    return all(xy == "!!" and rebuildable(p) for xy, p in entries)


def _git_dir(top: str) -> str | None:
    rc, out = _git(top, "rev-parse", "--absolute-git-dir")
    return out.strip() if rc == 0 and out.strip() else None


def no_uncommitted_work(repo: str) -> str | None:
    """A reason when the repository holds no work git could lose: every work tree (main and linked) has only clean
    tracked files and ignored rebuildable ones, the stash is empty, no merge/rebase/cherry-pick/revert/am is under way,
    and there are no submodules. None otherwise (the model decides)."""
    top = toplevel(repo)
    if not top:
        return None
    if os.path.exists(os.path.join(top, ".gitmodules")):
        return None
    rc, out = _git(top, "worktree", "list", "--porcelain")
    trees = [l[len("worktree "):] for l in out.splitlines() if l.startswith("worktree ")] if rc == 0 else [top]
    for t in trees or [top]:
        if not os.path.isdir(t):
            continue  # a missing linked worktree holds no files
        e = _entries(t)
        if e is None or not _clean(e):
            return None
        gd = _git_dir(t)
        if gd is None or any(os.path.exists(os.path.join(gd, x)) for x in
                             ("MERGE_HEAD", "rebase-merge", "rebase-apply", "CHERRY_PICK_HEAD", "REVERT_HEAD")):
            return None
    rc, out = _git(top, "stash", "list")
    if rc != 0 or out.strip():
        return None
    return "no uncommitted work in the repository (everything is committed or ignored and rebuildable)"


PURE_READ = {"cat", "head", "tail", "wc", "ls", "du", "df", "stat", "file", "diff", "cmp", "grep", "egrep", "fgrep", "rg",
             "less", "more", "nl", "tac", "rev", "cut", "paste", "tr", "uniq", "column", "strings", "xxd", "od", "readlink",
             "realpath", "md5", "md5sum", "sha1sum", "sha256sum", "shasum", "jq", "which", "type", "echo", "printf",
             "pwd", "true", "false", "test", "[", "basename", "dirname", "date", "touch", "mkdir", "cd", "git"}
FIND_WRITES = {"-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint", "-fprint0", "-fprintf", "-fls"}


RUNNERS = {"go": {"build", "test", "vet", "list", "version", "env", "doc", "help"},
           "cargo": {"build", "test", "check", "clippy", "bench", "doc"},
           "npm": {"test", "t"}, "pnpm": {"test"}, "yarn": {"test"}}
RUNNER_OUTPUTS = ("-o", "-coverprofile", "-cpuprofile", "-memprofile", "-blockprofile", "-mutexprofile", "-trace",
                  "-outputdir", "--output", "--out-dir", "--target-dir")


def _runner(name: str, texts: list) -> bool:
    """Test, build and lint runners whose own writes are caches or build outputs (rebuildable): `go test ./...`,
    `python -m pytest`, `npm test`, `npx ava`, `gofmt -l`, `cargo test`. Any output option makes it a writer."""
    if any(t.split("=", 1)[0] in RUNNER_OUTPUTS for t in texts):
        return False
    first = next((t for t in texts if not t.startswith("-")), None)
    if name in RUNNERS:
        if name == "npm" and first == "run":
            rest = [t for t in texts if not t.startswith("-")]
            return len(rest) > 1 and rest[1] == "test"
        return first in RUNNERS[name]
    if name == "gofmt":
        return "-w" not in texts
    if name in ("python", "python3") or name.startswith("python3."):
        return len(texts) >= 2 and texts[0] == "-m" and texts[1] in ("pytest", "unittest", "doctest")
    if name == "pytest":
        return True
    if name == "npx":
        return first in ("ava", "tsc") and ("--noEmit" in texts or first == "ava")
    if name == "node":
        return "--test" in texts
    return False


def _pure_read(name: str, argv: list) -> bool:
    """A command that can change no file content by itself (its redirections are read separately), or a test/build
    runner whose writes are rebuildable. `git` here is a git command whose own effect the git guard judges (in the
    shell part of a line the hook replaces it with `true`)."""
    texts = [t for t in argv if t is not None]
    if _runner(name, texts):
        return True
    if name == "sed":
        return not any(t == "--in-place" or t.startswith("--in-place=") or
                       (t.startswith("-") and not t.startswith("--") and "i" in t[1:]) for t in texts)
    if name == "sort":
        return not any(t in ("-o", "--output") or t.startswith("--output=") or
                       (t.startswith("-") and not t.startswith("--") and "o" in t[1:]) for t in texts)
    if name == "find":
        return not any(t in FIND_WRITES for t in texts)
    return name in PURE_READ


def write_touched(view, cwd: str, shell: str | None = None):
    """(paths the lines' commands could change, what could not be read), with the shell guard's own reader: commands
    that only read touch nothing here (their redirections still count) and `cd` only moves the folder."""
    from . import shell as S

    class _Writes(S._Reader):
        def read_command(self, name, argv, base, k=0):
            if _pure_read(name, argv):
                return set()
            # an empty argument names no file (BSD `sed -i '' ...` gives one)
            return super().read_command(name, [a for a in argv if a != ""], base, k)

    rd = _Writes(os.path.realpath(cwd), shell or view.info.get("shell") or S.default_shell(), S._key(b"recover"), 200)
    for k, ps in enumerate(view.parsed, 1):
        rd.read_line(k, ps)
    return dict(rd.touched), list(rd.unread)


def touched_recoverable(view, cwd: str) -> str | None:
    """For the shell guard (shell.check's skip): a reason when every path the lines could change is recoverable, so
    nothing could be lost for good. None (the model decides) when a line runs xargs (its targets come from input), when
    a path is inside .git or holds a work tree, when a path is outside git, or when one is changed, untracked, or
    ignored but not rebuildable."""
    if any(command_is_xargs(ps) for ps in view.parsed):
        return None
    touched, unread = write_touched(view, cwd)
    if unread:
        return None
    root = os.path.realpath(cwd)
    by_top: dict = {}
    for r, how in touched.items():
        full = r if os.path.isabs(r) else os.path.normpath(os.path.join(root, r))
        if ".git" in full.replace(os.sep, "/").split("/"):
            return None
        if not os.path.lexists(full):
            continue  # nothing there to lose
        if os.path.isdir(full) and not os.path.islink(full) and os.path.exists(os.path.join(full, ".git")):
            return None  # a work tree itself, with its .git
        top = toplevel(full)
        if not top:
            return None
        real_full, real_top = os.path.realpath(full), os.path.realpath(top)
        if real_full == real_top or not real_full.startswith(real_top + os.sep):
            return None
        by_top.setdefault(top, []).append(os.path.relpath(real_full, real_top))
    for top, rels in by_top.items():
        e = _entries(top, rels)
        if e is None or not _clean(e):
            return None
    if not by_top:
        return "the lines change no file that exists now"
    return "everything the lines could change is committed in git or ignored and rebuildable"


def clean_recoverable(repo: str, command: str) -> bool:
    """A `git clean -X` (only ignored files) whose dry run (git's own -n with the same options) removes only
    rebuildable paths. Other forms (-x, or untracked files) are left to the model."""
    from . import prompts as P
    sub, args = P.parse_git(command)
    if sub != "clean" or any(a in ("-i", "--interactive") for a in args):
        return False
    if "X" not in P.short_flags(args, stop="e") or "x" in P.short_flags(args, stop="e"):
        return False
    dry = [a for a in args if a not in ("-f", "--force")]
    dry = ["-" + "".join(ch for ch in a[1:] if ch != "f") if a.startswith("-") and not a.startswith("--") else a
           for a in dry]
    dry = [a for a in dry if a != "-"]
    rc, out = _git(repo, "clean", "-n", *dry)
    if rc != 0:
        return False
    removed = [l[len("Would remove "):] for l in out.splitlines() if l.startswith("Would remove ")]
    return all(rebuildable(p) or _all_rebuildable(repo, p) for p in removed)


def _all_rebuildable(repo: str, rel: str) -> bool:
    """A folder git would remove as a whole: every file under it is rebuildable by name (pkg/ holding only
    pkg/__pycache__/m.pyc)."""
    top = os.path.join(repo, rel)
    if not os.path.isdir(top) or os.path.islink(top):
        return False
    for dp, dn, fn in os.walk(top):
        if ".git" in dn or ".git" in fn:
            return False
        for f in fn:
            if not rebuildable(os.path.relpath(os.path.join(dp, f), repo)):
                return False
    return True


def command_is_xargs(parsed) -> bool:
    from .shell import command_name
    return any(command_name(list(s.words))[0] == "xargs" for s in parsed.commands)
