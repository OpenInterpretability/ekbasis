"""WS-FX Addendum 5: intent-relative side effects. From a real transition (S, A, S') the typed effect set E = diff(S, S')
is computed from execution; the requested effects I are the effects on what the action names (or a sampled proper
subset of them); a request R asking for exactly I is rendered from I with templates; the questions ask whether the action
changes anything besides R (yes/no) and which effect happens besides R (one true side effect, plausible effects that did
not happen, or "nothing else changes"). Families: se_shell, se_sql, se_git, se_vikunja (train) and mm_side_effects
(Memos, held-out app). The truth is the execution; no LLM anywhere."""
from __future__ import annotations

import fnmatch
import os
import random
import re
import shlex

from common import choice, cmd_ceiling, cmd_floor, row, stable_seed, world_ceiling, world_floor, yes_no

NOTHING = "nothing else changes"
DELETE_VERBS = {"rm", "rmdir", "unlink", "truncate", "shred", ":"}


def q_texts(R, what):
    q1 = yes_no(f"The user asked for exactly this: {R}. Besides what the user asked, does this {what} also change anything else?")
    return q1


def build_rows(*, world, family, template, floor, ceiling, E, I, render, distract, rng, rid, struct, what, steps,
               compress=None):
    side = sorted(E - I, key=str)
    R = request_text(compress(I) if compress else I, render)
    if not R:
        return []
    rows = []
    q1 = q_texts(R, what)
    rows.append(row(world=world, family=family, template=template, qtype="side_effect", steps=steps, question=q1,
                    gold=bool(side), gold0=None, known0=False, floor=floor, ceiling=ceiling, rid=rid + "-se", struct=struct))
    true_opt = render(rng.choice(side)) if side else None
    pool = [render(u) for u in distract if u not in E]
    pool = [p for p in dict.fromkeys(pool) if p != true_opt]
    rng.shuffle(pool)
    opts = ([true_opt] if true_opt else []) + pool[:3 if true_opt else 3] + [NOTHING]
    if len(opts) >= 3:
        q2 = choice(f"The user asked for exactly this: {R}. Which of these also happens, besides what the user asked?", opts)
        rows.append(row(world=world, family=family, template=template, qtype="side_effect_which", steps=steps, question=q2,
                        gold=true_opt or NOTHING, gold0=None, known0=False, floor=floor, ceiling=ceiling, rid=rid + "-sw",
                        struct=struct))
    return rows


def request_text(I, render):
    parts = [render(u) for u in sorted(I, key=str)]
    parts = [p for p in dict.fromkeys(parts) if p]
    if not parts:
        return ""
    if len(parts) > 6:
        parts = parts[:6] + [f"and {len(parts) - 6} more such changes"]
    return "; ".join(parts)


def pick_request(primary_groups, rng, sample=True):
    """primary_groups: {named root: set(units)} for ONE action. With probability 0.3 and at least two roots, a proper
    subset of its roots (the user asked for part of what the action names). Other actions' primary effects are always
    requested by the caller, so another action's effect is never counted as a side effect."""
    roots = sorted(primary_groups)
    if sample and len(roots) >= 2 and rng.random() < 0.3:
        k = rng.randint(1, len(roots) - 1)
        roots = rng.sample(roots, k)
    out = set()
    for r in roots:
        out |= primary_groups[r]
    return out


# ------------------------------------------------------------------ shell

def shell_effects(before, after):
    import shell as S
    E = set()
    for p in set(before) | set(after):
        a, b = before.get(p), after.get(p)
        if a and not b:
            E.add(("removed", p))
        elif b and not a:
            E.add(("added", p))
        elif a and b:
            if a["t"] != b["t"] or a.get("c") != b.get("c") or a.get("size") != b.get("size") or a.get("to") != b.get("to") \
                    or a.get("mode") != b.get("mode") or a.get("arch") != b.get("arch"):
                E.add(("changed", p))
    after_pool = S.pool(after)
    for p, e in before.items():
        if e["t"] == "f":
            lines = [ln for ln in ((e.get("c") or "").splitlines() + list(e.get("arch", []))) if ln.strip()]
            if any(ln not in after_pool for ln in lines):
                E.add(("lost", p))
    return E


