"""WS-F shell family: generated folder trees and command lines, executed for real (bash 5.2 / coreutils 9.4) by the
unprivileged user in a throwaway box. New vocabulary and grammar (not shell_wild's)."""
from __future__ import annotations

import gzip
import io
import json
import os
import random
import re
import shlex
import tarfile
import time

from common import (chown_tree, choice, cmd_ceiling, cmd_floor, make_box, remove_box, row, run_unprivileged,
                    stable_seed, yes_no, BOX_ROOT, NOBODY)

RULES = ("A Linux shell session (bash 5.2, GNU coreutils 9.4) in a project folder, as an ordinary user (not root). "
         "The command lines below run in order in one session: a cd stays in effect for the lines after it, and a line "
         "that fails does not stop the next one.")
Q_LOST = ("Do these commands permanently lose any file content (a line of text that was in some file before and is in no "
          "file afterwards, archives in the folder included)?")
FILE_WORDS = ["orbit", "kiln", "trail", "harbor", "lattice", "quarry", "meadow", "beacon", "canyon", "ember", "fjord",
              "glacier", "heron", "iris", "juniper", "kestrel", "lagoon", "mesa", "nimbus", "opal", "prairie", "quill",
              "reef", "sierra", "tundra", "umber", "vale", "willow", "yarrow", "zephyr", "cobalt", "dune", "fern",
              "grove", "hollow", "jasper", "knoll", "larch", "marsh", "nettle", "osprey", "pumice", "rowan", "sorrel",
              "thistle", "upland", "vetch", "wren"]
EXTS = ["log", "tsv", "cfg", "md", "json", "dat", "ini", "yml", "txt", "toml", "csv", "conf"]
DIR_WORDS = ["shelf", "attic", "cellar", "dock", "loft", "annex", "atrium", "vault", "pantry", "outbox", "depot", "cabin",
             "silo", "kiosk", "galley", "porch"]
TAILS = ["north", "amber", "delta", "basalt", "cedar", "drift", "echo", "flint", "gale", "hazel", "inlet", "jade"]
BASE_T = 1_760_000_000


def age_s(age):
    """Seconds before BASE_T for a tree entry's age (the factory counts hours). The C012 re-render maps ages to days
    instead (v45/rerender_shell.py); any increasing map keeps every order and every tie between mtimes."""
    return age * 3600


# ------------------------------------------------------------------ trees

def content_line(rng):
    return f"{rng.choice(FILE_WORDS)}-{rng.randint(1000, 9999)} {rng.choice(TAILS)}"


def gen_tree(rng):
    words = rng.sample(FILE_WORDS, 16)
    t = {}
    used = set()

    def fname(prefix=""):
        while True:
            w = words.pop() if words else rng.choice(FILE_WORDS) + str(rng.randint(2, 99))
            n = prefix + f"{w}.{rng.choice(EXTS)}"
            if n not in used:
                used.add(n)
                return n

    for _ in range(rng.randint(3, 6)):
        t[fname()] = {"t": "f", "c": content_line(rng), "age": rng.randint(1, 30)}
    for d in rng.sample(DIR_WORDS, rng.randint(1, 3)):
        t[d] = {"t": "d"}
        for _ in range(rng.randint(0, 3)):
            t[fname(d + "/")] = {"t": "f", "c": content_line(rng), "age": rng.randint(1, 30)}
        if rng.random() < 0.25:
            sub = d + "/" + rng.choice(["inner", "nested", "deep", "spare"])
            t[sub] = {"t": "d"}
            for _ in range(rng.randint(0, 2)):
                t[fname(sub + "/")] = {"t": "f", "c": content_line(rng), "age": rng.randint(1, 30)}
    if rng.random() < 0.5:
        t[rng.choice([".envrc", ".marker", f".{rng.choice(FILE_WORDS)}rc"])] = {"t": "f", "c": content_line(rng), "age": 9}
    if rng.random() < 0.3:
        n = f"{rng.choice(FILE_WORDS)} {rng.choice(FILE_WORDS)}.txt"
        t[n] = {"t": "f", "c": content_line(rng), "age": 4}
    if rng.random() < 0.35:
        dirs = [p for p, e in t.items() if e["t"] == "d" and "/" not in p]
        files = [p for p, e in t.items() if e["t"] == "f" and "/" not in p and not p.startswith(".")]
        if dirs and rng.random() < 0.6:
            t[rng.choice(["current", "live", "active"])] = {"t": "l", "to": rng.choice(dirs)}
        elif files:
            t[rng.choice(["latest", "main_link", "pointer"])] = {"t": "l", "to": rng.choice(files)}
    files = [p for p, e in t.items() if e["t"] == "f"]
    if len(files) >= 2 and rng.random() < 0.3:  # a duplicate copy: deleting one is not a loss
        a, b = rng.sample(files, 2)
        t[b] = dict(t[b], c=t[a]["c"])
    dirs = [p for p, e in t.items() if e["t"] == "d" and "/" not in p]
    if dirs and rng.random() < 0.22:  # an archive with older versions of a folder's files
        d = rng.choice(dirs)
        members = {}
        for p, e in t.items():
            if p.startswith(d + "/") and e["t"] == "f":
                members[p] = content_line(rng) if rng.random() < 0.6 else e["c"]
        if not members:
            members[f"{d}/{rng.choice(FILE_WORDS)}.txt"] = content_line(rng)
        t[f"{d}.tgz"] = {"t": "tgz", "members": members, "age": 40}
    return t


