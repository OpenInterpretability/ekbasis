"""Confirmation scenarios for the shell guard: 28 command forms that are NOT among shell_wild's 84, a new seed and new
names, each with variants where the truth flips. Generated only after the client is frozen (eval/freeze.py), on Linux:
every scenario is built for real twice in throwaway folders and its truth is read from running bash (shell_wild's own
builder and runner; questions whose truth differs between the two runs are dropped).
python3 eval/shell_confirm_gen.py -> results/shell_confirm_items.jsonl"""
from __future__ import annotations

import json
import os
import random
import shutil
import sys

from common import OUT, VENDOR, require_frozen

require_frozen()
sys.path.insert(0, os.path.join(VENDOR, "shell_wild"))
import shell_wild as SW  # noqa: E402

SW.BOXES = os.path.join(OUT, "confirm_boxes")
SEED = 77012503
FILES = ["journal.md", "roadmap.md", "invoice.csv", "contacts.csv", "memo.txt", "outline.md", "metrics.csv",
         "changelog.md", "story.md", "recipes.txt"]
DIRS = ["vault", "inbox", "export", "keep", "media", "stash", "attic", "shelf", "depot", "cabinet"]
DISTRACT = ["NOTICE", "Dockerfile", "go.mod", "Cargo.toml", "pyproject.toml"]
PH = ["roadmap for the api team", "invoice 4410 for the photo shoot", "contacts for the conference", "metrics of the sign-up flow",
      "story idea about a lighthouse", "recipe: bread with olives", "minutes of the board call", "todo: renew the certificate",
      "draft of the press release", "plan for the garden beds", "notes on the vendor contract", "list of open support tickets"]
F, D, L, A, V = SW.F, SW.D, SW.L, SW.A, SW.V


def c(r):
    return SW.c(r, r.choice(PH))


def lines(r, k):
    return "\n".join(c(r) for _ in range(k))


# ---------------------------------------------------------------- families (the first variant is the typical one)

def fam_head_tmp(r):
    f = r.choice(FILES)
    x = lines(r, 4)
    cmd = f"head -n 2 {f} > {f}.tmp && mv {f}.tmp {f}"
    return [V("head -n N FILE > FILE.tmp && mv", {f: F(x)}, [cmd], [f], note="drops lines"),
            V("cp FILE FILE.orig && head ... && mv", {f: F(x)}, [f"cp {f} {f}.orig && {cmd}"], [f], note="backup first"),
            V("head -n N FILE > FILE.tmp && mv", {f: F(x)}, [f"head -n 9 {f} > {f}.tmp && mv {f}.tmp {f}"], [f], note="keeps every line")]


def fam_tr_self(r):
    f, g = r.sample(FILES, 2)
    return [V("tr < FILE > FILE", {f: F(c(r))}, [f"tr a-z A-Z < {f} > {f}"], [f], note="same file"),
            V("tr < FILE > OTHER", {f: F(c(r))}, [f"tr a-z A-Z < {f} > {g}"], [f, g], note="new file"),
            V("tr < FILE > OTHER", {f: F(c(r)), g: F(c(r))}, [f"tr a-z A-Z < {f} > {g}"], [f, g], note="other file exists")]


def fam_uniq_self(r):
    f = r.choice(FILES)
    x = c(r)
    return [V("uniq FILE > FILE", {f: F(x + "\n" + x)}, [f"uniq {f} > {f}"], [f], note="same file"),
            V("uniq FILE > FILE.u", {f: F(x + "\n" + x)}, [f"uniq {f} > {f}.u"], [f], note="other file")]


def fam_cat_two(r):
    a, b, o = r.sample(FILES, 3)
    return [V("cat A B > A", {a: F(c(r)), b: F(c(r))}, [f"cat {a} {b} > {a}"], [a], note="output is the first input"),
            V("cat A B > C", {a: F(c(r)), b: F(c(r))}, [f"cat {a} {b} > {o}"], [a, o], note="a new file")]


