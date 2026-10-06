"""WS-PI: side-by-side examples of the overlap between the 15,008 questions (ce_items) and the release lineage's training
rows, one or two per kind of match (overlap_public.json, pi_overlap.py's flags), picked with a fixed seed.
usage: python pi_examples.py   (in /root/decis/mission/PI; writes examples.md)"""
from __future__ import annotations

import json
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
FAC = "/dev/shm/conseq/fac"
flags = json.load(open(os.path.join(HERE, "overlap_public.json")))["flags"]["ce_items"]
items = [json.loads(l) for l in open(f"{FAC}/ce_items.jsonl")]


def kind(f):
    if f["identical"]:
        return "A. same prompt, same question" if f.get("questions_shared") else "B. same prompt, another question"
    if not f["near"]:
        return None
    if f["same_state"] and f["same_actions"]:
        return "C. near: same state and actions, other wording"
    if f["same_state"]:
        return "D. near: same start state, other actions"
    if f["same_actions"]:
        return "E. near: other start state, same actions"
    return "F. near: other state and other actions (same family template)"


rng = random.Random(0)
pool = {}
for f in flags:
    k = kind(f)
    if k:
        pool.setdefault(k, []).append(f)
want = {"A. same prompt, same question": 2, "B. same prompt, another question": 1, "C. near: same state and actions, other wording": 2,
        "D. near: same start state, other actions": 1, "E. near: other start state, same actions": 1,
        "F. near: other state and other actions (same family template)": 4}
picked = []
for k, n in want.items():
    fs = pool.get(k, [])
    fams = {}
    for f in rng.sample(fs, len(fs)):  # spread over families
        fams.setdefault(items[f["i"]]["world"], f)
    picked += [(k, f) for f in list(fams.values())[:n]]
need = {}
for _, f in picked:
    ref = f["identical_rows"][0] if f["identical"] else f["best"]
    need.setdefault(ref[0], set()).add(ref[1])
rows = {}
for n, idx in need.items():
    with open(f"{FAC}/{n}.jsonl") as fh:
        for i, line in enumerate(fh):
            if i in idx:
                rows[(n, i)] = json.loads(line)


def qtext(q):
    if isinstance(q, dict):
        return q.get("instructions", "") + " " + json.dumps(q.get("criteria") or {}, ensure_ascii=False)[:160]
    return str(q)


out = ["# Overlap examples: a test question (ce_items) beside the training row it matched\n",
       "Picked with random.Random(0), at most one per world family within each kind. Texts as stored; the training row's",
       "questions are listed with their gold answers.\n"]
for k, f in picked:
    it = items[f["i"]]
    ref = f["identical_rows"][0] if f["identical"] else f["best"]
    t = rows[tuple(ref)]
    tq = t.get("questions") or [t.get("question")]
    tg = t.get("golds") or [t.get("gold")]
    out += [f"## {k} — {it['world']}, group {it.get('group')}, item {f['i']}",
            f"Match: training file `{ref[0]}` row {ref[1]} (kind `{t.get('kind')}`), "
            + ("identical prompt" if f["identical"] else f"Jaccard {f['J']}")
            + f"; state lines that differ: {f.get('state_lines_differ')}, action lines that differ: {f.get('action_lines_differ')}.\n",
            "**Test item**\n", "```", it["floor"] if isinstance(it["floor"], str) else json.dumps(it["floor"]), "```",
            f"Question: {qtext(it.get('question'))}  → gold `{it.get('gold')}`\n",
            "**Training row**\n", "```", t["floor"] if isinstance(t["floor"], str) else json.dumps(t["floor"]), "```",
            "Questions: " + "; ".join(f"{qtext(q)} → `{g}`" for q, g in list(zip(tq, tg))[:4]) + "\n"]
open(os.path.join(HERE, "examples.md"), "w").write("\n".join(out))
print("\n".join(f"{k}: item {f['i']} {items[f['i']]['world']}" for k, f in picked))