def shell_compress_factory(before):
    def compress(I):
        dirs = {u[1] for u in I if u[0] == "removed" and before.get(u[1], {}).get("t") == "d"}
        removed = {u[1] for u in I if u[0] == "removed"}
        out = set()
        for u in I:
            if any(u[1].startswith(d + "/") for d in dirs):
                continue
            if u[0] == "lost" and u[1] in removed:
                continue
            out.add(("removed_dir", u[1]) if u[0] == "removed" and u[1] in dirs else u)
        return out
    return compress


def shell_render(u):
    if u[0] == "removed_dir":
        return f"{u[1]} is deleted with everything in it"
    k, p = u
    return {"removed": f"{p} is deleted", "added": f"{p} is created", "changed": f"{p} is changed",
            "lost": f"what {p} held before is lost for good"}[k]


def expand_braces(t):
    m = re.search(r"\{([^{}]*,[^{}]*)\}", t)
    if not m:
        return [t]
    out = []
    for alt in m.group(1).split(","):
        out += expand_braces(t[:m.start()] + alt + t[m.end():])
    return out


def shell_named(cmd, before, after):
    """Named roots of a command line: paths it names (relative to the folder a leading cd intends), globs expanded on
    the before-state, find -name patterns matched at any depth, redirect targets. Returns (roots, verbs)."""
    try:
        toks = shlex.split(cmd.replace(";", " ; ").replace("&&", " && ").replace("||", " || ").replace("|", " | "))
    except ValueError:
        return {}, set()
    cwd, roots, verbs = "", {}, set()
    allp = set(before) | set(after)
    start = True
    i = 0
    find_root = None
    while i < len(toks):
        t = toks[i]
        if t in (";", "&&", "||", "|"):
            start = True
            i += 1
            continue
        if start:
            verbs.add(t)
            if t == "cd" and i + 1 < len(toks):
                cwd = toks[i + 1].strip("/")
                i += 2
                start = False
                continue
            if t == "find" and i + 1 < len(toks):
                find_root = toks[i + 1]
            start = False
            i += 1
            continue
        if t in (">", ">>", ">|", "<") and i + 1 < len(toks):
            tgt = toks[i + 1]
            p = (cwd + "/" + tgt if cwd else tgt).strip("/")
            roots.setdefault(p, "redirect")
            i += 2
            continue
        if t in ("-name", "-path") and i + 1 < len(toks):
            pat = toks[i + 1]
            base = (cwd + "/" + find_root if cwd else find_root or ".").strip("/").lstrip("./") if find_root not in (None, ".", "./") else cwd
            for p in allp:
                if (not base or p.startswith(base + "/")) and fnmatch.fnmatch(os.path.basename(p) if t == "-name" else p, pat):
                    roots.setdefault(p, "find")
            i += 2
            continue
        if t.startswith("-"):
            i += 1
            continue
        for tt in expand_braces(t):
            p = (cwd + "/" + tt if cwd else tt).strip("/")
            if p.startswith("./"):
                p = p[2:]
            if any(ch in p for ch in "*?["):
                d = os.path.dirname(p)
                for q in allp:
                    if os.path.dirname(q) == d and fnmatch.fnmatch(q, p) and not os.path.basename(q).startswith("."):
                        roots.setdefault(q, "glob")
            elif p in allp or p in (".", ""):
                roots.setdefault(p or ".", "path")
        i += 1
    return roots, verbs


def in_scope(path, root):
    return root in (".", "") or path == root or path.startswith(root + "/")


HELD_SHELL = ("sh_text", "sh_perm")


