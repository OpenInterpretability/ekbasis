# PRELAUNCH PORT (P10) of _orig/realuse/realuse_guard.py: every changed line is marked PORT; the full diff is CHANGES.diff in this folder.
"""Real-use test of the Ekbasis git guard (the Claude Code hook and the client's git.check) on our own repositories,
in the state they are really in (uncommitted work and all). Nothing runs in the real repositories: every scenario gets
a fresh full copy (remotes pointed at a local path, git hooks off), the model is asked BEFORE anything runs, then the
commands run in that copy and the truth is read from what happened:
- lost: a version of a file that existed before as uncommitted work (working tree, index or a stash part, different
  from HEAD's) is afterwards in none of: the working tree, the index, any stash part, any branch (local or remote);
  the definition of the guard's training data (git_battery3.py);
- fails: each command's exit code.
usage: realuse_guard.py truth            (executes every scenario in copies; writes truth.json)
       realuse_guard.py predict <name> <url>   (the hook and git.check against that server; writes pred_<name>.json)"""
import json
import os
import shutil
import subprocess
import sys
import time

T = os.environ["WORK"]  # PORT: scratch copies and per-run files (it was the realuse2 folder)
BASE = os.environ.get("BASE", "<mac-scratch>/realuse2")  # PORT: the 4 Oct base copies
OUTD = os.environ["OUT"]  # PORT: truth / predictions
VENV = os.environ.get("CLIENT_VENV", "<mac-scratch>/venv_launch")  # PORT: the client that ran
REPOS = {"code_eikos": "/Volumes/SSD Major/news/decision_model/release_clean/code_eikos",
         "openinterp_web": "/Volumes/SSD Major/news/openinterp_web"}
ENV = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_EDITOR="true", GIT_PAGER="cat", PAGER="cat")


def sh(cmd, cwd, timeout=120):
    p = subprocess.run(cmd, shell=True, cwd=cwd, env=ENV, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                       timeout=timeout)
    return p.returncode, p.stdout


def base_copy(name):
    """One copy of the real repository per run: remotes pointed at a local path, hooks off, no signing prompts."""
    dst = f"{BASE}/base_{name}"
    if not os.path.isdir(dst):  # PORT: never rebuild from the live repositories (another state)
        raise SystemExit(f"missing base copy {dst}: the 4 Oct repository state is gone, P10 cannot run as published")
    if False:
        subprocess.run(["rsync", "-a", "--exclude", "node_modules", "--exclude", ".next", REPOS[name] + "/", dst + "/"], check=True)
        for r in sh("git remote", dst)[1].split():
            sh(f"git remote set-url {r} /nonexistent/ekbasis-realuse-{r} && git remote set-url --push {r} /nonexistent/ekbasis-realuse-{r}", dst)
        sh("git config core.hooksPath /dev/null && git config commit.gpgsign false", dst)
    return dst


def fresh(name, sid):
    dst = f"{T}/run/{name}_{sid}"
    shutil.rmtree(dst, ignore_errors=True)
    subprocess.run(["rsync", "-a", base_copy(name) + "/", dst + "/"], check=True)
    return dst


def facts(name):
    b = base_copy(name)
    st = sh("git status --porcelain=v1 --untracked-files=all", b)[1].splitlines()
    mod = [l[3:] for l in st if l[:2] in (" M", "M ", "MM")]
    unt = [l[3:] for l in st if l.startswith("??")]
    cur = sh("git rev-parse --abbrev-ref HEAD", b)[1].strip()
    other = [x for x in sh("git branch --format='%(refname:short)'", b)[1].split() if x != cur]
    return {"M": mod[0], "M2": mod[1] if len(mod) > 1 else mod[0], "U": unt[0], "B": other[0], "cur": cur}


def scenarios(name):
    f = facts(name)
    M, M2, U, B = f["M"], f["M2"], f["U"], f["B"]
    S = [
        ("status", ["git status"]), ("diff stat", ["git diff --stat"]), ("log", ["git log --oneline -3"]),
        ("commit everything", ["git add -A", "git commit -qm 'wip: save work'"]),
        ("commit tracked changes", ["git commit -qam 'wip: tracked'"]),
        ("stash", ["git stash"]), ("stash with untracked", ["git stash -u"]),
        ("stash and pop", ["git stash", "git stash pop"]), ("stash, apply", ["git add -A", "git stash", "git stash apply"]),
        ("new branch", ["git switch -c realuse-test"]), ("add one file", [f"git add {M}"]),
        ("add then unstage", [f"git add {M}", f"git restore --staged {M}"]), ("mixed reset", ["git reset"]),
        ("clean dry run", ["git clean -n"]), ("stash, switch, back, pop", ["git stash -u", f"git switch {B}", "git switch -", "git stash pop"]),
        ("checkout other branch", [f"git checkout {B}"]),
        ("discard one file (checkout)", [f"git checkout -- {M}"]), ("discard one file (restore)", [f"git restore {M2}"]),
        ("hard reset", ["git reset --hard"]), ("clean untracked", ["git clean -fd"]),
        ("stash then drop", ["git stash", "git stash drop"]), ("discard everything (checkout)", ["git checkout -- ."]),
        ("discard everything (restore)", ["git restore ."]), ("hard reset to HEAD", ["git reset --hard HEAD"]),
        ("remove a modified file", [f"git rm -qf {M}"]), ("stash -u then drop", ["git stash -u", "git stash drop"]),
        ("stage all then hard reset", ["git add -A", "git reset --hard"]), ("force switch", [f"git switch --discard-changes {B}"]),
        ("force checkout", [f"git checkout -f {B}"]), ("restore an old version", [f"git restore --source=HEAD~1 {M}"]),
        ("rebase onto the other branch", [f"git rebase {B}"]), ("merge the other branch", [f"git merge --no-edit {B}"]),
        ("switch to a missing branch", ["git switch realuse-missing-branch"]), ("pop with no stash", ["git stash pop"]),
        ("commit with nothing staged", ["git commit -qm 'nothing'"]), ("delete untracked by hand then status", [f"git rm -q --cached {M}", "git status"]),
    ]
    return [{"repo": name, "sid": i, "name": n, "commands": c} for i, (n, c) in enumerate(S)]


