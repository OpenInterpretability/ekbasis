"""Shared paths, environments, ledger and statistics for the 0.1.3 re-run of the real-terminal study (see
../SPEC.md and ../SPEC_ADDENDUM_013.md). Changed from harness/common.py: results_013, the US$ 5 budget, the caps,
and the 0.1.3 hook beside the published 0.1.2 one."""
from __future__ import annotations

import ctypes
import fcntl
import json
import math
import os
import subprocess
import time

STUDY = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(STUDY, "results_013")
W = os.path.realpath(os.environ.get("EKB_RT_WORK", "/tmp/ekb_rt"))           # work root (APFS, internal disk)
HOME = os.path.expanduser("~")
CLAUDE = os.path.join(HOME, ".local/bin/claude")
PY312 = os.environ.get("PY312", "/opt/homebrew/bin/python3.12")
EKB_VENV = os.path.join(W, "ekbasis_venv")
EKB_PY = os.path.join(EKB_VENV, "bin/python")
EKB_HOOK = os.path.join(EKB_VENV, "bin/ekbasis-claude-hook")
EKB_COMMIT = "c67ebed"
EKB013_VENV = os.path.join(W, "ekbasis013_venv")
EKB013_PY = os.path.join(EKB013_VENV, "bin/python")
EKB013_HOOK = os.path.join(EKB013_VENV, "bin/ekbasis-claude-hook")     # the version under test (live in arm H)
TUNNEL_URL = "http://127.0.0.1:18642"
BUDGET = 5.00
SESSION_CAP = 0.25          # Sonnet; the 0.1.2 study's costliest session was US$ 0.081
HAIKU_CAP = 0.20            # the 0.1.2 study's costliest Haiku session was US$ 0.079
LEDGER = os.path.join(RESULTS, "ledger.jsonl")
ORDER_SEED = 77012601
REPLAY_SEED = 77012602
REPLAY_SHARE = 0.25

REPOS = {  # name: (GitHub path, pinned commit, default branch)
    "more-itertools": ("more-itertools/more-itertools", "1ea82a7", "master"),
    "pflag": ("spf13/pflag", "c966cfe", "master"),
    "chalk": ("chalk/chalk", "47fc05a", "main"),
}

SETUP_GIT = {"GIT_AUTHOR_NAME": "Repo Maintainer", "GIT_AUTHOR_EMAIL": "maintainer@example.invalid",
             "GIT_COMMITTER_NAME": "Repo Maintainer", "GIT_COMMITTER_EMAIL": "maintainer@example.invalid"}


def d(*parts) -> str:
    return os.path.join(W, *parts)


def base_env(sid: str | None = None, python: bool = False) -> dict:
    """The clean environment every agent session, check and replay runs in (no user shell files, local caches)."""
    path = ["/opt/homebrew/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin"]
    if python and sid:
        path.insert(0, d("venvs", sid, "bin"))
    env = {
        "HOME": HOME, "USER": os.environ.get("USER", "user"), "LOGNAME": os.environ.get("USER", "user"),
        "PATH": ":".join(path), "SHELL": "/bin/zsh", "ZDOTDIR": d("zdot"), "XDG_CONFIG_HOME": d("xdg"),
        "LANG": "en_US.UTF-8", "TERM": "dumb",
        "TMPDIR": d("tmp", sid or "misc") + "/",
        "GOPATH": d("cache", "gopath"), "GOMODCACHE": d("cache", "gomod"), "GOCACHE": d("cache", "gobuild"),
        "GOTOOLCHAIN": "local", "npm_config_cache": d("cache", "npm"), "npm_config_update_notifier": "false",
        "npm_config_fund": "false", "npm_config_audit": "false", "PIP_CACHE_DIR": d("cache", "pip"),
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "GIT_CONFIG_GLOBAL": d("gitconfig"), "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0",
        "DISABLE_AUTOUPDATER": "1", "CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR": "1",
    }
    env["TMPPREFIX"] = env["TMPDIR"] + "zsh"   # zsh here-documents (added after the primary run, see the SPEC)
    os.makedirs(env["TMPDIR"], exist_ok=True)
    return env


def ekbasis_env(env: dict) -> dict:
    """What the hook process gets on top of the session's environment (only the H arm calls it)."""
    return {**env, "EKBASIS_URL": TUNNEL_URL, "EKBASIS_SHELL_GUARD": "1"}


def run(cmd, cwd=None, env=None, check=True, timeout=600, input=None):
    p = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout, input=input)
    if check and p.returncode != 0:
        raise RuntimeError(f"{cmd} failed ({p.returncode}): {p.stderr[-2000:]}")
    return p


def git(repo, *args, env=None, check=True, timeout=600):
    return run(["git", "-C", repo, *args], env=env, check=check, timeout=timeout)


def clone_tree(src: str, dst: str) -> float:
    """APFS copy-on-write clone of a folder (clonefile(2) on the whole tree); returns the seconds it took."""
    t = time.monotonic()
    if ctypes.CDLL("libc.dylib", use_errno=True).clonefile(src.encode(), dst.encode(), 0) != 0:
        subprocess.run(["cp", "-c", "-R", src, dst], check=True, capture_output=True)
    return time.monotonic() - t


# ------------------------------------------------------------------ ledger

def _locked(path, mode):
    fh = open(path, mode)
    fcntl.flock(fh, fcntl.LOCK_EX)
    return fh


def ledger_add(entry: dict) -> None:
    os.makedirs(RESULTS, exist_ok=True)
    with _locked(LEDGER, "a") as fh:
        fh.write(json.dumps({"t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **entry}) + "\n")


def ledger_spent() -> float:
    if not os.path.exists(LEDGER):
        return 0.0
    with _locked(LEDGER, "r") as fh:
        return round(sum(float(json.loads(x).get("usd", 0)) for x in fh if x.strip()), 6)


def read_jsonl(path):
    if not os.path.exists(path):
        return []
    with open(path) as fh:
        return [json.loads(x) for x in fh if x.strip()]


# ------------------------------------------------------------------ statistics

def wilson(k: int, n: int, z: float = 1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, c - h), min(1.0, c + h))


def pct(k, n) -> str:
    if not n:
        return "–"
    lo, hi = wilson(k, n)
    return f"{100 * k / n:.1f}% ({k}/{n}; IC95 {100 * lo:.1f}–{100 * hi:.1f})"
