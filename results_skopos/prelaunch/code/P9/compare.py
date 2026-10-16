"""P9, planning by search with no LLM (180 puzzles per set; containers, lamps, machines): Skopos against Ekbasis-27B's
published per-puzzle results (results/release_eval/search_w4a5rel_{agent,agent_hard}.json: plan works, questions asked).
Paired bootstrap per set (180) and both (360); questions per puzzle and seconds (from the logs) reported. Seconds are
only comparable with an Ekbasis-27B run on this machine (--ekbasis-rerun); that run also checks the regenerated puzzles
(the same plan-works list and question counts expected).
  python3 P9/compare.py --skopos <dir> --skopos-tag <tag> [--ekbasis-rerun <dir> --ekbasis-tag <tag>] --out <json>"""
import argparse
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "common"))
from paired import dump, paired, summary  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--skopos", required=True)
ap.add_argument("--skopos-tag", default="skopos_bf16")
ap.add_argument("--ekbasis-rerun")
ap.add_argument("--ekbasis-tag", default="ekbasis_bf16")
ap.add_argument("--out", required=True)
a = ap.parse_args()
REF = HERE.parent / "ref" / "release_eval"
PUB_SECONDS = dict(zip(("agent", "agent_hard"), map(int, re.findall(r"seconds: \{'Ekbasis \(release\)': (\d+)\}", open(REF / "plan_search.out").read()))))


def run(d, tag, s):
    j = json.load(open(pathlib.Path(d) / f"search_{tag}_{s}.json"))[tag]
    log = open(pathlib.Path(d) / f"search_{s}.log").read()
    m = re.search(r"seconds: \{'[^']*': (\d+)\}", log)
    return j["ok"], {int(k): v for k, v in j["asked"].items()}, int(m.group(1)) if m else None


recs, both_s, both_e, info, ident = [], [], [], {}, {}
for s, name in (("agent", "goals from 3-5-action plans"), ("agent_hard", "goals from 8-12-action plans")):
    pub = json.load(open(REF / f"search_w4a5rel_{s}.json"))["Ekbasis (release)"]
    eo, ea = pub["ok"], {int(k): v for k, v in pub["asked"].items()}
    so, sa, ss = run(a.skopos, a.skopos_tag, s)
    assert len(so) == len(eo) == 180
    recs.append(paired(so, eo, f"{name}: plans that work (180)"))
    both_s += so
    both_e += eo
    info[s] = {"questions_per_puzzle": {"skopos": sum(sa.values()) / 180, "ekbasis27b_published": sum(ea.values()) / 180},
               "seconds": {"skopos": ss, "ekbasis27b_published_old_rig": PUB_SECONDS[s]}}
    if a.ekbasis_rerun:
        ro, ra, rs = run(a.ekbasis_rerun, a.ekbasis_tag, s)
        info[s]["seconds"]["ekbasis27b_here"] = rs
        ident[s] = {"same_plan_works_as_published": sum(x == y for x, y in zip(ro, eo)), "same_question_count": sum(ra[i] == ea[i] for i in ea), "n": 180}
recs.insert(0, paired(both_s, both_e, "both sets: plans that work (360)"))
dump(a.out, {"item": "P9", "reference": "ref/release_eval/search_w4a5rel_*.json (Ekbasis-27B, published)",
             "summary": summary(recs), "measures": recs, "questions_and_seconds": info, "ekbasis27b_rerun_identity": ident or None})
