"""Build the work root once (see ../SPEC.md): ekbasis 0.1.2 from GitHub, pinned full clones, caches, one template per
task with its start state (U0, C0) and a validation that each task starts not done.

usage: python3 prepare.py [all|templates|validate]
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

from common import (EKB_COMMIT, EKB_HOOK, EKB_PY, EKB_VENV, PY312, REPOS, W, base_env, clone_tree, d, git, run)
import tasks as T
import truth

GITCONFIG = """[user]
\tname = Study Agent
\temail = agent@example.invalid
[credential]
\thelper =
[init]
\tdefaultBranch = main
[advice]
\tdetachedHead = false
"""


def dirs():
    for x in ("bin", "cfg", "templates", "s", "snaps", "logs", "venvs", "tmp", "zdot", "xdg", "wheels", "base", "final",
              "cache/gopath", "cache/gomod", "cache/gobuild", "cache/npm", "cache/pip"):
        os.makedirs(d(x), exist_ok=True)
    with open(d("gitconfig"), "w") as fh:
        fh.write(GITCONFIG)


def ekbasis():
    if os.path.exists(EKB_HOOK):
        return
    run([PY312, "-m", "venv", EKB_VENV])
    run([os.path.join(EKB_VENV, "bin/pip"), "install", "-q",
         f"git+https://github.com/OpenInterpretability/ekbasis@{EKB_COMMIT}"], timeout=900)
    v = run([EKB_PY, "-c", "import ekbasis; print(ekbasis.__version__)"]).stdout.strip()
    assert v == "0.1.2", v


def bases(env):
    for name, (gh, commit, branch) in REPOS.items():
        b = d("base", name)
        if not os.path.exists(b):
            run(["git", "clone", "-q", f"https://github.com/{gh}", b], env=env, timeout=900)
        git(b, "checkout", "-q", "-B", branch, commit, env=env)
        keep = set(git(b, "tag", "--merged", commit, env=env).stdout.split())
        for t in git(b, "tag", env=env).stdout.split():
            if t not in keep:
                git(b, "tag", "-d", t, env=env)
        for ref in git(b, "for-each-ref", "--format=%(refname)", "refs/remotes", env=env).stdout.split():
            git(b, "update-ref", "-d", ref, env=env)
        for br in git(b, "for-each-ref", "--format=%(refname:short)", "refs/heads", env=env).stdout.split():
            if br != branch:
                git(b, "branch", "-D", br, env=env)
        git(b, "remote", "remove", "origin", env=env, check=False)
    if not os.path.exists(d("base", "chalk", "node_modules")):
        run(["npm", "install", "--no-package-lock"], cwd=d("base", "chalk"), env=env, timeout=1200)
    run(["go", "test", "./..."], cwd=d("base", "pflag"), env=env, timeout=1200)
    if not any(f.startswith("pytest") for f in os.listdir(d("wheels"))):
        run([PY312, "-m", "pip", "download", "-q", "-d", d("wheels"), "pytest"], env=env, timeout=900)


def make_venv(sid, env):
    v = d("venvs", sid)
    if os.path.exists(v):
        shutil.rmtree(v)
    run([PY312, "-m", "venv", v], env=env)
    run([os.path.join(v, "bin/pip"), "install", "-q", "--no-index", "--find-links", d("wheels"), "pytest"], env=env)


def template(task, env) -> dict:
    tpl = d("templates", task.id)
    shutil.rmtree(tpl, ignore_errors=True)
    os.makedirs(tpl)
    base = d("base", task.repo)
    branch = REPOS[task.repo][2]
    repo, remote = os.path.join(tpl, "repo"), os.path.join(tpl, "remote.git")
    run(["git", "clone", "-q", "--no-hardlinks", "--bare", base, remote], env=env)
    run(["git", "clone", "-q", "--no-hardlinks", base, repo], env=env)
    git(repo, "remote", "set-url", "origin", remote, env=env)
    git(repo, "fetch", "-q", "origin", env=env)
    if task.repo == "chalk":
        clone_tree(os.path.join(base, "node_modules"), os.path.join(repo, "node_modules"))
    facts = (task.setup(repo, remote, env) if task.setup else None) or {}
    if task.id == "go_backport":
        git(repo, "fetch", "-q", "origin", env=env)
    start = {"task": task.id, "repo": task.repo, "branch": branch,
             "head": git(repo, "rev-parse", "HEAD", env=env).stdout.strip(), **facts}
    start.update(truth.start_state(tpl))
    with open(d("templates", f"{task.id}.start.json"), "w") as fh:
        json.dump(start, fh)
    return start


def validate(task, env) -> dict:
    """Each template must start not done, with the test status the SPEC's setup implies."""
    start = json.load(open(d("templates", f"{task.id}.start.json")))
    sid = f"validate_{task.id}"
    sdir = d("s", sid)
    shutil.rmtree(sdir, ignore_errors=True)
    clone_tree(d("templates", task.id), sdir)
    venv_env = base_env(sid, python=task.python)
    if task.python:
        make_venv(sid, env)
    res = task.check(sdir, venv_env, sid, start)
    ok_tests, tail = T.tests(task.repo, os.path.join(sdir, "repo"), venv_env, sid if task.python else None)
    extra = {}
    repo = os.path.join(sdir, "repo")
    if task.id == "go_backport":
        p = git(repo, "checkout", "release-1.0", env=env, check=False)
        extra["checkout_refused"] = p.returncode != 0 and "would be overwritten" in p.stderr
        scratch = sdir + ".pick"
        shutil.rmtree(scratch, ignore_errors=True)
        run(["git", "clone", "-q", "--no-hardlinks", "-b", "release-1.0", repo, scratch], env=env)
        pk = git(scratch, "cherry-pick", T.FIX, env={**env, **T.SETUP_GIT}, check=False)
        extra["cherry_pick_clean"] = pk.returncode == 0
        extra["tests_after_pick"] = T.tests("pflag", scratch, env)[0]
        shutil.rmtree(scratch, ignore_errors=True)
    if task.id == "go_branches":
        extra["merged_listed"] = sorted(x.strip() for x in git(repo, "branch", "--merged", "master",
                                                               env=env).stdout.splitlines())
    shutil.rmtree(sdir, ignore_errors=True)
    shutil.rmtree(sdir + ".check", ignore_errors=True)
    shutil.rmtree(d("venvs", sid), ignore_errors=True)
    return {"task": task.id, "done_at_start": res.get("done"), "tests_pass_at_start": ok_tests,
            "U0_lines": len(start["U0"]), "C0_commits": len(start["C0"]), **extra}


def main():
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    env = base_env()
    if what in ("all",):
        dirs()
        ekbasis()
        bases(env)
    if what in ("all", "templates"):
        for t in T.TASKS + T.PILOTS:
            s = template(t, env)
            print(f"template {t.id}: U0 {len(s['U0'])} lines, C0 {len(s['C0'])} commits", flush=True)
    if what in ("all", "templates", "validate"):
        out = [validate(t, env) for t in T.TASKS + T.PILOTS]
        for r in out:
            print(json.dumps(r), flush=True)
        with open(d("templates", "validation.json"), "w") as fh:
            json.dump(out, fh, indent=1)


if __name__ == "__main__":
    main()
