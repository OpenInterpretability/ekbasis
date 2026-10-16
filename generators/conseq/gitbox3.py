"""v3 of gitbox.py (gitbox3): v2 plus what decides a conflict, in the state shown to the model ("Compared with the
current branch": for every other branch and origin/main, the files that differ and the files changed on both sides
since they split, as an agent gets from git diff --name-only), and more command types in training (cherry-pick, merge
--ff-only / --squash, stash apply / --keep-index, reset HEAD~1, push -f, fetch, restore --staged --worktree, ...).
HELD stays rebase and restore_old, as in v2.

v2 of gitbox.py: states built to provoke conflicts (a branch that changed the same file as a local edit, merges
that conflict, a stash whose file was committed afterwards), more commands (stash -u, checkout -- file, reset HEAD file,
commit --amend, switch, rebase, restore --source=HEAD~1, merge --abort), unfinished merge/rebase shown in the state, a
question about it, and the held-out kinds HELD = rebase, restore_old.

Git/shell consequences with REAL execution: every example is a fresh throwaway repository (with a local bare remote),
a few commands an agent might run, and typed questions about the outcome; the gold answers come from running the
commands, not from a simulator we wrote.

Safety: the commands are built only from fixed tokens (file names, branch names, contents, messages from small pools; no
paths outside the sandbox, no user input); each example runs in its own directory with a time limit per command; on the
rig the runner drops to the unprivileged user `nobody` (SANDBOX_USER) so a command can only touch its own sandbox.
Commit authors are synthetic (no real names or emails).

Questions: file exists / file content / checked-out branch / working tree clean / file staged / command fails / stash
entries / remote has the commit / uncommitted work lost for good (the most valuable one: an uncommitted version of a
file that existed before and exists nowhere afterwards: not in the working tree, the index, any branch, any stash).
HELD command types never appear in training examples (test: novel commands)."""
from __future__ import annotations

import collections, os, random, shutil, subprocess, tempfile

FILES = ["README.md", "app.py", "notes.txt", "config.json", "src/main.py", "src/util.py", "docs/guide.md", "data.csv"]
CONTENTS = ["v1", "v2", "draft", "fix", "todo", "final", "wip", "hotfix", "old", "new"]
BRANCHES = ["main", "feature", "dev", "bugfix", "exp"]
MSGS = ["init", "add files", "update", "fix bug", "refactor", "docs", "tweak", "cleanup"]
HELD = {"rebase", "restore_old"}
ENV = {"GIT_AUTHOR_NAME": "Dev", "GIT_AUTHOR_EMAIL": "dev@example.invalid", "GIT_COMMITTER_NAME": "Dev",
       "GIT_COMMITTER_EMAIL": "dev@example.invalid", "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0",
       "LC_ALL": "C", "PATH": "/usr/local/bin:/usr/bin:/bin", "GIT_EDITOR": "true", "GIT_MERGE_AUTOEDIT": "no"}


