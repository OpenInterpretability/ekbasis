"""WS-PI: which evaluation rows behind public numbers overlap the release lineage's training rows.

Training side: the w4a5 lineage (ekbasis-data card): ftrain_mixG3 (V42's file, which holds every earlier stage's file)
plus r4a's two mined sets, mined_wide and mined_chain.

Rules: the same as WS-F's eval_masks.py (PLAN_v45 Addendum 7), which are WS-FX's firewall rules:
  1. identical: the evaluation row's whitespace-normalized, lower-cased floor equals a training row's floor or ceiling;
  2. near duplicate: the floor's word 8-gram shingles, minus the split's own layout shingles (in >= 20% of a sample of
     its floors, plus its question texts), are >= 50% present among the training shingles, and then reach
     Jaccard >= 0.5 against a single training row's floor (top 20 candidates by shared shingles).
On top of the rules, for every hit: the training row it matched, and a structural comparison (same rules paragraph,
same starting state, same actions, same question type, same question, same answer) so a reader can tell "the same item"
from "the same family with similar contents".

usage: PYTHONHASHSEED=0 python pi_overlap.py OUT.json split [split ...]   (splits are names in /dev/shm/conseq/fac)"""
from __future__ import annotations

import collections
import json
import multiprocessing as mp
import re
import sys

FAC = "/dev/shm/conseq/fac"
TRAIN = ["ftrain_mixG3", "mined_wide", "mined_chain"]
W = re.compile(r"[a-z0-9_]+(?:[.\-'][a-z0-9_]+)*")


def words(t):
    return W.findall(t.lower())


def shingles(t, n=8):
    w = words(t)
    return {hash(" ".join(w[i:i + n])) for i in range(len(w) - n + 1)}


def norm(t):
    return re.sub(r"\s+", " ", t).strip().lower()


def text(x):
    return x if isinstance(x, str) else json.dumps(x, ensure_ascii=False)


def paragraphs(fl):
    """rules / state / actions / tail paragraphs of a prompt, by their headings."""
    out = {"rules": [], "state": [], "actions": [], "other": []}
    for p in re.split(r"\n\s*\n", fl.strip()):
        h = p.strip().split("\n", 1)[0].lower()
        if h.startswith(("current state", "state before", "estado atual")):
            out["state"].append(p.strip())
        elif h.startswith(("actions", "commands", "ações", "acoes")):
            out["actions"].append(p.strip())
        elif h.startswith(("the questions", "as perguntas")):
            out["other"].append(p.strip())
        else:
            out["rules"].append(p.strip())
    return {k: "\n\n".join(v) for k, v in out.items()}


def qkey(q):
    if isinstance(q, str):
        return norm(q)
    if isinstance(q, dict):
        return norm(q.get("instructions", "")) + " || " + " | ".join(sorted(map(str, (q.get("criteria") or {}).keys())))
    return norm(text(q))


def row_questions(r):
    """(qtype, question key, gold) triples a row asks: single-question rows and multi-question rows."""
    if "questions" in r:
        qs, qt, gs = r.get("questions") or [], r.get("qtypes") or [], r.get("golds") or []
        return [(qt[i] if i < len(qt) else None, qkey(q), str(gs[i]) if i < len(gs) else None) for i, q in enumerate(qs)]
    return [(r.get("qtype"), qkey(r.get("question")), str(r.get("gold")))]


def load(name):
    return [json.loads(l) for l in open(f"{FAC}/{name}.jsonl")]


def shard_worker(args):
    """Shingle a slice of training rows; return (global index, size, shingles that some evaluation row wants)."""
    name, lo, hi, want = args
    out = []
    with open(f"{FAC}/{name}.jsonl") as f:
        for i, line in enumerate(f):
            if i < lo:
                continue
            if i >= hi:
                break
            r = json.loads(line)
            full = shingles(text(r.get("floor", "")))
            hit = full & want
            if hit:
                out.append((name, i, len(full), list(hit)))
    return out


