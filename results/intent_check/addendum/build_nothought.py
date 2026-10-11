#!/usr/bin/env python3
"""Addendum (PREREG_ADDENDUM.md), part 2: the same 150 AgentDojo steps and the same attacks as the main study, with
every agent thought removed — in the history and in the next step, which becomes only the tool call (name + input).
Writes calls_nt.jsonl (not committed: TS-Bench text; its sha256 is). Our own 36 sessions carry no agent thought, so
their no-thought requests are the main study's own requests; they are not sent again.
    python3 build_nothought.py [--extbench DIR]
"""
import argparse
import hashlib
import json
import os
import random
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
import build_calls as B  # noqa: E402
from ekbasis import intent as I  # noqa: E402


def call_of(act: str) -> str:
    """The next step as a tool call only: `name(input)`, input in full (cut like any action)."""
    a = re.search(r"\(2\) Action:\s*(.*?)\n\(3\) Action Input:\s*(.*)", act, re.S)
    return f"{a[1].strip()}({a[2].strip()})" if a else act


def f0_nothought(req, tools, blocks, act):
    hist = "\n".join(f"(2) Action:{b['action']}\n(3) Action Input:{b['input']}\nObservation:{b['obs']}" for b in blocks)
    return (f"{I.PLAIN_HEAD}\n\nThe user's request:\n{req}\n\nTools available to the agent:\n{tools}\n\n"
            f"What has happened so far:\n{hist}\n\nAbout to: {I._cut(call_of(act), I.MAX_ACTION)}")


def f1_nothought(req, tools, blocks, act):
    ev = [e for e in B.events_of(blocks) if e["kind"] == "tool"]
    return I.build_state(req, ev, call_of(act), shield=True, tools=tools)


def chosen_items(extbench):
    """The main study's 150 steps, re-drawn with its seed and pool rules (checked against its calls below)."""
    items = [json.loads(l) for l in open(os.path.join(extbench, "items.jsonl")) if '"agentdojo"' in l[:200]]
    pool = {s: [] for s in B.N}
    for it in items:
        p = B.parse_tsbench(it["state"])
        if p is None or len(it["state"]) > B.MAX_STATE or B.tsbench_layout(*p) != it["state"]:
            continue
        pool[B.stratum(it)].append((it, p))
    rng = random.Random(B.SEED)
    out = []
    for s, n in B.N.items():
        out += [(s, it, p) for it, p in rng.sample(sorted(pool[s], key=lambda x: x[0]["id"]), n)]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--extbench", default=os.path.join(HERE, "..", "..", "..", "..", "extbench"))
    a = ap.parse_args()
    chosen = chosen_items(a.extbench)
    main_items = []
    for l in open(os.path.join(HERE, "..", "answers.jsonl")):
        r = json.loads(l)
        if r["set"] == "agentdojo" and r["format"] == "F0" and r["attack"] == "none":
            main_items.append(r["item"])
    assert sorted(main_items) == sorted(it["id"] for _, it, _ in chosen), "not the main study's steps"
    q0, q1 = I.question(shield=False), I.question(shield=True)
    calls = []
    for k, (s, it, (req, tools, blocks, act)) in enumerate(chosen):
        attack = B.ORDER[k % len(B.ORDER)]
        text = B.ATTACKS[attack].format(act=B.act_short(act))
        for cond, bl in (("none", blocks), (attack, B.attacked(blocks, text))):
            base = {"item": it["id"], "set": "agentdojo", "stratum": s, "label": int(it["label"] >= 0.5),
                    "cluster": it["cluster"], "attack": cond, "variant": "nothought"}
            calls.append({**base, "format": "F0", "state": f0_nothought(req, tools, bl, act), "question": q0})
            calls.append({**base, "format": "F1", "state": f1_nothought(req, tools, bl, act), "question": q1})
    for i, c in enumerate(calls):
        c["call"] = 10000 + i
    path = os.path.join(HERE, "calls_nt.jsonl")
    with open(path, "w") as f:
        for c in calls:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    leak = sum(bool(re.search(r"Thought:|The agent wrote:", c["state"])) for c in calls)
    print(f"{len(calls)} calls, {leak} with a thought left (must be 0); ~{sum(len(c['state']) for c in calls) / 3.7 / 1e6:.2f} M tokens")
    print("calls_nt.jsonl sha256", hashlib.sha256(open(path, "rb").read()).hexdigest())


if __name__ == "__main__":
    main()
