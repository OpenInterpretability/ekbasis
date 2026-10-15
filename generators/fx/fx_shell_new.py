"""WS-FX new shell families (SPEC.md + Addendum 1): sh_text, sh_status_pipes, sh_glob_brace, sh_perm, sh_find_select,
sh_write_modes, sh_archive2. Same machinery as WS-F's shell family (trees, unprivileged execution, snapshots, flip twins);
new command forms, multi-line files for text processing, and folder/file modes for sh_perm. Held-out families
(sh_text, sh_perm) avoid the templates WS-F trained on (no same-file redirection, no read permission on a file)."""
from __future__ import annotations

import json
import os
import random
import re
import shutil

import shell as S
from common import NOBODY, choice, cmd_ceiling, cmd_floor, make_box, remove_box, row, run_unprivileged, stable_seed, \
    yes_no

DEFAULT_FILE_MODE, DEFAULT_DIR_MODE = 0o644, 0o755


# ------------------------------------------------------------------ trees

def ml_lines(rng, n):
    lines = [S.content_line(rng) for _ in range(n)]
    if rng.random() < 0.5 and n >= 3:  # a repeated line, adjacent or not (uniq vs sort -u)
        i, j = rng.sample(range(n), 2)
        lines[j] = lines[i]
    return lines


def gen_tree_fx(rng, family):
    t = S.gen_tree(rng)
    tops = [p for p, e in t.items() if e["t"] == "f" and "/" not in p and not p.startswith(".") and " " not in p]
    if family in ("sh_text", "sh_find_select", "sh_write_modes", "sh_status_pipes"):
        for p in rng.sample(tops, min(len(tops), rng.randint(2, 3))):
            t[p] = dict(t[p], c="\n".join(ml_lines(rng, rng.randint(3, 6))))
    if family == "sh_text":
        nums = [str(rng.choice([rng.randint(1, 9), rng.randint(10, 99), rng.randint(100, 999)])) for _ in range(rng.randint(4, 6))]
        t[f"{rng.choice(S.FILE_WORDS)}_nums.txt"] = {"t": "f", "c": "\n".join(nums), "age": rng.randint(1, 30)}
    if family == "sh_perm":
        dirs = [p for p, e in t.items() if e["t"] == "d" and "/" not in p]
        if dirs and rng.random() < 0.6:
            d = rng.choice(dirs)
            t[d] = dict(t[d], mode=rng.choice([0o555, 0o500, 0o700, 0o311]))
    return t


def apply_modes(tree, box):
    for p, e in sorted(tree.items(), key=lambda kv: -kv[0].count("/")):
        if "mode" in e:
            os.chmod(os.path.join(box, p), e["mode"])


def snapshot_fx(box):
    snap = S.snapshot(box)
    for p, e in snap.items():
        full = os.path.join(box, p)
        if e["t"] == "d" and not os.path.islink(full):
            e["mode"] = os.stat(full).st_mode & 0o777
    return snap


def render_fx(snap, layout):
    base = S.render(snap, layout).splitlines()
    out = [base[0]]
    for line in base[1:]:
        m = re.match(r"- (.+?)(/)? — ", line)
        if m:
            p = m.group(1)
            e = snap.get(p)
            if e is not None:
                mode = e.get("mode")
                if e["t"] == "d" and mode is not None and mode != DEFAULT_DIR_MODE:
                    line += f" (permissions {mode:03o})"
                elif e["t"] == "f" and mode not in (None, DEFAULT_FILE_MODE, 0):
                    line += f" (permissions {mode:03o})"
        out.append(line)
    return "\n".join(out)


