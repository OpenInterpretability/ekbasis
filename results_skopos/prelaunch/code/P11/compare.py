"""P11, GPU memory of each build: Skopos' builds under the caps Ekbasis-27B's were tested with, against Ekbasis-27B's
published memory tests (quant_w4a5_memory_tests.json: every cap up, 60 of 60 answers the same as at full memory).
Per cap: the server came up, the KV cache it got, answers the same as the same build at full memory (counts; fewer
than Ekbasis-27B's by 2 or more is flagged; any cap that does not come up is listed).
  python3 P11/compare.py --skopos <memory_tests.json> --out <json>"""
import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "common"))
from paired import counts, dump, summary  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--skopos", required=True)
ap.add_argument("--out", required=True)
a = ap.parse_args()
E = json.load(open(HERE.parent / "ref" / "handoff" / "quant_w4a5_memory_tests.json"))
S = json.load(open(a.skopos))
assert len(S) == len(E) == 4, len(S)
recs, caps = [], []
for s, e in zip(S, E):
    name = e["test"].split(" fraction")[0]
    same = s["same_answers"][0] if s["same_answers"] else 0
    recs.append(counts(f"{name}: answers the same as at full memory (of 60)", same, e["same_answers"][0], 60))
    caps.append({"cap": name, "settings": [s["settings"], e["settings"]], "up": [s["up"], e["up"]],
                 "kv_cache_tokens": [s["kv_cache_tokens"], e["kv_cache_tokens"]], "error": [s["error"], e["error"]]})
dump(a.out, {"item": "P11", "reference": "ref/handoff/quant_w4a5_memory_tests.json (Ekbasis-27B's builds, published in the cards)",
             "summary": {**summary(recs), "caps_not_up": [c["cap"] for c in caps if not c["up"][0]]},
             "measures": recs, "caps [skopos, ekbasis27b]": caps})