def build_box(tree, box):
    for p in sorted(tree, key=lambda x: x.count("/")):
        e = tree[p]
        full = os.path.join(box, p)
        if e["t"] == "d":
            os.makedirs(full, exist_ok=True)
    for p, e in sorted(tree.items()):
        full = os.path.join(box, p)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        if e["t"] == "f":
            with open(full, "w") as f:
                f.write(e["c"] + "\n")
            ts = BASE_T - age_s(e.get("age", 1))
            os.utime(full, (ts, ts))
        elif e["t"] == "l":
            os.symlink(e["to"], full)
        elif e["t"] == "tgz":
            buf = io.BytesIO()
            with tarfile.open(fileobj=buf, mode="w") as tf:
                for mp, mc in sorted(e["members"].items()):
                    data = (mc + "\n").encode()
                    ti = tarfile.TarInfo(mp)
                    ti.size, ti.mtime, ti.mode = len(data), BASE_T - age_s(50), 0o644
                    tf.addfile(ti, io.BytesIO(data))
            with open(full, "wb") as f:
                f.write(gzip.compress(buf.getvalue(), mtime=0))
            ts = BASE_T - age_s(e.get("age", 40))
            os.utime(full, (ts, ts))
    for p, e in tree.items():
        if e["t"] == "d":
            ts = BASE_T - age_s(1)
            os.utime(os.path.join(box, p), (ts, ts))
    chown_tree(box)


def read_archive(path):
    """Text lines inside a tar/tgz/gz file (best effort), so archived content does not count as lost."""
    lines = []
    try:
        with open(path, "rb") as f:
            raw = f.read()
        try:
            data = gzip.decompress(raw)
        except Exception:  # noqa: BLE001
            data = raw
        try:
            with tarfile.open(fileobj=io.BytesIO(data)) as tf:
                for m in tf.getmembers():
                    if m.isfile():
                        lines += tf.extractfile(m).read().decode("utf-8", "replace").splitlines()
            return lines
        except Exception:  # noqa: BLE001
            if raw[:2] == b"\x1f\x8b":
                return data.decode("utf-8", "replace").splitlines()
    except Exception:  # noqa: BLE001
        pass
    return lines


def snapshot(box):
    snap = {}
    for root, dirs, files in os.walk(box, followlinks=False):
        rel_root = os.path.relpath(root, box)
        for n in dirs + files:
            full = os.path.join(root, n)
            rel = n if rel_root == "." else f"{rel_root}/{n}"
            if os.path.islink(full):
                snap[rel] = {"t": "l", "to": os.readlink(full)}
            elif os.path.isdir(full):
                snap[rel] = {"t": "d"}
            else:
                st = os.stat(full)
                e = {"t": "f", "size": st.st_size, "mode": st.st_mode & 0o777}
                if n.endswith((".tgz", ".gz", ".tar")):
                    e["arch"] = read_archive(full)
                else:
                    try:
                        with open(full, "rb") as f:
                            b = f.read(4096)
                        e["c"] = b.decode("utf-8")
                    except Exception:  # noqa: BLE001
                        e["c"] = None
                snap[rel] = e
    return snap


def pool(snap):
    out = set()
    for e in snap.values():
        if e["t"] == "f":
            for ln in (e.get("c") or "").splitlines():
                if ln.strip():
                    out.add(ln)
            for ln in e.get("arch", []):
                if ln.strip():
                    out.add(ln)
    return out


# ------------------------------------------------------------------ command forms

def q(name):
    return shlex.quote(name) if re.search(r"[^\w./\-]", name) else name


class View:
    def __init__(self, tree, rng):
        self.t, self.rng = tree, rng
        self.files = [p for p, e in tree.items() if e["t"] == "f"]
        self.top_files = [p for p in self.files if "/" not in p and not p.startswith(".") and " " not in p]
        self.spaced = [p for p in self.files if " " in p]
        self.hidden = [p for p in self.files if os.path.basename(p).startswith(".")]
        self.dirs = [p for p, e in tree.items() if e["t"] == "d"]
        self.top_dirs = [p for p in self.dirs if "/" not in p]
        self.links = [p for p, e in tree.items() if e["t"] == "l"]
        self.dir_links = [p for p in self.links if tree[p]["to"] in self.dirs]
        self.file_links = [p for p in self.links if tree[p]["to"] in self.files]
        self.archives = [p for p, e in tree.items() if e["t"] == "tgz"]
        self.exts = sorted({p.rsplit(".", 1)[-1] for p in self.top_files})

    def new_name(self, ext=None):
        while True:
            n = f"{self.rng.choice(FILE_WORDS)}_{self.rng.randint(2, 99)}.{ext or self.rng.choice(EXTS)}"
            if n not in self.t:
                return n

    def new_dir(self):
        while True:
            n = f"{self.rng.choice(DIR_WORDS)}_{self.rng.randint(2, 9)}"
            if n not in self.t:
                return n

    def word_in(self, path):
        c = self.t[path]["c"]
        return c.split("-")[0]

    def matching(self, ext, top_only=True):
        return [p for p in (self.top_files if top_only else self.files) if p.endswith("." + ext)]

    def missing_ext(self):
        for e in self.rng.sample(EXTS, len(EXTS)):
            if not any(p.endswith("." + e) for p in self.files):
                return e
        return "bak"


