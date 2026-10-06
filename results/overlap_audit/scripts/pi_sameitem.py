"""WS-PI: for every published evaluation and validation split (the configs of the ekbasis-data card), the rows that
repeat a training row of the release lineage (ftrain_mixG3, mined_wide, mined_chain): the same prompt (floor, or the
training row's hindsight prompt), and among those the same question, and the same question with the same answer. This
is the dataset card's own test ("share the prompt and the question") applied to every split; pi_overlap.py gives the
near duplicates.
usage: python pi_sameitem.py   (in /root/decis/mission/PI; writes sameitem.json)"""
from __future__ import annotations

import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from pi_overlap import FAC, TRAIN, norm, text  # noqa: E402


def row_questions(r):
    """(question, answer) pairs of a row; a question is its whole typed JSON (instructions, options or criteria)."""
    qs = r["questions"] if "questions" in r else [r.get("question")]
    gs = r.get("golds") if "questions" in r else [r.get("gold")]
    gs = list(gs or []) + [None] * (len(qs or []) - len(gs or []))
    return [(norm(q) if isinstance(q, str) else norm(json.dumps(q, sort_keys=True, ensure_ascii=False)), str(g))
            for q, g in zip(qs or [], gs)]

RAW = "/dev/shm/conseq/release/ekbasis-data/raw"  # the exact files the dataset publishes
SPLITS = ["ce_items", "multi_test_trainfam", "multi_test_testfam", "ftest_family", "git3_test_known", "git3_test_held",
          "git2_test_known", "git2_test_held", "guard_known", "guard_held", "m3val", "fval_git", "fval_git2", "fval_git3"]

prompt_q = collections.defaultdict(set)  # prompt hash -> {(question key, answer)}
for n in TRAIN:
    for line in open(f"{FAC}/{n}.jsonl"):
        r = json.loads(line)
        qs = set(row_questions(r))
        prompt_q[hash(norm(text(r.get("floor", ""))))] |= qs
        if r.get("ceiling"):
            prompt_q[hash(norm(text(r["ceiling"])))] |= qs
res = {}
for sp in SPLITS:
    c = collections.Counter()
    for line in open(f"{RAW}/{sp}.jsonl"):
        r = json.loads(line)
        c["rows"] += 1
        h = hash(norm(text(r["floor"])))
        if h not in prompt_q:
            continue
        c["same_prompt"] += 1
        tq = prompt_q[h]
        tk = {k for k, _ in tq}
        ev = row_questions(r)
        c["same_prompt_same_question"] += any(qk in tk for qk, _ in ev)
        c["same_prompt_same_question_same_answer"] += any((qk, g) in tq for qk, g in ev)
    res[sp] = dict(c)
    print(sp, res[sp], flush=True)
json.dump(res, open(os.path.join(HERE, "sameitem.json"), "w"), indent=1)
