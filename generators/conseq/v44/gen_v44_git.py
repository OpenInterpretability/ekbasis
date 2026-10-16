"""V44 git items with REAL execution, aimed at the three blind spots client 0.1.1 still misses (capability map, 05/10):
  A ignored_overwrite - an ignored file at a path that the target of checkout / switch / merge / reset --hard <ref> /
                        checkout <ref> -- <path> tracks: git overwrites it without a word (controls: the path is untracked
                        but not ignored, the target does not track it, git stash -a first, git stash -u first);
  B sparse_ignored    - git sparse-checkout set <dirs> with ignored files in directories that leave the checkout
                        (controls: the ignored file is in a kept directory or at the top level);
  C abort_resolved    - --abort (merge, rebase, cherry-pick) after the conflict was resolved by hand, staged or not
                        (controls: markers still in the file, --continue / commit instead of --abort).
Every example is a fresh repository in a throwaway directory; the answers come from running the commands. Names (files,
branches, contents) differ from the held-out git suites (git_wild, client_next confirmation) and from gitbox3.

Each example is written twice: in the training layout of gitbox3 (render_old: no facts, every file in the working
directory listed with its content, ignored ones included) and in the layout client 0.1.1 sends (ekbasis.git.inspect
with facts, plus the notes the commands need). Questions = the client's own (lost, fails k, in progress).
python3 gen_v44_git.py <out.jsonl> <n_examples> <seed_tag>   (run on the rig: real git, many processes)"""
import json
import multiprocessing as mp
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.environ.get("EKB_CLIENT", "/root/decis/conseq/v44/client011"))
from ekbasis import git as EG  # noqa: E402
from ekbasis import prompts as P  # noqa: E402

ENV = {"GIT_AUTHOR_NAME": "Dev", "GIT_AUTHOR_EMAIL": "dev@example.invalid", "GIT_COMMITTER_NAME": "Dev",
       "GIT_COMMITTER_EMAIL": "dev@example.invalid", "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0",
       "LC_ALL": "C", "PATH": "/usr/local/bin:/usr/bin:/bin", "GIT_EDITOR": "true", "GIT_MERGE_AUTOEDIT": "no"}
TRACKED = ["pkg/core.rs", "web/index.html", "scripts/deploy.sh", "Makefile", "CHANGES.txt", "lib/parse.c",
           "schema/model.sql", "assets/theme.css"]
IGNORED = [("local.settings", "local.settings"), ("secrets/token.txt", "secrets/"), ("out/app.bin", "out/"),
           ("tmp/session.dat", "tmp/"), ("coverage.json", "coverage.json"), ("profile.local", "*.local"),
           ("cache/rows.sqlite", "cache/"), ("draft.swp", "*.swp")]
BRANCHES = ["topic", "staging", "release", "spike", "wip-ui"]
WORDS = ["amber", "basil", "cobalt", "dune", "ember", "fjord", "garnet", "harbor", "indigo", "juniper", "kelp", "lumen",
         "maple", "nectar", "onyx", "pollen", "quartz", "russet", "saffron", "tundra"]
TOKRE = re.compile(r"\b[a-z]+-\d{5}\b")


def tok(rng):
    return f"{rng.choice(WORDS)}-{rng.randrange(10000, 99999)}"


class Box:
    def __init__(self, root):
        self.dir = tempfile.mkdtemp(prefix="g44_", dir=root)
        self.work = os.path.join(self.dir, "work")
        os.makedirs(self.work)
        self.env = dict(ENV, HOME=self.dir)

    def sh(self, cmd):
        try:
            p = subprocess.run(["bash", "-c", cmd], cwd=self.work, env=self.env, timeout=10, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True)
        except subprocess.TimeoutExpired:
            return 124, ""
        return p.returncode, p.stdout

    def write(self, path, content):
        full = os.path.join(self.work, path)
        os.makedirs(os.path.dirname(full) or self.work, exist_ok=True)
        with open(full, "w") as f:
            f.write(content + "\n")

    def close(self):
        shutil.rmtree(self.dir, ignore_errors=True)


