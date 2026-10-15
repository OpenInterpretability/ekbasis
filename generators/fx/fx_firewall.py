"""WS-FX firewall (SPEC.md): every FX row against every evaluation set we have.
1. identical prompts: whitespace-normalized floor hash vs every string (> 200 chars) of every evaluation item;
2. near duplicates: word 8-gram shingles of the floor (FX's own layout n-grams removed); rows whose shingles are >= 50%
   contained in the evaluation shingle set are checked item by item (Jaccard >= 0.5 against any single evaluation item);
3. actions: multi-step action sequences equal to an evaluation item's sequence; single commands shared are reported;
4. Python code: code-token 8-grams vs CRUXEval and B2 (dropped above 30% of the row's code grams).
Writes data/firewall.json (report) and data/firewall_drop.txt (ids to drop). Run with PYTHONHASHSEED=0."""
from __future__ import annotations

import collections
import glob
import gzip
import io
import json
import multiprocessing as mp
import os
import re
import sys
import tokenize

import numpy as np

assert os.environ.get("PYTHONHASHSEED") == "0", "run with PYTHONHASHSEED=0"
W = re.compile(r"[a-z0-9_]+(?:[.\-'][a-z0-9_]+)*")
FX = "/root/decis/mission/FX"


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
    """Lists of strings under action-like keys, anywhere in an item."""
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
    fac = [p for p in glob.glob("/dev/shm/conseq/fac/*.jsonl")
           if not re.search(r"/(ftrain|v44train_|mined_)", p)]
    held = glob.glob("/root/decis/mission/F/heldout/*.jsonl")
    u = glob.glob("/root/decis/mission/U/confirm/fresh_rows.jsonl") + glob.glob("/root/decis/mission/U/confirm/cap/**/*.jsonl", recursive=True)
    b3 = [p for p in glob.glob("/root/decis/mission/B3/**/*", recursive=True) if p.endswith((".json", ".jsonl"))]
    loc = [p for p in glob.glob(f"{FX}/eval_fp/local/**/*", recursive=True)
           if os.path.isfile(p) and p.endswith((".json", ".jsonl", ".py", ".md", ".txt", ".sh")) and os.path.getsize(p) < 50e6]
    return sorted(set(fac + held + u + b3 + loc))


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
            acts.add(hash(a))
            for c in a:
                acts.add(hash(("single", c)))
        if is_code:
            for s in ss:
                if len(s) > 20:
                    code |= code_grams(s)
    return path, n, np.fromiter(sh, dtype=np.int64, count=len(sh)), longs, acts, code


E = None
LONGS = set()
ACTS = set()
CODE = set()
LAYOUT = {}


def fx_action_tuple(r):
    st = r.get("struct") or {}
    for k in ("cmds", "stmts"):
        if isinstance(st.get(k), list):
            return tuple(s.strip() for s in st[k])
    if isinstance(st.get("actions"), list) and st["actions"] and isinstance(st["actions"][0], str):
        return tuple(s.strip() for s in st["actions"])
    if isinstance(st.get("action"), str):
        return (st["action"].strip(),)
    return None


def fx_code(r):
    st = r.get("struct") or {}
    parts = []
    for k in ("setup", "actions"):
        v = st.get(k)
        if isinstance(v, list):
            parts += [x for x in v if isinstance(x, str)]
    return "\n".join(parts)


def fx_worker(path):
    fam = os.path.basename(path).split("__")[0]
    lay = LAYOUT.get(fam, set())
    res = {"family": fam, "file": os.path.basename(path), "rows": 0, "identical": 0, "near_candidates": 0, "action_seq": 0,
           "code_over": 0, "single_cmds_shared": set(), "flagged": [], "drop": []}
    for line in gzip.open(path, "rt"):
        r = json.loads(line)
        res["rows"] += 1
        fl = r["floor"]
        if hash(norm(fl)) in LONGS:
            res["identical"] += 1
            res["drop"].append(r["id"])
            continue
        s = shingles(fl) - lay
        if len(s) >= 10:
            arr = np.fromiter(s, dtype=np.int64, count=len(s))
            idx = np.searchsorted(E, arr)
            idx[idx >= len(E)] = len(E) - 1
            c = float((E[idx] == arr).mean())
            if c >= 0.5:
                res["near_candidates"] += 1
                res["flagged"].append((r["id"], list(s)))
        a = fx_action_tuple(r)
        if a:
            if len(a) >= 2 and hash(a) in ACTS:
                res["action_seq"] += 1
                res["drop"].append(r["id"])
                continue
            for c1 in a:
                if hash(("single", c1)) in ACTS:
                    res["single_cmds_shared"].add(c1)
        if r.get("family") == "python" and CODE:
            g = code_grams(fx_code(r))
            if g and len(g & CODE) / len(g) > 0.3:
                res["code_over"] += 1
                res["drop"].append(r["id"])
    res["single_cmds_shared"] = sorted(res["single_cmds_shared"])[:40] + ([f"... {len(res['single_cmds_shared'])} in all"]
                                                                          if len(res["single_cmds_shared"]) > 40 else [])
    return res