def fam_awk_self(r):
    f, g = r.sample(FILES, 2)
    x = lines(r, 3)
    return [V("awk 'NR<3' FILE > FILE", {f: F(x)}, [f"awk 'NR<3' {f} > {f}"], [f], note="same file"),
            V("awk 'NR<3' FILE > OTHER", {f: F(x)}, [f"awk 'NR<3' {f} > {g}"], [f, g], note="other file")]


def fam_mv_t(r):
    a, b = r.sample(FILES, 2)
    d = r.choice(DIRS)
    return [V("mv -t DIR A B", {a: F(c(r)), b: F(c(r)), d: D()}, [f"mv -t {d} {a} {b}"], [a, f"{d}/{a}"], note="the folder exists"),
            V("mv -t DIR A B", {a: F(c(r)), b: F(c(r))}, [f"mv -t {d} {a} {b}"], [a, f"{d}/{a}"], note="no folder"),
            V("mv -t DIR A B", {a: F(c(r)), b: F(c(r)), f"{d}/{a}": F(c(r))}, [f"mv -t {d} {a} {b}"], [a, f"{d}/{a}"],
              note="the folder has a same-named file")]


def fam_cp_t(r):
    a = r.choice(FILES)
    d = r.choice(DIRS)
    return [V("cp -t DIR FILE", {a: F(c(r)), f"{d}/{a}": F(c(r))}, [f"cp -t {d} {a}"], [f"{d}/{a}"], note="same-named file inside"),
            V("cp -t DIR FILE", {a: F(c(r)), d: D()}, [f"cp -t {d} {a}"], [f"{d}/{a}"], note="no collision")]


def fam_ln_hard(r):
    a, b = r.sample(FILES, 2)
    k = r.choice(DIRS)
    xb = c(r)
    return [V("ln -f A B", {a: F(c(r)), b: F(xb)}, [f"ln -f {a} {b}"], [a, b], note="replaces B"),
            V("ln A B", {a: F(c(r)), b: F(xb)}, [f"ln {a} {b}"], [a, b], note="B exists, no -f"),
            V("ln -f A B", {a: F(c(r)), b: F(xb), f"{k}/{b}": F(xb)}, [f"ln -f {a} {b}"], [a, b], note="B is backed up")]


def fam_dd(r):
    a, b = r.sample(FILES, 2)
    return [V("dd if=A of=B", {a: F(c(r)), b: F(c(r))}, [f"dd if={a} of={b} status=none"], [b], note="B exists"),
            V("dd if=A of=B", {a: F(c(r))}, [f"dd if={a} of={b} status=none"], [b], note="B is new")]


def fam_truncate_size(r):
    f = r.choice(FILES)
    return [V("truncate -s N FILE", {f: F(c(r))}, [f"truncate -s 5 {f}"], [f], note="shrinks"),
            V("truncate -s +N FILE", {f: F(c(r))}, [f"truncate -s +5 {f}"], [f], note="grows")]


def fam_shred_keep(r):
    f = r.choice(FILES)
    k = r.choice(DIRS)
    x = c(r)
    return [V("shred -n 1 FILE", {f: F(x)}, [f"shred -n 1 {f}"], [f], note="the only copy"),
            V("shred -n 1 FILE", {f: F(x), f"{k}/{f}": F(x)}, [f"shred -n 1 {f}"], [f], note="a copy elsewhere")]


def _trees(r):
    s, t = r.sample(DIRS, 2)
    f = r.choice(FILES)
    return s, t, f


def fam_rsync_remove(r):
    s, t, f = _trees(r)
    return [V("rsync -a --remove-source-files SRC/ DEST/", {f"{s}/{f}": F(c(r)), t: D()},
              [f"rsync -a --remove-source-files {s}/ {t}/"], [f"{s}/{f}", f"{t}/{f}"], note="no collision"),
            V("rsync -a --remove-source-files SRC/ DEST/", {f"{s}/{f}": F(c(r)), f"{t}/{f}": F(c(r))},
              [f"rsync -a --remove-source-files {s}/ {t}/"], [f"{s}/{f}", f"{t}/{f}"], note="a same-named file in DEST")]


