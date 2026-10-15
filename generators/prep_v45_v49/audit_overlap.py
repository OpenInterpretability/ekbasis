"""Overlap audit of the ACTUAL training files of V45/V46/V47's runs against every evaluation set (the coordinator's
integrity request after WS-FX's firewall found that F's Python generator repeats prompts across seeds).
Rules are WS-FX's firewall rules (FX/factory/fx_firewall.py), with attribution to the evaluation file hit:
1. identical: the whitespace-normalized, lower-cased floor (and ceiling: the "read" kind trains on it) equals a string of
   more than 200 characters of an evaluation item;
2. near duplicate: the floor's word 8-gram shingles (minus the training file's own layout shingles: in >= 20% of a sample
   of its floors, plus its question texts) are >= 50% contained in the evaluation shingle set, and then reach Jaccard
   >= 0.5 against a single evaluation item;
3. actions: a sequence of 2+ actions equal to an evaluation item's sequence (single shared commands are only reported);
4. Python code: code-token 8-grams of the row's setup + actions overlap CRUXEval / B2 code grams above 30%.
Training side: ftrain_mixG3 (TRAIN of every run), mined_chain, v45_v44git, v45rx_{git,py,shell,sql}, v46_anchor,
v47_v44git, v47rx_{git,shell,sql}, v47_softreplay.
Evaluation side: every test/validation/buffer split in /dev/shm/conseq/fac (training files and gold sidecars excluded),
F/heldout (capability map + CRUXEval), U's fresh_rows and cap, B3, and the local copies WS-FX collected (X, RA, PC,
real_terminal, B1, B2).
PYTHONHASHSEED=0 /opt/sglang/bin/python audit_overlap.py   -> v47/audit_overlap.json"""
from __future__ import annotations

import collections
import glob
import io
import json
import multiprocessing as mp
import os
import re
import sys
import tokenize

import numpy as np

assert os.environ.get("PYTHONHASHSEED") == "0", "run with PYTHONHASHSEED=0"
FAC = "/dev/shm/conseq/fac"
TRAIN = ["ftrain_mixG3", "mined_chain", "v45_v44git", "v45rx_git", "v45rx_py", "v45rx_shell", "v45rx_sql", "v46_anchor",
         "v47_v44git", "v47rx_git", "v47rx_shell", "v47rx_sql", "v47_softreplay"]
RUN_FILES = {
    "v45g": ["ftrain_mixG3", "mined_chain", "v45_v44git", "v45rx_git"],
    "v45a": ["ftrain_mixG3", "mined_chain", "v45_v44git", "v45rx_git", "v45rx_py", "v45rx_shell", "v45rx_sql"],
    "v45b": ["ftrain_mixG3", "mined_chain", "v45_v44git", "v45rx_git", "v45rx_py", "v45rx_shell", "v45rx_sql"],
    "v45d": ["ftrain_mixG3", "mined_chain", "v45_v44git", "v45rx_git", "v45rx_shell", "v45rx_sql"],
    "v46a/b/c": ["ftrain_mixG3", "mined_chain", "v45_v44git", "v45rx_git", "v45rx_shell", "v45rx_sql", "v46_anchor"],
    "v47a/b": ["ftrain_mixG3", "mined_chain", "v47_v44git", "v47rx_git", "v47rx_shell", "v47rx_sql", "v47_softreplay"],
}
NOT_EVAL = re.compile(r"^(ftrain|mined_|v44train_|v45rx_|v45_v44git|v46_anchor|v47rx_|v47_v44git|v47_softreplay|gold0_|gold_fix_)")
W = re.compile(r"[a-z0-9_]+(?:[.\-'][a-z0-9_]+)*")


def words(t):
    return W.findall(t.lower())


def shingles(t, n=8):
    w = words(t)
    return {hash(" ".join(w[i:i + n])) for i in range(len(w) - n + 1)}


def norm(t):
    return re.sub(r"\s+", " ", t).strip().lower()