def execute_fx(tree, cmds, tag):
    """WS-F's execute(), plus folder/file modes applied after building and recorded in both snapshots."""
    box = make_box(tag)
    meta = box + ".meta"
    if os.path.isdir(meta):
        shutil.rmtree(meta, ignore_errors=True)
    os.makedirs(meta, exist_ok=True)
    try:
        S.build_box(tree, box)
        apply_modes(tree, box)
        os.chown(meta, NOBODY, NOBODY)
        lines = [f'cd "{box}" || exit 99']
        for k, c in enumerate(cmds, 1):
            lines += ["{ " + c, f'}} 2>"{meta}/{k}.err" </dev/null; echo $? > "{meta}/{k}.rc"']
        with open(os.path.join(meta, "run.sh"), "w") as f:
            f.write("\n".join(lines) + "\n")
        before = snapshot_fx(box)
        run_unprivileged(["bash", "--noprofile", "--norc", os.path.join(meta, "run.sh")], cwd=box)
        codes, errs = [], []
        for k in range(1, len(cmds) + 1):
            try:
                codes.append(int(open(os.path.join(meta, f"{k}.rc")).read().strip()))
                e = open(os.path.join(meta, f"{k}.err"), errors="replace").read().strip().splitlines()
                errs.append(re.sub(r"^\S*run\.sh: line \d+: ", "bash: ", e[0]).replace(box + "/", "").replace(box, ".")[:140]
                            if e else "")
            except Exception:  # noqa: BLE001
                return None
        after = snapshot_fx(box)
        return {"before": before, "after": after, "codes": codes, "errs": errs}
    finally:
        os.system(f"chmod -R u+rwx {box} 2>/dev/null")
        remove_box(box)
        shutil.rmtree(meta, ignore_errors=True)


# ------------------------------------------------------------------ forms

q = S.q


class V(S.View):
    def ml_files(self):
        return [p for p in self.top_files if "\n" in (self.t[p].get("c") or "")]

    def nums(self):
        return [p for p in self.top_files if p.endswith("_nums.txt")]

    def words_in(self, p):
        return sorted({ln.split("-")[0] for ln in (self.t[p].get("c") or "").splitlines() if ln})


FORMS = {}


def form(family, name):
    def deco(fn):
        FORMS[name] = (family, fn)
        return fn
    return deco


# sh_text: text tools writing into a new file (never back into their own input)
@form("sh_text", "sort_into")
def _(v):
    f = (v.ml_files() or v.top_files) and v.rng.choice(v.ml_files() or v.top_files)
    n = v.new_name("txt")
    return f and (f"sort {v.rng.choice(['', '-r ', '-u '])}{q(f)} > {n}".replace("  ", " "), [n, f])


@form("sh_text", "sort_numeric")
def _(v):
    f = v.nums() and v.rng.choice(v.nums())
    n = v.new_name("txt")
    return f and (f"sort {v.rng.choice(['', '-n ', '-rn ', '-r '])}{f} > {n}".replace("  ", " "), [n])


@form("sh_text", "sort_key")
def _(v):
    f = v.ml_files() and v.rng.choice(v.ml_files())
    n = v.new_name("txt")
    return f and (f"sort -k{v.rng.choice([1, 2])} {q(f)} > {n}", [n])


@form("sh_text", "uniq_into")
def _(v):
    f = v.ml_files() and v.rng.choice(v.ml_files())
    n = v.new_name("txt")
    return f and (f"uniq {v.rng.choice(['', '-c ', '-d '])}{q(f)} > {n}".replace("  ", " "), [n])


@form("sh_text", "cut_into")
def _(v):
    f = v.ml_files() and v.rng.choice(v.ml_files())
    n = v.new_name("txt")
    d, k = v.rng.choice([("' '", 1), ("' '", 2), ("-", 1), ("-", 2)])
    return f and (f"cut -d{d} -f{k} {q(f)} > {n}", [n])


@form("sh_text", "tr_into")
def _(v):
    f = (v.ml_files() or v.top_files) and v.rng.choice(v.ml_files() or v.top_files)
    n = v.new_name("txt")
    op = v.rng.choice(["a-z A-Z", "-d 0-9", "-s ' '", "'-' ' '"])
    return f and (f"tr {op} < {q(f)} > {n}", [n])


@form("sh_text", "head_tail_into")
def _(v):
    f = v.ml_files() and v.rng.choice(v.ml_files())
    n = v.new_name("txt")
    return f and (f"{v.rng.choice(['head', 'tail'])} -n {v.rng.randint(1, 3)} {q(f)} > {n}", [n])