def fam_rsync_exclude(r):
    s, t, f = _trees(r)
    k = r.choice(["keep.txt", "local.cfg", "notes.local"])
    base = {f"{s}/{f}": F(c(r)), f"{t}/{k}": F(c(r))}
    return [V("rsync -a --delete --exclude NAME SRC/ DEST/", dict(base), [f"rsync -a --delete --exclude {k} {s}/ {t}/"],
              [f"{t}/{k}"], note="the extra file is excluded"),
            V("rsync -a --delete --exclude NAME SRC/ DEST/", dict(base), [f"rsync -a --delete --exclude other.txt {s}/ {t}/"],
              [f"{t}/{k}"], note="another name is excluded")]


def fam_rsync_backup(r):
    s, t, f = _trees(r)
    st = {f"{s}/{f}": F(c(r)), f"{t}/{f}": F(c(r))}
    return [V("rsync -a --backup SRC/ DEST/", dict(st), [f"rsync -a --backup {s}/ {t}/"], [f"{t}/{f}", f"{t}/{f}~"], note="backup"),
            V("rsync -a SRC/ DEST/ (control)", dict(st), [f"rsync -a {s}/ {t}/"], [f"{t}/{f}", f"{t}/{f}~"], note="no backup")]


def fam_find_mv_collide(r):
    l1, l2 = r.sample(["app.log", "web.log", "db.log", "queue.log"], 2)
    a_, b_ = r.sample(["east", "west", "north", "south"], 2)
    cmd = 'find . -name "*.log" -exec mv {} archive/ \\;'
    return [V("find -exec mv {} DIR/", {f"{a_}/{l1}": F(c(r)), f"{b_}/{l1}": F(c(r)), "archive": D()}, [cmd],
              [f"archive/{l1}"], note="two logs with the same name"),
            V("find -exec mv {} DIR/", {f"{a_}/{l1}": F(c(r)), f"{b_}/{l2}": F(c(r)), "archive": D()}, [cmd],
              [f"archive/{l1}", f"archive/{l2}"], note="different names")]


def fam_find_mindepth(r):
    d = r.choice(DIRS)
    a, b = r.sample(FILES, 2)
    return [V("find DIR -mindepth 1 -delete", {f"{d}/{a}": F(c(r)), f"{d}/x.tmp": F("")}, [f"find {d} -mindepth 1 -delete"],
              [d, f"{d}/{a}"], note="empties the folder"),
            V("find DIR -mindepth 1 -name *.tmp -delete", {f"{d}/{a}": F(c(r)), f"{d}/x.tmp": F("")},
              [f'find {d} -mindepth 1 -name "*.tmp" -delete'], [d, f"{d}/{a}"], note="only empty .tmp files")]


def fam_tar_skip(r):
    f = r.choice(FILES)
    arch = r.choice(["backup.tgz", "old.tgz", "snap.tgz"])
    st = {f: F(c(r), 1), arch: A({f: c(r)}, 30)}
    return [V("tar --skip-old-files -xzf", dict(st), [f"tar --skip-old-files -xzf {arch}"], [f], f, note="keeps the newer file"),
            V("tar -xzf (control)", dict(st), [f"tar -xzf {arch}"], [f], f, note="replaces it")]


def fam_tar_overwrite(r):
    d = r.choice(DIRS)
    f = r.choice(FILES)
    out = r.choice(["out.tgz", "bundle.tgz", "pack.tgz"])
    return [V("tar czf EXISTING.tgz DIR", {f"{d}/{f}": F(c(r)), out: A({"old.txt": c(r)})}, [f"tar czf {out} {d}"], [out],
              note="the archive held other content"),
            V("tar czf NEW.tgz DIR", {f"{d}/{f}": F(c(r))}, [f"tar czf {out} {d}"], [out], note="new archive")]