def strings(x, out):
    if isinstance(x, str):
        out.append(x)
    elif isinstance(x, dict):
        for v in x.values():
            strings(v, out)
    elif isinstance(x, list):
        for v in x:
            strings(v, out)
    return out


def actions_of(x, out):
    if isinstance(x, dict):
        for k, v in x.items():
            if k in ("cmds", "commands", "stmts", "statements", "actions", "plan", "steps") and isinstance(v, list) and \
                    v and all(isinstance(s, str) for s in v):
                out.append(tuple(s.strip() for s in v))
            else:
                actions_of(v, out)
    elif isinstance(x, list):
        for v in x:
            actions_of(v, out)
    return out


def code_grams(src, n=8):
    toks = []
    try:
        for t in tokenize.generate_tokens(io.StringIO(src).readline):
            if t.type in (tokenize.NAME, tokenize.OP, tokenize.NUMBER, tokenize.STRING):
                toks.append(t.string)
    except Exception:  # noqa: BLE001
        toks = re.findall(r"\w+|[^\s\w]", src)
    return {hash(" ".join(toks[i:i + n])) for i in range(len(toks) - n + 1)}


def eval_files():
    fac = [p for p in glob.glob(f"{FAC}/*.jsonl") if not NOT_EVAL.match(os.path.basename(p))]
    held = glob.glob("/root/decis/mission/F/heldout/*.jsonl")
    u = glob.glob("/root/decis/mission/U/confirm/fresh_rows.jsonl") + glob.glob("/root/decis/mission/U/confirm/cap/**/*.jsonl", recursive=True)
    b3 = [p for p in glob.glob("/root/decis/mission/B3/**/*", recursive=True) if p.endswith((".json", ".jsonl"))]
    loc = [p for p in glob.glob("/root/decis/mission/FX/eval_fp/local/**/*", recursive=True)
           if os.path.isfile(p) and p.endswith((".json", ".jsonl", ".py", ".md", ".txt", ".sh")) and os.path.getsize(p) < 50e6]
    return sorted(set(fac + held + u + b3 + loc))


def tag_of(p):
    for pre, t in (("/dev/shm/conseq/fac/", "fac:"), ("/root/decis/mission/F/heldout/", "heldout:"), ("/root/decis/mission/", "")):
        if p.startswith(pre):
            return t + p[len(pre):]
    return p


def eval_items(path):
    if path.endswith(".jsonl"):
        for line in open(path, errors="replace"):
            try:
                yield json.loads(line)
            except Exception:  # noqa: BLE001
                continue
    elif path.endswith(".json"):
        try:
            d = json.load(open(path, errors="replace"))
        except Exception:  # noqa: BLE001
            return
        if isinstance(d, list):
            yield from d
        elif isinstance(d, dict):
            yield d
    else:
        yield open(path, errors="replace").read()


def eval_worker(path):
    sh, longs, acts, code = set(), set(), set(), set()
    is_code = ("cruxeval" in path) or ("/B2/" in path)
    n = 0
    for it in eval_items(path):
        n += 1
        ss = strings(it, [])
        sh |= shingles(" ".join(ss))
        for s in ss:
            if len(s) > 200:
                longs.add(hash(norm(s)))
        for a in actions_of(it, []):
            if len(a) >= 2:
                acts.add(hash(a))
            for c in a:
                acts.add(hash(("single", c)))
        if is_code:
            for s in ss:
                if len(s) > 20:
                    code |= code_grams(s)
    return path, n, np.fromiter(sh, dtype=np.int64, count=len(sh)), longs, acts, code


E = None
LONGS = {}
ACTS = {}
CODE = set()
LAYOUT = {}


def text(x):
    return x if isinstance(x, str) else json.dumps(x, ensure_ascii=False)


