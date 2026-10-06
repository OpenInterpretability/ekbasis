"""WS-U firewall (coordinator, 06/10): every WS-U evaluation item against EVERY training file of the released w4a5's
lineage, with WS-FX's firewall rules (FX/factory/fx_firewall.py, as used by F's Addendum 7 audit), item by item so the
verdicts can be recomputed on the clean subset. CPU only; reads, never writes, the evaluation folders.

Evaluation side: dev (WS-P's dataset, 29,029 rows), confirm-1, confirm-2 (kept rows), confirm-3 (when its rows exist).
The unit is the EVIDENCE: the state text the server read, the field that training rows store as "floor". Rows of the
same scenario share it.

Training side: every ftrain*.jsonl in /dev/shm/conseq/fac, which is a superset of the lineage (V42 trained on
ftrain_mixG3 = ftrain_mixG2M + git3_train from V41's checkpoint, whose chain runs through ftrain_mixG2M,
ftrain_mixG2, ftrain_multi, ftrain_mix, ftrain_m3only and earlier), plus mined_wide and mined_chain (r4a). Hits are
attributed to each file, so the lineage files can be read apart.

Rules (FX):
  1. identical: whitespace-normalised, lower-cased floor (or ceiling) == an evaluation evidence (> 200 characters);
  2. near-duplicate: the floor's word 8-gram shingles, minus the training file's layout shingles (in >= 20% of a
     sample of its floors, plus its question texts), are >= 50% contained in the evaluation shingle set; then
     Jaccard >= 0.5 against a single evaluation evidence. Exact Jaccard on the candidates; the candidates are ranked
     by shared shingles that occur in <= 2,000 evidences (ranking only).
  3. action sequences and 4. Python code: FX applies them to rows with a "struct" field; the lineage files have none
     (checked), so they do not apply.
PYTHONHASHSEED=0 python3 fw_u.py [dev,c1,c2,c3 | ce]  ->  fw_u_<sets>.json (summary), fw_u_flags_<sets>.jsonl (one line
per flagged evidence: hits by rule and file). "ce" (the paper's 15,008 items) is the POSITIVE CONTROL: F's audit found it
overlaps ftrain_mixG3, so this code must find it too."""
from __future__ import annotations

import collections
import glob
import json
import multiprocessing as mp
import os
import re
import sys

import numpy as np

assert os.environ.get("PYTHONHASHSEED") == "0", "run with PYTHONHASHSEED=0"
HERE = os.path.dirname(os.path.abspath(__file__))
U = os.path.dirname(HERE)
FAC = "/dev/shm/conseq/fac"
SETS = {"dev": "/root/decis/mission/P/data/dataset.jsonl", "c1": f"{U}/confirm/fresh_rows.jsonl",
        "c2": f"{U}/confirm2/fresh_rows.jsonl", "c3": f"{U}/confirm3/fresh_rows.jsonl",
        "ce": "/dev/shm/conseq/fac/ce_items.jsonl"}  # ce: POSITIVE CONTROL only (F found it overlaps ftrain_mixG3)
TRAIN = sorted(os.path.basename(p)[:-6] for p in glob.glob(f"{FAC}/ftrain*.jsonl")) + ["mined_wide", "mined_chain"]
LINEAGE = ["ftrain_mixG3", "ftrain_mixG2M", "ftrain_mixG2", "ftrain_multi", "ftrain_mix", "ftrain_m3only", "mined_wide", "mined_chain"]
W = re.compile(r"[a-z0-9_]+(?:[.\-'][a-z0-9_]+)*")
RANK_CAP = 2000


def words(t):
    return W.findall(t.lower())


def shingles(t, n=8):
    w = words(t)
    return {hash(" ".join(w[i:i + n])) for i in range(len(w) - n + 1)}


def norm(t):
    return re.sub(r"\s+", " ", t).strip().lower()


