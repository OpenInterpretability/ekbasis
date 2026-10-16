"""P4, predict, observe, correct (long_chain3.py): Skopos against Ekbasis-27B's published chains, paired by (world,
length, seed index). Formulas checked against RELEASE_EVAL.md (the self-test with Ekbasis-27B as both sides gives its
published table): exact = whole final state right; steps wrong per 100 actions = 100 sum(wrong_steps) / sum(len); looks
per 100 actions = 100 sum(looks) / sum(len).
- Rules compared (long_chain3.jsonl): 40 chains per rule, counts (and the card table, 8 per length).
- 200 more chains (long_chain3_fresh.jsonl): mode check0.9 (the published table) and conf0.5 (also run), 200 chains each:
  paired bootstrap of exact chains and of steps wrong per 100 actions (both errors: a blocker if worse); looks per 100
  actions with its interval, reported (a cost, not an error).
- Never looking on 40 fresh chains (long_chain3_fresh_text.jsonl): wrong steps and those at probability >= 0.9, counts.
  python3 P4/compare.py --skopos <dir> --out <json>"""
import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "common"))
from paired import counts, dump, paired, summary  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--skopos", required=True)
ap.add_argument("--out", required=True)
a = ap.parse_args()
L = lambda p: [json.loads(x) for x in open(p)]
REF = HERE.parent / "ref" / "release_eval"
SK = pathlib.Path(a.skopos)
key = lambda r: (r["fam"], r["len"], r["i"], r["mode"])


def pair(fe, fs):
    E, S = {key(r): r for r in L(fe)}, {key(r): r for r in L(fs)}
    assert set(E) == set(S), f"{fs}: chains differ from the reference ({len(set(E) ^ set(S))})"
    for k in E:  # the world's size is fixed by the seed: the same chain on both sides
        assert E[k]["n_vars"] == S[k]["n_vars"], ("identity", k)
    return E, S


per100 = lambda g, f: 100 * sum(r[f] for r in g) / sum(r["len"] for r in g)
recs, tables = [], {}
# rules compared
E, S = pair(REF / "long_chain3.jsonl", SK / "long_chain3_rules.jsonl")
tab = []
for m in ("text", "conf0.5", "until0.5", "check0.5", "conf0.9", "until0.9", "check0.9"):
    ks = sorted(k for k in E if k[3] == m)
    ge, gs = [E[k] for k in ks], [S[k] for k in ks]
    recs.append(counts(f"rules, {m}: exact at the end (of {len(ks)})", sum(r["state_ok"] for r in gs), sum(r["state_ok"] for r in ge), len(ks)))
    tab.append({"rule": m, "chains": len(ks), "exact": [sum(r["state_ok"] for r in gs), sum(r["state_ok"] for r in ge)],
                "wrong_steps_per_100_actions": [per100(gs, "wrong_steps"), per100(ge, "wrong_steps")],
                "looks_per_100_actions": [per100(gs, "looks"), per100(ge, "looks")]})
tables["rules_compared [skopos, ekbasis27b]"] = tab
cards = []
for m in ("text", "obs50", "conf0.5", "conf0.9", "step0.9", "dual_conf0.9"):
    row = {"rule": m}
    for L_ in (100, 200):
        ks = sorted(k for k in E if k[0] == "cards" and k[1] == L_ and k[3] == m)
        gs, ge = [S[k] for k in ks], [E[k] for k in ks]
        row[f"exact_{L_} (of {len(ks)})"] = [sum(r["state_ok"] for r in gs), sum(r["state_ok"] for r in ge)]
        row[f"looks_per_100_{L_}"] = [per100(gs, "looks"), per100(ge, "looks")]
        recs.append(counts(f"cards {L_}, {m}: exact at the end (of {len(ks)})", row[f"exact_{L_} (of {len(ks)})"][0], row[f"exact_{L_} (of {len(ks)})"][1], len(ks)))
    cards.append(row)
tables["cards [skopos, ekbasis27b]"] = cards
# 200 more chains
E, S = pair(REF / "long_chain3_fresh.jsonl", SK / "long_chain3_fresh.jsonl")
for m in ("check0.9", "conf0.5"):
    ks = sorted(k for k in E if k[3] == m)
    ge, gs = [E[k] for k in ks], [S[k] for k in ks]
    lens = [r["len"] for r in ge]
    tag = f"200 more chains, {m}" + (" (published table)" if m == "check0.9" else " (run, not in the published table)")
    recs.append(paired([r["state_ok"] for r in gs], [r["state_ok"] for r in ge], f"{tag}: exact at the end"))
    recs.append(paired([r["wrong_steps"] for r in gs], [r["wrong_steps"] for r in ge], f"{tag}: steps wrong per 100 actions",
                       higher_is_better=False, den=lens))
    lk = paired([r["looks"] for r in gs], [r["looks"] for r in ge], f"{tag}: looks per 100 actions", higher_is_better=False, den=lens)
    lk["release_blocker"] = False
    lk["note"] = "a cost (looks), reported with its interval; not an error measure"
    recs.append(lk)
    per = []
    for fam in ("jugs", "toggles", "machines", "cards"):
        gs2, ge2 = [S[k] for k in ks if k[0] == fam], [E[k] for k in ks if k[0] == fam]
        recs.append(counts(f"{tag}, {fam}: exact at the end (of {len(gs2)})", sum(r["state_ok"] for r in gs2), sum(r["state_ok"] for r in ge2), len(gs2)))
        per.append({"world": fam, "chains": len(gs2), "exact": [sum(r["state_ok"] for r in gs2), sum(r["state_ok"] for r in ge2)],
                    "wrong_steps_per_100_actions": [per100(gs2, "wrong_steps"), per100(ge2, "wrong_steps")],
                    "looks_per_100_actions": [per100(gs2, "looks"), per100(ge2, "looks")]})
    tables[f"{tag} per world [skopos, ekbasis27b]"] = per
# never looking, 40 fresh chains: per-step traces
E, S = pair(REF / "long_chain3_fresh_text.jsonl", SK / "long_chain3_fresh_text.jsonl")
nl = []
for fam in ("jugs", "toggles", "machines", "cards"):
    st = [s for k in sorted(S) if k[0] == fam for s in S[k]["trace"]]
    et = [s for k in sorted(E) if k[0] == fam for s in E[k]["trace"]]
    nl.append({"world": fam, "steps": [len(st), len(et)], "wrong": [sum(not s[1] for s in st), sum(not s[1] for s in et)],
               "wrong_at_p>=0.9": [sum((not s[1]) and s[0] >= 0.9 for s in st), sum((not s[1]) and s[0] >= 0.9 for s in et)]})
    recs.append(counts(f"never looking, {fam}: wrong steps (of {len(et)})", nl[-1]["wrong"][0], nl[-1]["wrong"][1], len(et), higher_is_better=False))
tables["never looking, 40 fresh chains [skopos, ekbasis27b]"] = nl
dump(a.out, {"item": "P4", "reference": "ref/release_eval/long_chain3*.jsonl (Ekbasis-27B, published)", "summary": summary(recs),
             "measures": recs, "tables": tables})
