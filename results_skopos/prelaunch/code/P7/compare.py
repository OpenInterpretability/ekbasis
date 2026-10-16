"""P7, chains that start from an image (60 items: containers and lamps, 10-20 actions): Skopos against Ekbasis-27B's
per-item results of the release run (image_chain.json of the rig's output folder release_w4a5/, kept in the hand-off
eval_handoff/release_w4a5/ but not published; its totals are the published release_image_chain.out). Paired by item
(position i = seed 7000 + i); 60 < 100: counts. Identity: each item's world and number of actions must match.
  python3 P7/compare.py --skopos <dir> --out <json>"""
import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "common"))
from paired import dump, paired, summary  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--skopos", required=True)
ap.add_argument("--out", required=True)
a = ap.parse_args()
E = json.load(open(HERE.parent / "ref" / "handoff" / "image_chain_w4a5.json"))
S = json.load(open(pathlib.Path(a.skopos) / "image_chain.json"))
assert [(r["fam"], r["n_act"]) for r in S] == [(r["fam"], r["n_act"]) for r in E], "items differ"
recs = []
for k, name in (("text", "final answer from a text start"), ("image", "final answer from the image"),
                ("image1", "final answer from the image + first action"), ("read_ok", "start state read exactly")):
    for fam in ("all", "jugs", "toggles"):
        idx = [i for i, r in enumerate(E) if fam == "all" or r["fam"] == fam]
        recs.append(paired([S[i][k] for i in idx], [E[i][k] for i in idx], f"{name}, {fam} ({len(idx)})"))
vars_read = {"skopos": 100 * sum(r["read_vars"] for r in S) / len(S), "ekbasis27b": 100 * sum(r["read_vars"] for r in E) / len(E)}
dump(a.out, {"item": "P7", "reference": "ref/handoff/image_chain_w4a5.json (Ekbasis-27B, the release run's per-item file)",
             "summary": summary(recs), "measures": recs, "variables_read_pct": vars_read})
