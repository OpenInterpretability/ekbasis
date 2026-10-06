"""WS-PI: a readable summary of chains.json (pi_chains.py): for every chain file, per rule, on all steps and on the
steps whose prompt does not overlap the training rows: errors made (the per-step trace: the step itself wrong from the
model's own previous state) and how many at a step probability >= 0.9; the published metrics (silent wrong steps and
looks per 100 actions, chains exact) on all chains and on the chains with no overlapping step.
usage: python pi_chains_summary.py   (in /root/decis/mission/PI; writes chains_summary.txt)"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
r = json.load(open(os.path.join(HERE, "chains.json")))
out = ["overlap of the step prompts, per world: " + json.dumps(r["overlap"]["chains"]), ""]
hdr = ("file", "cell", "chains", "steps", "clean steps", "errors made", "at>=0.9", "clean-step errors", "at>=0.9",
       "silent/100", "looks/100", "exact", "clean chains", "silent/100", "looks/100", "exact")
out.append(" | ".join(hdr))


def f(x, d=2):
    return "-" if x is None else (f"{x:.{d}f}" if isinstance(x, float) else str(x))


for k, v in r["chains"].items():
    for c in sorted(v):
        s = dict(v[c])
        if s.get("chains_without_trace"):  # no per-step trace kept for these chains: no error counts
            for x in ("errors_made", "errors_made_ge0.9", "errors_made_clean", "errors_made_clean_ge0.9"):
                s[x] = None
        out.append(" | ".join([k, c, f(s["chains"]), f(s["steps"]), f(s["steps_clean"]), f(s.get("errors_made")),
                               f(s.get("errors_made_ge0.9")), f(s.get("errors_made_clean")), f(s.get("errors_made_clean_ge0.9")),
                               f(s["carried_wrong_per_100"]), f(s["looks_per_100"], 1), f(s["exact"]), f(s.get("chains_clean", 0)),
                               f(s.get("carried_wrong_per_100_clean_chains")), f(s.get("looks_per_100_clean_chains"), 1),
                               f(s.get("exact_clean_chains"))]))
open(os.path.join(HERE, "chains_summary.txt"), "w").write("\n".join(out) + "\n")
print(len(out), "lines")