@form("sh_text", "wc_into")
def _(v):
    f = (v.ml_files() or v.top_files) and v.rng.choice(v.ml_files() or v.top_files)
    n = v.new_name("txt")
    return f and (f"wc -{v.rng.choice(['l', 'w'])} < {q(f)} > {n}", [n])


@form("sh_text", "grep_into")
def _(v):
    f = v.ml_files() and v.rng.choice(v.ml_files())
    if not f:
        return None
    w = v.rng.choice(v.words_in(f) + [v.rng.choice(S.FILE_WORDS)])
    n = v.new_name("txt")
    return (f"grep {v.rng.choice(['', '-v ', '-c ', '-i '])}{w} {q(f)} > {n}".replace("  ", " "), [n])


@form("sh_text", "sort_o_inplace")
def _(v):
    f = v.ml_files() and v.rng.choice(v.ml_files())
    return f and (f"sort {v.rng.choice(['', '-u ', '-r '])}-o {q(f)} {q(f)}".replace("  ", " "), [f])


# sh_status_pipes: what && / || / ; and pipelines run and leave behind
@form("sh_status_pipes", "and_chain")
def _(v):
    f = S.F_one(v)
    d = v.rng.choice([v.new_dir()] + v.top_dirs)
    return f and (f"mkdir {d} && cp {q(f)} {d}/", [d, f"{d}/{f}"])


@form("sh_status_pipes", "or_chain")
def _(v):
    src = v.rng.choice([v.new_name(), S.F_one(v) or v.new_name()])
    n, n2 = v.new_name(), v.new_name("log")
    return (f"cp {q(src)} {n} || touch {n2}", [n, n2])


@form("sh_status_pipes", "semi_vs_and")
def _(v):
    n = v.new_name()
    first = v.rng.choice(["false", "true", f"ls {v.new_name()}", f"test -e {S.F_one(v) or 'x.txt'}"])
    return (f"{first} {v.rng.choice([';', '&&', '||'])} touch {n}", [n])


@form("sh_status_pipes", "pipe_missing_input")
def _(v):
    n = v.new_name("txt")
    src = v.rng.choice([v.new_name(), S.F_one(v) or v.new_name()])
    return (f"cat {q(src)} | sort > {n}", [n])


@form("sh_status_pipes", "grep_status")
def _(v):
    f = S.F_one(v)
    n, n2 = v.new_name("txt"), v.new_name("log")
    w = v.rng.choice(S.FILE_WORDS)
    return f and (f"grep {w} {q(f)} > {n} && touch {n2}", [n, n2])


@form("sh_status_pipes", "cd_and_rm")
def _(v):
    d = v.rng.choice(v.top_dirs + [v.new_dir()]) if v.top_dirs else v.new_dir()
    f = S.F_one(v)
    return f and (f"cd {d} && rm {q(f)}", [f, f"{d}/{f}"])


@form("sh_status_pipes", "subshell_cd")
def _(v):
    d = v.top_dirs and v.rng.choice(v.top_dirs)
    n = v.new_name()
    return d and (f"(cd {d} && touch {n}) ; touch {n}", [n, f"{d}/{n}"])


# sh_glob_brace: what globs and braces expand to
@form("sh_glob_brace", "cp_star_into")
def _(v):
    d = v.top_dirs and v.rng.choice(v.top_dirs)
    return d and (f"cp * {d}/", [d] + [f"{d}/{p}" for p in (v.hidden[:1] + v.top_files[:1])])


@form("sh_glob_brace", "mv_unmatched")
def _(v):
    d = v.top_dirs and v.rng.choice(v.top_dirs)
    e = v.missing_ext()
    return d and (f"mv *.{e} {d}/", [d, f"*.{e}"])


@form("sh_glob_brace", "brace_backup")
def _(v):
    f = v.top_files and v.rng.choice(v.top_files)
    op = v.rng.choice(["cp", "mv"])
    suf = v.rng.choice([".bak", ".old", "~orig"]).replace("~", "_")
    return f and (f"{op} {f}{{,{suf}}}", [f, f + suf])