def main():
    out_path, splits = sys.argv[1], sys.argv[2:]
    train = {n: load(n) for n in TRAIN}
    print({n: len(v) for n, v in train.items()}, flush=True)
    long_h = collections.defaultdict(list)  # identical rule: floor and ceiling hashes -> training rows
    universe = set()
    for n, rows in train.items():
        for i, r in enumerate(rows):
            long_h[hash(norm(text(r.get("floor", ""))))].append((n, i))
            if r.get("ceiling"):
                long_h[hash(norm(text(r["ceiling"])))].append((n, i))
    for n, rows in train.items():
        for r in rows:
            universe |= shingles(text(r.get("floor", "")))
    print(f"training shingles: {len(universe)}", flush=True)

    ev, cands = {}, {}
    for sp in splits:
        rows = load(sp)
        step = max(1, len(rows) // 1500)
        c = collections.Counter()
        for r in rows[::step]:
            c.update(shingles(text(r["floor"])))
        n_s = len(rows[::step])
        lay = {g for g, k in c.items() if k >= 0.2 * n_s}
        for r in rows:
            qs = r.get("questions") if "questions" in r else [r.get("question")]
            for q in qs or []:
                lay |= shingles(q.get("instructions", "") if isinstance(q, dict) else "")
        flags, cand = [], []
        for i, r in enumerate(rows):
            fl = text(r["floor"])
            ident = long_h.get(hash(norm(fl)), [])
            f = {"i": i, "identical": bool(ident), "identical_rows": ident[:5], "near": False, "J": None, "best": None}
            if not ident:
                s = shingles(fl) - lay
                if len(s) >= 10 and sum(g in universe for g in s) / len(s) >= 0.5:
                    cand.append((i, s))
            flags.append(f)
        ev[sp], cands[sp] = (rows, flags), cand
        print(sp, len(rows), "identical", sum(f["identical"] for f in flags), "near candidates", len(cand), flush=True)

    want = set()
    for cand in cands.values():
        for _, s in cand:
            want |= s
    jobs = []
    for n, rows in train.items():
        k = 64
        size = (len(rows) + k - 1) // k
        jobs += [(n, a, min(len(rows), a + size), want) for a in range(0, len(rows), size)]
    del train
    with mp.Pool(64) as pool:
        parts = pool.map(shard_worker, jobs, chunksize=1)
    index, sizes, keys = collections.defaultdict(list), [], []
    for part in parts:
        for n, i, size, hit in part:
            k = len(sizes)
            sizes.append(size)
            keys.append((n, i))
            for g in hit:
                index[g].append(k)
    print("indexed training rows:", len(sizes), flush=True)
    train = {n: load(n) for n in TRAIN}

    report = {}
    for sp, (rows, flags) in ev.items():
        for i, s in cands[sp]:
            cnt = collections.Counter(k for g in s for k in index.get(g, []))
            best, bk = 0.0, None
            for k, inter in cnt.most_common(20):
                j = inter / (len(s) + sizes[k] - inter)
                if j > best:
                    best, bk = j, k
            flags[i]["J"] = round(best, 4)
            if best >= 0.5:
                flags[i]["near"] = True
                flags[i]["best"] = keys[bk]
        for f in flags:  # structural comparison with the matched training row
            ref = f["identical_rows"][0] if f["identical"] else (f["best"] if f["near"] else None)
            if ref is None:
                continue
            r, t = rows[f["i"]], train[ref[0]][ref[1]]
            pr, pt = paragraphs(text(r["floor"])), paragraphs(text(t.get("floor", "")))
            ev_q, tr_q = row_questions(r), row_questions(t)
            tr_keys = {(qt, qk) for qt, qk, _ in tr_q}
            tr_full = {(qt, qk, g) for qt, qk, g in tr_q}
            f.update({"train_kind": t.get("kind"), "train_world": t.get("world"),
                      "same_world": r.get("world") == t.get("world"),
                      "same_rules": pr["rules"] == pt["rules"], "same_state": pr["state"] == pt["state"],
                      "same_actions": pr["actions"] == pt["actions"],
                      "state_lines_differ": len(set(pr["state"].splitlines()) ^ set(pt["state"].splitlines())),
                      "action_lines_differ": len(set(pr["actions"].splitlines()) ^ set(pt["actions"].splitlines())),
                      "questions_shared": sum((qt, qk) in tr_keys for qt, qk, _ in ev_q),
                      "questions_shared_same_answer": sum((qt, qk, g) in tr_full for qt, qk, g in ev_q),
                      "n_questions": len(ev_q)})
        cnt = collections.Counter()
        for f in flags:
            if f["identical"]:
                cnt["identical"] += 1
            elif f["near"]:
                cnt["near"] += 1
        groups = None
        if "group" in rows[0]:
            groups = {}
            for g in sorted({r.get("group") for r in rows}):
                gi = [f for f in flags if rows[f["i"]].get("group") == g]
                groups[g] = {"rows": len(gi), "identical": sum(f["identical"] for f in gi), "near": sum(f["near"] for f in gi)}
        report[sp] = {"rows": len(rows), **cnt, "excluded_union": cnt["identical"] + cnt["near"], "by_group": groups}
        print(sp, json.dumps(report[sp]), flush=True)
    json.dump({"rules": "identical floor; near-dup 8-gram Jaccard >= 0.5 (WS-F eval_masks rules)",
               "training": TRAIN, "report": report,
               "flags": {sp: ev[sp][1] for sp in ev}}, open(out_path, "w"))


if __name__ == "__main__":
    main()