class Box:
    """One sandbox directory: work/ (the repository) and origin.git (its bare remote)."""

    def __init__(self, root=None):
        self.dir = tempfile.mkdtemp(prefix="gbx_", dir=root)
        self.work = os.path.join(self.dir, "work")
        os.makedirs(self.work)
        self.env = dict(ENV, HOME=self.dir)
        user = os.environ.get("SANDBOX_USER")  # numeric uid (used as gid too), e.g. 65534 = nobody
        if user:
            for p in (self.dir, self.work):
                os.chown(p, int(user), int(user))
        self.prefix = ["setpriv", "--reuid", user, "--regid", user, "--clear-groups"] if user else []

    def sh(self, cmd, cwd=None):
        """Runs one shell command in the sandbox; returns (exit code, output)."""
        try:
            p = subprocess.run(self.prefix + ["bash", "-c", cmd], cwd=cwd or self.work, env=self.env, timeout=5,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        except subprocess.TimeoutExpired:
            return 124, ""
        return p.returncode, p.stdout

    def close(self):
        shutil.rmtree(self.dir, ignore_errors=True)


# ------------------------------------------------------------------ observing the state
def branch_diffs(b: Box, s):
    """For every other branch and origin/main: (files that differ from HEAD, files changed on both sides since the split)."""
    out = {}
    refs = [x for x in sorted(s["branches"]) if x != s["branch"]] + (["origin/main"] if s["origin_main"] else [])
    for ref in refs:
        rc, dif = b.sh(f"git diff --name-only HEAD {ref} 2>/dev/null")
        if rc != 0:
            continue
        rc, base = b.sh(f"git merge-base HEAD {ref} 2>/dev/null")
        both = []
        if rc == 0 and base.strip():
            _, ours = b.sh(f"git diff --name-only {base.strip()} HEAD")
            _, theirs = b.sh(f"git diff --name-only {base.strip()} {ref}")
            both = sorted(set(ours.split()) & set(theirs.split()))
        out[ref] = (sorted(dif.split()), both)
    return out


def snapshot(b: Box, diffs=False):
    """Everything the questions need, read with git and the file system (diffs: also the per-branch differences)."""
    s = {}
    rc, out = b.sh("git rev-parse --abbrev-ref HEAD")
    s["branch"] = out.strip() if rc == 0 else "(none)"
    rc, out = b.sh("git for-each-ref --format='%(refname:short)|%(contents:subject)' refs/heads")
    s["branches"] = dict(l.split("|", 1) for l in out.strip().splitlines() if "|" in l)
    rc, out = b.sh("git log -1 --format=%s origin/main 2>/dev/null")
    s["origin_main"] = out.strip() if rc == 0 and out.strip() else None
    rc, out = b.sh("git log --format=%s origin/main 2>/dev/null")
    s["origin_msgs"] = out.strip().splitlines() if rc == 0 else []
    rc, out = b.sh("git status --porcelain=v1 --untracked-files=all")
    s["status"] = [l for l in out.splitlines() if l.strip()]
    rc, out = b.sh("git stash list")
    s["stash"] = len([l for l in out.splitlines() if l.strip()])
    files = {}
    for f in FILES:
        p = os.path.join(b.work, f)
        if os.path.isfile(p):
            files[f] = " / ".join(open(p).read().split())
    s["files"] = files
    s["staged"] = sorted({l[3:] for l in s["status"] if l[0] not in " ?"})
    s["merge"] = os.path.exists(os.path.join(b.work, ".git", "MERGE_HEAD"))
    s["rebase"] = any(os.path.exists(os.path.join(b.work, ".git", d)) for d in ("rebase-merge", "rebase-apply"))
    s["diffs"] = branch_diffs(b, s) if diffs else {}
    return s


def versions_everywhere(b: Box):
    """(file, content) pairs that exist anywhere: working tree, index, any branch tip, any stash entry."""
    have = set()
    for f in FILES:
        p = os.path.join(b.work, f)
        if os.path.isfile(p):
            have.add((f, open(p).read().strip()))
    refs = []
    rc, out = b.sh("git for-each-ref --format='%(refname)' refs/heads refs/remotes")
    refs += out.split()
    rc, out = b.sh("git stash list --format=%H")
    for h in out.split():
        refs += [h, h + "^2", h + "^3"]  # stash commit (working tree), its index commit, its untracked commit
    for ref in refs + [":"]:
        for f in FILES:
            rc, out = b.sh(f"git show '{ref}:{f}' 2>/dev/null" if ref != ":" else f"git show ':{f}' 2>/dev/null")
            if rc == 0:
                have.add((f, out.strip()))
    return have


def stash_versions(b: Box):
    """(file, content) pairs saved in stash entries (working tree, index and untracked parts) that are on no branch."""
    out, onbranch = set(), set()
    rc, refs = b.sh("git for-each-ref --format='%(refname)' refs/heads refs/remotes")
    for ref in refs.split():
        for f in FILES:
            rc, c = b.sh(f"git show '{ref}:{f}' 2>/dev/null")
            if rc == 0:
                onbranch.add((f, c.strip()))
    rc, hs = b.sh("git stash list --format=%H")
    for h in hs.split():
        for ref in (h, h + "^2", h + "^3"):
            for f in FILES:
                rc, c = b.sh(f"git show '{ref}:{f}' 2>/dev/null")
                if rc == 0 and (f, c.strip()) not in onbranch:
                    out.add((f, c.strip()))
    return out


def uncommitted_versions(b: Box):
    """(file, content) pairs in the working tree or the index that differ from HEAD."""
    out = set()
    for f in FILES:
        rc, head = b.sh(f"git show 'HEAD:{f}' 2>/dev/null")
        head = head.strip() if rc == 0 else None
        p = os.path.join(b.work, f)
        if os.path.isfile(p):
            c = open(p).read().strip()
            if c != head:
                out.add((f, c))
        rc, idx = b.sh(f"git show ':{f}' 2>/dev/null")
        if rc == 0 and idx.strip() != head:
            out.add((f, idx.strip()))
    return out


def render(s):
    lines = [f"Current branch: {s['branch']}"]
    lines.append("Branches (last commit message): " + ", ".join(f"{k} ({v})" for k, v in sorted(s["branches"].items())))
    lines.append(f"Remote origin/main last commit: {s['origin_main'] or '(none)'}")
    if s.get("diffs"):
        parts = []
        for ref, (dif, both) in sorted(s["diffs"].items()):
            t = f"{ref} differs in {', '.join(dif)}" if dif else f"{ref} has the same files"
            parts.append(t + (f" (changed on both sides since they split: {', '.join(both)})" if both else ""))
        lines.append("Compared with the current branch: " + "; ".join(parts))
    st = {"M": "modified", "A": "added", "D": "deleted", "R": "renamed", "?": "untracked", "U": "unmerged (conflict)"}
    if s["status"]:
        lines.append("git status: " + "; ".join(
            f"{l[3:]} ({'staged ' + st.get(l[0], l[0]) if l[0] not in ' ?' else ''}"
            f"{', ' if l[0] not in ' ?' and l[1] != ' ' else ''}"
            f"{('unstaged ' + st.get(l[1], l[1])) if l[1] not in ' ?' else ''}{'untracked' if l[:2] == '??' else ''})"
            for l in s["status"]))
    else:
        lines.append("git status: nothing to commit, working tree clean")
    lines.append(f"Stash entries: {s['stash']}")
    if s.get("merge") or s.get("rebase"):
        lines.append(f"Operation in progress: {'merge' if s.get('merge') else 'rebase'} (unfinished)")
    lines.append("Files in the working directory (content): " +
                 (", ".join(f"{f} ({c})" for f, c in sorted(s["files"].items())) if s["files"] else "(none)"))
    return "\n".join(lines)


# ------------------------------------------------------------------ initial states and commands
def setup(b: Box, rng):
    """A repository with a few commits, a pushed main, maybe a second branch, local changes, untracked files, a stash."""
    b.sh("git init -q -b main && git config commit.gpgsign false")
    b.sh("git init -q --bare ../origin.git && git remote add origin ../origin.git")
    tracked = rng.sample(FILES, rng.randint(2, 4))
    for f in tracked:
        b.sh(f"mkdir -p $(dirname {f}) && echo {rng.choice(CONTENTS)} > {f}")
    b.sh(f"git add -A && git commit -qm '{MSGS[0]}'")
    for _ in range(rng.randint(0, 2)):
        f = rng.choice(tracked)
        b.sh(f"echo {rng.choice(CONTENTS)} > {f} && git commit -qam '{rng.choice(MSGS[1:])}'")
    b.sh("git push -q origin main 2>/dev/null")
    hot = rng.choice(tracked)  # the file other branches / stashes also change: local edits to it can conflict
    if rng.random() < 0.6:
        br = rng.choice(BRANCHES[1:])
        b.sh(f"git checkout -q -b {br} && echo {rng.choice(CONTENTS)} > {hot} && git commit -qam 'on {br}'")
        b.sh("git checkout -q main")
        if rng.random() < 0.5:  # main moves on too (same file half the time: merges that conflict)
            f = hot if rng.random() < 0.5 else rng.choice(tracked)
            b.sh(f"echo {rng.choice(CONTENTS)} > {f} && git commit -qam '{rng.choice(MSGS[1:])}'")
        if rng.random() < 0.4:
            b.sh(f"git checkout -q {br}")
    if rng.random() < 0.35:
        b.sh(f"echo {rng.choice(CONTENTS)} > {hot} && git stash -q")
        if rng.random() < 0.5:  # the stashed file changes in a commit afterwards: a later pop conflicts
            b.sh(f"echo {rng.choice(CONTENTS)} > {hot} && git commit -qam '{rng.choice(MSGS[1:])}'")
    for _ in range(rng.randint(0, 3)):  # local work: modified, staged, untracked
        k = rng.random()
        f = hot if k < 0.35 else (rng.choice(tracked) if k < 0.7 else rng.choice([x for x in FILES if x not in tracked] or tracked))
        b.sh(f"mkdir -p $(dirname {f}) && echo {rng.choice(CONTENTS)} > {f}")
        if rng.random() < 0.4:
            b.sh(f"git add {f}")


def sample_command(rng, s, allow_held):
    files = sorted(s["files"])
    anyf = rng.choice(FILES)
    f = rng.choice(files) if files else anyf
    others = [x for x in sorted(s["branches"]) if x != s["branch"]]
    br = rng.choice(others or sorted(s["branches"]) or ["main"])
    new = rng.choice([x for x in BRANCHES if x not in s["branches"]] or ["tmp"])
    c, m = rng.choice(CONTENTS), rng.choice(MSGS[1:])
    menu = [
        ("write", f"echo {c} > {anyf}"), ("append", f"echo {c} >> {f}"), ("rm", f"rm {f}"),
        ("mv", f"mv {f} {anyf}"), ("cp", f"cp {f} {anyf}"),
        ("add", f"git add {f}"), ("add_all", "git add -A"), ("commit", f"git commit -m '{m}'"),
        ("commit_a", f"git commit -am '{m}'"), ("checkout", f"git checkout {br}"), ("switch_c", f"git switch -c {new}"),
        ("branch_d", f"git branch -D {br}"), ("merge", f"git merge {br}"), ("reset_hard", "git reset --hard"),
        ("reset_soft", "git reset --soft HEAD~1"), ("unstage", f"git restore --staged {f}"),
        ("restore", f"git restore {f}"), ("stash", "git stash"), ("stash_pop", "git stash pop"),
        ("rm_cached", f"git rm --cached {f}"), ("git_rm", f"git rm {f}"), ("push", f"git push origin {br}"),
        ("pull", "git pull origin main"), ("revert", "git revert --no-edit HEAD"),
        ("clean_fd", "git clean -fd"), ("stash_drop", "git stash drop"), ("reset_hard_head1", "git reset --hard HEAD~1"),
        ("checkout_dot", "git checkout -- ."), ("stash_u", "git stash -u"), ("checkout_file", f"git checkout -- {f}"),
        ("reset_file", f"git reset HEAD {f}"), ("amend", "git commit --amend --no-edit"), ("switch", f"git switch {br}"),
        ("merge_abort", "git merge --abort"), ("checkout", f"git checkout {br}"), ("merge", f"git merge {br}"),
        ("rebase", f"git rebase {br}"), ("restore_old", f"git restore --source=HEAD~1 {f}"),
        ("cherry_pick", f"git cherry-pick {br}"), ("checkout_b", f"git checkout -b {new}"), ("branch_new", f"git branch {new}"),
        ("stash_apply", "git stash apply"), ("stash_keep_index", "git stash --keep-index"), ("reset_mixed", "git reset HEAD~1"),
        ("push_force", f"git push -f origin {br}"), ("fetch", "git fetch origin"), ("merge_ff_only", f"git merge --ff-only {br}"),
        ("merge_squash", f"git merge --squash {br}"), ("revert_no_commit", "git revert --no-commit HEAD"),
        ("clean_n", "git clean -n"), ("commit_empty", f"git commit --allow-empty -m '{m}'"),
        ("restore_both", f"git restore --staged --worktree {f}"), ("checkout_head_file", f"git checkout HEAD -- {f}"),
        ("reset_merge", "git reset --merge"),
    ]
    menu = [x for x in menu if allow_held or x[0] not in HELD]
    return rng.choice(menu)


# ------------------------------------------------------------------ questions
def questions(s0, s1, codes, lost, rng):
    """All typed questions about the outcome, each with its gold answer and the answer in the initial state."""
    qs = []
    f = rng.choice(FILES)
    qs.append(("exists", {"type": "noul", "instructions": f"After these commands, does the file {f} exist in the working directory?"},
               f in s1["files"], f in s0["files"]))
    cands = sorted(set(s0["files"].values()) | set(s1["files"].values()) | {"(no such file)"})
    if 3 <= len(cands) <= 12:
        g, g0 = s1["files"].get(f, "(no such file)"), s0["files"].get(f, "(no such file)")
        qs.append(("content", {"type": "choice", "instructions": f"After these commands, what does {f} contain?",
                               "criteria": {c: c for c in cands}}, g, g0))
    br = sorted(set(s0["branches"]) | set(s1["branches"]) | {s0["branch"], s1["branch"]})
    if len(br) >= 2:
        qs.append(("branch", {"type": "choice", "instructions": "After these commands, which branch is checked out?",
                              "criteria": {x: x for x in br}}, s1["branch"], s0["branch"]))
    qs.append(("clean", {"type": "noul", "instructions": "After these commands, is the working tree clean (nothing to commit, no untracked files)?"},
               not s1["status"], not s0["status"]))
    qs.append(("staged", {"type": "noul", "instructions": f"After these commands, does {f} have staged changes?"},
               f in s1["staged"], f in s0["staged"]))
    qs.append(("stash", {"type": "choice", "instructions": "After these commands, how many stash entries are there?",
                         "criteria": {str(k): str(k) for k in range(4)}}, str(min(3, s1["stash"])), str(min(3, s0["stash"]))))
    j = rng.randrange(len(codes))
    qs.append(("fails", {"type": "noul", "instructions": f"Does command {j + 1} fail (exit with an error)?"}, codes[j] != 0, None))
    qs.append(("lost", {"type": "noul", "instructions": "Do these commands permanently lose any uncommitted work (a version of a file that "
                        "existed before and afterwards is in none of: the working directory, the staging area, any branch, any stash)?"},
               lost, None))
    qs.append(("in_progress", {"type": "noul", "instructions": "After these commands, is a merge or rebase left unfinished "
                                                                 "(in progress)?"}, bool(s1["merge"] or s1["rebase"]), bool(s0["merge"] or s0["rebase"])))
    if s1["origin_msgs"] or s0["origin_msgs"]:
        msg = rng.choice(sorted(set(s1["branches"].values()) | set(s0["branches"].values())))
        qs.append(("remote", {"type": "noul", "instructions": f"After these commands, does origin/main include a commit with the message '{msg}'?"},
                   msg in s1["origin_msgs"], msg in s0["origin_msgs"]))
    return qs


RULES = ("You are looking at a git repository on a developer machine (a Linux shell; 'origin' is its remote). "
         "The commands below are run in order in the repository root; a command that fails changes nothing more and "
         "the next one still runs.")


def example(rng, n_cmds, allow_held=False, root=None):
    """One example: (floor text, ceiling text, [(qtype, question, gold, gold0)], command kinds)."""
    b = Box(root)
    try:
        setup(b, rng)
        s0 = snapshot(b, diffs=True)
        before = uncommitted_versions(b) | stash_versions(b)
        cmds, kinds, codes = [], [], []
        s = s0
        for _ in range(n_cmds):
            kind, cmd = sample_command(rng, s, allow_held)
            rc, _ = b.sh(cmd)
            cmds.append(cmd)
            kinds.append(kind)
            codes.append(rc)
            s = snapshot(b)
        s = snapshot(b, diffs=True)
        after = versions_everywhere(b)
        # lost: an uncommitted version whose content survives nowhere, not even inside another version of the file
        lost = any(not any(f == g and c in d.split() for g, d in after) for f, c in before)
        s1 = s
        cmd_text = "\n".join(f"{i + 1}. {c}" for i, c in enumerate(cmds))
        floor = f"{RULES}\n\nState before:\n{render(s0)}\n\nCommands, in order:\n{cmd_text}\n\nThe questions are about the state after all these commands."
        log = "; ".join(f"command {i + 1}: {'failed' if rc else 'ok'}" for i, rc in enumerate(codes))
        ceiling = (f"{RULES}\n\nCommands that were run:\n{cmd_text}\n\nState after the commands:\n{render(s1)}\n"
                   f"What happened: {log}. Uncommitted work lost for good: {'yes' if lost else 'no'}.")
        return floor, ceiling, questions(s0, s1, codes, lost, rng), kinds
    finally:
        b.close()


def to_rows(rng, n_examples, steps, allow_held=False, require_held=False, root=None, per_example=2):
    """Rows in the trainer's format; per example, `per_example` questions (the 'lost' and 'fails' ones favoured)."""
    rows = []
    while len(rows) < n_examples * per_example:
        floor, ceiling, qs, kinds = example(rng, rng.choice(steps), allow_held, root)
        if require_held and not (set(kinds) & HELD):
            continue
        pref = [q for q in qs if q[0] in ("lost", "fails", "in_progress")]
        rest = [q for q in qs if q[0] not in ("lost", "fails", "in_progress")]
        rng.shuffle(rest)
        for qt, q, gold, gold0 in (rng.sample(pref, 1) + rest)[:per_example]:
            rows.append({"world": "git", "qtype": qt, "steps": len(kinds), "question": q, "gold": gold, "floor": floor,
                         "ceiling": ceiling, "gold0": gold0, "known0": gold0 is not None,
                         "held_used": sorted(set(kinds) & HELD), "kinds": kinds})
    return rows
