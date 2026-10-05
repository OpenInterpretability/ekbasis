"""PLAN_paper_base_loop.md: Eikos-27B (before consequence training) against Ekbasis-27B on the same chains.
argv: eikos.jsonl (long_chain3, TRACE=1) results/release_eval/ (Ekbasis rows) out.json"""
import json
import sys

from scipy.stats import fisher_exact

eik = [json.loads(l) for l in open(sys.argv[1])]
R = sys.argv[2].rstrip("/")
ekb = [json.loads(l) for l in open(f"{R}/long_chain3.jsonl")]
ekb_trace = [json.loads(l) for l in open(f"{R}/long_chain3_controls_trace.jsonl")] + \
            [r for r in (json.loads(l) for l in open(f"{R}/long_chain3_trace.jsonl")) if r["mode"] == "text"]
MODES = ("text", "conf0.5", "conf0.9", "check0.5", "check0.9")
TRAINED, UNSEEN = ("jugs", "toggles"), ("machines", "cards")
key = lambda r: (r["fam"], r["len"], r["i"])

# the pairing: the same chains, mode by mode
for m in MODES:
    a = {key(r) for r in eik if r["mode"] == m}
    b = {key(r) for r in ekb if r["mode"] == m}
    assert a == b and len(a) == 40, (m, len(a), len(b))
assert {key(r) for r in ekb_trace} == {key(r) for r in eik if r["mode"] == "text"}


def steps(rows, fams):
    return [s for r in rows if r["fam"] in fams for s in r["trace"]]


def auroc(st):
    right = sorted(p for p, ok in st if ok)
    wrong = [p for p, ok in st if not ok]
    if not right or not wrong:
        return None
    import bisect
    s = sum(bisect.bisect_left(right, p) + 0.5 * (bisect.bisect_right(right, p) - bisect.bisect_left(right, p)) for p in wrong)
    return 1 - s / (len(right) * len(wrong))  # P(a right step's probability > a wrong step's)


def trace_stats(rows, fams):
    st = steps(rows, fams)
    wrong = [p for p, ok in st if not ok]
    right = [p for p, ok in st if ok]
    return {"steps": len(st), "wrong": len(wrong), "wrong_at_0.9": sum(p >= 0.9 for p in wrong),
            "share_wrong_at_0.9": sum(p >= 0.9 for p in wrong) / len(wrong) if wrong else None,
            "share_right_at_0.9": sum(p >= 0.9 for p in right) / len(right) if right else None,
            "auroc": auroc(st)}


eik_text = [r for r in eik if r["mode"] == "text"]
rep = {"traces": {}, "loop": {}}
for name, fams in (("trained", TRAINED), ("unseen", UNSEEN)) + tuple((f, (f,)) for f in TRAINED + UNSEEN):
    rep["traces"][name] = {"eikos": trace_stats(eik_text, fams), "ekbasis": trace_stats(ekb_trace, fams)}

e, k = rep["traces"]["trained"]["eikos"], rep["traces"]["trained"]["ekbasis"]
table = [[e["wrong_at_0.9"], e["wrong"] - e["wrong_at_0.9"]], [k["wrong_at_0.9"], k["wrong"] - k["wrong_at_0.9"]]]
p1 = fisher_exact(table, alternative="less").pvalue
p1 = float(p1)  # plain Python types for the JSON (scipy returns numpy scalars)
rep["P1"] = {"table_eikos_then_ekbasis": table, "p_one_sided": p1, "inconclusive": bool(e["wrong"] < 10),
             "confirmed": bool(e["wrong"] >= 10 and p1 < 0.05)}


def loop(rows, m, fams=None):
    g = [r for r in rows if r["mode"] == m and (fams is None or r["fam"] in fams)]
    acts = sum(r["len"] for r in g)
    return {"chains": len(g), "exact": sum(r["state_ok"] for r in g), "silent_wrong_per_100": 100 * sum(r["wrong_steps"] for r in g) / acts,
            "looks_per_100": 100 * sum(r["looks"] for r in g) / acts}


for m in MODES:
    rep["loop"][m] = {"eikos": loop(eik, m), "ekbasis": loop(ekb, m),
                      "per_world": {f: {"eikos": loop(eik, m, (f,)), "ekbasis": loop(ekb, m, (f,))} for f in TRAINED + UNSEEN}}
rep["checks_gain"] = {who: rep["loop"]["conf0.9"][who]["silent_wrong_per_100"] - rep["loop"]["check0.9"][who]["silent_wrong_per_100"]
                      for who in ("eikos", "ekbasis")}
json.dump(rep, open(sys.argv[3], "w"), indent=1)

fmt = lambda x: "-" if x is None else f"{x:.3f}"
print("never-look traces: wrong steps at >= 0.9 (share), right steps at >= 0.9, AUROC")
for name, x in rep["traces"].items():
    for who in ("eikos", "ekbasis"):
        s = x[who]
        print(f"  {name:9s} {who:8s} steps {s['steps']:5d} wrong {s['wrong']:4d} at>=0.9 {s['wrong_at_0.9']:4d} ({fmt(s['share_wrong_at_0.9'])})"
              f"  right at>=0.9 {fmt(s['share_right_at_0.9'])}  AUROC {fmt(s['auroc'])}")
print(f"P1 (trained worlds, Eikos share < Ekbasis share): table {table}, one-sided Fisher p = {p1:.2e} -> "
      f"{'INCONCLUSIVE (< 10 wrong steps)' if rep['P1']['inconclusive'] else 'CONFIRMED' if rep['P1']['confirmed'] else 'not confirmed'}")
print("loop: exact / silent wrong per 100 actions / looks per 100 actions")
for m in MODES:
    a, b = rep["loop"][m]["eikos"], rep["loop"][m]["ekbasis"]
    print(f"  {m:9s} Eikos {a['exact']:2d}/40 {a['silent_wrong_per_100']:6.2f} {a['looks_per_100']:6.1f}   "
          f"Ekbasis {b['exact']:2d}/40 {b['silent_wrong_per_100']:6.2f} {b['looks_per_100']:6.1f}")
print(f"checks' gain (conf0.9 - check0.9, silent wrong per 100): Eikos {rep['checks_gain']['eikos']:.2f}, Ekbasis {rep['checks_gain']['ekbasis']:.2f}")