@form("sh_glob_brace", "brace_seq")
def _(v):
    stem = v.rng.choice(S.FILE_WORDS)
    a, b = 1, v.rng.randint(2, 4)
    d = v.rng.choice(v.top_dirs) if v.top_dirs and v.rng.random() < 0.5 else None
    pre = f"{d}/" if d else ""
    seq = ",".join(str(i) for i in range(a, b + 1))
    return (f"touch {pre}{stem}{{{seq}}}.txt", [f"{pre}{stem}1.txt", f"{pre}{stem}{b}.txt"] + ([d] if d else []))


@form("sh_glob_brace", "brace_rm_two")
def _(v):
    if len(v.top_files) < 1:
        return None
    a = v.rng.choice(v.top_files)
    b = v.rng.choice([x for x in v.top_files if x != a] + [v.new_name()])
    return (f"rm {{{a},{b}}}", [a, b])


@form("sh_glob_brace", "glob_class")
def _(v):
    lo, hi = v.rng.choice([("a", "f"), ("g", "m"), ("n", "z"), ("a", "m")])
    e = v.rng.choice(v.exts) if v.exts else "txt"
    return (f"rm [{lo}-{hi}]*.{e}", [p for p in v.top_files if p.endswith("." + e)][:2] or [f"[{lo}-{hi}]*.{e}"])


@form("sh_glob_brace", "glob_question")
def _(v):
    e = v.rng.choice(v.exts) if v.exts else "txt"
    n = v.rng.randint(4, 8)
    return (f"rm {'?' * n}.{e}", [p for p in v.top_files if p.endswith("." + e)][:2] or [f"{'?' * n}.{e}"])


@form("sh_glob_brace", "quoted_glob")
def _(v):
    e = v.rng.choice(v.exts) if v.exts else "txt"
    return (f"rm '*.{e}'", [p for p in v.top_files if p.endswith("." + e)][:2] or [f"*.{e}"])


# sh_perm: folder write/search bits, mkdir -m, umask, chmod -R (never read permission on a file)
@form("sh_perm", "touch_in_readonly")
def _(v):
    ro = [p for p in v.top_dirs if v.t[p].get("mode") in (0o555, 0o500)]
    d = ro and v.rng.choice(ro)
    n = v.new_name()
    return d and (f"touch {d}/{n}", [f"{d}/{n}", d])


@form("sh_perm", "rm_in_readonly")
def _(v):
    ro = [p for p in v.top_dirs if v.t[p].get("mode") in (0o555, 0o500)]
    if not ro:
        return None
    d = v.rng.choice(ro)
    inside = [p for p in v.files if p.startswith(d + "/")]
    f = inside and v.rng.choice(inside)
    return f and (f"rm {v.rng.choice(['', '-f '])}{f}".replace("  ", " "), [f])


@form("sh_perm", "chmod_dir_then")
def _(v):
    d = v.top_dirs and v.rng.choice(v.top_dirs)
    if not d:
        return None
    bit = v.rng.choice(["a-w", "u-w", "a-x", "u+w", "u+rwx"])
    n = v.new_name()
    return (f"chmod {bit} {d} ; touch {d}/{n}", [f"{d}/{n}", d])


@form("sh_perm", "mkdir_mode")
def _(v):
    d = v.new_dir()
    m = v.rng.choice(["500", "700", "555", "300"])
    n = v.new_name()
    return (f"mkdir -m {m} {d} ; touch {d}/{n}", [d, f"{d}/{n}"])


@form("sh_perm", "umask_mkdir")
def _(v):
    d = v.new_dir()
    u = v.rng.choice(["022", "277", "077", "222"])
    n = v.new_name()
    return (f"umask {u} ; mkdir {d} ; touch {d}/{n}", [d, f"{d}/{n}"])


@form("sh_perm", "chmod_R_then_rm")
def _(v):
    d = v.top_dirs and v.rng.choice(v.top_dirs)
    return d and (f"chmod -R {v.rng.choice(['a-w', 'u-w'])} {d} ; rm -r{v.rng.choice(['', 'f'])} {d}", [d])


@form("sh_perm", "mv_out_of_readonly")
def _(v):
    ro = [p for p in v.top_dirs if v.t[p].get("mode") in (0o555, 0o500)]
    if not ro:
        return None
    d = v.rng.choice(ro)
    inside = [p for p in v.files if p.startswith(d + "/")]
    f = inside and v.rng.choice(inside)
    return f and (f"mv {f} {os.path.basename(f)}", [f, os.path.basename(f)])