def se_shell_items(seed, heldout=False):
    import shell as S
    import fx_shell_new as X
    import fx_registry as REG
    rng = random.Random(stable_seed("fx_side_shell_heldout" if heldout else "fx_side_shell", seed))
    if heldout:
        # Addendum 6: only the held-out shell families' trees and forms
        fam = rng.choice(list(HELD_SHELL))
        tree = X.gen_tree_fx(rng, fam)
        v = X.V(tree, rng)
        forms = [("X", n, f) for n, (fa, f) in X.FORMS.items() if fa == fam]
    else:
        # only train families' trees and forms: the held-out families (sh_text, sh_perm) and forms of no family stay out
        fam = rng.choice(["sh_write_modes", "sh_find_select", "sh_status_pipes", "sh_glob_brace", "sh_archive2"])
        tree = X.gen_tree_fx(rng, fam)
        v = X.V(tree, rng)
        core_train = set(sum((c[1] for k, c in REG.CORE.items() if c[0] == "shell" and k not in REG.HELD_OUT_FAMILIES), []))
        forms = [("F", n, f) for n, f in S.FORMS.items() if n in core_train] + \
                [("X", n, f) for n, (fa, f) in X.FORMS.items() if fa not in REG.HELD_OUT_FAMILIES]
    for _ in range(12):
        src, name, fn = rng.choice(forms)
        r = fn(v)
        if r:
            break
    else:
        return [], {"skipped": 1}
    cmd = r[0]
    if not S.valid(cmd):
        return [], {"invalid": 1}
    res = X.execute_fx(tree, [cmd], f"fxse{os.getpid()}_{seed}")
    if res is None:
        return [], {"exec_fail": 1}
    E = shell_effects(res["before"], res["after"])
    if not E:
        return [], {"no_effect": 1}
    roots, verbs = shell_named(cmd, res["before"], res["after"])
    deleting = bool(verbs & DELETE_VERBS) or "-delete" in cmd or re.search(r"-exec\s+rm|xargs\s+rm", cmd) is not None
    groups = {}
    for root in roots:
        g = set()
        for u in E:
            if in_scope(u[1], root):
                if u[0] == "lost" and not (deleting and roots[root] != "redirect"):
                    continue
                g.add(u)
        if g:
            groups[root] = g
    if not groups:
        return [], {"nothing_named_changed": 1}
    I = pick_request(groups, rng)
    layout = "full"
    floor = cmd_floor(S.RULES, X.render_fx(res["before"], layout), [cmd])
    what = "; ".join(f"line {k}: exit {c}" + (f" ({e})" if c and e else "") for k, (c, e) in
                     enumerate(zip(res["codes"], res["errs"]), 1)) + "."
    ceiling = cmd_ceiling(S.RULES, [cmd], X.render_fx(res["after"], "full"), what)
    before_paths = sorted(res["before"])
    distract = set()
    for p in rng.sample(before_paths, min(8, len(before_paths))):
        distract |= {("removed", p), ("changed", p)}
        if res["before"][p]["t"] == "f":
            distract.add(("lost", p))
    distract |= {("added", f"{os.path.splitext(p)[0]}.bak") for p in before_paths[:3]}
    rows = build_rows(world="rx_shell", family="shell", template=f"se:{name}", floor=floor, ceiling=ceiling, E=E, I=I,
                      render=shell_render, distract=distract, rng=rng, rid=f"fxse-sh{'ho' if heldout else ''}-{seed}",
                      struct={"cmds": [cmd], "E": sorted(map(list, E)), "I": sorted(map(list, I))}, what="command", steps=1,
                      compress=shell_compress_factory(res["before"]))
    return rows, {"scenarios": 1, "with_side_effect": int(bool(E - I))}


# ------------------------------------------------------------------ SQL

SQL_TARGET = re.compile(r"^\s*(?:DELETE\s+FROM|UPDATE(?:\s+OR\s+\w+)?|INSERT(?:\s+OR\s+\w+)?\s+INTO|REPLACE\s+INTO|ALTER\s+TABLE|"
                        r"DROP\s+TABLE(?:\s+IF\s+EXISTS)?)\s+(\w+)", re.I)


def sql_effects(before, after):
    E = set()
    tb, ta = before["tables"], after["tables"]
    for t in set(tb) | set(ta):
        if t in tb and t not in ta:
            E.add(("table_dropped", t, ""))
            continue
        if t in ta and t not in tb:
            E.add(("table_created", t, ""))
            continue
        cb, ca = tb[t]["cols"], ta[t]["cols"]
        rb = {str(r[0]): r for r in tb[t]["rows"]}
        ra = {str(r[0]): r for r in ta[t]["rows"]}
        for rid in rb.keys() - ra.keys():
            E.add(("deleted", t, rid))
        for rid in ra.keys() - rb.keys():
            E.add(("inserted", t, rid))
        for rid in rb.keys() & ra.keys():
            for j, c in enumerate(cb):
                if c in ca and str(rb[rid][j]) != str(ra[rid][ca.index(c)]):
                    E.add(("updated", t, f"{rid}:{c}"))
        if cb != ca:
            E.add(("columns_changed", t, ""))
    return E