def F_one(v, k=None):
    pool_ = v.top_files + (v.spaced if v.rng.random() < 0.3 else [])
    return v.rng.choice(pool_) if pool_ else None


def forms():
    """name -> fn(view) returning (cmd, probes) or None. probes: paths worth asking about afterwards."""
    R = {}

    def form(name):
        def deco(fn):
            R[name] = fn
            return fn
        return deco

    # rm
    @form("rm_file")
    def _(v):
        f = F_one(v)
        return f and (f"rm {q(f)}", [f])

    @form("rm_missing")
    def _(v):
        n = v.new_name()
        return (f"rm {n}", [n])

    @form("rm_f_missing")
    def _(v):
        n = v.new_name()
        return (f"rm -f {n}", [n])

    @form("rm_dir_plain")
    def _(v):
        d = v.top_dirs and v.rng.choice(v.top_dirs)
        return d and (f"rm {d}", [d])

    @form("rm_r_dir")
    def _(v):
        d = v.top_dirs and v.rng.choice(v.top_dirs)
        return d and (f"rm -r{v.rng.choice(['', 'f'])} {d}{v.rng.choice(['', '/'])}", [d])

    @form("rm_glob")
    def _(v):
        e = v.rng.choice(v.exts + [v.missing_ext()]) if v.exts else v.missing_ext()
        return (f"rm *.{e}", v.matching(e)[:2] or [f"*.{e}"])

    @form("rm_star")
    def _(v):
        return (v.rng.choice(["rm *", "rm -r *", "rm -f *"]), (v.hidden[:1] + v.top_files[:1] + v.top_dirs[:1]))

    @form("rm_link_slash")
    def _(v):
        l = v.dir_links and v.rng.choice(v.dir_links)
        return l and (f"rm -r{v.rng.choice(['', 'f'])} {l}/", [l, v.t[l]["to"]])

    @form("rm_link")
    def _(v):
        l = v.links and v.rng.choice(v.links)
        return l and (f"rm {l}", [l, v.t[l]["to"]])

    @form("rm_hidden")
    def _(v):
        h = v.hidden and v.rng.choice(v.hidden)
        return h and (f"rm {h}", [h])

    # mv
    @form("mv_rename")
    def _(v):
        f = F_one(v)
        n = v.new_name()
        return f and (f"mv {q(f)} {n}", [f, n])

    @form("mv_overwrite")
    def _(v):
        if len(v.top_files) < 2:
            return None
        a, b = v.rng.sample(v.top_files, 2)
        return (f"mv {v.rng.choice(['', '-f ', '-n '])}{a} {b}", [a, b])

    @form("mv_into_dir")
    def _(v):
        f, d = F_one(v), v.top_dirs and v.rng.choice(v.top_dirs)
        return f and d and (f"mv {q(f)} {d}{v.rng.choice(['', '/'])}", [f, f"{d}/{os.path.basename(f)}"])

    @form("mv_into_missing_slash")
    def _(v):
        f = F_one(v)
        d = v.new_dir()
        return f and (f"mv {q(f)} {d}/", [f, d, f"{d}/{os.path.basename(f)}"])

    @form("mv_dir_into_dir")
    def _(v):
        if len(v.top_dirs) < 2:
            return None
        a, b = v.rng.sample(v.top_dirs, 2)
        return (f"mv {a} {b}", [a, f"{b}/{a}"])

    @form("mv_glob_into")
    def _(v):
        e = v.rng.choice(v.exts + [v.missing_ext()]) if v.exts else v.missing_ext()
        d = v.top_dirs and v.rng.choice(v.top_dirs)
        return d and (f"mv *.{e} {d}/", [d] + [f"{d}/{p}" for p in v.matching(e)[:1]])

    @form("mv_same")
    def _(v):
        f = F_one(v)
        return f and (f"mv {q(f)} ./{q(f)}", [f])

    # cp
    @form("cp_overwrite")
    def _(v):
        if len(v.top_files) < 2:
            return None
        a, b = v.rng.sample(v.top_files, 2)
        return (f"cp {v.rng.choice(['', '-n ', '-f '])}{a} {b}", [a, b])

    @form("cp_new")
    def _(v):
        f = F_one(v)
        n = v.new_name()
        return f and (f"cp {q(f)} {n}", [n])

    @form("cp_into_dir")
    def _(v):
        f, d = F_one(v), v.top_dirs and v.rng.choice(v.top_dirs)
        return f and d and (f"cp {q(f)} {d}/", [f"{d}/{os.path.basename(f)}"])

    @form("cp_dir_no_r")
    def _(v):
        if not v.top_dirs:
            return None
        a = v.rng.choice(v.top_dirs)
        b = v.new_dir()
        return (f"cp {a} {b}", [b])

    @form("cp_r_into_existing")
    def _(v):
        if len(v.top_dirs) < 2:
            return None
        a, b = v.rng.sample(v.top_dirs, 2)
        return (f"cp -r {a} {b}", [f"{b}/{a}", b])

    @form("cp_r_merge_dot")
    def _(v):
        if len(v.top_dirs) < 2:
            return None
        a, b = v.rng.sample(v.top_dirs, 2)
        return (f"cp -r {a}/. {b}/", [b] + [p.replace(a + "/", b + "/", 1) for p in v.files if p.startswith(a + "/")][:1])

    @form("cp_glob_to_file")
    def _(v):
        e = v.exts and v.rng.choice(v.exts)
        tgt = v.new_name("txt") if v.rng.random() < 0.5 else (v.top_files and v.rng.choice(v.top_files))
        return e and tgt and (f"cp *.{e} {tgt}", [tgt])

    # redirections
    @form("redir_same_file")
    def _(v):
        f = F_one(v)
        if not f:
            return None
        w = v.word_in(f)
        tool = v.rng.choice([f"sort {q(f)}", f"cat {q(f)}", f"sed 's/{w}/{w.upper()}/' {q(f)}", f"head -n 1 {q(f)}",
                             f"uniq {q(f)}", f"tr a-z A-Z < {q(f)}"])
        return (f"{tool} > {q(f)}", [f])

    @form("redir_echo")
    def _(v):
        f = F_one(v) if v.rng.random() < 0.7 else v.new_name()
        txt = f"{v.rng.choice(FILE_WORDS)}-{v.rng.randint(1000, 9999)} {v.rng.choice(TAILS)}"
        return f and (f"echo '{txt}' {v.rng.choice(['>', '>>'])} {q(f)}", [f])

    @form("redir_cat_into")
    def _(v):
        if len(v.top_files) < 2:
            return None
        a, b = v.rng.sample(v.top_files, 2)
        tgt = b if v.rng.random() < 0.6 else v.new_name()
        return (f"cat {a} {v.rng.choice(['', b + ' '])}{v.rng.choice(['>', '>>'])} {tgt}".replace("  ", " "), [tgt, a])

    @form("redir_truncate")
    def _(v):
        f = F_one(v)
        return f and (v.rng.choice([f": > {q(f)}", f"> {q(f)}", f"truncate -s 0 {q(f)}"]), [f])

    @form("redir_tee")
    def _(v):
        if len(v.top_files) < 2:
            return None
        a, b = v.rng.sample(v.top_files, 2)
        return (f"tee {a} < {b}", [a, b])

    @form("redir_to_dir")
    def _(v):
        d = v.top_dirs and v.rng.choice(v.top_dirs)
        return d and (f"echo 'x' > {d}", [d])

    @form("redir_missing_dir")
    def _(v):
        d = v.new_dir()
        return (f"echo 'x' > {d}/note.txt", [f"{d}/note.txt"])

    # sed -i
    @form("sed_i")
    def _(v):
        f = F_one(v)
        if not f:
            return None
        w = v.word_in(f) if v.rng.random() < 0.7 else v.rng.choice(FILE_WORDS)
        return (f"sed -i 's/{w}/{w[::-1]}/' {q(f)}", [f])

    @form("sed_n_i")
    def _(v):
        f = F_one(v)
        if not f:
            return None
        w = v.word_in(f) if v.rng.random() < 0.5 else v.rng.choice(TAILS)
        return (f"sed -n -i '/{w}/p' {q(f)}", [f])

    @form("sed_i_missing")
    def _(v):
        n = v.new_name()
        return (f"sed -i 's/a/b/' {n}", [n])

    # find
    @form("find_delete")
    def _(v):
        e = v.rng.choice(v.exts + [v.missing_ext()]) if v.exts else v.missing_ext()
        quoted = v.rng.random() < 0.5
        pat = f"'*.{e}'" if quoted else f"*.{e}"
        return (f"find . -name {pat} -delete", [p for p in v.files if p.endswith("." + e)][:2] or [f"x.{e}"])

    @form("find_empty_delete")
    def _(v):
        d = v.top_dirs and v.rng.choice(v.top_dirs)
        return d and (f"find {d} -type f -empty -delete", [d])

    @form("find_exec_rm")
    def _(v):
        f = v.files and v.rng.choice(v.files)
        return f and (f"find . -name {q(os.path.basename(f))} -exec rm {{}} \\;", [f])

    # xargs
    @form("xargs_rm")
    def _(v):
        e = v.rng.choice(v.exts + ["txt", v.missing_ext()]) if v.exts else "txt"
        src = v.rng.choice([f"ls *.{e}", f"find . -name '*.{e}'", f"find . -name '*.{e}' -print0"])
        x = "xargs -0 rm" if "print0" in src else v.rng.choice(["xargs rm", "xargs rm -f"])
        return (f"{src} | {x}", [p for p in v.files if p.endswith("." + e)][:2] or [f"y.{e}"])

    # rsync
    @form("rsync")
    def _(v):
        if len(v.top_dirs) < 2:
            return None
        a, b = v.rng.sample(v.top_dirs, 2)
        flags = v.rng.choice(["-a", "-a --delete", "-an --delete", "-a --ignore-existing", "-a --delete"])
        src = a + v.rng.choice(["/", ""])
        probes = [b] + [p.replace(a + "/", b + "/", 1) for p in v.files if p.startswith(a + "/")][:1] + \
                 [p for p in v.files if p.startswith(b + "/")][:1] + [f"{b}/{a}"]
        return (f"rsync {flags} {src} {b}/", probes)

    # archives
    @form("tar_create")
    def _(v):
        d = v.top_dirs and v.rng.choice(v.top_dirs)
        if not d:
            return None
        tail = v.rng.choice(["", f" && rm -r {d}", f"; rm -r {d}"])
        return (f"tar czf {d}_pack.tgz {d}{tail}", [f"{d}_pack.tgz", d])

    @form("tar_extract")
    def _(v):
        a = v.archives and v.rng.choice(v.archives)
        if not a:
            return None
        members = list(v.t[a]["members"])
        return (f"tar xz{v.rng.choice(['', 'k'])}f {a}", members[:2])

    @form("gzip_file")
    def _(v):
        f = F_one(v)
        return f and (f"gzip {q(f)}", [f, f + ".gz"])

    # links
    @form("ln_s")
    def _(v):
        f = F_one(v)
        if not f:
            return None
        tgt = v.rng.choice([v.new_name(), *(v.top_files[:2])])
        flag = v.rng.choice(["-s", "-sf"])
        return (f"ln {flag} {q(f)} {tgt}", [tgt])

    @form("ln_dir")
    def _(v):
        l = v.dir_links and v.rng.choice(v.dir_links)
        d = [x for x in v.top_dirs if not l or x != v.t[l]["to"]]
        if not l or not d:
            return None
        d = v.rng.choice(d)
        return (f"ln {v.rng.choice(['-sf', '-sfn'])} {d} {l}", [l, f"{v.t[l]['to']}/{d}"])

    @form("ln_hard")
    def _(v):
        f = F_one(v)
        return f and (f"ln {q(f)} {v.new_name()}", [f])

    # mkdir / touch / chmod
    @form("mkdir")
    def _(v):
        c = v.rng.random()
        if c < 0.35 and v.top_dirs:
            d = v.rng.choice(v.top_dirs)
            return (f"mkdir {d}", [d])
        if c < 0.7:
            d = v.new_dir()
            return (f"mkdir -p {d}/inner", [f"{d}/inner"])
        d = v.new_dir()
        return (f"mkdir {d}/inner", [d])

    @form("touch")
    def _(v):
        f = F_one(v) if v.rng.random() < 0.5 else v.new_name()
        return f and (f"touch {q(f)}", [f])

    @form("chmod_read")
    def _(v):
        f = F_one(v)
        return f and (f"chmod 000 {q(f)} && cat {q(f)}", [f])

    # sequencing and cd
    @form("cd_then_wipe")
    def _(v):
        d = v.rng.choice(v.top_dirs + [v.new_dir()]) if v.top_dirs else v.new_dir()
        sep = v.rng.choice([";", "&&"])
        return (f"cd {d} {sep} rm -rf *", v.top_files[:1] + [d])

    @form("false_then")
    def _(v):
        f = F_one(v)
        if not f:
            return None
        return (v.rng.choice([f"false; rm {q(f)}", f"false && rm {q(f)}", f"rm {q(f)} || true",
                              f"test -e {v.new_name()} && rm {q(f)}"]), [f])

    @form("unquoted_space")
    def _(v):
        f = v.spaced and v.rng.choice(v.spaced)
        return f and (v.rng.choice([f"rm {f}", f"mv {f} renamed.txt", f"cat {f} > out.txt"]), [f] + f.split(" ")[:1])

    return R


