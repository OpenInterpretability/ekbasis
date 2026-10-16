"""P8, short checks (1-3 actions, one question the actions change; 120 items x 2 wordings): Skopos against Ekbasis-27B's
published per-item predictions (results/release_eval/short_eval_release.json, "predictions", the same item order;
items alternate original / paraphrased). Paired bootstrap per wording (120) and both (240). The routing rule and the
calibration bins as each run's script computed them. With --ekbasis-rerun: Ekbasis-27B re-served here, its answers
against its published ones (identity of the regenerated items).
  python3 P8/compare.py --skopos <dir> [--ekbasis-rerun <dir>] --out <json>"""
import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "common"))
from paired import dump, paired, summary  # noqa: E402
sys.path.insert(0, str(HERE))
from make_saved import DEVIATION  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--skopos", required=True)
ap.add_argument("--ekbasis-rerun")
ap.add_argument("--out", required=True)
ap.add_argument("--note", action="append", default=[], help="run conditions to record (repeatable)")
ap.add_argument("--identity-only", action="store_true", help="write only the re-run's identity block; the rule's measures stay in P8.json")
a = ap.parse_args()
pub = json.load(open(HERE.parent / "ref" / "release_eval" / "short_eval_release.json"))
sk = json.load(open(pathlib.Path(a.skopos) / "short_eval_release.json"))
saved = json.load(open(pathlib.Path(a.skopos) / "short_eval_saved.json"))
names = [it[2] for it in saved["items"]]
E, S = pub["predictions"], sk["predictions"]
assert len(E) == len(S) == len(names) == 240
recs = [paired([r["ok"] for r in S], [r["ok"] for r in E], "both wordings (240)")]
for w in ("orig", "para"):
    idx = [k for k, n in enumerate(names) if n == w]
    recs.append(paired([S[k]["ok"] for k in idx], [E[k]["ok"] for k in idx], f"{w} wording (120)"))
ident = None
if a.ekbasis_rerun:
    R = json.load(open(pathlib.Path(a.ekbasis_rerun) / "short_eval_release.json"))["predictions"]
    ident = {"same_right_wrong_as_published": sum(x["ok"] == e["ok"] for x, e in zip(R, E)), "n": 240,
             "max_confidence_difference": max(abs(x["conf"] - e["conf"]) for x, e in zip(R, E))}
if a.identity_only:  # the rule's measures and outcome are in P8.json; repeating them here would list its blockers/flags twice
    dump(a.out, {"run_conditions": a.note, "item": "P8 identity re-run (Ekbasis-27B on this machine against its published answers)",
                 "rule_outcome_in": "P8.json", "summary": {"release_blockers": [], "flagged_worse_by_2": []}, "measures": [],
                 "ekbasis27b_rerun_identity": ident})
    sys.exit()
dump(a.out, {"run_conditions": a.note, "item": "P8", "reference": "ref/release_eval/short_eval_release.json (Ekbasis-27B, published)",
             "deviation": saved.get("deviation", DEVIATION),
             "summary": summary(recs), "measures": recs,
             "routing": {"skopos": sk["routing"], "ekbasis27b": pub["routing"]},
             "calibration": {"skopos": sk["calibration"], "ekbasis27b": pub["calibration"]},
             "qwen_published_context": {k: v for k, v in pub["accuracy"].items() if k.startswith("Qwen")},
             "ekbasis27b_rerun_identity": ident})