def text(x):
    return x if isinstance(x, str) else json.dumps(x, ensure_ascii=False)


def evidence_of(prompt):
    user = prompt.split("<|im_start|>user\n", 1)[1].split("<|im_end|>", 1)[0]
    return json.loads(user)["evidence"]


# ---------------------------------------------------------------- evaluation side (built once, shared by fork)
EV_TEXT, EV_SH, EV_LEN = [], [], []
LONGS, POST = {}, {}
E = None


def build_eval(names):
    rows_by_ev = collections.defaultdict(list)
    counts = collections.Counter()
    for name in names:
        path = SETS[name]
        if not os.path.exists(path):
            print(f"{name}: {path} missing, skipped", flush=True)
            continue
        for l in open(path):
            r = json.loads(l)
            if name not in ("dev", "ce") and r.get("exclude") is not None:
                continue
            if name == "ce":
                ev, suite, rid, conf = text(r["floor"]), f"ce_{r.get('group')}", f"ce:{len(rows_by_ev)}", True
            else:
                ev, suite, rid, conf = evidence_of(r["prompt"]), r["suite"], r.get("rid") or str(r.get("qid")), \
                    bool((r.get("conf") or 0) >= 0.9)
            rows_by_ev[ev].append((name, suite, rid, conf))
            counts[(name, suite)] += 1
    for ev, rs in rows_by_ev.items():
        k = len(EV_TEXT)
        EV_TEXT.append(ev)
        sh = shingles(ev)
        EV_SH.append(sh)
        EV_LEN.append(len(sh))
        if len(ev) > 200:
            LONGS.setdefault(hash(norm(ev)), []).append(k)
        for g in sh:
            POST.setdefault(g, []).append(k)
    return rows_by_ev, counts


def layout_for(name):
    c, n, qs = collections.Counter(), 0, set()
    for i, line in enumerate(open(f"{FAC}/{name}.jsonl")):
        if i % 7:
            continue
        r = json.loads(line)
        c.update(shingles(text(r.get("floor", ""))))
        q = r.get("question") or {}
        qs |= shingles(q.get("instructions", "") if isinstance(q, dict) else "")
        n += 1
        if n >= 1500:
            break
    return {g for g, k in c.items() if k >= 0.2 * max(n, 1)} | qs


LAYOUT = {}


def worker(job):
    name, part, nparts = job
    lay = LAYOUT[name]
    ident, near = collections.defaultdict(int), collections.defaultdict(float)
    rows = has_struct = cands = 0
    best_js = []
    seen = set()
    for i, line in enumerate(open(f"{FAC}/{name}.jsonl")):
        if i % nparts != part:
            continue
        r = json.loads(line)
        rows += 1
        has_struct += "struct" in r
        fl = text(r.get("floor", ""))
        key = hash(fl)
        if key in seen:  # the same floor twice in this file: one check is enough
            continue
        seen.add(key)
        for t in (fl, text(r["ceiling"]) if r.get("ceiling") else None):
            if t:
                for k in LONGS.get(hash(norm(t)), []):
                    ident[k] += 1
        s = shingles(fl) - lay
        if len(s) < 10:
            continue
        arr = np.fromiter(s, dtype=np.int64, count=len(s))
        idx = np.searchsorted(E, arr)
        idx[idx >= len(E)] = len(E) - 1
        if float((E[idx] == arr).mean()) < 0.5:
            continue
        cands += 1
        cnt = collections.Counter()
        for g in s:
            p = POST.get(g)
            if p is not None and len(p) <= RANK_CAP:
                cnt.update(p)
        best = 0.0
        for k, _ in cnt.most_common(50):
            inter = len(s & EV_SH[k])
            j = inter / (len(s) + EV_LEN[k] - inter)
            best = max(best, j)
            if j >= 0.5:
                near[k] = max(near[k], j)
        best_js.append(round(best, 4))
    return name, rows, has_struct, cands, dict(ident), dict(near), best_js