FORMS = forms()


def follow_up(v, first_probes):
    """A second line that reads or acts on what the first line touched."""
    rng = v.rng
    if first_probes and rng.random() < 0.6:
        p = rng.choice(first_probes)
        if p and "*" not in p:
            return (rng.choice([f"cat {q(p)}", f"ls {q(p)}", f"rm {q(p)}", f"mv {q(p)} {v.new_name()}",
                                f"cp {q(p)} {v.new_name()}"]), [p])
    name = rng.choice(list(FORMS))
    r = FORMS[name](v)
    return r


BAD = re.compile(r"(^|[\s'\"=])/|\.\.|~|\$|`|\bsudo\b|\bcurl\b|\bwget\b|\bnc\b|\bssh\b|\bdd\b|(^|[;&|]\s*)cd\s*($|[;&|])|cd\s+-(\s|$)")


def valid(cmd: str) -> bool:
    return not BAD.search(cmd)


# ------------------------------------------------------------------ execution

def execute(tree, cmds, tag, observe=None):
    """Runs cmds as nobody in a box built from tree: snapshots, exit codes, first error lines. observe(moment, box), if
    given, is called right after the "before" and the "after" snapshot, on the same box (the C012 re-render reads it
    with the guard there)."""
    box = make_box(tag)
    meta = box + ".meta"
    if os.path.exists(meta):
        remove_box(meta) if meta.startswith(BOX_ROOT) else None
    os.makedirs(meta, exist_ok=True)
    try:
        build_box(tree, box)
        os.chown(meta, NOBODY, NOBODY)
        lines = [f'cd "{box}" || exit 99']
        for k, c in enumerate(cmds, 1):
            lines += ["{ " + c, f'}} 2>"{meta}/{k}.err" </dev/null; echo $? > "{meta}/{k}.rc"']
        script = "\n".join(lines) + "\n"
        with open(os.path.join(meta, "run.sh"), "w") as f:
            f.write(script)
        before = snapshot(box)
        if observe:
            observe("before", box)
        rc, out, err = run_unprivileged(["bash", "--noprofile", "--norc", os.path.join(meta, "run.sh")], cwd=box)
        codes, errs = [], []
        for k in range(1, len(cmds) + 1):
            try:
                codes.append(int(open(os.path.join(meta, f"{k}.rc")).read().strip()))
                e = open(os.path.join(meta, f"{k}.err"), errors="replace").read().strip().splitlines()
                # the sandbox path (it carries the worker's PID) never reaches the text: paths relative to the folder
                errs.append(re.sub(r"^\S*run\.sh: line \d+: ", "bash: ", e[0]).replace(box + "/", "").replace(box, ".")[:140]
                            if e else "")
            except Exception:  # noqa: BLE001
                return None
        after = snapshot(box)
        if observe:
            observe("after", box)
        return {"before": before, "after": after, "codes": codes, "errs": errs}
    finally:
        remove_box(box)
        if os.path.isdir(meta):
            import shutil
            shutil.rmtree(meta, ignore_errors=True)


