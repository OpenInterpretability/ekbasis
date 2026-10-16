"""P3, long chains: per cell (world, length, start), 6 chains each, Skopos against Ekbasis-27B's published chains
(results/release_eval/release_long_chain.jsonl, the release run of long_chain2.py; its rows carry no seed index, so the
cells are compared as counts). Final answer right, whole final state right, median first error (as the script prints
it; "-" = never), and a cell where Skopos is worse by 2 or more is flagged. Identity check: whether the final answer
depends on the start is decided by the simulator alone, so each cell's count must be the same for both runs.
  python3 P3/compare.py --skopos <dir with long_chain.jsonl> --out <json>"""
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
L = lambda p: [json.loads(x) for x in open(p)]
ek = L(HERE.parent / "ref" / "release_eval" / "release_long_chain.jsonl")
sk = L(pathlib.Path(a.skopos) / "long_chain.jsonl")
NAME = {"jugs": "Containers", "toggles": "Lamps", "machines": "Machines", "cards": "Cards (orderings)"}


def med_first(g, L_):
    fe = sorted(r["first_err"] if r["first_err"] is not None else L_ + 1 for r in g)
    m = fe[len(fe) // 2]
    return "-" if m > L_ else m


recs, cells, ident = [], [], []
for L_ in (100, 200):
    for fam in ("jugs", "toggles", "machines", "cards"):
        for mode in ("text", "image", "image_obs"):
            ge = [r for r in ek if r["fam"] == fam and r["len"] == L_ and r["mode"] == mode]
            gs = [r for r in sk if r["fam"] == fam and r["len"] == L_ and r["mode"] == mode]
            if not ge:
                continue
            assert len(ge) == len(gs) == 6, (fam, L_, mode, len(ge), len(gs))
            c = f"{NAME[fam]} {L_} {mode}"
            recs.append(counts(f"{c}: final answer right", sum(r["final_ok"] for r in gs), sum(r["final_ok"] for r in ge), 6))
            recs.append(counts(f"{c}: whole final state right", sum(r["state_ok"] for r in gs), sum(r["state_ok"] for r in ge), 6))
            cells.append({"cell": c, "first_error_median": {"skopos": med_first(gs, L_), "ekbasis27b": med_first(ge, L_)}})
            ident.append({"cell": c, "depends_on_start": [sum(r["depends_on_start"] for r in gs), sum(r["depends_on_start"] for r in ge)]})
bad = [x["cell"] for x in ident if x["depends_on_start"][0] != x["depends_on_start"][1]]
dump(a.out, {"item": "P3", "reference": "ref/release_eval/release_long_chain.jsonl (Ekbasis-27B, published)",
             "summary": {**summary(recs), "identity_check_failed_cells": bad}, "measures": recs, "first_error": cells,
             "identity_depends_on_start": ident})
