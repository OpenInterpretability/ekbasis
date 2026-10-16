"""P1, the 240-question git comparison: Skopos against Ekbasis-27B's published per-item answers on the same 240 rows
(results/release_eval/preds_git2_test_{known,held}_240.jsonl; pick(seed 11) reproduces their row order, checked by
common/identity_offline.py). Per half (120: paired bootstrap) and both halves (240), per question type (40: counts);
the other systems' published counts (comparison_240.json) are carried for context. With --ekbasis-rerun, Ekbasis-27B
re-served here on the same script: its answers against its published ones (identity of items and serving).
  python3 P1/compare.py --skopos <dir> [--ekbasis-rerun <dir>] --out <json>"""
import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "common"))
from paired import counts, dump, paired, summary  # noqa: E402

REF = HERE.parent / "ref" / "release_eval"
L = lambda p: [json.loads(x) for x in open(p)]
ap = argparse.ArgumentParser()
ap.add_argument("--skopos", required=True)
ap.add_argument("--ekbasis-rerun")
ap.add_argument("--out", required=True)
ap.add_argument("--note", action="append", default=[], help="run conditions to record (repeatable)")
ap.add_argument("--identity-only", action="store_true", help="write only the re-run's identity block; the rule's measures stay in P1.json")
a = ap.parse_args()

recs, both_s, both_e, ident = [], [], [], {}
TYPES = {"lost": lambda q: q == "lost", "fails": lambda q: q == "fails", "state (changed)": lambda q: q not in ("lost", "fails")}
for split, half in (("git2_test_known", "seen command types"), ("git2_test_held", "never-seen command types")):
    ek = L(REF / f"preds_{split}_240.jsonl")
    sk = L(pathlib.Path(a.skopos) / f"preds_{split}_240.jsonl")
    assert [r["row"] for r in sk] == [r["row"] for r in ek], f"{split}: rows differ from the published order"
    assert all(s["gold"] == e["gold"] for s, e in zip(sk, ek)), f"{split}: golds differ"
    recs.append(paired([r["ok"] for r in sk], [r["ok"] for r in ek], f"{half}: all 120"))
    for t, sel in TYPES.items():
        idx = [i for i, r in enumerate(ek) if sel(r["qtype"])]
        recs.append(paired([sk[i]["ok"] for i in idx], [ek[i]["ok"] for i in idx], f"{half}: {t} ({len(idx)})"))
    both_s += [r["ok"] for r in sk]
    both_e += [r["ok"] for r in ek]
    if a.ekbasis_rerun:
        rr = L(pathlib.Path(a.ekbasis_rerun) / f"preds_{split}_240.jsonl")
        ident[split] = {"same_answer_as_published": sum(x["pred"] == e["pred"] for x, e in zip(rr, ek)), "n": len(ek),
                        "rerun_right": sum(x["ok"] for x in rr), "published_right": sum(e["ok"] for e in ek)}
recs.insert(0, paired(both_s, both_e, "both halves: all 240"))
ctx = json.load(open(REF / "comparison_240.json"))
ctx["Ekbasis-Skopos-27B (this run)"] = {"git_known": [sum(r["ok"] for r in L(pathlib.Path(a.skopos) / "preds_git2_test_known_240.jsonl")), 120],
                                       "git_held": [sum(r["ok"] for r in L(pathlib.Path(a.skopos) / "preds_git2_test_held_240.jsonl")), 120]}
if a.identity_only:  # the rule's measures and outcome are in P1.json; repeating them here would list its blockers/flags twice
    dump(a.out, {"run_conditions": a.note, "item": "P1 identity re-run (Ekbasis-27B on this machine against its published answers)",
                 "rule_outcome_in": "P1.json", "summary": {"release_blockers": [], "flagged_worse_by_2": []}, "measures": [],
                 "ekbasis27b_rerun_identity": ident})
    sys.exit()
dump(a.out, {"run_conditions": a.note, "item": "P1", "reference": "ref/release_eval/preds_git2_test_*_240.jsonl (Ekbasis-27B, published)",
             "summary": summary(recs), "measures": recs, "ekbasis27b_rerun_identity": ident or None,
             "context_other_systems_published": ctx})