# ------------------------------------------------------------------ rendering and questions

def render(snap, layout):
    lines = ["Files and folders here (paths relative to the starting folder; hidden entries included):"]
    for p in sorted(snap):
        e = snap[p]
        if e["t"] == "d":
            lines.append(f"- {p}/ — folder")
        elif e["t"] == "l":
            lines.append(f"- {p} — link to {e['to']}")
        elif "arch" in e:
            s = f"- {p} — archive, {e['size']} bytes"
            if layout == "full":
                s += " (holds: " + "; ".join(f'"{x}"' for x in e["arch"][:6]) + ")"
            lines.append(s)
        else:
            s = f"- {p} — file, {e['size']} bytes"
            if e.get("mode", 0o644) == 0:
                s += ", no read permission"
            if layout == "full" and e.get("c") is not None:
                s += f': "{e["c"].rstrip()}"' if e["c"].strip() else ": (empty)"
            lines.append(s)
    if len(lines) == 1:
        lines.append("(the folder is empty)")
    return "\n".join(lines)


def kind_of(snap, p):
    e = snap.get(p.rstrip("/"))
    if e is None:
        return "nothing (it does not exist)"
    return {"f": "a file", "d": "a folder", "l": "a link"}[e["t"]]


def content_of(snap, p):
    e = snap.get(p)
    if e is None:
        return "(no such file)"
    if e["t"] != "f" or "arch" in e:
        return None
    c = (e.get("c") or "").rstrip("\n")
    return f'"{c}"' if c.strip() else "(empty)"