def fam_perl_pi(r):
    f = r.choice(FILES)
    x = SW.c(r, "mode staging for the api")
    return [V("perl -pi -e s///", {f: F(x)}, [f"perl -pi -e 's/staging/live/' {f}"], [f], note="in place"),
            V("perl -pi.bak -e s///", {f: F(x)}, [f"perl -pi.bak -e 's/staging/live/' {f}"], [f, f + ".bak"], note="with a backup"),
            V("perl -pi -e s///", {f: F(x)}, [f"perl -pi -e 's/absent/live/' {f}"], [f], note="no line matches")]


def fam_xargs_I(r):
    d = r.choice(DIRS)
    n1, n2 = f"old {r.choice(FILES)}", f"new {r.choice(FILES)}"
    st = {n1: F(c(r)), n2: F(c(r)), "list.txt": F(f"{n1}\n{n2}"), d: D()}
    return [V("xargs -I{} mv {} DIR/ < LIST", dict(st), [f"xargs -I{{}} mv {{}} {d}/ < list.txt"], [n1, f"{d}/{n1}"], note="whole lines"),
            V("xargs mv -t DIR < LIST", dict(st), [f"xargs mv -t {d} < list.txt"], [n1, f"{d}/{n1}"], note="split at spaces")]


def fam_cp_a(r):
    s, t, f = _trees(r)
    return [V("cp -a SRC DEST", {f"{s}/{f}": F(c(r)), t: D()}, [f"cp -a {s} {t}"], [f"{t}/{s}/{f}"], note="DEST exists"),
            V("cp -a SRC DEST", {f"{s}/{f}": F(c(r)), f"{t}/{s}/{f}": F(c(r))}, [f"cp -a {s} {t}"], [f"{t}/{s}/{f}"],
              note="DEST/SRC has a same-named file")]


def fam_rm_dash(r):
    f = "-" + r.choice(FILES)
    return [V("rm -- -NAME", {f: F(c(r))}, [f"rm -- {f}"], [f], note="with --"),
            V("rm -NAME", {f: F(c(r))}, [f"rm {f}"], [f], note="read as options")]


def fam_heredoc(r):
    f = r.choice(FILES)
    body = SW.c(r, "status: all checks passed")
    return [V("cat <<EOF > FILE", {f: F(c(r))}, [f"cat <<'EOF' > {f}\n{body}\nEOF"], [f], note="overwrites"),
            V("cat <<EOF >> FILE", {f: F(c(r))}, [f"cat <<'EOF' >> {f}\n{body}\nEOF"], [f], note="appends"),
            V("cat <<EOF > FILE", {}, [f"cat <<'EOF' > {f}\n{body}\nEOF"], [f], note="new file")]


def fam_printf(r):
    f = r.choice(FILES)
    return [V("printf > FILE", {f: F(c(r))}, [f"printf '%s\\n' done > {f}"], [f], note="overwrites"),
            V("printf >> FILE", {f: F(c(r))}, [f"printf '%s\\n' done >> {f}"], [f], note="appends")]


def fam_colon(r):
    f = r.choice(FILES)
    return [V(": > FILE", {f: F(c(r))}, [f": > {f}"], [f], note="empties"),
            V(": >> FILE", {f: F(c(r))}, [f": >> {f}"], [f], note="leaves it")]


def fam_mv_then_rm(r):
    f = r.choice(FILES)
    d = r.choice(DIRS)
    return [V("mkdir -p D && mv F D/ && rm -rf D", {f: F(c(r))}, [f"mkdir -p {d} && mv {f} {d}/ && rm -rf {d}"], [f], note="moved"),
            V("mkdir -p D && cp F D/ && rm -rf D", {f: F(c(r))}, [f"mkdir -p {d} && cp {f} {d}/ && rm -rf {d}"], [f], note="copied")]