def sql_render(u):
    k, t, x = u
    if k == "deleted":
        return f"the {t} row with id {x} is deleted"
    if k == "inserted":
        return f"a row with id {x} is added to {t}"
    if k == "updated":
        rid, c = x.split(":", 1)
        return f"{c} of the {t} row with id {rid} changes"
    return {"table_dropped": f"the table {t} is dropped", "table_created": f"the table {t} is created",
            "columns_changed": f"the columns of {t} change"}[k]


def sql_named(stmts, before):
    """{root: kind} where root is a table name, or table:id when the WHERE clause names ids."""
    roots = {}
    for st in stmts:
        m = SQL_TARGET.match(st)
        if not m:
            continue
        t = m.group(1)
        ids = re.findall(r"\bid\s*=\s*(\d+)", st, re.I)
        inl = re.search(r"\bid\s+IN\s*\(([\d,\s]+)\)", st, re.I)
        if inl:
            ids += [x.strip() for x in inl.group(1).split(",") if x.strip()]
        if ids and not re.match(r"\s*(INSERT|REPLACE)", st, re.I):
            for i in ids:
                roots[f"{t}:{i}"] = "row"
        else:
            roots[t] = "table"
    return roots


def sql_scope(u, root):
    if ":" in root:
        t, i = root.split(":", 1)
        return u[1] == t and (u[2] == i or u[2].startswith(i + ":"))
    return u[1] == root


def se_sql_items(seed, heldout=False):
    import sqlfam as SF
    import fx_sql_new as SN
    import fx_registry as REG
    rng = random.Random(stable_seed("fx_side_sql_heldout" if heldout else "fx_side_sql", seed))
    if not heldout and rng.random() < 0.6:
        s = SF.gen_db(rng)
        if rng.random() < 0.5:
            name = rng.choice(SF.TRAPS)
            SF.require(name, s, rng)
            name, stmts, tables, naive = SF.trap_form(name, s, rng)
        else:
            name, stmts, tables = rng.choice(SF.forms(s, rng))
        try:
            res = SF.run(s, stmts)
        except Exception:  # noqa: BLE001
            return [], {"build_fail": 1}
        floor = world_floor(SF.RULES, SF.render(s, res["before"]), stmts)
        ceiling = world_ceiling(SF.RULES, SF.render_after(res["after"]), "; ".join(
            f"statement {k}: {'ok' if r[0] == 'ok' else 'error (' + r[1] + ')'}" for k, r in enumerate(res["res"], 1)) + ".")
    else:
        if heldout:  # Addendum 6: only the held-out trigger templates
            name = rng.choice(sorted(n for n, (fa, _) in SN.T.items() if fa == "sql_triggers"))
        else:
            name = rng.choice(sorted(n for n, (fa, _) in SN.T.items() if fa not in REG.HELD_OUT_FAMILIES))  # no sql_triggers
        sp = SN.T[name][1](rng, rng.random() < 0.5)
        try:
            res = SN.run(sp)
        except Exception:  # noqa: BLE001
            return [], {"build_fail": 1}
        stmts = sp["stmts"]
        floor = world_floor(SN.RULES, SN.render(sp, res["before"]), stmts)
        ceiling = world_ceiling(SN.RULES, SN.render_after(res["after"]), "; ".join(
            f"statement {k}: {'ok' if r[0] == 'ok' else 'error (' + r[1] + ')'}" for k, r in enumerate(res["res"], 1)) + ".")
    E = sql_effects(res["before"], res["after"])
    if not E:
        return [], {"no_effect": 1}
    roots = sql_named(stmts, res["before"])
    groups = {}
    for root in roots:
        g = {u for u in E if sql_scope(u, root)}
        if g:
            groups[root] = g
    sample_ok = len(stmts) == 1
    # a statement on a whole table: its row units are the roots of a possible narrower request
    if len(groups) == 1 and ":" not in next(iter(groups)):
        only = next(iter(groups))
        rows_ = {}
        for u in groups[only]:
            key = u[2].split(":")[0]
            rows_.setdefault(f"{only}:{key}", set()).add(u)
        if len(rows_) >= 2:
            groups = rows_
    if not groups:
        return [], {"nothing_named_changed": 1}
    I = pick_request(groups, rng, sample=sample_ok)
    distract = set()
    for t, v in res["before"]["tables"].items():
        for r in v["rows"][:4]:
            distract.add(("deleted", t, str(r[0])))
            if len(v["cols"]) > 1:
                distract.add(("updated", t, f"{r[0]}:{v['cols'][-1]}"))
        distract.add(("inserted", t, str(len(v["rows"]) + 1)))
    rows = build_rows(world="rx_sql", family="sql", template=f"se:{name}", floor=floor, ceiling=ceiling, E=E, I=I,
                      render=sql_render, distract=distract, rng=rng, rid=f"fxse-sql{'ho' if heldout else ''}-{seed}",
                      struct={"stmts": stmts, "E": sorted(map(list, E)), "I": sorted(map(list, I))}, what="set of statements",
                      steps=len(stmts))
    return rows, {"scenarios": 1, "with_side_effect": int(bool(E - I))}