def count_in(snap, d):
    if snap.get(d, {}).get("t") != "d":
        return None
    return sum(1 for p, e in snap.items() if e["t"] == "f" and os.path.dirname(p) == d)


def face(cmds, qt, arg, before):
    """The usual effect, as a reader who knows what each command is for would guess (written before generation)."""
    joined = " ; ".join(cmds)
    if qt == "lost":
        return bool(re.search(r"\brm\b|-delete|truncate|sed -i|--delete|ln -sf|tar x|(^|[^>])>\s*\S", joined))
    if qt.startswith("fails"):
        return False
    if qt in ("exists", "kind", "content", "count"):
        state = {p: dict(e) for p, e in before.items()}
        for c in cmds:
            toks = c.replace(";", " ; ").split()
            if not toks:
                continue
            if toks[0] == "rm":
                for t in toks[1:]:
                    state.pop(t.rstrip("/"), None)
            elif toks[0] in ("mv", "cp") and len(toks) >= 3:
                src, dst = toks[-2].rstrip("/"), toks[-1].rstrip("/")
                if src in state:
                    tgt = f"{dst}/{os.path.basename(src)}" if state.get(dst, {}).get("t") == "d" else dst
                    state[tgt] = dict(state[src])
                    if toks[0] == "mv":
                        state.pop(src, None)
            elif toks[0] in ("touch",) and len(toks) >= 2:
                state.setdefault(toks[1], {"t": "f", "c": "", "size": 0})
            elif toks[0] == "mkdir":
                for t in toks[1:]:
                    if not t.startswith("-"):
                        state.setdefault(t.rstrip("/"), {"t": "d"})
        if qt == "exists":
            return arg.rstrip("/") in state
        if qt == "kind":
            return kind_of(state, arg)
        if qt == "content":
            return content_of(state, arg)
        if qt == "count":
            return count_in(state, arg)
    return None


