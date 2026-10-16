"""P6, Portuguese: the same 90 questions the actions change (machines, lamps, containers; 30 each) in English and in
Portuguese. Ekbasis-27B kept no per-item answers, so both models run here (P6/run.sh) and are paired by item; 90 < 100:
counts, per language and world (worse by 2 or more flagged). The Ekbasis-27B re-run is also set against its published
totals (77 / 75 of 90; release_pt.out).
  python3 P6/compare.py --skopos <dir> --ekbasis <dir> --out <json>"""
import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "common"))
from paired import dump, paired, summary  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--skopos", required=True)
ap.add_argument("--ekbasis", required=True, help="Ekbasis-27B re-run here")
ap.add_argument("--out", required=True)
a = ap.parse_args()
L = lambda p: [json.loads(x) for x in open(p)]
S, E = L(pathlib.Path(a.skopos) / "pt_items.jsonl"), L(pathlib.Path(a.ekbasis) / "pt_items.jsonl")
assert [(r["k"], r["fam"], r["changed"]) for r in S] == [(r["k"], r["fam"], r["changed"]) for r in E]
recs = []
for lang, f in (("English", "en_ok"), ("Portuguese", "pt_ok")):
    for fam in ("all", "machines", "toggles", "jugs"):
        idx = [k for k, r in enumerate(S) if r["changed"] and (fam == "all" or r["fam"] == fam)]
        recs.append(paired([S[k][f] for k in idx], [E[k][f] for k in idx], f"{lang}, {fam}: changed answers right ({len(idx)})"))
ch = [k for k, r in enumerate(E) if r["changed"]]
dump(a.out, {"item": "P6", "reference": "Ekbasis-27B re-run here (no published per-item answers)", "summary": summary(recs),
             "measures": recs, "ekbasis27b_rerun_vs_published_totals": {
                 "rerun": [sum(E[k]["en_ok"] for k in ch), sum(E[k]["pt_ok"] for k in ch)], "published": [77, 75], "of": len(ch)}})