def action_tuple(r):
    st = r.get("struct") or {}
    for k in ("cmds", "stmts"):
        if isinstance(st.get(k), list):
            return tuple(s.strip() for s in st[k])
    if isinstance(st.get("actions"), list) and st["actions"] and isinstance(st["actions"][0], str):
        return tuple(s.strip() for s in st["actions"])
    return None


def code_of(r):
    st = r.get("struct") or {}
    parts = []
    for k in ("setup", "actions"):
        v = st.get(k)
        if isinstance(v, list):
            parts += [x for x in v if isinstance(x, str)]
    return "\n".join(parts)


def train_rows(name):
    """The rows a training file holds; for the slimmed copies in fac (no struct), the factory's packed file with struct."""
    src = {"v45rx_py": "/root/decis/mission/F/data/train_python.jsonl", "v45rx_git": "/root/decis/mission/F/data/train_git.jsonl",
           "v45rx_sql": "/root/decis/mission/F/data/train_sql.jsonl", "v45rx_shell": "/root/decis/mission/F/data/train_shell_c012.jsonl"}
    path = src.get(name, f"{FAC}/{name}.jsonl")
    for line in open(path):
        yield json.loads(line)


def train_worker(job):
    name, part, nparts = job
    lay = LAYOUT.get(name, set())
    res = {"file": name, "rows": 0, "identical": collections.Counter(), "near_candidates": 0, "action_seq": collections.Counter(),
           "code_over": 0, "single_cmds_shared": set(), "flagged": [], "ids": collections.defaultdict(list)}
    for i, r in enumerate(train_rows(name)):
        if i % nparts != part:
            continue
        res["rows"] += 1
        rid = r.get("id") or f"{name}:{i}"
        fl = text(r.get("floor", ""))
        hit = LONGS.get(hash(norm(fl))) or (LONGS.get(hash(norm(text(r["ceiling"])))) if r.get("ceiling") else None)
        if hit:
            for t in hit:
                res["identical"][t] += 1
            res["ids"]["identical"].append(rid)
            continue
        s = shingles(fl) - lay
        if len(s) >= 10:
            arr = np.fromiter(s, dtype=np.int64, count=len(s))
            idx = np.searchsorted(E, arr)
            idx[idx >= len(E)] = len(E) - 1
            if float((E[idx] == arr).mean()) >= 0.5:
                res["near_candidates"] += 1
                res["flagged"].append((rid, list(s)))
        a = action_tuple(r)
        if a:
            if len(a) >= 2 and hash(a) in ACTS:
                for t in ACTS[hash(a)]:
                    res["action_seq"][t] += 1
                res["ids"]["action_seq"].append(rid)
            for c1 in a:
                if hash(("single", c1)) in ACTS:
                    res["single_cmds_shared"].add(c1)
        if r.get("family") == "python" and CODE:
            g = code_grams(code_of(r))
            if g and len(g & CODE) / len(g) > 0.3:
                res["code_over"] += 1
                res["ids"]["code_over"].append(rid)
    res["single_cmds_shared"] = sorted(res["single_cmds_shared"])
    return res


def layout_for(names):
    out = {}
    for name in names:
        c, n, qs = collections.Counter(), 0, set()
        for i, r in enumerate(train_rows(name)):
            if i % 7:
                continue
            c.update(shingles(text(r.get("floor", ""))))
            q = r.get("question") or {}
            qs |= shingles(q.get("instructions", "") if isinstance(q, dict) else "")
            n += 1
            if n >= 1500:
                break
        out[name] = {g for g, k in c.items() if k >= 0.2 * max(n, 1)} | qs
    return out