# sh_find_select: find tests and actions
@form("sh_find_select", "find_maxdepth")
def _(v):
    e = v.rng.choice(v.exts) if v.exts else "txt"
    return (f"find . -maxdepth 1 -name '*.{e}' -delete", [p for p in v.files if p.endswith("." + e)][:2] or [f"x.{e}"])


@form("sh_find_select", "find_mindepth")
def _(v):
    e = v.rng.choice(S.EXTS)
    return (f"find . -mindepth 2 -type f -name '*.{e}' -delete", [p for p in v.files if p.endswith("." + e)][:2] or [f"x.{e}"])


@form("sh_find_select", "find_newer")
def _(v):
    f = v.top_files and v.rng.choice(v.top_files)
    return f and (f"find . -type f -newer {f} -delete", [p for p in v.files if p != f][:2] + [f])


@form("sh_find_select", "find_size")
def _(v):
    n = v.rng.choice([20, 30, 60, 100])
    return (f"find . -type f -size {v.rng.choice(['+', '-'])}{n}c -delete", v.files[:2])


@form("sh_find_select", "find_path_mv")
def _(v):
    d = v.top_dirs and v.rng.choice(v.top_dirs)
    nd = v.new_dir()
    e = v.rng.choice(S.EXTS)
    return d and (f"mkdir {nd} && find {d} -name '*.{e}' -exec mv {{}} {nd}/ \\;", [nd] + [p for p in v.files if p.startswith(d + "/")][:2])


@form("sh_find_select", "find_empty_dirs")
def _(v):
    return ("find . -mindepth 1 -type d -empty -delete", v.top_dirs[:2])


# sh_write_modes: how a write treats what was there
@form("sh_write_modes", "append_or_trunc")
def _(v):
    f = S.F_one(v)
    word = f"{v.rng.choice(S.FILE_WORDS)}-{v.rng.randint(1000, 9999)}"
    return f and (f"echo '{word}' {v.rng.choice(['>', '>>'])} {q(f)}", [f])


@form("sh_write_modes", "noclobber")
def _(v):
    f = v.rng.choice([S.F_one(v) or v.new_name(), v.new_name()])
    word = f"{v.rng.choice(S.FILE_WORDS)}-{v.rng.randint(1000, 9999)}"
    op = v.rng.choice([">", ">|", ">>"])
    return (f"set -C ; echo '{word}' {op} {q(f)}", [f])


@form("sh_write_modes", "tee_mode")
def _(v):
    f = v.rng.choice([S.F_one(v) or v.new_name(), v.new_name()])
    word = f"{v.rng.choice(S.FILE_WORDS)}-{v.rng.randint(1000, 9999)}"
    return (f"echo '{word}' | tee {v.rng.choice(['', '-a '])}{q(f)}".replace("  ", " "), [f])


@form("sh_write_modes", "printf_lines")
def _(v):
    f = v.rng.choice([S.F_one(v) or v.new_name(), v.new_name()])
    a, b = v.rng.sample(S.FILE_WORDS, 2)
    return (f"printf '{a}\\n{b}\\n' {v.rng.choice(['>', '>>'])} {q(f)}", [f])


@form("sh_write_modes", "truncate_size")
def _(v):
    f = S.F_one(v)
    return f and (f"truncate -s {v.rng.choice(['0', '5', '+3'])} {q(f)}", [f])


@form("sh_write_modes", "colon_trunc")
def _(v):
    f = S.F_one(v)
    return f and (f": > {q(f)}", [f])


# sh_archive2: archives that move or keep what they pack
@form("sh_archive2", "tar_remove_files")
def _(v):
    d = v.top_dirs and v.rng.choice(v.top_dirs)
    n = f"{v.rng.choice(S.FILE_WORDS)}_{v.rng.randint(2, 99)}.tgz"
    return d and (f"tar czf {n} {d} {v.rng.choice(['--remove-files', ''])}".strip(), [d, n])