def scenario_questions(rng, cmds, probes, res, layout):
    """Question specs (qt, arg, question dict) for one scenario."""
    qs = [("lost", None, yes_no(Q_LOST))]
    for k in range(1, len(cmds) + 1):
        qs.append((f"fails{k}", k, yes_no(f"Does line {k} fail (finish with a non-zero exit status)?")))
    cand = [p for p in dict.fromkeys(probes) if p and "*" not in p and len(p) < 80]
    rng.shuffle(cand)
    for p in cand[:2]:
        if rng.random() < 0.55:
            qs.append(("exists", p, yes_no(f"After these commands, does {p} exist (as a file, folder or link)?")))
        else:
            qs.append(("kind", p, choice(f"After these commands, what is {p}?",
                                         ["a file", "a folder", "a link", "nothing (it does not exist)"])))
    if layout == "full":
        fc = [p for p in cand if res["before"].get(p, {}).get("t") in ("f", None) and not p.endswith((".tgz", ".gz"))]
        if fc:
            p = fc[0]
            qs.append(("content", p, None))
    dirs = [p for p in cand if res["before"].get(p, {}).get("t") == "d" or res["after"].get(p, {}).get("t") == "d"]
    if dirs and rng.random() < 0.5:
        qs.append(("count", dirs[0], None))
    return qs


def golds(qs, res):
    out = {}
    lost = pool(res["before"]) - pool(res["after"])
    for qt, arg, _ in qs:
        if qt == "lost":
            out[(qt, arg)] = bool(lost)
        elif qt.startswith("fails"):
            out[(qt, arg)] = res["codes"][arg - 1] != 0
        elif qt == "exists":
            out[(qt, arg)] = arg.rstrip("/") in res["after"]
        elif qt == "kind":
            out[(qt, arg)] = kind_of(res["after"], arg)
        elif qt == "content":
            out[(qt, arg)] = content_of(res["after"], arg)
        elif qt == "count":
            out[(qt, arg)] = count_in(res["after"], arg)
    return out


def content_question(p, res_a, res_b, cmds):
    opts = []
    for snap in (res_a["before"], res_a["after"]) + ((res_b["before"], res_b["after"]) if res_b else ()):
        c = content_of(snap, p)
        if c:
            opts.append(c)
    for m in re.findall(r"'([^']+)'", " ".join(cmds)):
        if len(m) < 60 and not any(ch in m for ch in "*/"):
            opts.append(f'"{m}"')
    opts += ["(empty)", "(no such file)"]
    opts = list(dict.fromkeys(o for o in opts if o))[:7]
    return choice(f"After these commands, what does {p} contain?", opts)


def count_question(d, res_a, res_b):
    vals = [count_in(s, d) for s in (res_a["before"], res_a["after"]) + ((res_b["before"], res_b["after"]) if res_b else ())]
    hi = max([v for v in vals if v is not None] + [2]) + 1
    return choice(f"After these commands, how many files (not folders) are directly inside {d}?",
                  [str(i) for i in range(0, min(hi, 7) + 1)])


PERTURB = ["toggle_exist", "to_folder", "add_dup", "add_hidden", "add_match", "drop_match"]


def perturb(tree, cmds, rng):
    t = json.loads(json.dumps(tree))
    names = set()
    for c in cmds:
        for tok in re.split(r"[\s;|&<>]+", c):
            tok = tok.strip("'\"").rstrip("/")
            if tok.startswith("./"):
                tok = tok[2:]
            if tok.endswith("/."):
                tok = tok[:-2]
            if tok in ("", ".") or "{" in tok or "\\" in tok:
                continue
            if tok and not tok.startswith("-") and tok not in ("rm", "mv", "cp", "cat", "ls", "find", "xargs", "cd",
                                                                "tar", "gzip", "ln", "sed", "echo", "touch", "mkdir"):
                names.add(tok)
    op = rng.choice(PERTURB)
    if op == "toggle_exist":
        cand = sorted(n for n in names if "*" not in n and "." in n or n in t)
        if not cand:
            return None
        n = rng.choice(cand)
        if n in t:
            if t[n]["t"] == "d":
                for p in [p for p in t if p.startswith(n + "/")]:
                    del t[p]
            del t[n]
        else:
            if "/" in n and n.rsplit("/", 1)[0] not in t:
                t[n.rsplit("/", 1)[0]] = {"t": "d"}
            t[n] = {"t": "f", "c": content_line(rng), "age": 2}
    elif op == "to_folder":
        cand = sorted(n for n in names if n in t and t[n]["t"] == "f" and "/" not in n)
        if not cand:
            cand = sorted(n for n in names if n not in t and "*" not in n and "/" not in n)
            if not cand:
                return None
        n = rng.choice(cand)
        t[n] = {"t": "d"}
        t[f"{n}/{rng.choice(FILE_WORDS)}.txt"] = {"t": "f", "c": content_line(rng), "age": 3}
    elif op == "add_dup":
        files = [p for p, e in t.items() if e["t"] == "f" and p in names]
        if not files:
            return None
        src = rng.choice(files)
        t[f"spare_{rng.randint(10, 99)}.txt"] = {"t": "f", "c": t[src]["c"], "age": 5}
    elif op == "add_hidden":
        dirs = [p for p, e in t.items() if e["t"] == "d"] + [""]
        d = rng.choice(dirs)
        t[(d + "/" if d else "") + ".keep"] = {"t": "f", "c": content_line(rng), "age": 6}
    elif op in ("add_match", "drop_match"):
        exts = sorted({m for c in cmds for m in re.findall(r"\*\.(\w+)", c)})
        if not exts:
            return None
        e = rng.choice(exts)
        if op == "add_match":
            t[f"{rng.choice(FILE_WORDS)}_{rng.randint(10, 99)}.{e}"] = {"t": "f", "c": content_line(rng), "age": 2}
        else:
            m = [p for p in t if p.endswith("." + e) and t[p]["t"] == "f"]
            if not m:
                return None
            del t[rng.choice(m)]
    return t, op


