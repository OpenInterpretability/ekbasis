#!/usr/bin/env python3
"""The hosted-API scorecard's items (ekbasis repository scorecard/scorecard.py at 941968e, `fetch`), rebuilt for the D8
audit as rows with a "floor" (the state text the scorecard sends), so audit_overlap_skopos.py can add them as sets
scorecard_<suite> with its rules unchanged.

- git3_known, git3_held, guard_held, worlds: scorecard.py's own sampling (random.Random("scorecard|<suite>").sample of
  ekbasis-data raw/<set>.jsonl, here the copies of ekbasis-data@b455316fce in hf/ekbasis-data/raw, the dataset's current
  revision); "src_i" = the row's index in the parent set.
- intent: the 300 of ekbasis-cookbook studies/llm-judge-intent/items.jsonl (main, fetched to hf/scorecard/
  intent_source.jsonl; sha256 recorded below) that scorecard.py samples with random.Random("scorecard|intent").
- chains: the step prompts `simulate` sends for scorecard.py's chains (2 worlds × 8 chains × 15 actions), built with
  ekbasis.prompts.world_state from the TRUE state before each action: the prompt simulate sends at a step whose state it
  predicted right, or after a look (observe returns the true state). Steps after an unobserved wrong prediction differ.
usage: python3 build_scorecard_items.py   (writes hf/scorecard/items/*.jsonl)"""
import hashlib
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SC = os.path.join(HERE, "hf", "scorecard")
RAW = os.path.join(HERE, "hf", "ekbasis-data", "raw")
OUT = os.path.join(SC, "items")
sys.path.insert(0, os.path.join(SC, "src"))  # scorecard.py and ekbasis/prompts.py of the ekbasis repository at 941968e
from prompts import world_state  # noqa: E402
import scorecard as S  # noqa: E402

INTENT_SHA256 = "60e3cf9246cc98956a07e17b38431199b7b1fc58265174fcaa3de04b6618c828"


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, (src, n) in S.SUITES.items():
        rows = [json.loads(l) for l in open(f"{RAW}/{src}.jsonl")]
        idx = list(range(len(rows)))
        # scorecard.py samples the rows themselves; sampling their indices with the same Random draws the same positions
        pick = random.Random(f"scorecard|{name}").sample(idx, min(n, len(rows)))
        with open(f"{OUT}/{name}.jsonl", "w") as f:
            for i, k in enumerate(pick):
                r = rows[k]
                f.write(json.dumps({"i": i, "src_i": k, "floor": r["floor"], "question": r["question"], "gold": r["gold"],
                                    "world": r.get("world"), "qtype": r.get("qtype")}) + "\n")
        print(name, len(pick))
    raw = open(f"{SC}/intent_source.jsonl", "rb").read()
    assert hashlib.sha256(raw).hexdigest() == INTENT_SHA256, "intent_source.jsonl changed"
    rows = random.Random("scorecard|intent").sample([json.loads(l) for l in raw.decode().splitlines()], 300)
    with open(f"{OUT}/intent.jsonl", "w") as f:
        for i, r in enumerate(rows):
            f.write(json.dumps({"i": i, "id": r.get("id"), "floor": r["state"], "question": r["question"],
                                "gold": r["kind"] == "attack", "world": r["kind"]}) + "\n")
    print("intent", len(rows))
    n = 0
    with open(f"{OUT}/chains.jsonl", "w") as f:
        for name, w in S.chain_worlds().items():
            for c in range(8):
                rng = random.Random(f"scorecard|chain|{name}|{c}")
                s = w["start"](rng)
                acts = [rng.choice(w["actions"]) for _ in range(15)]
                for t, a in enumerate(acts):
                    f.write(json.dumps({"i": n, "chain": f"{name}|{c}", "step": t + 1, "world": name,
                                        "floor": world_state(w["rules"], w["render"](s), [a])}) + "\n")
                    s = w["step"](s, a)
                    n += 1
    print("chains (step prompts)", n)


if __name__ == "__main__":
    main()
