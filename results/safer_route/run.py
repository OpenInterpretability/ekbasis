"""The safer route on the classic losses, against a real Ekbasis server: for each scenario a throwaway repository, the
original command checked (model and code), the route search timed, then the route RUN in the repository and checked
to keep what the original would lose. Run: EKBASIS_URL=... EKBASIS_API_KEY=... python3 results/safer_route/run.py
[reps] > results/safer_route/runs.json"""
import io
import json
import os
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from ekbasis import claude_code_hook as H  # noqa: E402
from ekbasis import git as G  # noqa: E402
from ekbasis import safer as SF  # noqa: E402
from ekbasis.client import Ekbasis  # noqa: E402

ENV = dict(os.environ, GIT_AUTHOR_NAME="Dev", GIT_AUTHOR_EMAIL="dev@example.invalid", GIT_COMMITTER_NAME="Dev",
           GIT_COMMITTER_EMAIL="dev@example.invalid", GIT_CONFIG_NOSYSTEM="1", LC_ALL="C")


def sh(cmd, cwd, check=True):
    p = subprocess.run(["bash", "-c", cmd], cwd=cwd, env=ENV, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if check and p.returncode:
        raise RuntimeError(f"{cmd}: {p.stdout}")
    return p.stdout


def base(root):
    """main (2 commits, pushed); feature (app.py differs); unmerged (1 own commit); one stash entry."""
    sh(f"git init -q --bare -b main {root}/origin.git", root)
    r = os.path.join(root, "work")
    os.makedirs(r)
    for c in ("git init -q -b main", "git config commit.gpgsign false", "git remote add origin ../origin.git",
              "printf 'def f():\\n    return 1\\n' > app.py", "echo r > README.md", "git add -A", "git commit -qm one",
              "echo '# v2' >> app.py", "git commit -qam two", "git push -q -u origin main", "git checkout -qb feature",
              "echo '# feature' >> app.py", "git commit -qam feat", "git checkout -q main", "git checkout -qb unmerged",
              "echo u > u.txt", "git add u.txt", "git commit -qm unmerged-work", "git checkout -q main"):
        sh(c, r)
    return r


def edit(r):
    sh("echo 'WORK = \"uncommitted edit\"' >> app.py", r)


def stash_has(text, ref="stash@{0}"):
    return lambda r: text in sh(f"git stash show -p '{ref}'", r, check=False)


def setup_push(r):
    other = os.path.join(os.path.dirname(r), "other")
    sh(f"git clone -q ../origin.git {other}", r)
    sh("git config commit.gpgsign false && echo theirs > theirs.txt && git add theirs.txt && git commit -qm theirs "
       "&& git push -q", other)
    sh("git fetch -q && git commit -q --allow-empty -m mine", r)


SCENARIOS = [
    ("reset --hard", "git reset --hard", edit, stash_has("uncommitted edit")),
    ("reset --hard HEAD~1 (unpushed commit)", "git reset --hard HEAD~1",
     lambda r: (sh("git commit -q --allow-empty -m local-only", r), edit(r)),
     lambda r: stash_has("uncommitted edit")(r) and "local-only" in sh("git log -1 --format=%s backup/main", r, False)),
    ("checkout -- file", "git checkout -- app.py", edit, stash_has("uncommitted edit")),
    ("restore file", "git restore app.py", edit, stash_has("uncommitted edit")),
    ("checkout -f branch", "git checkout -f feature", edit,
     lambda r: stash_has("uncommitted edit")(r) and sh("git branch --show-current", r).strip() == "feature"),
    ("clean -fd", "git clean -fd", lambda r: sh("echo n > notes.txt && mkdir -p scratch && echo s > scratch/s.txt", r),
     lambda r: not os.path.exists(os.path.join(r, "notes.txt"))
     and {"notes.txt", "scratch/s.txt"} <= set(sh("git show --name-only --format= 'stash@{0}^3'", r, False).split())),
    ("branch -D unmerged", "git branch -D unmerged", lambda r: None,
     lambda r: "unmerged-work" in sh("git log -1 --format=%s backup/unmerged", r, False)
     or "unmerged-work" in sh("git log -1 --format=%s unmerged", r, False)),
    ("stash drop", "git stash drop", lambda r: sh("echo stashed >> README.md && git stash -q", r),
     lambda r: "stashed" in sh("git diff backup/stash-0^1 backup/stash-0", r, False)),
    ("push --force over remote commits", "git push --force", setup_push,
     lambda r: "theirs" in sh("git log -1 --format=%s backup/origin-main", r, False)
     and "mine" in sh("git --git-dir=../origin.git log -1 --format=%s main", r, False)),
]


def hook(cmd, r, safer):
    """The Claude Code hook on this line (nothing runs): seconds, and its message."""
    old_in, old_out, old_env = sys.stdin, sys.stdout, os.environ.get("EKBASIS_SAFER")
    sys.stdin, sys.stdout = io.StringIO(json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": r})), io.StringIO()
    os.environ["EKBASIS_SAFER"] = "1" if safer else "0"
    t0 = time.monotonic()
    try:
        H.main()
        out = sys.stdout.getvalue().strip()
    finally:
        sys.stdin, sys.stdout = old_in, old_out
        if old_env is None:
            os.environ.pop("EKBASIS_SAFER", None)
        else:
            os.environ["EKBASIS_SAFER"] = old_env
    took = time.monotonic() - t0
    return round(took, 2), (json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"] if out else None)


def one(name, cmd, prep, kept, client):
    with tempfile.TemporaryDirectory() as root:
        r = base(os.path.realpath(root))
        prep(r)
        t0 = time.monotonic()
        v = G.check([cmd], repo=r, client=client)
        t_check = time.monotonic() - t0
        code = SF.code_problems([cmd], r)
        s = SF.search([cmd], repo=r, client=client)
        h_off, _ = hook(cmd, r, False)
        h_on, msg = hook(cmd, r, True)
        row = {"scenario": name, "command": cmd, "p_lost": round(v.p_lost, 4), "model_risky": v.risky,
               "code": code, "check_s": round(t_check, 2), "search_s": round(s.seconds, 2), "tried": s.tried,
               "route": s.route.commands if s.route else None, "route_p_lost": round(s.route.p_lost, 4) if s.route else None,
               "note": s.note, "hook_s_off": h_off, "hook_s_on": h_on, "hook_message": msg}
        if s.route:
            out = subprocess.run(["bash", "-c", " && ".join(s.route.commands)], cwd=r, env=ENV, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True)
            row["route_exit"] = out.returncode
            row["work_kept"] = bool(kept(r))
        if name.startswith("push"):   # --force-with-lease alone, on a fresh copy of the same state
            with tempfile.TemporaryDirectory() as root2:
                r2 = base(os.path.realpath(root2))
                prep(r2)
                rc = subprocess.run(["git", "push", "--force-with-lease"], cwd=r2, env=ENV, capture_output=True).returncode
                row["lease_alone"] = {"exit": rc, "remote_main": sh("git --git-dir=../origin.git log -1 --format=%s main",
                                                                     r2).strip()}
        return row


def main():
    reps = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    client = Ekbasis(timeout=60, surface="safer-route-study")
    rows = [dict(one(*sc, client), rep=k) for k in range(reps) for sc in SCENARIOS]
    print(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