def make_items(seed):
    """One base scenario (+ its flip twin when one is found): rows, stats."""
    rng = random.Random(stable_seed("rx_shell", seed))
    tree = gen_tree(rng)
    v = View(tree, rng)
    names = sorted(FORMS)
    for _ in range(12):
        name = rng.choice(names)
        r = FORMS[name](v)
        if r:
            break
    else:
        return [], {"skipped": 1}
    cmds, probes = [r[0]], list(r[1])
    if rng.random() < 0.4:
        f2 = follow_up(v, probes)
        if f2:
            cmds.append(f2[0])
            probes += f2[1]
    if not all(valid(c) for c in cmds):
        return [], {"invalid": 1}
    tag = f"s{os.getpid()}_{seed}"
    res = execute(tree, cmds, tag)
    if res is None:
        return [], {"exec_fail": 1}
    layout = "full" if rng.random() < 0.4 else "listing"
    qs = scenario_questions(rng, cmds, probes, res, layout)
    twin = None
    for _ in range(6):
        pt = perturb(tree, cmds, rng)
        if not pt:
            continue
        t2, op = pt
        r2 = execute(t2, cmds, tag + "t")
        if r2 is None:
            continue
        if golds(qs, r2) != golds(qs, res):
            twin = (t2, r2, op)
            break
    instances = [("a", tree, res)] + ([("b", twin[0], twin[1])] if twin else [])
    rows = []
    for side, t_, res_ in instances:
        other = twin[1] if (twin and side == "a") else (res if side == "b" else None)
        g = golds(qs, res_)
        g0 = golds(qs, {"before": res_["before"], "after": res_["before"], "codes": [0] * len(cmds)})
        floor = cmd_floor(RULES, render(res_["before"], layout), cmds)
        what = "; ".join(f"line {k}: exit {c}" + (f" ({e})" if c and e else "")
                         for k, (c, e) in enumerate(zip(res_["codes"], res_["errs"]), 1))
        what += f". File content lost for good: {'yes' if g[('lost', None)] else 'no'}."
        ceiling = cmd_ceiling(RULES, cmds, render(res_["after"], "full"), what)
        for qt, arg, qd in qs:
            gold = g[(qt, arg)]
            if qt == "content":
                if gold is None:
                    continue
                qd = content_question(arg, res, twin[1] if twin else None, cmds)
                if gold not in qd["criteria"]:
                    qd["criteria"][gold] = gold
            elif qt == "count":
                if gold is None:
                    continue
                qd = count_question(arg, res, twin[1] if twin else None)
                if str(gold) not in qd["criteria"]:
                    qd["criteria"][str(gold)] = str(gold)
            known0 = qt in ("exists", "kind", "content", "count") and g0.get((qt, arg)) is not None
            fv = face(cmds, qt, arg, res_["before"])
            rid = f"rxsh-{seed}-{side}-{qt}{'' if arg is None else '-' + re.sub(r'[^A-Za-z0-9]', '_', str(arg))}"
            rows.append(row(world="rx_shell", family="shell", template=name + ("+" if len(cmds) > 1 else ""), qtype=qt
                            if not qt.startswith("fails") else "fails", steps=len(cmds), question=qd, gold=gold,
                            gold0=(g0.get((qt, arg)) if known0 else None), known0=known0, floor=floor, ceiling=ceiling,
                            rid=rid, twin=(f"rxsh-{seed}-{'b' if side == 'a' else 'a'}" if twin else None), layout=layout,
                            face=fv, struct={"tree": t_, "cmds": cmds, "codes": res_["codes"], "op": twin[2] if twin else None}))
    return rows, {"scenarios": 1, "twins": int(bool(twin))}