def layout_for(paths):
    """FX layout shingles per family: in >= 20% of a sample of its floors, plus its question texts."""
    out = {}
    for p in paths:
        fam = os.path.basename(p).split("__")[0]
        c, n, qs = collections.Counter(), 0, set()
        for i, line in enumerate(gzip.open(p, "rt")):
            if i % 7:
                continue
            r = json.loads(line)
            c.update(shingles(r["floor"]))
            qs |= shingles(r["question"]["instructions"])
            n += 1
            if n >= 1500:
                break
        out.setdefault(fam, set())
        out[fam] |= {g for g, k in c.items() if k >= 0.2 * max(n, 1)} | qs
    return out


def main():
    global E, LONGS, ACTS, CODE, LAYOUT
    ev = eval_files()
    with mp.Pool(48) as pool:
        parts = pool.map(eval_worker, ev, chunksize=1)
    E = np.unique(np.concatenate([p[2] for p in parts])) if parts else np.zeros(1, dtype=np.int64)
    for p in parts:
        LONGS |= p[3]
        ACTS |= p[4]
        CODE |= p[5]
    ev_report = {"files": len(ev), "items": sum(p[1] for p in parts), "unique_shingles": int(len(E)),
                 "long_strings": len(LONGS), "action_keys": len(ACTS), "code_grams": len(CODE),
                 "by_dir": dict(collections.Counter(os.path.dirname(p[0]).replace(FX, "FX") for p in parts))}
    tag = sys.argv[1] if len(sys.argv) > 1 else "all"
    include = sys.argv[2].split(",") if len(sys.argv) > 2 and sys.argv[2] else None
    exclude = sys.argv[3].split(",") if len(sys.argv) > 3 and sys.argv[3] else []
    fx_files = sorted(p for p in (glob.glob(f"{FX}/data/raw/*.jsonl.gz") + glob.glob("/dev/shm/fx/raw2/*.jsonl.gz"))
                      if (include is None or any(os.path.basename(p).startswith(i) for i in include))
                      and not any(os.path.basename(p).startswith(e) for e in exclude))
    LAYOUT = layout_for(fx_files)
    with mp.Pool(48) as pool:
        results = pool.map(fx_worker, fx_files, chunksize=1)
    # phase 2: per-item Jaccard for the flagged rows
    flagged = [(fid, set(s)) for r in results for fid, s in r["flagged"]]
    near_drop = []
    if flagged:
        want = set().union(*[s for _, s in flagged])
        index = collections.defaultdict(list)
        item_sh = []
        for path in ev:
            for it in eval_items(path):
                s = shingles(" ".join(strings(it, []))) & want
                if s:
                    k = len(item_sh)
                    item_sh.append((path, s, len(shingles(" ".join(strings(it, []))))))
                    for g in s:
                        index[g].append(k)
        for fid, s in flagged:
            cand = collections.Counter(k for g in s for k in index.get(g, []))
            best = 0.0
            for k, inter in cand.most_common(20):
                j = inter / (len(s) + item_sh[k][2] - inter)
                best = max(best, j)
            if best >= 0.5:
                near_drop.append(fid)
    drop = sorted(set(sum((r["drop"] for r in results), [])) | set(near_drop))
    rep = {"eval": ev_report, "families": {}, "near_duplicates_dropped": len(near_drop), "dropped_total": len(drop)}
    for r in results:
        f = rep["families"].setdefault(r["family"], {"rows": 0, "identical": 0, "near_candidates": 0, "action_seq": 0,
                                                       "code_over": 0, "single_cmds_shared": []})
        for k in ("rows", "identical", "near_candidates", "action_seq", "code_over"):
            f[k] += r[k]
        f["single_cmds_shared"] = (f["single_cmds_shared"] + r["single_cmds_shared"])[:40]
    rep["fx_files"] = [os.path.basename(p) for p in fx_files]
    json.dump(rep, open(f"{FX}/data/firewall_{tag}.json", "w"), indent=1)
    open(f"{FX}/data/firewall_drop_{tag}.txt", "w").write("\n".join(drop) + "\n")
    print(json.dumps({k: v for k, v in rep.items() if k != "families"}, indent=1))
    print(json.dumps({f: {k: v for k, v in d.items() if k != "single_cmds_shared"} for f, d in rep["families"].items()}))


if __name__ == "__main__":
    main()
