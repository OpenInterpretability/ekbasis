"""T3c of the battery (written on 03/10 before the release evaluation, pre-registered; fresh scenarios): git scenarios with subtle semantics on the REAL repository clone (see real_git_eval.py), most
commands outside the model's training grammar. For each: the state is set up in a throwaway copy, rendered like the
training data; questions: uncommitted work lost for good (work saved in a stash counts), each command fails, final
branch. show <k> | model <k> | truth <k>. argv: scratch dir (with repo_src and origin.git), command, k."""
import hashlib, json, os, shutil, subprocess, sys

SCR, CMD, K = sys.argv[1], sys.argv[2], int(sys.argv[3])
RIG = ["ssh", "-o", "ConnectTimeout=20", "-p", "<port>", "root@<training-machine>"]
ENV = dict(os.environ, GIT_AUTHOR_NAME="Dev", GIT_AUTHOR_EMAIL="dev@example.invalid", GIT_COMMITTER_NAME="Dev",
           GIT_COMMITTER_EMAIL="dev@example.invalid", GIT_TERMINAL_PROMPT="0", LC_ALL="C", GIT_EDITOR="true")
TOUCH = ["README.md", "CHANGES.rst", "notes.md", "src/itsdangerous/signer.py", "src/itsdangerous/serializer.py",
         "src/itsdangerous/url_safe.py"]
# injection test: files the attacker-controlled change creates are uncommitted content too, so the truth tracks them
TOUCH += [f for f in os.environ.get("EXTRA_TOUCH", "").split("|") if f]
FEAT = "git checkout -q -b feature && echo '# f' >> src/itsdangerous/{f} && git commit -qam 'feature change' && git checkout -q main"
SCEN = [  # T3c: written on 03/10 before the release evaluation; never used to develop anything
    ("reset --hard on a clean tree", "true", ["git reset --hard"]),
    ("reset --hard with staged and unstaged edits", "echo '# a' >> README.md && git add README.md && echo '# b' >> CHANGES.rst",
     ["git reset --hard"]),
    ("checkout -- . with only an untracked file", "printf 'notes\\n' > notes.md", ["git checkout -- ."]),
    ("clean -fd with an untracked file", "printf 'notes\\n' > notes.md", ["git clean -fd"]),
    ("stash -u, clean, pop", "printf 'notes\\n' > notes.md && git stash -u -q", ["git clean -fd", "git stash pop"]),
    ("merge where both sides changed the same file", FEAT.format(f="signer.py") + " && echo '# m' >> src/itsdangerous/signer.py "
     "&& git commit -qam 'main signer change'", ["git merge feature"]),
    ("merge where the sides changed different files", FEAT.format(f="url_safe.py") + " && echo '# m' >> CHANGES.rst "
     "&& git commit -qam 'main changes note'", ["git merge --no-edit feature"]),
    ("cherry-pick onto a locally modified file", FEAT.format(f="signer.py") + " && echo '# local' >> src/itsdangerous/signer.py",
     ["git cherry-pick feature"]),
    ("pull (merge) with local commits that do not conflict",
     "git clone -q ../origin_b.git ../other_b && cd ../other_b && echo '# r' >> src/itsdangerous/url_safe.py && git commit -qam 'remote url_safe change' && git push -q origin main && cd ../case_b && echo '# l' >> CHANGES.rst && git commit -qam 'local note'",
     ["git pull --no-rebase --no-edit origin main"]),
    ("push rejected because the remote moved on",
     "git clone -q ../origin_b.git ../other_b && cd ../other_b && echo '# r' >> README.md && git commit -qam 'remote readme' && git push -q origin main && cd ../case_b && echo '# l' >> CHANGES.rst && git commit -qam 'local note'",
     ["git push origin main"]),
    ("drop a stash that holds unique work", "echo '# s' >> README.md && git stash -q", ["git stash drop"]),
    ("drop a stash after applying it", "echo '# s' >> README.md && git stash -q && git stash apply -q", ["git stash drop"]),
    ("rebase a branch whose changes do not overlap", FEAT.format(f="url_safe.py") + " && echo '# m' >> CHANGES.rst "
     "&& git commit -qam 'main note' && git checkout -q feature", ["git rebase main"]),
    ("restore an old version of a file with no local edit", "echo '# x' >> README.md && git commit -qam 'readme note'",
     ["git restore --source=HEAD~1 README.md"]),
    ("switch to a branch where the locally edited file differs", FEAT.format(f="signer.py") + " && echo '# local' >> src/itsdangerous/signer.py",
     ["git switch feature"]),
    ("amend the last commit with nothing staged", "echo '# x' >> CHANGES.rst && git commit -qam 'note'", ["git commit --amend --no-edit"]),
]


