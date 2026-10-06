"""Every number the 0.1.3 docs cite, recomputed from the result files: each expected phrase must appear in each doc
that cites it. Exit code = the number of misses.

usage: python3 check_docs_013.py
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.join(os.path.dirname(HERE), "ekbasis")
RES = os.path.join(REPO, "results", "client_0.1.3")
ASK = ("ask", "deny")


def pct(k, n):
    return f"{100 * k / n:.1f}"


def main():
    S = json.load(open(os.path.join(RES, "fresh_sessions_summary.json")))
    calls = [json.loads(l) for l in open(os.path.join(RES, "fresh_sessions_calls.jsonl"))]
    off = json.load(open(os.path.join(RES, "offline_replay_summary.json")))
    so, ha = S["sonnet"], S["haiku"]
    hs = [c for c in calls if c["sid"].startswith("s") and c["arm"] == "H"]
    v12_h = sum(1 for c in hs if (c["offline_0.1.2"] or {}).get("decision") in ASK)
    hy = [c for c in calls if c["sid"].startswith("y") and c["arm"] == "H"]
    v12_hy = sum(1 for c in hy if (c["offline_0.1.2"] or {}).get("decision") in ASK)
    n = so["calls"]
    facts = {
        "sonnet_013_h": (pct(so["h_asks_013"]["k"], so["h_calls"]), f"{so['h_asks_013']['k']}/{so['h_calls']}"),
        "sonnet_012_same": (pct(v12_h, len(hs)), f"{v12_h}/{len(hs)}"),
        "sonnet_012_first": (pct(S["study_012_sonnet"]["h_asks"]["k"], S["study_012_sonnet"]["h_asks"]["n"]),),
        "sonnet_d": (pct(so["needless_013"]["d"]["k"], n), pct(so["needless_012"]["d"]["k"], n),
                     f"{so['needless_013']['d']['k']}/{n}", f"{so['needless_012']['d']['k']}/{n}"),
        "sonnet_c": (pct(so["needless_013"]["c"]["k"], n), pct(so["needless_012"]["c"]["k"], n)),
        "latency": (f"{so['latency_offline_C_first_013']['median']:.2f} s",
                    f"{so['latency_offline_C_first_012']['median']:.2f} s"),
        "done": (f"{so['done_H']['k']}/{so['done_H']['n']}", f"{so['done_C']['k']}/{so['done_C']['n']}"),
        "haiku_a": (f"{ha['class_a_caught_013']['k']}/{ha['class_a_caught_013']['n']}",),
        "haiku_kept": (f"{ha['preserved_H']['k']}/{ha['preserved_H']['n']}", f"{ha['preserved_C']['k']}/{ha['preserved_C']['n']}"),
        "haiku_h": (pct(ha["h_asks_013"]["k"], ha["h_calls"]), pct(v12_hy, len(hy))),
        "insample": (pct(off["primary"]["012"]["asks"]["k"], off["primary"]["calls"]),
                     pct(off["primary"]["013"]["asks"]["k"], off["primary"]["calls"])),
    }
    docs = {
        "results/client_0.1.3/RESULTS.md": list(facts),
        "CHANGELOG.md": ["sonnet_013_h", "sonnet_012_same", "sonnet_012_first", "sonnet_d", "sonnet_c", "latency",
                         "done", "haiku_a", "haiku_kept", "insample"],
        "README.md": ["sonnet_013_h", "sonnet_012_same", "haiku_a"],
        "MODEL_CARD.md": ["sonnet_013_h", "sonnet_012_same"],
        "docs/PLAYBOOK.md": ["sonnet_013_h", "sonnet_012_same", "haiku_a"],
    }
    words = {"haiku_a": lambda v: [v, v.replace("/", " of ")]}
    misses = 0
    for doc, keys in docs.items():
        text = open(os.path.join(REPO, doc)).read()
        for k in keys:
            for v in facts[k]:
                variants = words.get(k, lambda v: [v])(v)
                if k == "sonnet_013_h" and doc in ("README.md", "MODEL_CARD.md", "docs/PLAYBOOK.md") and "/" in v:
                    continue  # these cite the rate only
                if k == "sonnet_012_same" and doc in ("README.md", "MODEL_CARD.md", "docs/PLAYBOOK.md") and "/" in v:
                    continue
                if not any(x in text for x in variants):
                    misses += 1
                    print(f"MISSING in {doc}: {k} = {v}")
    print(json.dumps({"facts": facts, "misses": misses}))
    return misses


if __name__ == "__main__":
    sys.exit(main())
