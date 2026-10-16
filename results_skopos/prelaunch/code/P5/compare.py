"""P5, speed: Skopos against Ekbasis-27B on the same 80 forecasts (speed_bench.py items 0-79, seeds 5000+i), both
served here on the same GPU and serving (the published times are from the old rig, so Ekbasis-27B is re-run; its
published files are carried as context). Accuracy: counts (80 < 100), with the items each gets wrong. Latency: the
median of the 8 forecasts made one at a time (secs[len // 2], as speed_bench.py sum); throughput: forecasts per minute
with 16 in parallel (60 x 80 / wall). One check (P8 timing): short_eval_release.py time.
  python3 P5/compare.py --skopos <dir> --ekbasis <dir> [--skopos-p8 <dir> --ekbasis-p8 <dir>] --out <json>"""
import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "common"))
from paired import dump, paired, summary  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--skopos", required=True)
ap.add_argument("--ekbasis", required=True, help="Ekbasis-27B re-run here (P5/run.sh ekbasis_bf16)")
ap.add_argument("--skopos-p8")
ap.add_argument("--ekbasis-p8")
ap.add_argument("--out", required=True)
ap.add_argument("--note", action="append", default=[], help="run conditions to record (repeatable)")
a = ap.parse_args()
L = lambda p: [json.loads(x) for x in open(p)]
PUB = HERE.parent / "ref" / "release_eval" / "speed_bf16"


def speed(d, mode):
    d = pathlib.Path(d)
    r16, r1 = L(d / f"{mode}_par16.jsonl"), L(d / f"{mode}_par1.jsonl")
    m16 = json.load(open(d / f"{mode}_par16.meta.json"))
    secs = sorted(r["seconds"] for r in r1)
    return r16, {"accuracy_pct": 100 * sum(r["ok"] for r in r16) / len(r16), "latency_median_of_8_s": secs[len(secs) // 2],
                 "forecasts_per_min_at_16": 60 * len(r16) / m16["wall"], "wrong_items": [r["i"] for r in r16 if not r["ok"]]}


recs, tab = [], {}
for mode, name in (("cq", "one prompt per question"), ("cqm", "state read once per step")):
    s16, s = speed(a.skopos, mode)
    e16, e = speed(a.ekbasis, mode)
    _, p = speed(PUB, mode)
    assert [r["i"] for r in s16] == [r["i"] for r in e16] and [(r["kind"], r["n_act"]) for r in s16] == [(r["kind"], r["n_act"]) for r in e16]
    recs.append(paired([r["ok"] for r in s16], [r["ok"] for r in e16], f"{name}: accuracy (80)"))
    tab[name] = {"skopos": s, "ekbasis27b_here": e, "ekbasis27b_published_old_rig": p}
if a.skopos_p8 and a.ekbasis_p8:
    t = lambda d: json.load(open(pathlib.Path(d) / "short_eval_release_timing.json"))
    tab["one check (P8 timing)"] = {"skopos": t(a.skopos_p8), "ekbasis27b_here": t(a.ekbasis_p8),
                                    "ekbasis27b_published_old_rig": json.load(open(PUB / "short_timing.json"))}
dump(a.out, {"run_conditions": a.note, "item": "P5", "reference": "Ekbasis-27B re-run on this machine (published speed_bf16/ for context)",
             "summary": summary(recs), "measures": recs, "speed": tab})
