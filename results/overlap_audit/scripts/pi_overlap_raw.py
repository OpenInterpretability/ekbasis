"""WS-PI: pi_overlap.py's rules on the evaluation and validation splits exactly as the ekbasis-data dataset publishes
them (raw/), against the same training files.
usage: PYTHONHASHSEED=0 python pi_overlap_raw.py OUT.json split [split ...]"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pi_overlap as P  # noqa: E402

RAW = "/dev/shm/conseq/release/ekbasis-data/raw"
_load = P.load
P.load = lambda name: _load(name) if name in P.TRAIN else [json.loads(l) for l in open(f"{RAW}/{name}.jsonl")]
P.main()