def main():
    global E, LONGS, ACTS, CODE, LAYOUT
    ev = eval_files()
    with mp.Pool(48) as pool:
        parts = pool.map(eval_worker, ev, chunksize=1)
    E = np.unique(np.concatenate([p[2] for p in parts if len(p[2])])) if parts else np.zeros(1, dtype=np.int64)
    for p in parts:
        t = tag_of(p[0])
        for h in p[3]:
            LONGS.setdefault(h, set()).add(t)
        for h in p[4]:
            ACTS.setdefault(h, set()).add(t)
        CODE |= p[5]
    ev_report = {"files": len(ev), "items": sum(p[1] for p in parts), "unique_shingles": int(len(E)),
                 "long_strings": len(LONGS), "code_grams": len(CODE),
                 "by_dir": dict(collections.Counter(tag_of(os.path.dirname(p[0]) + "/") for p in parts))}
    print(json.dumps(ev_report)[:2000], flush=True)
    LAYOUT = layout_for(TRAIN)
    jobs = [(n, k, 16 if n == "ftrain_mixG3" else 1) for n in TRAIN for k in range(16 if n == "ftrain_mixG3" else 1)]
    with mp.Pool(48) as pool:
        results = pool.map(train_worker, jobs, chunksize=1)
    flagged = [(r["file"], fid, set(s)) for r in results for fid, s in r["flagged"]]
    near = collections.defaultdict(collections.Counter)
    near_ids = collections.defaultdict(list)
    if flagged:
        want = set().union(*[s for _, _, s in flagged])
        index, item_sh = collections.defaultdict(list), []
        for path in ev:
            for it in eval_items(path):
                full = shingles(" ".join(strings(it, [])))
                s = full & want
                if s:
                    k = len(item_sh)
                    item_sh.append((tag_of(path), len(full)))
                    for g in s:
                        index[g].append(k)
        for fname, fid, s in flagged:
            cand = collections.Counter(k for g in s for k in index.get(g, []))
            best, bt = 0.0, None
            for k, inter in cand.most_common(20):
                j = inter / (len(s) + item_sh[k][1] - inter)
                if j > best:
                    best, bt = j, item_sh[k][0]
            if best >= 0.5:
                near[fname][bt] += 1
                near_ids[fname].append(fid)
    rep = {"eval": ev_report, "files": {}}
    for r in results:
        f = rep["files"].setdefault(r["file"], {"rows": 0, "identical": collections.Counter(), "near_candidates": 0,
                                                "action_seq": collections.Counter(), "code_over": 0, "single_cmds_shared": set(),
                                                "ids": collections.defaultdict(list)})
        f["rows"] += r["rows"]
        f["identical"].update(r["identical"])
        f["near_candidates"] += r["near_candidates"]
        f["action_seq"].update(r["action_seq"])
        f["code_over"] += r["code_over"]
        f["single_cmds_shared"] |= set(r["single_cmds_shared"])
        for k, v in r["ids"].items():
            f["ids"][k] += v
    for name, f in rep["files"].items():
        f["near_dup"] = dict(near.get(name, {}))
        f["ids"]["near_dup"] = near_ids.get(name, [])
        f["identical"] = dict(f["identical"])
        f["action_seq"] = dict(f["action_seq"])
        f["single_cmds_shared"] = sorted(f["single_cmds_shared"])[:30]
        f["n_contaminated"] = len(set(f["ids"]["identical"]) | set(f["ids"]["near_dup"]) | set(f["ids"]["action_seq"]) | set(f["ids"]["code_over"]))
        f["ids"] = {k: v[:50] for k, v in f["ids"].items()}
    suites = {}
    for run, files in RUN_FILES.items():
        hit = collections.Counter()
        for n in files:
            f = rep["files"].get(n, {})
            for d in ("identical", "near_dup", "action_seq"):
                hit.update(f.get(d, {}))
        suites[run] = dict(hit)
    rep["runs"] = suites
    json.dump(rep, open("/root/decis/mission/F/v47/audit_overlap.json", "w"), indent=1, default=list)
    for name, f in rep["files"].items():
        print(name, {k: f[k] for k in ("rows", "n_contaminated", "identical", "near_dup", "action_seq", "code_over")}, flush=True)
    print("RUNS", json.dumps(suites))


if __name__ == "__main__":
    main()
