"""WS-FX new git families (SPEC.md + Addendum 1): git_tag and git_bare_push (held out), git_worktree (only worktree forms
WS-F does not have) and git_reflog_gc. Repositories come from WS-F's setup (gitfam.setup_script) plus a few extra setup
lines per family; the state is the released client's own rendering (as in WS-F) followed by a References block (branches,
tags, the origin's branches, linked worktrees, with short commit ids and subjects). Truth from real git (2.43) run by the
unprivileged user."""
from __future__ import annotations

import json
import os
import random
import re
import shutil

import gitfam as G
from common import NOBODY, choice, make_box, remove_box, row, run_unprivileged, stable_seed, yes_no

EG, P = G.EG, G.P


def gitc(repo, *args):
    rc, out = G.git_root(repo, *args)
    return out if rc == 0 else ""


def refs(repo, box):
    def fmt_refs(path, pattern):
        out = gitc(path, "for-each-ref", "--format=%(refname:short)\t%(objecttype)\t%(*objectname:short)\t%(objectname:short)"
                                           "\t%(*subject)\t%(subject)", pattern)
        res = {}
        for line in out.splitlines():
            name, typ, peeled, obj, psub, sub = (line.split("\t") + [""] * 6)[:6]
            if typ == "tag":
                res[name] = {"commit": peeled, "subject": psub, "annotated": True}
            else:
                res[name] = {"commit": obj, "subject": sub, "annotated": False}
        return res
    origin = os.path.join(box, "origin.git")
    wts = []
    for block in gitc(repo, "worktree", "list", "--porcelain").split("\n\n"):
        d = dict(l.split(" ", 1) if " " in l else (l, "") for l in block.splitlines() if l)
        if "worktree" in d:
            p = os.path.relpath(d["worktree"], os.path.join(box, "repo"))
            wts.append({"path": p, "branch": d.get("branch", "").replace("refs/heads/", "") or "(detached)",
                        "locked": "locked" in d})
    return {"branches": fmt_refs(repo, "refs/heads"), "tags": fmt_refs(repo, "refs/tags"),
            "origin": fmt_refs(origin, "refs/heads") if os.path.isdir(origin) else None, "worktrees": wts}


def label(c):
    return f"commit {c['commit']} ('{c['subject']}')" if c else "(none)"


def render_refs(R):
    lines = ["References:"]
    lines.append("Branches: " + ("; ".join(f"{b} → {label(c)}" for b, c in sorted(R["branches"].items())) or "(none)"))
    lines.append("Tags: " + ("; ".join(f"{t}{' (annotated)' if c['annotated'] else ''} → {label(c)}"
                                         for t, c in sorted(R["tags"].items())) or "(none)"))
    if R["origin"] is not None:
        lines.append("On origin: " + ("; ".join(f"{b} → {label(c)}" for b, c in sorted(R["origin"].items())) or "(no branches)"))
    lines.append("Worktrees: " + "; ".join(f"{w['path']} ({w['branch']}{', locked' if w['locked'] else ''})" for w in R["worktrees"]))
    return "\n".join(lines)


EXTRA = {
    "git_tag": lambda sp, rng: ["git tag v1 HEAD~1 2>/dev/null || git tag v1 HEAD", f"git tag -a rel-{rng.randint(1, 9)} -m 'release' {sp['branch']}"] +
                               (["git tag keep HEAD"] if rng.random() < 0.5 else []),
    "git_bare_push": lambda sp, rng: ([f"git push -q origin {sp['branch']}"] if rng.random() < 0.4 else []),
    "git_reflog_gc": lambda sp, rng: [],
    "git_worktree": lambda sp, rng: ([f"git worktree add -q ../wt {sp['branch']}"] if not sp.get("worktree") and rng.random() < 0.6 else []),
}