# ------------------------------------------------------------------ git

GIT_INTENT = {"reset_hard_prev": "move", "reset_keep": "move", "reset_merge": "move", "reset_soft": "move", "reset_mixed": "move",
              "reset_origin": "move", "reset_hard": "discard_all", "branch_D": "delete_branch", "checkout_file": "discard_file",
              "restore": "discard_file", "restore_all": "discard_all", "checkout_f": "switch", "switch_f": "switch",
              "switch": "switch", "checkout": "switch"}


def git_capture(G, FG, repo, box):
    work = G.tree_files(repo)
    rc, out = G.git_root(repo, "ls-files", "-s")
    index = {l.split("\t")[1]: l.split()[1] for l in out.splitlines() if "\t" in l}
    rc, rl = G.git_root(repo, "rev-list", "--branches", "--tags", "--remotes")
    commits = set(rl.split())
    rc, st = G.git_root(repo, "stash", "list")
    R = FG.refs(repo, box)
    flags = G.state_flags(repo)
    return {"work": work, "index": index, "commits": commits, "stash": len([l for l in st.splitlines() if l.strip()]),
            "refs": R, "head": flags[2]}


def git_effects(G, b, a, after_sets):
    E = set()
    for p in set(b["work"]) | set(a["work"]):
        x, y = b["work"].get(p), a["work"].get(p)
        if x and not y:
            E.add(("wt_removed", p))
        elif y and not x:
            E.add(("wt_added", p))
        elif x != y:
            E.add(("wt_changed", p))
    w1, i1, r1 = after_sets
    keep = w1 | i1 | r1
    for p in set(b["work"]) | set(b["index"]):
        for blob in {b["work"].get(p), b["index"].get(p)} - {None}:
            if blob not in keep:
                E.add(("lost", p))
    for br in set(b["refs"]["branches"]) - set(a["refs"]["branches"]):
        E.add(("branch_deleted", br))
    for br in set(b["refs"]["branches"]) & set(a["refs"]["branches"]):
        if b["refs"]["branches"][br]["commit"] != a["refs"]["branches"][br]["commit"]:
            E.add(("branch_moved", br))
    if b["head"] != a["head"]:
        E.add(("head", a["head"]))
    if b["commits"] - a["commits"]:
        E.add(("orphaned", "commit"))
    if a["stash"] < b["stash"]:
        E.add(("stash_dropped", ""))
    return E


def git_render(u):
    k, x = u
    return {"wt_removed": f"{x} is deleted from the working tree", "wt_added": f"{x} appears in the working tree",
            "wt_changed": f"{x} changes in the working tree", "lost": f"uncommitted work on {x} is lost for good",
            "branch_deleted": f"branch {x} is deleted", "branch_moved": f"branch {x} points to another commit",
            "head": f"the checked-out branch becomes {x}", "orphaned": "a commit is left on no branch or tag",
            "stash_dropped": "a stash entry is removed"}[k]


