"""WS-F git family: repositories built for real (history, a bare origin, a topic branch, conflicts, stashes, linked
worktrees, ignored and untracked files), commands from a broad grammar run for real by the unprivileged user, and the
state rendered by the released client 0.1.1 itself (layout new = facts + notes, old = 0.1.0 text), so training matches
inference. The lost oracle follows the client's question: a version of a file that existed before (working directory,
staging area, ignored files included) and afterwards is in none of: a working directory, the staging area, any branch,
any stash."""
from __future__ import annotations

import hashlib
import json
import os
import random
import re
import subprocess
import sys

from common import BOX_ROOT, NOBODY, choice, make_box, remove_box, row, run_unprivileged, stable_seed, yes_no

sys.path.insert(0, "/root/decis/mission/F/client011")
os.environ.update({"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "safe.directory", "GIT_CONFIG_VALUE_0": "*"})
from ekbasis import git as EG  # noqa: E402
from ekbasis import prompts as P  # noqa: E402

GIT_ENV = {"GIT_AUTHOR_NAME": "Dev", "GIT_AUTHOR_EMAIL": "dev@example.org", "GIT_COMMITTER_NAME": "Dev",
           "GIT_COMMITTER_EMAIL": "dev@example.org", "GIT_AUTHOR_DATE": "2026-09-01T10:00:00Z",
           "GIT_COMMITTER_DATE": "2026-09-01T10:00:00Z", "GIT_CONFIG_NOSYSTEM": "1", "GIT_EDITOR": "true",
           "GIT_SEQUENCE_EDITOR": "true", "GIT_TERMINAL_PROMPT": "0", "GIT_PAGER": "cat", "GIT_MERGE_AUTOEDIT": "no"}
FILES = ["lib/parser.py", "assets/theme.css", "manual/intro.md", "tools/build.sh", "data/seed.json", "app/main.go",
         "api/routes.ts", "conf/app.toml", "src/engine.rs", "ui/panel.vue", "sql/schema.sql", "bin/run.sh"]
WORDS = ["amber", "basil", "cobalt", "dahlia", "ermine", "falcon", "garnet", "hemlock", "indigo", "jackal", "kelp",
         "lotus", "magma", "nectar", "onyx", "pecan", "quince", "raven", "saffron", "tamarind"]
BRANCHES = ["topic", "hotfix", "sprint", "spike", "polish", "rework"]


def tok(rng):
    return f"{rng.choice(WORDS)}-{rng.randint(100, 999)}"


def gen_params(rng):
    files = rng.sample(FILES, rng.randint(3, 5))
    sp = {"files": {f: tok(rng) for f in files}, "branch": rng.choice(BRANCHES),
          "ignore": rng.random() < 0.55, "origin": rng.random() < 0.5, "origin_ahead": False, "stash": 0,
          "worktree": None, "inprog": None, "wt": []}
    sp["feat_mod"] = rng.choice(files)
    sp["feat_tok"] = tok(rng)
    sp["feat_adds"] = rng.random() < 0.3  # the branch also adds a file
    sp["feat_new"] = rng.choice(["notes/todo.md", "config.local", ".env"])
    sp["main_mod"] = rng.choice(files)
    sp["main_tok"] = tok(rng)
    sp["origin_ahead"] = sp["origin"] and rng.random() < 0.35
    sp["stash"] = rng.choice([0, 0, 0, 1, 2])
    if rng.random() < 0.18:
        sp["worktree"] = {"dirty": rng.random() < 0.5}
    r = rng.random()
    if r < 0.12:
        sp["inprog"] = "merge_conflict"
    elif r < 0.2:
        sp["inprog"] = rng.choice(["merge_resolved", "merge_resolved_staged"])
    elif r < 0.25:
        sp["inprog"] = "rebase_conflict"
    elif r < 0.29:
        sp["inprog"] = "cherry_conflict"
    if sp["inprog"]:
        sp["main_mod"] = sp["feat_mod"]
    for _ in range(rng.randint(1, 3)):
        kind = rng.choice(["modify", "modify", "stage", "untracked", "ignored", "delete", "modify"])
        f = rng.choice(files)
        sp["wt"].append([kind, f, tok(rng)])
    return sp


def q(s):
    return "'" + s.replace("'", "'\\''") + "'"


def setup_script(sp):
    L = ["set -e", "git init -q -b main repo", "cd repo"]
    for f, c in sp["files"].items():
        L += [f"mkdir -p {q(os.path.dirname(f))}" if "/" in f else ":", f"printf '%s\\n' {q(c)} > {q(f)}"]
    if sp["ignore"]:
        L.append("printf '%s\\n' '*.log' 'build/' '.env' 'config.local' > .gitignore")
    L += ["git add -A", "git commit -q -m start"]
    if sp["origin"]:
        L += ["git init -q --bare ../origin.git", "git remote add origin ../origin.git", "git push -q -u origin main"]
    b = sp["branch"]
    L += [f"git checkout -q -b {b}", f"printf '%s\\n' {q(sp['feat_tok'])} > {q(sp['feat_mod'])}"]
    if sp["feat_adds"]:
        d = os.path.dirname(sp["feat_new"])
        L += [f"mkdir -p {q(d)}" if d else ":", f"printf '%s\\n' 'branch version' > {q(sp['feat_new'])}",
              f"git add -f {q(sp['feat_new'])}"]
    L += ["git commit -q -am 'work on branch'", "git checkout -q main"]
    L += [f"printf '%s\\n' {q(sp['main_tok'])} > {q(sp['main_mod'])}", "git commit -q -am 'change on main'"]
    if sp["origin_ahead"]:
        L += ["git push -q origin main", "git reset -q --hard HEAD~1"]
    for i in range(sp["stash"]):
        f = list(sp["files"])[i % len(sp["files"])]
        L += [f"printf '%s\\n' 'stashed {i}' >> {q(f)}", f"git stash push -q -m 'saved {i}'"]
    if sp["worktree"]:
        L += [f"git worktree add -q ../wt {b}"]
        if sp["worktree"]["dirty"]:
            L += [f"printf '%s\\n' 'wt edit' >> ../wt/{q(sp['feat_mod'])}"]
    ip = sp["inprog"]
    if ip and ip.startswith("merge"):
        L += [f"git merge -q {b} >/dev/null 2>&1 || true"]
        if ip in ("merge_resolved", "merge_resolved_staged"):
            L += [f"printf '%s\\n' 'resolved by hand' > {q(sp['feat_mod'])}"]
            if ip == "merge_resolved_staged":
                L += [f"git add {q(sp['feat_mod'])}"]
    elif ip == "rebase_conflict":
        L += [f"git checkout -q {b}", "git rebase -q main >/dev/null 2>&1 || true"]
    elif ip == "cherry_conflict":
        L += [f"git cherry-pick {b} >/dev/null 2>&1 || true"]
    if not ip:
        for kind, f, c in sp["wt"]:
            if kind == "modify":
                L.append(f"[ -e {q(f)} ] && printf '%s\\n' {q(c)} > {q(f)} || true")
            elif kind == "stage":
                L.append(f"[ -e {q(f)} ] && printf '%s\\n' {q(c)} > {q(f)} && git add {q(f)} || true")
            elif kind == "untracked":
                L.append(f"printf '%s\\n' {q(c)} > {q(os.path.basename(f) + '.new')}")
            elif kind == "ignored":
                L.append(f"printf '%s\\n' {q(c)} > {q(rng_ignored(c))}")
            elif kind == "delete":
                L.append(f"rm -f {q(f)}")
    return "\n".join(L) + "\n"


def rng_ignored(c):
    return {0: "runtime.log", 1: ".env", 2: "config.local"}[int(hashlib.md5(c.encode()).hexdigest(), 16) % 3]


def command_forms(sp, rng):
    b = sp["branch"]
    files = list(sp["files"])
    f = rng.choice(files)
    f2 = rng.choice(files)
    ip = sp["inprog"]
    C = [
        ("checkout", f"git checkout {b}"), ("checkout_f", f"git checkout -f {b}"), ("switch", f"git switch {b}"),
        ("switch_f", f"git switch {rng.choice(['-f', '--discard-changes'])} {b}"), ("switch_c", "git switch -c trial"),
        ("checkout_file", f"git checkout -- {f}"), ("checkout_rev_file", f"git checkout {b} -- {f}"),
        ("switch_detach", "git switch --detach HEAD~1"), ("checkout_rev", "git checkout HEAD~1"),
        ("restore", f"git restore {f}"), ("restore_staged", f"git restore --staged {f}"),
        ("restore_source", f"git restore --source={b} {f}"), ("restore_both", f"git restore --staged --worktree {f}"),
        ("restore_all", "git restore ."),
        ("reset_hard", "git reset --hard"), ("reset_hard_prev", "git reset --hard HEAD~1"), ("reset_soft", "git reset --soft HEAD~1"),
        ("reset_mixed", "git reset HEAD~1"), ("reset_merge", "git reset --merge HEAD~1"), ("reset_keep", "git reset --keep HEAD~1"),
        ("reset_path", f"git reset -- {f}"), ("reset_hard_path", f"git reset --hard {f}"),
        ("stash", "git stash"), ("stash_u", "git stash -u"), ("stash_a", "git stash -a"), ("stash_pop", "git stash pop"),
        ("stash_apply", "git stash apply"), ("stash_drop", "git stash drop"), ("stash_clear", "git stash clear"),
        ("stash_keep_index", "git stash -k"), ("stash_path", f"git stash push {f}"),
        ("clean_n", "git clean -n"), ("clean_f", "git clean -f"), ("clean_fd", "git clean -fd"), ("clean_fdx", "git clean -fdx"),
        ("clean_fX", "git clean -fX"), ("clean_d", "git clean -d"),
        ("merge", f"git merge {b}"), ("merge_squash", f"git merge --squash {b}"), ("merge_no_commit", f"git merge --no-commit {b}"),
        ("rebase", f"git rebase {b}"), ("cherry_pick", f"git cherry-pick {b}"), ("cherry_pick_n", f"git cherry-pick -n {b}"),
        ("revert", "git revert --no-edit HEAD"),
        ("commit_a", "git commit -am wip"), ("commit", "git commit -m wip"), ("amend", "git commit --amend -m redo"),
        ("add_commit", "git add -A && git commit -m all"),
        ("rm", f"git rm {f}"), ("rm_cached", f"git rm --cached {f}"), ("rm_f", f"git rm -f {f}"),
        ("mv", f"git mv {f} {f}.old"), ("mv_f", f"git mv -f {f} {f2}"),
        ("branch_D", f"git branch -D {b}"), ("branch_f", f"git branch -f {b} HEAD"), ("branch_new", "git branch extra"),
        ("sparse_set", f"git sparse-checkout set {os.path.dirname(f) or 'docs'}"), ("sparse_disable", "git sparse-checkout disable"),
    ]
    if sp["origin"]:
        C += [("pull", "git pull"), ("pull_rebase", "git pull --rebase"), ("push_force", "git push --force"),
              ("fetch", "git fetch"), ("reset_origin", "git reset --hard origin/main")]
    if sp["worktree"]:
        C += [("wt_remove", "git worktree remove ../wt"), ("wt_remove_f", "git worktree remove --force ../wt")]
    if ip:
        C += [("merge_abort", "git merge --abort"), ("merge_continue", "git merge --continue"), ("rebase_abort", "git rebase --abort"),
              ("rebase_continue", "git rebase --continue"), ("rebase_skip", "git rebase --skip"),
              ("cherry_abort", "git cherry-pick --abort"), ("cherry_continue", "git cherry-pick --continue"),
              ("checkout_ours", f"git checkout --ours {sp['feat_mod']}"), ("add_resolved", f"git add {sp['feat_mod']}")]
        C += [x for x in C if x[0].endswith(("abort", "continue", "skip", "ours"))] * 2
    return C


def blob(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def git_root(repo, *args):
    p = subprocess.run(["git", "-C", repo] + list(args), capture_output=True, text=True,
                       env={**os.environ, "GIT_CONFIG_NOSYSTEM": "1"})
    return p.returncode, p.stdout


def tree_files(top):
    out = {}
    if not os.path.isdir(top):
        return out
    for root, dirs, files in os.walk(top):
        if ".git" in dirs:
            dirs.remove(".git")
        for n in files:
            p = os.path.join(root, n)
            if os.path.islink(p) or n == ".git":
                continue
            try:
                out[os.path.relpath(p, top)] = blob(open(p, "rb").read())
            except Exception:  # noqa: BLE001
                pass
    return out


def versions(box):
    repo = os.path.join(box, "repo")
    work = set(tree_files(repo).values()) | set(tree_files(os.path.join(box, "wt")).values())
    rc, out = git_root(repo, "ls-files", "-s")
    index = {l.split()[1] for l in out.splitlines() if l.strip()}
    reach = set()
    rc, out = git_root(repo, "rev-list", "--objects", "--all")
    objs = [l.split()[0] for l in out.splitlines() if l.strip()]
    rc, st = git_root(repo, "log", "-g", "--format=%H", "refs/stash")
    if rc == 0 and st.strip():
        rc2, o2 = git_root(repo, "rev-list", "--objects", *st.split())
        objs += [l.split()[0] for l in o2.splitlines() if l.strip()]
    if objs:
        p = subprocess.run(["git", "-C", repo, "cat-file", "--batch-check=%(objectname) %(objecttype)"],
                           input="\n".join(objs), capture_output=True, text=True)
        reach = {l.split()[0] for l in p.stdout.splitlines() if l.endswith(" blob")}
    return work, index, reach


def run_cmds(box, cmds):
    meta = box + ".meta"
    os.makedirs(meta, exist_ok=True)
    os.chown(meta, NOBODY, NOBODY)
    lines = [f'cd "{box}/repo" || exit 99']
    for k, c in enumerate(cmds, 1):
        lines += ["{ " + c, f'}} >/dev/null 2>"{meta}/{k}.err" </dev/null; echo $? > "{meta}/{k}.rc"']
    open(os.path.join(meta, "run.sh"), "w").write("\n".join(lines) + "\n")
    run_unprivileged(["bash", "--noprofile", "--norc", os.path.join(meta, "run.sh")], cwd=box, env_extra=GIT_ENV,
                     timeout=20, cpu=15)
    codes, errs = [], []
    for k in range(1, len(cmds) + 1):
        try:
            codes.append(int(open(os.path.join(meta, f"{k}.rc")).read().strip()))
            e = [x for x in open(os.path.join(meta, f"{k}.err"), errors="replace").read().splitlines() if x.strip()]
            errs.append(e[0][:140] if e else "")
        except Exception:  # noqa: BLE001
            return None, None
    return codes, errs


def state_flags(repo):
    g = os.path.join(repo, ".git")
    inprog = any(os.path.exists(os.path.join(g, x)) for x in ("MERGE_HEAD", "rebase-merge", "rebase-apply"))
    rc, out = git_root(repo, "status", "--porcelain")
    clean = rc == 0 and not out.strip()
    rc, br = git_root(repo, "symbolic-ref", "--short", "-q", "HEAD")
    branch = br.strip() if rc == 0 and br.strip() else "(detached HEAD)"
    rc, bl = git_root(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads")
    return inprog, clean, branch, sorted(bl.split())


def execute(sp, cmds, tag, layouts):
    box = make_box(tag)
    try:
        os.chown(box, NOBODY, NOBODY)
        os.makedirs(box + ".meta", exist_ok=True)
        os.chown(box + ".meta", NOBODY, NOBODY)
        open(box + ".meta/setup.sh", "w").write(setup_script(sp))
        rc, out, err = run_unprivileged(["bash", "--noprofile", "--norc", box + ".meta/setup.sh"], cwd=box,
                                        env_extra=GIT_ENV, timeout=30, cpu=20)
        repo = os.path.join(box, "repo")
        if rc != 0 or not os.path.isdir(repo):
            return None
        views = {}
        for lay in layouts:
            facts = lay == "new"
            v = EG.inspect(repo, cmds, facts=facts)
            notes = P.git_notes(cmds, v.info) if facts else None
            views[lay] = {"state": v.state, "notes": notes, "floor": P.git_state(v.state, cmds, notes=notes)}
        w0, i0, r0 = versions(box)
        f0 = state_flags(repo)
        codes, errs = run_cmds(box, cmds)
        if codes is None:
            return None
        w1, i1, r1 = versions(box)
        f1 = state_flags(repo)
        after = EG.inspect(repo, (), facts=True).state if os.path.isdir(os.path.join(repo, ".git")) else "(no repository)"
        lost = bool((w0 | i0) - (w1 | i1 | r1))
        return {"views": views, "codes": codes, "errs": errs, "lost": lost, "inprog": f1[0], "clean": f1[1],
                "branch": f1[2], "branches": f1[3], "before_flags": f0, "after_state": after}
    finally:
        remove_box(box)
        import shutil
        shutil.rmtree(box + ".meta", ignore_errors=True)


def face(cmds, qt, arg, before_flags):
    j = " ; ".join(cmds)
    if qt == "lost":
        return bool(re.search(r"reset --hard|checkout -f|switch (-f|--discard)|clean -[a-zA-Z]*f|stash (drop|clear)|"
                              r"restore (?!--staged )|checkout -- |rm -f|worktree remove --force|branch -D", j))
    if qt == "fails":
        return False
    if qt == "in_progress":
        return False
    if qt == "clean":
        return bool(re.search(r"reset --hard|stash|commit|clean -f", j)) or before_flags[1]
    if qt == "branch":
        m = re.findall(r"git (?:checkout|switch)(?: -[a-zA-Z-]+)* (\w+)$", cmds[-1])
        return m[-1] if m and m[-1] in arg else before_flags[2]
    return None


def perturb(sp, rng):
    s2 = json.loads(json.dumps(sp))
    op = rng.choice(["ignore", "wt_drop", "wt_add", "inprog", "stash", "feat_adds", "origin"])
    if op == "ignore":
        s2["ignore"] = not s2["ignore"]
    elif op == "wt_drop":
        if not s2["wt"]:
            return None
        s2["wt"].pop(rng.randrange(len(s2["wt"])))
    elif op == "wt_add":
        s2["wt"].append([rng.choice(["modify", "stage", "untracked", "ignored"]), rng.choice(list(s2["files"])), tok(rng)])
    elif op == "inprog":
        s2["inprog"] = rng.choice([None, "merge_conflict", "merge_resolved", "merge_resolved_staged"])
        if s2["inprog"]:
            s2["main_mod"] = s2["feat_mod"]
    elif op == "stash":
        s2["stash"] = 0 if s2["stash"] else 1
    elif op == "feat_adds":
        s2["feat_adds"] = not s2["feat_adds"]
    else:
        s2["origin"] = not s2["origin"]
        s2["origin_ahead"] = s2["origin"] and rng.random() < 0.5
    return s2, op


def golds(res, ncmd):
    g = {("lost", None): res["lost"], ("in_progress", None): res["inprog"], ("clean", None): res["clean"]}
    for k in range(1, ncmd + 1):
        g[("fails", k)] = res["codes"][k - 1] != 0
    g[("branch", None)] = res["branch"]
    return g


def make_items(seed):
    rng = random.Random(stable_seed("rx_git", seed))
    sp = gen_params(rng)
    C = command_forms(sp, rng)
    RISKY = {"checkout", "checkout_f", "switch", "switch_f", "checkout_file", "restore", "restore_both", "restore_all",
             "reset_hard", "reset_hard_prev", "reset_merge", "reset_keep", "stash_drop", "stash_clear", "clean_f",
             "clean_fd", "clean_fdx", "clean_fX", "rm_f", "mv_f", "merge", "rebase", "stash_pop", "wt_remove_f",
             "sparse_set", "reset_origin", "pull", "checkout_rev_file", "restore_source", "merge_abort", "rebase_abort",
             "cherry_abort", "checkout_ours", "stash_u", "stash_a"}
    pool_ = [x for x in C if x[0] in RISKY] if rng.random() < 0.6 else C
    name, c1 = rng.choice(pool_ or C)
    cmds = [c1]
    if rng.random() < 0.35:
        n2, c2 = rng.choice(C)
        if c2 != c1:
            cmds.append(c2)
            name += "+" + n2
    if any(".." in c and "../wt" not in c for c in cmds):
        return [], {"invalid": 1}
    tag = f"g{os.getpid()}_{seed}"
    layout = "new" if rng.random() < 0.6 else "old"
    res = execute(sp, cmds, tag, [layout])
    if res is None:
        return [], {"exec_fail": 1}
    twin = None
    for _ in range(4):
        pt = perturb(sp, rng)
        if not pt:
            continue
        s2, op = pt
        r2 = execute(s2, cmds, tag + "t", [layout])
        if r2 is None:
            continue
        ga, gb = golds(res, len(cmds)), golds(r2, len(cmds))
        if {k: v for k, v in ga.items() if k[0] != "branch"} != {k: v for k, v in gb.items() if k[0] != "branch"}:
            twin = (s2, r2, op)
            break
    inst = [("a", sp, res)] + ([("b", twin[0], twin[1])] if twin else [])
    rows = []
    for side, sp_, res_ in inst:
        g = golds(res_, len(cmds))
        floor = res_["views"][layout]["floor"]
        what = "; ".join(f"command {k}: {'ok' if c == 0 else 'fails'}" for k, c in enumerate(res_["codes"], 1))
        what += f". Uncommitted work lost for good: {'yes' if res_['lost'] else 'no'}."
        ceiling = (f"{P.GIT_RULES}\n\nCommands that were run:\n{P.numbered(cmds)}\n\nState after the commands:\n"
                   f"{res_['after_state']}\nWhat happened: {what}")
        qs = [("lost", None, P.GIT_LOST), ("in_progress", None, P.GIT_IN_PROGRESS), ("clean", None, P.GIT_CLEAN)]
        qs += [("fails", k, P.git_fails(k)) for k in range(1, len(cmds) + 1)]
        br = sorted(set(res_["branches"]) | ({res_["branch"]} if res_["branch"] != "(detached HEAD)" else set()))
        if res_["branch"] != "(detached HEAD)" and len(br) >= 2 and rng.random() < 0.5:
            qs.append(("branch", None, P.git_branch(br)))
        for qt, arg, qd in qs:
            gold = g[(qt, arg)]
            fv = face(cmds, qt, br if qt == "branch" else arg, res_["before_flags"])
            known0 = qt in ("in_progress", "clean", "branch")
            g0 = {"in_progress": res_["before_flags"][0], "clean": res_["before_flags"][1],
                  "branch": res_["before_flags"][2]}.get(qt)
            if qt == "branch" and g0 not in qd["criteria"]:
                known0, g0 = False, None
            rows.append(row(world="rx_git", family="git", template=name, qtype=qt, steps=len(cmds), question=qd,
                            gold=gold, gold0=g0 if known0 else None, known0=known0, floor=floor, ceiling=ceiling,
                            rid=f"rxgit-{seed}-{side}-{qt}{'' if arg is None else arg}",
                            twin=(f"rxgit-{seed}-{'b' if side == 'a' else 'a'}" if twin else None), layout=layout,
                            face=fv, struct={"params": sp_, "cmds": cmds, "codes": res_["codes"], "op": twin[2] if twin else None}))
    return rows, {"scenarios": 1, "twins": int(bool(twin))}