def blobs(repo, files, refs):
    """{(file, blob)} present in the working tree, the index and the given refs (git cat-file in one batch)."""
    have = set()
    for f in files:
        p = os.path.join(repo, f)
        if os.path.isfile(p):
            rc, h = sh(f"git hash-object -- '{f}'", repo)
            if rc == 0:
                have.add((f, h.strip()))
    lines = [f"{r}:{f}" for r in [""] + refs for f in files]
    p = subprocess.run(["git", "cat-file", "--batch-check=%(objectname) %(objecttype)"], cwd=repo, env=ENV, input="\n".join(lines) + "\n",
                       stdout=subprocess.PIPE, text=True)
    for spec, out in zip(lines, p.stdout.splitlines()):
        parts = out.split()
        if len(parts) == 2 and parts[1] == "blob":
            have.add((spec.split(":", 1)[1], parts[0]))
    return have


def stash_refs(repo):
    refs = []
    for h in sh("git stash list --format=%H", repo)[1].split():
        refs += [h, h + "^2"]
        if sh(f"git rev-parse -q --verify {h}^3", repo)[0] == 0:
            refs.append(h + "^3")
    return refs


def truth(sc):
    w = fresh(sc["repo"], sc["sid"])
    files = set(l[3:].split(" -> ")[-1] for l in sh("git status --porcelain=v1 --untracked-files=all", w)[1].splitlines())
    head = {(f, h) for f, h in blobs(w, sorted(files), ["HEAD"]) if sh(f"git cat-file -e 'HEAD:{f}' 2>/dev/null", w)[0] == 0}
    before_all = blobs(w, sorted(files), stash_refs(w))
    head_map = {}
    for f in files:
        rc, h = sh(f"git rev-parse -q --verify 'HEAD:{f}' 2>/dev/null", w)
        head_map[f] = h.strip() if rc == 0 else None
    before = {(f, h) for f, h in before_all if head_map.get(f) != h}
    codes = [sh(c, w)[0] for c in sc["commands"]]
    branches = sh("git for-each-ref --format='%(refname)' refs/heads refs/remotes", w)[1].split()
    after = blobs(w, sorted(files), stash_refs(w) + branches)
    lost_versions = sorted(f for f, h in before if (f, h) not in after)
    shutil.rmtree(w, ignore_errors=True)
    return {**sc, "lost": bool(lost_versions), "lost_files": lost_versions[:8], "n_lost": len(lost_versions), "fails": [c != 0 for c in codes],
            "uncommitted_versions_before": len(before)}


def predict(sc, url):
    w = fresh(sc["repo"], sc["sid"])
    env = dict(ENV, EKBASIS_URL=url)
    code = ("import json, sys\nfrom ekbasis import git as G\n"
            f"v = G.check({sc['commands']!r}, repo={w!r})\n"
            "print(json.dumps({'p_lost': v.p_lost, 'p_fail': v.p_fail, 'risky': v.risky}))")
    t0 = time.time()
    p = subprocess.run([f"{VENV}/bin/python", "-c", code], cwd="/tmp", env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=300)
    dt = time.time() - t0
    hook_in = json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": " && ".join(sc["commands"])}, "cwd": w})
    h = subprocess.run([f"{VENV}/bin/ekbasis-claude-hook"], input=hook_in, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=300)
    decision = json.loads(h.stdout)["hookSpecificOutput"]["permissionDecision"] if h.stdout.strip() else "allow"
    shutil.rmtree(w, ignore_errors=True)
    out = json.loads(p.stdout.strip().splitlines()[-1]) if p.returncode == 0 and p.stdout.strip() else {"error": p.stderr[-300:]}
    return {"repo": sc["repo"], "sid": sc["sid"], "name": sc["name"], **out, "hook": decision, "seconds": round(dt, 2)}


if __name__ == "__main__":
    os.makedirs(f"{T}/run", exist_ok=True)
    scs = [s for name in REPOS for s in scenarios(name)]
    if sys.argv[1] == "truth":
        res = [truth(s) for s in scs]
        json.dump(res, open(f"{OUTD}/truth.json", "w"), indent=1)
        print(f"{len(res)} scenarios: {sum(r['lost'] for r in res)} lose work, {sum(any(r['fails']) for r in res)} have a failing command")
    else:
        name, url = sys.argv[2], sys.argv[3]
        res = [predict(s, url) for s in scs]
        json.dump(res, open(f"{OUTD}/pred_{name}.json", "w"), indent=1)
        print(f"{name}: {len(res)} predictions, {sum(r.get('hook') == 'ask' for r in res)} hook asks, errors {sum('error' in r for r in res)}")