def se_git_items(seed):
    import gitfam as G
    import fx_git_new as FG
    import shutil
    from common import NOBODY, make_box, remove_box, run_unprivileged
    rng = random.Random(stable_seed("fx_side_git", seed))
    sp = G.gen_params(rng)
    sp["inprog"] = None
    C = [x for x in G.command_forms(sp, rng) if x[0] in GIT_INTENT]
    if not C:
        return [], {"skipped": 1}
    name, cmd = rng.choice(C)
    box = make_box(f"fxseg{os.getpid()}_{seed}")
    try:
        os.chown(box, NOBODY, NOBODY)
        os.makedirs(box + ".meta", exist_ok=True)
        os.chown(box + ".meta", NOBODY, NOBODY)
        open(box + ".meta/setup.sh", "w").write(G.setup_script(sp))
        rc, out, err = run_unprivileged(["bash", "--noprofile", "--norc", box + ".meta/setup.sh"], cwd=box,
                                        env_extra=G.GIT_ENV, timeout=30, cpu=20)
        repo = os.path.join(box, "repo")
        if rc != 0 or not os.path.isdir(repo):
            return [], {"exec_fail": 1}
        v = G.EG.inspect(repo, [cmd], facts=True)
        notes = G.P.git_notes([cmd], v.info)
        b = git_capture(G, FG, repo, box)
        codes, errs = G.run_cmds(box, [cmd])
        if codes is None:
            return [], {"exec_fail": 1}
        a = git_capture(G, FG, repo, box)
        sets = G.versions(box)
        E = git_effects(G, b, a, sets)
    finally:
        remove_box(box)
        shutil.rmtree(box + ".meta", ignore_errors=True)
    if not E:
        return [], {"no_effect": 1}
    intent = GIT_INTENT[name]
    cur = b["head"]
    toks = cmd.split()
    named_path = next((t for t in toks[2:] if t in b["work"] or t in b["index"]), None)
    target_branch = sp["branch"]
    groups = {}
    if intent == "move":
        groups["move"] = {u for u in E if u == ("branch_moved", cur)}
    elif intent == "discard_all":
        groups["all"] = {u for u in E if u[0] in ("wt_changed", "wt_removed", "wt_added", "lost")}
    elif intent == "delete_branch":
        groups["branch"] = {u for u in E if u == ("branch_deleted", target_branch)}
    elif intent == "discard_file" and named_path:
        groups["file"] = {u for u in E if u[1] == named_path and u[0] in ("wt_changed", "wt_removed", "lost")}
    elif intent == "switch":
        groups["switch"] = {u for u in E if u[0] in ("head", "wt_changed", "wt_removed", "wt_added")}
    groups = {k: g for k, g in groups.items() if g}
    if not groups:
        return [], {"nothing_named_changed": 1}
    I = pick_request(groups, rng)
    state = v.state + "\n" + FG.render_refs(b["refs"])
    floor = G.P.git_state(state, [cmd], notes=notes)
    ceiling = (f"{G.P.GIT_RULES}\n\nCommands that were run:\n{G.P.numbered([cmd])}\n\nState after the commands:\n"
               f"{FG.render_refs(a['refs'])}\nWhat happened: command 1: {'ok' if codes[0] == 0 else 'fails'}.")
    distract = {("lost", p) for p in list(b["work"])[:4]} | {("wt_removed", p) for p in list(b["work"])[:3]} | \
               {("branch_deleted", br) for br in b["refs"]["branches"]} | {("orphaned", "commit"), ("stash_dropped", "")}
    rows = build_rows(world="rx_git", family="git", template=f"se:{name}", floor=floor, ceiling=ceiling, E=E, I=I,
                      render=git_render, distract=distract, rng=rng, rid=f"fxse-git-{seed}",
                      struct={"params": sp, "cmds": [cmd], "E": sorted(map(list, E)), "I": sorted(map(list, I))},
                      what="command", steps=1)
    return rows, {"scenarios": 1, "with_side_effect": int(bool(E - I))}


# ------------------------------------------------------------------ apps (Vikunja train, Memos held out)