def forms(family, sp, rng, R):
    b = sp["branch"]
    tags = sorted(R["tags"])
    commits = {k: v["commit"] for k, v in R["branches"].items()}
    if family == "git_tag":
        t = rng.choice(tags) if tags else "v1"
        return [("tag_delete", f"git tag -d {t}"), ("tag_force_move", f"git tag -f {t} {rng.choice(['HEAD', b])}"),
                ("tag_create_existing", f"git tag {t}"), ("tag_new_on_branch", f"git tag v{rng.randint(2, 9)} {b}"),
                ("tag_checkout", f"git checkout {t}"), ("tag_branch_D_kept", f"git branch -D {b}"),
                ("tag_annotated_new", f"git tag -a v{rng.randint(2, 9)} -m note HEAD~1")]
    if family == "git_bare_push":
        return [("push_plain", rng.choice(["git push", "git push origin main"])),
                ("push_force_lease", "git push --force-with-lease origin main"),
                ("push_new_branch", f"git push origin {b}"), ("push_delete_branch", f"git push origin --delete {b}"),
                ("push_refspec", f"git push origin HEAD:refs/heads/release"),
                ("push_after_fetch_lease", "git fetch -q && git push --force-with-lease origin main")]
    if family == "git_reflog_gc":
        drop = rng.choice([f"git branch -D {b}", "git reset --hard HEAD~1", "git commit --amend -m redo"])
        gc = "git reflog expire --expire=now --all && git gc -q --prune=now"
        return [("drop_then_gc", f"{drop} && {gc}"), ("drop_only", drop), ("gc_only", gc),
                ("drop_then_gc_keep_reflog", f"{drop} && git gc -q --prune=now")]
    if family == "git_worktree":
        return [("wt_add_new_branch", "git worktree add -b trial ../wt2"),
                ("wt_add_branch_in_use", f"git worktree add ../wt3 {rng.choice(['main', b])}"),
                ("wt_move", "git worktree move ../wt ../wt_moved"),
                ("wt_lock_then_remove", "git worktree lock ../wt && git worktree remove ../wt"),
                ("wt_prune_after_delete", "rm -rf ../wt && git worktree prune"),
                ("switch_branch_in_use", f"git switch {b}"),
                ("wt_add_detached", "git worktree add --detach ../wt4 HEAD~1")]
    return []


FAMILY_FORMS = {"git_tag": ["tag_delete", "tag_force_move", "tag_create_existing", "tag_new_on_branch", "tag_checkout",
                            "tag_branch_D_kept", "tag_annotated_new"],
                "git_bare_push": ["push_plain", "push_force_lease", "push_new_branch", "push_delete_branch", "push_refspec",
                                  "push_after_fetch_lease"],
                "git_reflog_gc": ["drop_then_gc", "drop_only", "gc_only", "drop_then_gc_keep_reflog"],
                "git_worktree": ["wt_add_new_branch", "wt_add_branch_in_use", "wt_move", "wt_lock_then_remove",
                                 "wt_prune_after_delete", "switch_branch_in_use", "wt_add_detached"]}
FAMILY_OF = {f: fam for fam, fs in FAMILY_FORMS.items() for f in fs}


def obj_exists(repo, sha):
    rc, _ = G.git_root(repo, "cat-file", "-e", f"{sha}^{{commit}}")
    return rc == 0


def execute(sp, extra, cmds, tag, watch):
    box = make_box(tag)
    try:
        os.chown(box, NOBODY, NOBODY)
        os.makedirs(box + ".meta", exist_ok=True)
        os.chown(box + ".meta", NOBODY, NOBODY)
        script = G.setup_script(sp)
        script += "\n".join(extra) + "\n" if extra else ""
        open(box + ".meta/setup.sh", "w").write(script)
        rc, out, err = run_unprivileged(["bash", "--noprofile", "--norc", box + ".meta/setup.sh"], cwd=box,
                                        env_extra=G.GIT_ENV, timeout=30, cpu=20)
        repo = os.path.join(box, "repo")
        if rc != 0 or not os.path.isdir(repo):
            return None
        v = EG.inspect(repo, cmds, facts=True)
        notes = P.git_notes(cmds, v.info)
        R0 = refs(repo, box)
        w0, i0, r0 = G.versions(box)
        f0 = G.state_flags(repo)
        watch_shas = {k: R0["branches"].get(k, {}).get("commit") for k in watch}
        full = {k: gitc(repo, "rev-parse", s).strip() for k, s in watch_shas.items() if s}
        codes, errs = G.run_cmds(box, cmds)
        if codes is None:
            return None
        R1 = refs(repo, box)
        w1, i1, r1 = G.versions(box)
        f1 = G.state_flags(repo)
        exists = {k: obj_exists(repo, s) for k, s in full.items()}
        dirs = {d: os.path.isdir(os.path.join(box, d)) for d in ("wt", "wt2", "wt3", "wt4", "wt_moved")}
        dirs0 = {d: os.path.isdir(os.path.join(box, d)) for d in dirs}
        lost = bool((w0 | i0) - (w1 | i1 | r1))
        return {"state": v.state, "notes": notes, "R0": R0, "R1": R1, "codes": codes, "errs": errs, "lost": lost,
                "inprog": f1[0], "clean": f1[1], "branch": f1[2], "before_flags": f0, "exists": exists,
                "watch": {k: R0["branches"].get(k) for k in watch}, "dirs": dirs, "dirs0": dirs0}
    finally:
        remove_box(box)
        shutil.rmtree(box + ".meta", ignore_errors=True)