# ------------------------------------------------------------------ observing
def work_files(b):
    out = {}
    for root, dirs, files in os.walk(b.work):
        if ".git" in dirs:
            dirs.remove(".git")
        for f in files:
            p = os.path.join(root, f)
            rel = os.path.relpath(p, b.work)
            try:
                out[rel] = open(p, errors="replace").read().strip()
            except OSError:
                pass
    return out


def blobs(b, ids):
    if not ids:
        return []
    p = subprocess.run(["git", "cat-file", "--batch"], cwd=b.work, env=b.env, input="\n".join(ids) + "\n",
                       stdout=subprocess.PIPE, text=True, errors="replace", timeout=20)
    return [p.stdout]


def committed_tokens(b):
    rc, revs = b.sh("git rev-list --all 2>/dev/null")
    commits = set(revs.split())
    rc, st = b.sh("git stash list --format=%H 2>/dev/null")
    for h in st.split():
        commits.add(h)
        for par in ("^2", "^3"):
            rc2, x = b.sh(f"git rev-parse --verify --quiet {h}{par}")
            if rc2 == 0:
                commits.add(x.strip())
    ids = set()
    for c in commits:
        rc, t = b.sh(f"git ls-tree -r {c}")
        ids.update(l.split()[2] for l in t.splitlines() if l.split()[1:2] == ["blob"])
    toks = set()
    for chunk in blobs(b, sorted(ids)):
        toks.update(TOKRE.findall(chunk))
    return toks


def index_tokens(b):
    rc, t = b.sh("git ls-files -s 2>/dev/null")
    ids = sorted({l.split()[1] for l in t.splitlines() if len(l.split()) >= 2})
    toks = set()
    for chunk in blobs(b, ids):
        toks.update(TOKRE.findall(chunk))
    return toks


def all_tokens(b):
    wt = set()
    for c in work_files(b).values():
        wt.update(TOKRE.findall(c))
    return wt | index_tokens(b) | committed_tokens(b)


def uncommitted_tokens(b):
    wt = set()
    for c in work_files(b).values():
        wt.update(TOKRE.findall(c))
    return (wt | index_tokens(b)) - committed_tokens(b)


def in_progress(b):
    g = os.path.join(b.work, ".git")
    return any(os.path.exists(os.path.join(g, x)) for x in ("MERGE_HEAD", "rebase-merge", "rebase-apply", "CHERRY_PICK_HEAD", "REVERT_HEAD"))