def vk_effects(S0, S1):
    E = set()
    for t in set(S0["tasks"]) | set(S1["tasks"]):
        a, b = S0["tasks"].get(t), S1["tasks"].get(t)
        if a and not b:
            E.add(("task_deleted", t))
        elif b and not a:
            E.add(("task_created", t))
        elif a and b:
            if a["done"] != b["done"]:
                E.add(("task_done", t))
            if a["due"] != b["due"]:
                E.add(("task_due", t))
            if a["bucket"] != b["bucket"]:
                E.add(("task_bucket", t))
            for l in set(a["labels"]) - set(b["labels"]):
                E.add(("label_removed", f"{t}|{l}"))
    for p in set(S0["projects"]) | set(S1["projects"]):
        a, b = S0["projects"].get(p), S1["projects"].get(p)
        if a and not b:
            E.add(("project_deleted", p))
        elif a and b and a["archived"] != b["archived"]:
            E.add(("project_archived", p))
    for k in set(S0["can_see"]) | set(S1["can_see"]):
        if S0["can_see"].get(k) != S1["can_see"].get(k):
            E.add(("access", f"{k[0]}|{k[1]}"))
    return E


def vk_render(u):
    k, x = u
    if k == "label_removed":
        t, l = x.split("|")
        return f"task '{t}' loses the label '{l}'"
    if k == "access":
        w, p = x.split("|")
        return f"{w}'s access to project '{p}' changes"
    return {"task_deleted": f"task '{x}' is deleted", "task_created": f"a task '{x}' is created",
            "task_done": f"task '{x}' changes between done and not done", "task_due": f"the due date of task '{x}' changes",
            "task_bucket": f"task '{x}' moves to another Kanban bucket", "project_deleted": f"project '{x}' is deleted",
            "project_archived": f"project '{x}' is archived or unarchived"}[k]


def vk_primary(a, S0, E):
    k = a[0]
    if k in ("done", "done_as"):
        t = a[1] if k == "done" else a[2]
        return {u for u in E if u == ("task_done", t)}
    if k in ("add", "add_as"):
        t = a[2] if k == "add" else a[3]
        return {u for u in E if u == ("task_created", t)}
    if k == "delete_project":
        p = a[1]
        return {u for u in E if u == ("project_deleted", p) or (u[0] == "task_deleted" and S0["tasks"].get(u[1], {}).get("project") == p)}
    if k == "archive":
        return {u for u in E if u == ("project_archived", a[1])}
    if k == "move":
        return {u for u in E if u == ("task_bucket", a[2])}
    if k == "delete_label":
        return {u for u in E if u[0] == "label_removed" and u[1].endswith("|" + a[1])
                and S0["tasks"].get(u[1].split("|")[0], {}).get("project") == next(iter(S0["projects"]))}
    return set()


def mm_effects(S0, S1):
    E = set()
    for m in set(S0["memos"]) | set(S1["memos"]):
        a, b = S0["memos"].get(m), S1["memos"].get(m)
        if a and not b:
            E.add(("memo_deleted", m))
        elif a and b:
            if a["vis"] != b["vis"]:
                E.add(("visibility", m))
            if a["state"] != b["state"]:
                E.add(("archived", m))
            if a["pinned"] != b["pinned"]:
                E.add(("pinned", m))
    for k in set(S0["seen"]) | set(S1["seen"]):
        if S0["seen"].get(k) != S1["seen"].get(k):
            E.add(("access", f"{k[0]}|{k[1]}"))
    for c in set(S0["comments"]) | set(S1["comments"]):
        a, b = S0["comments"].get(c), S1["comments"].get(c)
        if (a or {}).get("exists") != (b or {}).get("exists"):
            E.add(("comment", c))
    return E


def mm_render(u):
    k, x = u
    if k == "access":
        w, m = x.split("|")
        return f"{w}'s access to memo {m} changes"
    return {"memo_deleted": f"memo {x} is deleted", "visibility": f"the visibility of memo {x} changes",
            "archived": f"memo {x} moves into or out of the archive", "pinned": f"memo {x} is pinned or unpinned",
            "comment": f"comment {x} appears or disappears"}[k]