def questions(family, rng, cmds, res):
    b = res["R0"]["branches"]
    qs = [("fails", k) for k in range(1, len(cmds) + 1)]
    if family == "git_tag":
        tags = sorted(set(res["R0"]["tags"]) | set(res["R1"]["tags"]))
        for t in rng.sample(tags, min(2, len(tags))):
            qs.append(("tag_exists", t) if rng.random() < 0.4 else ("tag_target", t))
        qs.append(("branch", None))
        bb = [k for k in b if k != "main"]
        if bb:
            qs.append(("found", bb[0]))
    elif family == "git_bare_push":
        qs += [("origin_tip", "main"), ("origin_has", rng.choice([k for k in b if k != "main"] + ["release"]))]
    elif family == "git_reflog_gc":
        c0 = cmds[0]
        m = re.search(r"git branch -D (\S+)", c0)
        target = m.group(1) if m else res["before_flags"][2]
        if res["watch"].get(target):
            qs.append(("found", target))
        others = [k for k in res["watch"] if k != target and res["watch"][k]]
        if others and rng.random() < 0.3:
            qs.append(("found", rng.choice(others)))
        qs.append(("lost", None))
    elif family == "git_worktree":
        qs += [("dir_exists", d) for d in ("wt", "wt2", "wt3", "wt_moved") if res["dirs"][d] or res["dirs0"][d] or d in " ".join(cmds)][:2]
        qs.append(("branch", None))
        qs.append(("lost", None))
    return qs


def gold(q, res):
    k, a = q
    if k == "fails":
        return res["codes"][a - 1] != 0
    if k == "tag_exists":
        return a in res["R1"]["tags"]
    if k == "tag_target":
        return label(res["R1"]["tags"].get(a)) if a in res["R1"]["tags"] else "(the tag no longer exists)"
    if k == "branch":
        return res["branch"]
    if k == "found":
        return res["exists"].get(a, False)
    if k == "origin_tip":
        return label((res["R1"]["origin"] or {}).get(a)) if (res["R1"]["origin"] or {}).get(a) else "(no such branch on origin)"
    if k == "origin_has":
        return a in (res["R1"]["origin"] or {})
    if k == "lost":
        return res["lost"]
    if k == "dir_exists":
        return res["dirs"][a]
    return None


def gold0(q, res):
    k, a = q
    if k == "tag_exists":
        return a in res["R0"]["tags"]
    if k == "tag_target":
        return label(res["R0"]["tags"].get(a)) if a in res["R0"]["tags"] else "(the tag no longer exists)"
    if k == "branch":
        return res["before_flags"][2]
    if k == "origin_tip":
        return label((res["R0"]["origin"] or {}).get(a)) if (res["R0"]["origin"] or {}).get(a) else "(no such branch on origin)"
    if k == "origin_has":
        return a in (res["R0"]["origin"] or {})
    if k == "dir_exists":
        return res["dirs0"][a]
    if k == "found":
        return True
    return None


def qdict(q, res, other):
    k, a = q
    if k == "fails":
        return P.git_fails(a)
    if k == "lost":
        return P.GIT_LOST
    if k == "tag_exists":
        return yes_no(f"After these commands, does the tag {a} exist?")
    if k == "found":
        c = res["watch"].get(a) or {}
        return yes_no(f"After these commands, does the repository still contain the commit {c.get('commit')} "
                      f"('{c.get('subject')}') that branch {a} pointed to before (in any branch, tag, stash or the reflog)?")
    if k == "origin_has":
        return yes_no(f"After these commands, does origin have a branch named {a}?")
    if k == "dir_exists":
        return yes_no(f"After these commands, does the folder ../{a} exist?")
    if k == "branch":
        opts = sorted(set(res["R0"]["branches"]) | set(res["R1"]["branches"]) | {"(detached HEAD)"})
        return choice("After these commands, which branch is checked out?", opts)
    labels = set()
    for r_ in (res, other):
        if r_ is None:
            continue
        for R in (r_["R0"], r_["R1"]):
            for c in list(R["branches"].values()) + list(R["tags"].values()) + list((R["origin"] or {}).values()):
                labels.add(label(c))
    if k == "tag_target":
        opts = sorted(labels)[:6] + ["(the tag no longer exists)"]
        return choice(f"After these commands, which commit does the tag {a} point to?", opts)
    if k == "origin_tip":
        opts = sorted(labels)[:6] + ["(no such branch on origin)"]
        return choice(f"After these commands, which commit is origin's {a} at?", opts)
    return None