def render_old(b):
    """The gitbox3 training layout (no facts): every file in the working directory is listed with its content."""
    rc, br = b.sh("git rev-parse --abbrev-ref HEAD 2>/dev/null")
    br = br.strip() or "(none)"
    rc, bl = b.sh("git for-each-ref --format='%(refname:short) %(subject)' refs/heads")
    branches = []
    for l in bl.splitlines():
        name, _, subj = l.partition(" ")
        branches.append(f"{name} ({subj})")
    rc, om = b.sh("git log -1 --format=%s refs/remotes/origin/main 2>/dev/null")
    lines = [f"Current branch: {br}", "Branches (last commit message): " + ", ".join(sorted(branches)),
             f"Remote origin/main last commit: {om.strip() or '(none)'}"]
    rc, heads = b.sh("git for-each-ref --format='%(refname:short)' refs/heads")
    parts = []
    for o in sorted(h for h in heads.split() if h != br):
        rc, dif = b.sh(f"git diff --name-only HEAD {o} 2>/dev/null")
        dif = sorted(dif.split())
        rc, mb = b.sh(f"git merge-base HEAD {o} 2>/dev/null")
        both = []
        if mb.strip():
            rc, a = b.sh(f"git diff --name-only {mb.strip()} HEAD")
            rc, c = b.sh(f"git diff --name-only {mb.strip()} {o}")
            both = sorted(set(a.split()) & set(c.split()))
        t = f"{o} differs in {', '.join(dif)}" if dif else f"{o} has the same files"
        parts.append(t + (f" (changed on both sides since they split: {', '.join(both)})" if both else ""))
    if parts:
        lines.append("Compared with the current branch: " + "; ".join(parts))
    rc, st = b.sh("git status --porcelain=v1 2>/dev/null")
    stn = {"M": "modified", "A": "added", "D": "deleted", "R": "renamed", "?": "untracked", "U": "unmerged (conflict)"}
    ent = []
    for l in st.splitlines():
        x, y, f = l[0], l[1], l[3:]
        if l[:2] == "??":
            ent.append(f"{f} (untracked)")
        elif l[:2] in ("UU", "AA", "DU", "UD", "AU", "UA", "DD"):
            ent.append(f"{f} (unmerged (conflict))")
        else:
            s1 = f"staged {stn.get(x, x)}" if x != " " else ""
            s2 = f"unstaged {stn.get(y, y)}" if y != " " else ""
            ent.append(f"{f} ({', '.join(p for p in (s1, s2) if p)})")
    lines.append("git status: " + ("; ".join(ent) if ent else "nothing to commit, working tree clean"))
    rc, sl = b.sh("git stash list 2>/dev/null")
    lines.append(f"Stash entries: {len(sl.splitlines())}")
    if in_progress(b):
        g = os.path.join(b.work, ".git")
        op = "merge" if os.path.exists(os.path.join(g, "MERGE_HEAD")) else (
            "cherry-pick" if os.path.exists(os.path.join(g, "CHERRY_PICK_HEAD")) else "rebase")
        lines.append(f"Operation in progress: {op} (unfinished)")
    files = work_files(b)
    lines.append("Files in the working directory (content): " + (
        ", ".join(f"{f} ({' / '.join(c.splitlines())[:120]})" for f, c in sorted(files.items())) if files else "(none)"))
    return "\n".join(lines)


# ------------------------------------------------------------------ scenarios
def base_repo(b, rng, n=None):
    b.sh("git init -q -b main && git config commit.gpgsign false && git init -q --bare ../origin.git && git remote add origin ../origin.git")
    tracked = rng.sample(TRACKED, n or rng.randint(2, 4))
    for f in tracked:
        b.write(f, tok(rng))
    b.sh("git add -A && git commit -qm 'initial import' && git push -q origin main 2>/dev/null")
    return tracked


def scen_ignored(b, rng):
    tracked = base_repo(b, rng)
    path, pattern = rng.choice(IGNORED)
    target_kind = rng.choice(["branch", "branch", "tag"])
    tgt = rng.choice(BRANCHES)
    tracks = rng.random() < 0.8                       # control: the target does not track the path
    ignore = rng.random() < 0.8                       # control: the local file is untracked but not ignored
    b.sh(f"git checkout -q -b {tgt}")
    if tracks:
        b.write(path, tok(rng))
        b.sh(f"git add -f '{path}' && git commit -qm 'add {os.path.basename(path)}'")
    else:
        f = rng.choice(tracked)
        b.write(f, tok(rng))
        b.sh(f"git commit -qam 'update {os.path.basename(f)}'")
    b.sh("git checkout -q main")
    if target_kind == "tag":
        b.sh(f"git tag v{rng.randint(1, 9)}.{rng.randint(0, 9)} {tgt}")
        rc, tags = b.sh("git tag")
        ref = tags.split()[0]
        b.sh(f"git branch -D {tgt} -q")
    else:
        ref = tgt
    if ignore:
        b.write(".gitignore", pattern)
        b.sh("git add .gitignore && git commit -qm 'ignore local files'")
    b.write(path, tok(rng))  # the local version: ignored (or just untracked)
    if rng.random() < 0.4:
        f = rng.choice(tracked)
        b.write(f, tok(rng))
    menu = [[f"git checkout {ref}"], [f"git merge {ref}"], [f"git reset --hard {ref}"], [f"git checkout {ref} -- {path}"]]
    if target_kind == "branch":
        menu += [[f"git switch {ref}"], ["git stash -a", f"git switch {ref}"], ["git stash -u", f"git checkout {ref}"],
                 [f"git checkout -f {ref}"]]
    if target_kind == "tag":
        menu += [[f"git checkout --detach {ref}"], ["git stash -a", f"git checkout {ref}"]]
    return rng.choice(menu), "ignored_overwrite"