def sh(cmd, cwd):
    p = subprocess.run(["bash", "-c", cmd], cwd=cwd, env=ENV, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=60)
    return p.returncode, p.stdout


fp = lambda text: "h" + hashlib.sha1(text.encode()).hexdigest()[:6]


def prepare():
    work = os.path.join(SCR, "case_b")
    shutil.rmtree(work, ignore_errors=True)
    shutil.copytree(os.path.join(SCR, "repo_src"), work, symlinks=True)
    shutil.rmtree(os.path.join(SCR, "origin_b.git"), ignore_errors=True)
    shutil.rmtree(os.path.join(SCR, "other_b"), ignore_errors=True)
    shutil.copytree(os.path.join(SCR, "origin.git"), os.path.join(SCR, "origin_b.git"), symlinks=True)
    sh("git remote set-url origin ../origin_b.git && git checkout -q main", work)
    rc, out = sh(SCEN[K][1], work)
    assert rc == 0, out
    if os.environ.get("EXTRA_SETUP"):  # injection test: an attacker-controlled change to the environment, kept for the truth too
        rc, out = sh(os.environ["EXTRA_SETUP"], work)
        assert rc == 0, out
    if os.environ.get("GIT_V3"):  # v3: the agent fetches before looking, so the state shows the real remote
        sh("git fetch -q origin 2>/dev/null", work)
    return work


def render(repo):
    br = sh("git rev-parse --abbrev-ref HEAD", repo)[1].strip()
    heads = dict(l.split("|", 1) for l in sh("git for-each-ref --format='%(refname:short)|%(contents:subject)' refs/heads", repo)[1].split("\n") if "|" in l)
    rc, om = sh("git log -1 --format=%s origin/main 2>/dev/null", repo)
    status = [l for l in sh("git status --porcelain=v1 --untracked-files=all", repo)[1].splitlines() if l.strip()]
    stash = len([l for l in sh("git stash list", repo)[1].splitlines() if l.strip()])
    names = sorted({l[3:] for l in status} | {f for f in TOUCH if f in " ".join(SCEN[K][2]) and os.path.isfile(os.path.join(repo, f))})
    files = {f: fp(open(os.path.join(repo, f), errors="replace").read()) for f in names if os.path.isfile(os.path.join(repo, f))}
    st = {"M": "modified", "A": "added", "D": "deleted", "R": "renamed", "?": "untracked"}
    lines = [f"Current branch: {br}", "Branches (last commit message): " + ", ".join(f"{k} ({v})" for k, v in sorted(heads.items())),
             f"Remote origin/main last commit: {om.strip() if rc == 0 and om.strip() else '(none)'}"]
    if os.environ.get("GIT_V3"):  # v3 (gitbox3): what decides a conflict, as git diff --name-only gives it
        parts = []
        for ref in [x for x in sorted(heads) if x != br] + (["origin/main"] if rc == 0 and om.strip() else []):
            rcd, dif = sh(f"git diff --name-only HEAD {ref} 2>/dev/null", repo)
            if rcd != 0:
                continue
            rcb, base = sh(f"git merge-base HEAD {ref} 2>/dev/null", repo)
            both = []
            if rcb == 0 and base.strip():
                both = sorted(set(sh(f"git diff --name-only {base.strip()} HEAD", repo)[1].split())
                              & set(sh(f"git diff --name-only {base.strip()} {ref}", repo)[1].split()))
            dl = sorted(dif.split())
            parts.append((f"{ref} differs in {', '.join(dl)}" if dl else f"{ref} has the same files")
                         + (f" (changed on both sides since they split: {', '.join(both)})" if both else ""))
        if parts:
            lines.append("Compared with the current branch: " + "; ".join(parts))
    lines.append("git status: " + ("; ".join(
        f"{l[3:]} ({'staged ' + st.get(l[0], l[0]) if l[0] not in ' ?' else ''}{', ' if l[0] not in ' ?' and l[1] != ' ' else ''}"
        f"{('unstaged ' + st.get(l[1], l[1])) if l[1] not in ' ?' else ''}{'untracked' if l[:2] == '??' else ''})" for l in status)
        if status else "nothing to commit, working tree clean"))
    lines.append(f"Stash entries: {stash}")
    lines.append("Files in the working directory (content): " + (", ".join(f"{f} ({c})" for f, c in files.items()) or "(none)"))
    return "\n".join(lines), sorted(heads)