def main():
    global E, LAYOUT
    names = (sys.argv[1] if len(sys.argv) > 1 else "dev,c1,c2").split(",")
    rows_by_ev, counts = build_eval(names)
    E = np.unique(np.fromiter((g for s in EV_SH for g in s), dtype=np.int64))
    print(f"evaluation: {sum(counts.values())} rows, {len(EV_TEXT)} distinct evidences, {len(E)} shingles; "
          f"training files: {len(TRAIN)}", flush=True)
    with mp.Pool(min(len(TRAIN), 32)) as pool:
        LAYOUT = dict(zip(TRAIN, pool.map(layout_for, TRAIN)))
    jobs = []
    for name in TRAIN:
        size = os.path.getsize(f"{FAC}/{name}.jsonl")
        n = max(1, min(16, int(size // 20e6)))
        jobs += [(name, k, n) for k in range(n)]
    with mp.Pool(48) as pool:
        res = pool.map(worker, jobs, chunksize=1)
    per_file = collections.defaultdict(lambda: {"rows": 0, "with_struct": 0, "near_candidates": 0})
    hits = collections.defaultdict(lambda: {"identical": set(), "near": {}})
    for name, rows, st, cands, ident, near, best_js in res:
        f = per_file[name]
        f["rows"] += rows
        f["with_struct"] += st
        f["near_candidates"] += cands
        f.setdefault("best_j", []).extend(best_js)
        for k in ident:
            hits[k]["identical"].add(name)
        for k, j in near.items():
            hits[k]["near"][name] = max(hits[k]["near"].get(name, 0), j)
    for f in per_file.values():
        b = sorted(f.pop("best_j", []))
        f["candidate_best_jaccard"] = {"n": len(b), "max": b[-1] if b else None,
                                       "p99": b[int(0.99 * (len(b) - 1))] if b else None,
                                       "median": b[len(b) // 2] if b else None, "n_at_least_0.4": sum(x >= 0.4 for x in b)}
    summary = {"sets": names, "eval_rows": {f"{a}|{b}": n for (a, b), n in sorted(counts.items())},
               "distinct_evidences": len(EV_TEXT), "training": {k: dict(v) for k, v in per_file.items()},
               "lineage_files": LINEAGE, "by_set_suite": {}}
    tally = collections.defaultdict(lambda: collections.Counter())
    tag = "_".join(names)
    with open(os.path.join(HERE, f"fw_u_flags_{tag}.jsonl"), "w") as out:
        for k, h in hits.items():
            lin = bool(h["identical"] & set(LINEAGE)) or bool(set(h["near"]) & set(LINEAGE))
            rec = {"evidence_sha": __import__("hashlib").sha256(EV_TEXT[k].encode()).hexdigest(),
                   "identical": sorted(h["identical"]), "near": {n: round(j, 3) for n, j in sorted(h["near"].items())},
                   "lineage_hit": lin, "rows": rows_by_ev[EV_TEXT[k]]}
            out.write(json.dumps(rec) + "\n")
            for name, suite, rid, conf in rows_by_ev[EV_TEXT[k]]:
                t = tally[f"{name}|{suite}"]
                t["rows_hit_any_file"] += 1
                t["rows_hit_lineage"] += lin
                t["rows_identical"] += bool(h["identical"])
                t["rows_near_only"] += (not h["identical"]) and bool(h["near"])
                t["confident_rows_hit_lineage"] += lin and conf
    for key, n in sorted(summary["eval_rows"].items()):
        summary["by_set_suite"][key] = {"rows": n, **dict(tally.get(key, {}))}
    json.dump(summary, open(os.path.join(HERE, f"fw_u_{tag}.json"), "w"), indent=1)
    print(json.dumps(summary["by_set_suite"], indent=1))
    print(json.dumps({k: v for k, v in summary["training"].items()}, indent=0)[:3000])


if __name__ == "__main__":
    main()