def scen_sparse(b, rng):
    b.sh("git init -q -b main && git config commit.gpgsign false && git init -q --bare ../origin.git && git remote add origin ../origin.git")
    dirs = rng.sample(["web", "pkg", "schema", "assets", "lib", "scripts", "tools"], 3)
    for d in dirs:
        for _ in range(rng.randint(1, 2)):
            b.write(f"{d}/{rng.choice(['main', 'util', 'spec', 'mod', 'conf'])}.{rng.choice(['rs', 'c', 'sql', 'css', 'sh'])}", tok(rng))
    b.write("Makefile", tok(rng))
    pat = rng.choice(["*.log", "*.tmp", "*.out"])
    b.write(".gitignore", pat)
    b.sh("git add -A && git commit -qm 'layout' && git push -q origin main 2>/dev/null")
    ext = pat[1:]
    where = rng.choice(["drop", "drop", "keep", "top"])
    keep = rng.sample(dirs, rng.randint(1, 2))
    drop = [d for d in dirs if d not in keep]
    if where == "drop" and drop:
        ig = f"{rng.choice(drop)}/debug{ext}"
    elif where == "keep":
        ig = f"{rng.choice(keep)}/debug{ext}"
    else:
        ig = f"session{ext}"
    b.write(ig, tok(rng))
    if rng.random() < 0.3 and drop:  # an untracked, not ignored file too
        b.write(f"{rng.choice(drop)}/scratch.txt", tok(rng))
    cmds = [f"git sparse-checkout set {' '.join(keep)}"]
    if rng.random() < 0.3:
        cmds = [f"git sparse-checkout set {' '.join(keep)}", "git sparse-checkout disable"]
    return cmds, "sparse_ignored"


def scen_abort(b, rng):
    f = rng.choice(TRACKED)
    b.sh("git init -q -b main && git config commit.gpgsign false && git init -q --bare ../origin.git && git remote add origin ../origin.git")
    b.write(f, tok(rng))
    other = rng.choice([x for x in TRACKED if x != f])
    b.write(other, tok(rng))
    b.sh("git add -A && git commit -qm 'start' && git push -q origin main 2>/dev/null")
    tgt = rng.choice(BRANCHES)
    b.sh(f"git checkout -q -b {tgt}")
    b.write(f, tok(rng))
    b.sh(f"git commit -qam 'change on {tgt}'")
    b.sh("git checkout -q main")
    b.write(f, tok(rng))
    b.sh("git commit -qam 'change on main'")
    op = rng.choice(["merge", "rebase", "cherry-pick"])
    if op == "merge":
        b.sh(f"git merge {tgt}")
    elif op == "rebase":
        b.sh(f"git rebase {tgt}")
    else:
        b.sh(f"git cherry-pick {tgt}")
    if not in_progress(b):
        return None, None
    res = rng.choice(["markers", "hand", "hand_added", "hand_added"])
    if res != "markers":
        b.write(f, tok(rng))
        if res == "hand_added":
            b.sh(f"git add '{f}'")
    finish = {"merge": ["git commit --no-edit"], "rebase": ["git rebase --continue"], "cherry-pick": ["git cherry-pick --continue"]}[op]
    abort = [f"git {op} --abort"]
    cmds = abort if rng.random() < 0.7 else (finish if res == "hand_added" else rng.choice([abort, ["git status"] + abort]))
    return cmds, "abort_resolved"


SCEN = [scen_ignored, scen_ignored, scen_sparse, scen_abort, scen_abort]