@form("sh_archive2", "tar_extract_C")
def _(v):
    a = v.archives and v.rng.choice(v.archives)
    if not a:
        return None
    d = v.rng.choice(v.top_dirs + [v.new_dir()]) if v.top_dirs else v.new_dir()
    return (f"tar xzf {a} -C {d}", [d])


@form("sh_archive2", "gzip_keep")
def _(v):
    f = v.top_files and v.rng.choice(v.top_files)
    return f and (f"gzip {v.rng.choice(['-k ', '', '-f '])}{f}".replace("  ", " "), [f, f + ".gz"])


@form("sh_archive2", "tar_partial")
def _(v):
    f = v.top_files and v.rng.choice(v.top_files)
    n = f"{v.rng.choice(S.FILE_WORDS)}_{v.rng.randint(2, 99)}.tgz"
    return f and (f"tar czf {n} {f} {v.new_name()}", [n, f])


@form("sh_archive2", "tar_list_into")
def _(v):
    a = v.archives and v.rng.choice(v.archives)
    n = v.new_name("txt")
    return a and (f"tar tzf {a} > {n}", [n])


@form("sh_archive2", "gunzip_existing")
def _(v):
    f = v.top_files and v.rng.choice(v.top_files)
    return f and (f"gzip -k {f} ; gzip -d {v.rng.choice(['', '-f '])}{f}.gz".replace("  ", " "), [f, f + ".gz"])


FAMILIES = sorted({fam for fam, _ in FORMS.values()})
FAMILY_FORMS = {fam: sorted(n for n, (f, _) in FORMS.items() if f == fam) for fam in FAMILIES}


# ------------------------------------------------------------------ perturbations (flip twins)

def perturb_fx(tree, cmds, rng, family):
    if family == "sh_perm" and rng.random() < 0.6:
        t = json.loads(json.dumps(tree))
        dirs = [p for p, e in t.items() if e["t"] == "d" and "/" not in p]
        if dirs:
            d = rng.choice([p for p in dirs if any(p in c for c in cmds)] or dirs)
            cur = t[d].get("mode", DEFAULT_DIR_MODE)
            t[d]["mode"] = DEFAULT_DIR_MODE if cur != DEFAULT_DIR_MODE else rng.choice([0o555, 0o500])
            return t, "toggle_dir_mode"
    if family == "sh_text" and rng.random() < 0.5:
        t = json.loads(json.dumps(tree))
        fs = [p for p, e in t.items() if e["t"] == "f" and "\n" in e.get("c", "") and any(p in c for c in cmds)]
        if fs:
            p = rng.choice(fs)
            lines = t[p]["c"].splitlines()
            rng.shuffle(lines)
            if rng.random() < 0.5:
                lines.append(lines[0])
            t[p]["c"] = "\n".join(lines)
            return t, "reorder_lines"
    return S.perturb(tree, cmds, rng)


# ------------------------------------------------------------------ items

def content_options(p, res, twin_res, cmds):
    """WS-F's options (this path before/after, in both twins; quoted strings) plus, for an output file that did not
    exist before, the content of the input files the command line names (the 'nothing happened to the text' reading)."""
    qd = S.content_question(p, res, twin_res, cmds)
    if res["before"].get(p) is None:
        toks = re.split(r"[\s;|&<>()]+", " ".join(cmds))
        for tok in toks:
            tok = tok.strip("'\"")
            if tok and tok != p and res["before"].get(tok, {}).get("t") == "f":
                c = S.content_of(res["before"], tok)
                if c and c not in qd["criteria"] and len(qd["criteria"]) < 7:
                    qd["criteria"][c] = c
    return qd