def fam_install(r):
    a, b = r.sample(FILES, 2)
    return [V("install -m 644 A B", {a: F(c(r)), b: F(c(r))}, [f"install -m 644 {a} {b}"], [b], note="B exists"),
            V("install -m 644 A B", {a: F(c(r))}, [f"install -m 644 {a} {b}"], [b], note="B is new")]


def fam_cp_glob_merge(r):
    s, t, f = _trees(r)
    g = r.choice([x for x in FILES if x != f])
    return [V("cp -r SRC/* DEST/", {f"{s}/{f}": F(c(r)), f"{t}/{f}": F(c(r))}, [f"cp -r {s}/* {t}/"], [f"{t}/{f}"], note="collision"),
            V("cp -r SRC/* DEST/", {f"{s}/{f}": F(c(r)), f"{t}/{g}": F(c(r))}, [f"cp -r {s}/* {t}/"], [f"{t}/{f}"], note="no collision")]


FAMILIES = [v for k, v in sorted(globals().items()) if k.startswith("fam_")]


def build_items():
    items = []
    for fam in FAMILIES:
        n_var = len(fam(random.Random(0)))
        for i in range(4 if n_var >= 3 else 5):
            r = random.Random(f"{SEED}-{fam.__name__}-{i}")
            variants = fam(r)
            dis = {name: F(c(r), r.randint(1, 9)) for name in r.sample(DISTRACT, 2)}
            gid = f"{fam.__name__[4:]}#{i}"
            for k, v in enumerate(variants):
                st = dict(v["state"])
                if v["dis"]:
                    for name, e in dis.items():
                        st.setdefault(name, e)
                for p, e in st.items():
                    if e["t"] == "f" and e.get("age") is None:
                        st[p] = dict(e, age=random.Random(f"{gid}-{p}").randint(1, 8))
                items.append({"id": f"{gid}/{k}", "group": gid, "family": fam.__name__[4:], "variant": k, "canonical": k == 0,
                              "form": v["form"], "note": v["note"], "state": st, "cmds": v["cmds"], "exists": v["exists"][:4],
                              "content": None})
    random.Random(SEED).shuffle(items)
    return items


def main():
    if os.uname().sysname != "Linux":
        sys.exit("generate on Linux: the truth comes from running bash with GNU coreutils")
    items = build_items()
    os.makedirs(SW.BOXES, exist_ok=True)
    out = []
    for n, it in enumerate(items):
        runs = []
        for rep in range(2):
            tag = f"{n:04d}_{rep}"
            run = SW.run_box(tag, it["state"], it["cmds"])
            runs.append((run, SW.truth_of(run, it)))
            shutil.rmtree(os.path.join(SW.BOXES, tag), ignore_errors=True)
        (r0, t0), (r1, t1) = runs
        it["truth"], it["dropped"] = t0, []
        if not (r0["complete"] and r1["complete"]):
            it["dropped"].append("incomplete run")
        if t0["lost"] != t1["lost"]:
            it["dropped"].append("lost")
        if t0["fails"] != t1["fails"]:
            it["dropped"].append("fails")
        it["lost_lines"], it["exit_codes"], it["stderr"] = r0["lost_lines"], r0["codes"], r0["stderr"]
        out.append(it)
    shutil.rmtree(SW.BOXES, ignore_errors=True)
    path = os.path.join(OUT, "shell_confirm_items.jsonl")
    with open(path, "w") as f:
        for it in out:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    print(f"{len(out)} scenarios, {len({i['group'] for i in out})} groups, {len({i['form'] for i in out})} forms, "
          f"{len(FAMILIES)} families; lost=yes {sum(i['truth']['lost'] for i in out)}; "
          f"{sum(1 for i in out if i['dropped'])} with a dropped question -> {path}")


if __name__ == "__main__":
    main()