def example(rng, root):
    b = Box(root)
    try:
        cmds, name = rng.choice(SCEN)(b, rng)
        if not cmds:
            return None
        old = render_old(b)
        view = EG.inspect(b.work, cmds, facts=True)
        new_state = view.state
        notes = P.git_notes(cmds, view.info)
        before = uncommitted_tokens(b)
        ip0 = in_progress(b)
        codes = [b.sh(c)[0] for c in cmds]
        after = all_tokens(b)
        lost = bool(before - after)
        ip1 = in_progress(b)
        after_old = render_old(b)
        cmd_text = "\n".join(f"{i + 1}. {c}" for i, c in enumerate(cmds))
        log = "; ".join(f"command {i + 1}: {'failed' if rc else 'ok'}" for i, rc in enumerate(codes))
        ceiling = (f"{P.GIT_RULES}\n\nCommands that were run:\n{cmd_text}\n\nState after the commands:\n{after_old}\n"
                   f"What happened: {log}. Uncommitted work lost for good: {'yes' if lost else 'no'}.")
        floors = {"old": P.git_state(old, cmds), "new": P.git_state(new_state, cmds, notes=notes or None)}
        qs = [("lost", P.GIT_LOST, lost, None), ("in_progress", P.GIT_IN_PROGRESS, ip1, ip0)]
        qs += [("fails", P.git_fails(k + 1), codes[k] != 0, None) for k in range(len(cmds))]
        return {"scenario": name, "cmds": cmds, "codes": codes, "lost": lost, "floors": floors, "ceiling": ceiling, "qs": qs}
    finally:
        b.close()


def work(args):
    seed, n, root = args
    rng = random.Random(seed)
    out = []
    tries = 0
    while len(out) < n and tries < n * 5:
        tries += 1
        try:
            ex = example(rng, root)
        except Exception as e:  # noqa: BLE001
            print("skip:", type(e).__name__, e, file=sys.stderr)
            continue
        if ex:
            out.append(ex)
    return out


def rows_from(ex, rng):
    """Two rows per example (the 'lost' question and one other), each in one of the two layouts."""
    rows = []
    pick = [ex["qs"][0], rng.choice(ex["qs"][1:])]
    for qt, q, gold, gold0 in pick:
        lay = rng.choice(["old", "new", "new"])
        rows.append({"kind": "floorGV", "world": "git", "qtype": qt, "scenario": ex["scenario"], "layout": lay,
                     "steps": len(ex["cmds"]), "question": q, "gold": bool(gold), "gold0": gold0, "known0": gold0 is not None,
                     "floor": ex["floors"][lay], "ceiling": ex["ceiling"], "cmds": ex["cmds"], "held_used": [], "kinds": [ex["scenario"]]})
    return rows


def balance(rows, rng):
    out = [r for r in rows if r["qtype"] not in ("lost", "fails")]
    for qt in ("lost", "fails"):
        for sc in sorted({r["scenario"] for r in rows}):
            yes = [r for r in rows if r["qtype"] == qt and r["scenario"] == sc and r["gold"]]
            no = [r for r in rows if r["qtype"] == qt and r["scenario"] == sc and not r["gold"]]
            rng.shuffle(yes)
            rng.shuffle(no)
            k = min(len(yes), len(no)) if min(len(yes), len(no)) else max(len(yes), len(no)) // 3
            out += yes[:max(k, min(len(yes), int(1.25 * k)))] + no[:max(k, min(len(no), int(1.25 * k)))]
    rng.shuffle(out)
    return out


if __name__ == "__main__":
    out, n, tag = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    root = os.environ.get("G44_ROOT", "/root/decis/conseq/v44/boxes")
    os.makedirs(root, exist_ok=True)
    chunks = int(os.environ.get("CHUNKS", "64"))
    per = max(1, n // chunks)
    with mp.Pool(min(chunks, 96)) as pool:
        parts = pool.map(work, [(f"{tag}-{i}", per, root) for i in range(chunks)])
    exs = [e for p in parts for e in p]
    rng = random.Random(f"{tag}-rows")
    rows = []
    for e in exs:
        rows += rows_from(e, rng)
    rows = balance(rows, rng)
    with open(out, "w") as f:
        for i, r in enumerate(rows):
            r["id"] = f"{tag}-git-{i}"
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    import collections
    c = collections.Counter((r["scenario"], r["qtype"], r["gold"]) for r in rows)
    print(len(exs), "examples ->", len(rows), "rows")
    for k in sorted(c):
        print(" ", k, c[k])