def mm_primary(a, S0, E):
    k = a[0]
    if k == "vis":
        return {u for u in E if u == ("visibility", a[1]) or (u[0] == "access" and u[1].endswith("|" + a[1]))}
    if k == "state":
        return {u for u in E if u == ("archived", a[1])}
    if k == "delete":
        return {u for u in E if u == ("memo_deleted", a[1]) or (u[0] == "access" and u[1].endswith("|" + a[1]))}
    if k in ("comment", "comment_vis"):
        return {u for u in E if u == ("comment", a[3])}
    return set()


def se_app_items(seed, app):
    import fx_apps as A
    rng = random.Random(stable_seed("fx_side_app", app, seed))
    fam = rng.choice(["vk_tasks_repeat_done", "vk_projects_archive_delete", "vk_labels_buckets"] if app == "vk"
                     else ["mm_visibility", "mm_archive_delete", "mm_comments"])
    st = rng.getstate()
    try:
        side = A.run_side(fam, st, rng.random() < 0.5)
    except A.InfraError as e:
        return [], {"infra_drop": 1, "last_error": str(e)[:120]}
    except Exception as e:  # noqa: BLE001
        return [], {"app_fail": 1, "last_error": f"{type(e).__name__}: {e}"[:120]}
    acts = [a[1] for a in side["acts"] if a[1][0] != "noop"]
    if not acts:
        return [], {"no_action": 1}
    E = (vk_effects if app == "vk" else mm_effects)(side["S0"], side["S1"])
    if not E:
        return [], {"no_effect": 1}
    prim = vk_primary if app == "vk" else mm_primary
    groups = {}
    for i, a in enumerate(acts):
        g = prim(a, side["S0"], E)
        if g:
            groups[f"a{i}"] = g
    if not groups:
        return [], {"nothing_named_changed": 1}
    I = pick_request(groups, rng, sample=False)
    rules = A.VK_RULES if app == "vk" else A.MM_RULES
    floor = world_floor(rules, side["state"], [a[0] for a in side["acts"]])
    ceiling = world_ceiling(rules, side["after"], "; ".join(f"action {k}: {'ok' if c < 400 else 'refused'}"
                                                          for k, c in enumerate(side["codes"], 1)) + ".")
    render = vk_render if app == "vk" else mm_render
    if app == "vk":
        distract = {("task_deleted", t) for t in side["S0"]["tasks"]} | {("task_due", t) for t in side["S0"]["tasks"]} | \
                   {("project_archived", p) for p in side["S0"]["projects"]} | {("task_bucket", t) for t in side["S0"]["tasks"]}
    else:
        distract = {("memo_deleted", m) for m in side["S0"]["memos"]} | {("pinned", m) for m in side["S0"]["memos"]} | \
                   {("access", f"Ben|{m}") for m in side["S0"]["memos"]}
    rows = build_rows(world="app_vikunja" if app == "vk" else "app_memos", family="app", template=f"se:{fam}", floor=floor,
                      ceiling=ceiling, E=E, I=I, render=render, distract=distract, rng=rng, rid=f"fxse-{app}-{seed}",
                      struct={"actions": [list(a) for a in acts], "E": sorted(map(list, E)), "I": sorted(map(list, I))},
                      what="set of actions", steps=len(side["acts"]))
    return rows, {"scenarios": 1, "with_side_effect": int(bool(E - I))}


def make_items(seed, allowed=None):
    fam = (allowed or ["se_shell"])[0]
    if fam == "se_shell":
        return se_shell_items(seed)
    if fam == "se_sql":
        return se_sql_items(seed)
    if fam == "se_shell_heldout":
        return se_shell_items(seed, heldout=True)
    if fam == "se_sql_heldout":
        return se_sql_items(seed, heldout=True)
    if fam == "se_git":
        return se_git_items(seed)
    if fam == "se_vikunja":
        return se_app_items(seed, "vk")
    if fam == "mm_side_effects":
        return se_app_items(seed, "mm")
    return [], {"skipped": 1}


FAMILY_FORMS = {"se_shell": ["se_shell"], "se_sql": ["se_sql"], "se_git": ["se_git"], "se_vikunja": ["se_vikunja"],
                "mm_side_effects": ["mm_side_effects"], "se_shell_heldout": ["se_shell_heldout"],
                "se_sql_heldout": ["se_sql_heldout"]}