def make_items(seed, allowed=None):
    names = [n for n in (allowed or FAMILY_OF) if n in FAMILY_OF]
    if not names:
        return [], {"skipped": 1}
    family = FAMILY_OF[names[0]]
    rng = random.Random(stable_seed("fx_git", family, seed))
    sp = G.gen_params(rng)
    sp["inprog"] = None if rng.random() < 0.85 else sp["inprog"]
    if family == "git_bare_push":
        sp["origin"] = True
        sp["origin_ahead"] = rng.random() < 0.5
    if family == "git_worktree" and rng.random() < 0.5:
        sp["worktree"] = {"dirty": rng.random() < 0.5}
    extra = EXTRA[family](sp, rng)
    # a first pass only to read the references the forms need (tags, branch tips)
    probe = execute(sp, extra, ["git status"], f"fxgp{os.getpid()}_{seed}", [])
    if probe is None:
        return [], {"exec_fail": 1}
    F = dict(forms(family, sp, rng, probe["R0"]))
    cand = [n for n in names if n in F]
    if not cand:
        return [], {"skipped": 1}
    name = rng.choice(cand)
    cmds = [F[name]]
    if any(".." in c and "../wt" not in c and "../origin" not in c for c in cmds):
        return [], {"invalid": 1}
    watch = [k for k in probe["R0"]["branches"]]
    tag = f"fxg{os.getpid()}_{seed}"
    res = execute(sp, extra, cmds, tag, watch)
    if res is None:
        return [], {"exec_fail": 1}
    qs = questions(family, rng, cmds, res)
    twin = None
    for _ in range(3):
        pt = G.perturb(sp, rng)
        if not pt:
            continue
        s2, op = pt
        if family == "git_bare_push":
            s2["origin"] = True
            s2["origin_ahead"] = not sp["origin_ahead"] if op == "origin" else sp["origin_ahead"]
        r2 = execute(s2, extra, cmds, tag + "t", watch)
        if r2 is None:
            continue
        if [gold(q, r2) for q in qs] != [gold(q, res) for q in qs]:
            twin = (s2, r2, op)
            break
    inst = [("a", sp, res)] + ([("b", twin[0], twin[1])] if twin else [])
    rows = []
    for side, sp_, r_ in inst:
        other = twin[1] if (twin and side == "a") else (res if side == "b" else None)
        state = r_["state"] + "\n" + render_refs(r_["R0"])
        floor = P.git_state(state, cmds, notes=r_["notes"])
        what = "; ".join(f"command {k}: {'ok' if c == 0 else 'fails'}" + (f" ({e})" if c and e else "")
                         for k, (c, e) in enumerate(zip(r_["codes"], r_["errs"]), 1))
        ceiling = (f"{P.GIT_RULES}\n\nCommands that were run:\n{P.numbered(cmds)}\n\nState after the commands:\n"
                   f"{render_refs(r_['R1'])}\nWhat happened: {what}.")
        for q in qs:
            g = gold(q, r_)
            qd = qdict(q, r_, other)
            if qd is None or g is None:
                continue
            if qd["type"] == "choice" and str(g) not in qd["criteria"]:
                qd["criteria"][str(g)] = str(g)
            g0 = gold0(q, r_)
            known0 = g0 is not None and (qd["type"] != "choice" or str(g0) in qd["criteria"])
            rows.append(row(world="rx_git", family="git", template=name, qtype=q[0], steps=len(cmds), question=qd,
                            gold=str(g) if qd["type"] == "choice" else bool(g),
                            gold0=(str(g0) if qd["type"] == "choice" else bool(g0)) if known0 else None, known0=known0,
                            floor=floor, ceiling=ceiling,
                            rid=f"fxgit-{seed}-{side}-{q[0]}-{re.sub(r'[^A-Za-z0-9]', '_', str(q[1]))}",
                            twin=(f"fxgit-{seed}-{'b' if side == 'a' else 'a'}" if twin else None), layout="new",
                            struct={"params": sp_, "extra": extra, "cmds": cmds, "codes": r_["codes"],
                                    "op": twin[2] if twin else None}))
    return rows, {"scenarios": 1, "twins": int(bool(twin))}