def make_items(seed, allowed=None):
    """allowed: the forms of one family (fx_new_registry). One base scenario and its flip twin when one is found."""
    names = sorted(n for n in FORMS if allowed is None or n in allowed)
    if not names:
        return [], {"skipped": 1}
    family = FORMS[names[0]][0]
    rng = random.Random(stable_seed("fx_shell", family, seed))
    tree = gen_tree_fx(rng, family)
    v = V(tree, rng)
    for _ in range(12):
        name = rng.choice(names)
        r = FORMS[name][1](v)
        if r:
            break
    else:
        return [], {"skipped": 1}
    cmds, probes = [r[0]], list(r[1])
    if rng.random() < 0.3:
        n2 = rng.choice(names)
        r2 = FORMS[n2][1](v)
        if r2 and r2[0] != cmds[0]:
            cmds.append(r2[0])
            probes += list(r2[1])
    if not all(S.valid(c) for c in cmds):
        return [], {"invalid": 1}
    tag = f"fx{os.getpid()}_{seed}"
    res = execute_fx(tree, cmds, tag)
    if res is None:
        return [], {"exec_fail": 1}
    layout = "full" if (family in ("sh_text", "sh_write_modes") or rng.random() < 0.4) else "listing"
    qs = S.scenario_questions(rng, cmds, probes, res, layout)
    if family in ("sh_text", "sh_write_modes", "sh_archive2", "sh_status_pipes"):
        # the content question goes to the file the command writes (the first probe of every form of these families)
        outs = [p for p in dict.fromkeys(probes) if p and "*" not in p and (res["after"].get(p, {}).get("t") == "f"
                                                                             or res["before"].get(p, {}).get("t") == "f")]
        qs = [x for x in qs if x[0] != "content"]
        if outs:
            qs.append(("content", outs[0], None))
    twin = None
    for _ in range(6):
        pt = perturb_fx(tree, cmds, rng, family)
        if not pt:
            continue
        t2, op = pt
        r2 = execute_fx(t2, cmds, tag + "t")
        if r2 is None:
            continue
        if S.golds(qs, r2) != S.golds(qs, res):
            twin = (t2, r2, op)
            break
    instances = [("a", tree, res)] + ([("b", twin[0], twin[1])] if twin else [])
    rows = []
    for side, t_, res_ in instances:
        g = S.golds(qs, res_)
        g0 = S.golds(qs, {"before": res_["before"], "after": res_["before"], "codes": [0] * len(cmds)})
        floor = cmd_floor(S.RULES, render_fx(res_["before"], layout), cmds)
        what = "; ".join(f"line {k}: exit {c}" + (f" ({e})" if c and e else "")
                         for k, (c, e) in enumerate(zip(res_["codes"], res_["errs"]), 1))
        what += f". File content lost for good: {'yes' if g[('lost', None)] else 'no'}."
        ceiling = cmd_ceiling(S.RULES, cmds, render_fx(res_["after"], "full"), what)
        for qt, arg, qd in qs:
            gold = g[(qt, arg)]
            if qt == "content":
                if gold is None:
                    continue
                qd = content_options(arg, res, twin[1] if twin else None, cmds)
                if gold not in qd["criteria"]:
                    qd["criteria"][gold] = gold
                if len(qd["criteria"]) < 2:
                    continue
            elif qt == "count":
                if gold is None:
                    continue
                qd = S.count_question(arg, res, twin[1] if twin else None)
                if str(gold) not in qd["criteria"]:
                    qd["criteria"][str(gold)] = str(gold)
            known0 = qt in ("exists", "kind", "content", "count") and g0.get((qt, arg)) is not None
            if known0 and qd["type"] == "choice" and str(g0.get((qt, arg))) not in qd["criteria"]:
                known0 = False
            fv = S.face(cmds, qt, arg, res_["before"])
            rid = f"fxsh-{seed}-{side}-{qt}{'' if arg is None else '-' + re.sub(r'[^A-Za-z0-9]', '_', str(arg))}"
            rows.append(row(world="rx_shell", family="shell", template=name + ("+" if len(cmds) > 1 else ""),
                            qtype=qt if not qt.startswith("fails") else "fails", steps=len(cmds), question=qd,
                            gold=gold, gold0=(g0.get((qt, arg)) if known0 else None), known0=known0, floor=floor,
                            ceiling=ceiling, rid=rid, twin=(f"fxsh-{seed}-{'b' if side == 'a' else 'a'}" if twin else None),
                            layout=layout, face=fv,
                            struct={"tree": t_, "cmds": cmds, "codes": res_["codes"], "op": twin[2] if twin else None}))
    return rows, {"scenarios": 1, "twins": int(bool(twin))}