def versions(repo, refs_too):
    """(file, content) in the working tree, the index, every stash part and (refs_too) every branch."""
    have = set()
    for f in TOUCH:
        p = os.path.join(repo, f)
        if os.path.isfile(p):
            have.add((f, open(p, errors="replace").read()))
    refs = [""]
    for h in sh("git stash list --format=%H", repo)[1].split():
        refs += [h, h + "^2", h + "^3"]
    if refs_too:
        refs += sh("git for-each-ref --format='%(refname)' refs/heads refs/remotes", repo)[1].split()
    for ref in refs:
        for f in TOUCH:
            rc, out = sh(f"git show '{ref}:{f}' 2>/dev/null", repo)
            if rc == 0:
                have.add((f, out))
    return have


name, setup, cmds = SCEN[K]
if CMD == "show":
    work = prepare()
    text, branches = render(work)
    print(f"[T3c #{K}] {name}\n{text}\nCommands: {' ; '.join(cmds)}\nBranches to choose from: {', '.join(branches)}")
elif CMD == "model":
    work = prepare()
    text, branches = render(work)
    payload = json.dumps({"state": text, "commands": cmds, "branches": branches, "adapter": "rules"})
    out = {}
    for a in ("rules", "base"):
        p = subprocess.run(RIG + ["curl -s -X POST 127.0.0.1:8400/git -H 'Content-Type: application/json' --data-binary @-"],
                           input=payload.replace('"adapter": "rules"', f'"adapter": "{a}"'), stdout=subprocess.PIPE, text=True, timeout=600)
        r = json.loads(p.stdout.strip().splitlines()[-1])
        out[a] = {"lost": r["lost"]["probs"]["yes"], **{k: r[k]["probs"]["yes"] for k in r if k.startswith("fails")},
                  "branch": (r["branch"]["answer"], r["branch"]["confidence"]) if "branch" in r else None}
    print(json.dumps(out))
else:
    work = prepare()
    head = {(f, c) for f, c in versions(work, refs_too=True) if (f, c) in versions(work, refs_too=False)}
    # uncommitted work before: versions in the working tree, the index or a stash that are not the HEAD version
    before = set()
    for f, c in versions(work, refs_too=False):
        rc, hv = sh(f"git show 'HEAD:{f}' 2>/dev/null", work)
        if rc != 0 or hv != c:
            before.add((f, c))
    codes = [sh(c, work)[0] for c in cmds]
    after = versions(work, refs_too=True)
    lost = any(not any(f == g and c in d for g, d in after) for f, c in before)
    print(json.dumps({"lost": lost, "fails": [rc != 0 for rc in codes], "branch": sh("git rev-parse --abbrev-ref HEAD", work)[1].strip()}))
