"""Fixture for client 0.1.5's tests (reproduce confirm-3's L2 decisions): the confirm-3 units exactly as
confirm3_analyze.py builds them (confirm2/metrics2.scored_rows, one confident question per scenario, seed 63), with
their raw signals kept, the frozen score S, and ltt3's L2 node and decision at α = 2%. A stratified sample: every
(node kind, decision) cell, up to 120 units each, seed 64. No model call; reads only.
python3 make_fixture.py  ->  confirm3_l2_fixture.jsonl"""
import collections
import hashlib
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
U = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(U, "confirm2"))
sys.path.insert(0, os.path.join(U, "confirm"))
import ltt3 as L  # noqa: E402
import metrics2 as M  # noqa: E402
from policy import FamilyRates, Policy, observable  # noqa: E402

SUITE2DOMAIN = {"rules_stress": "rules", "sql_wild": "sql", "shell_wild": "shell", "git_wild": "git", "accumulation": "totals"}


def main():
    pol = Policy()
    rows = [r for r in M.jl(os.path.join(HERE, "fresh_rows.jsonl")) if r["exclude"] is None]
    extra = {e["rid"]: e for e in M.jl(os.path.join(HERE, "extra.jsonl")) if "error" not in e}
    warm = FamilyRates.from_dev(tuple(pol.p["family_prior"]))
    for r in sorted(rows, key=lambda r: hashlib.sha256(f"{M.STREAM_SEED}|{r['rid']}".encode()).hexdigest()):
        k = (r["suite"], observable(r["suite"], r["family"]))
        r["famobs"] = warm.rate(k)
        warm.update(k, not r["correct"])
    out = []
    for r in rows:
        if r["suite"] not in M.PRIMARY or (r["conf"] or 0) < 0.9 or r["rid"] not in extra:
            continue
        e = extra[r["rid"]]
        mp = 1 - min(e["reorder"]["p_original"], e["para"]["p_original"])
        vf = float((e["verify"]["probabilities"] or {}).get("no", 0.0))
        out.append({"suite": r["suite"], "family": observable(r["suite"], r["family"]), "req": r["req"], "rid": r["rid"],
                    "wrong": not r["correct"], "famobs": r["famobs"], "minpert": mp, "verify": vf,
                    "S": pol.score(r["suite"], r["famobs"], mp, vf)})
    check, _ = M.scored_rows(os.path.join(HERE, "fresh_rows.jsonl"), os.path.join(HERE, "extra.jsonl"))
    assert [c["S"] for c in sorted(check, key=lambda c: c["rid"])] == [o["S"] for o in sorted(out, key=lambda o: o["rid"])]
    units = M.one_per_scenario(out, 63)
    P = json.load(open(os.path.join(HERE, "params_confirm3.json")))["a02"]
    acc = L.accept(units, P, "L2")
    cells = collections.defaultdict(list)
    for u, a in zip(units, acc):
        node = L.node_of(u, P, "L2")
        kind = node[0] if node else ("unseen" if f"{u['suite']}|{u['family']}" not in P["family_rate"] else "uncertified")
        u.update(node_kind=kind, node=node[1] if node else None, accepted=bool(a))
        cells[(kind, bool(a))].append(u)
    rng = random.Random(64)
    sample = []
    for key in sorted(cells):
        us = sorted(cells[key], key=lambda u: u["rid"])
        sample += rng.sample(us, min(120, len(us)))
    with open(os.path.join(HERE, "confirm3_l2_fixture.jsonl"), "w") as f:
        for u in sorted(sample, key=lambda u: u["rid"]):
            f.write(json.dumps({"domain": SUITE2DOMAIN[u["suite"]], "family": u["family"], "famobs": u["famobs"],
                                "minpert": u["minpert"], "verify": u["verify"], "S": u["S"], "node_kind": u["node_kind"],
                                "node": u["node"], "accepted": u["accepted"], "wrong": u["wrong"]}) + "\n")
    print({f"{k[0]}|{'accept' if k[1] else 'verify'}": len(v) for k, v in sorted(cells.items())}, "sample", len(sample),
          "| all units", len(units), "accepted", sum(acc), "errors among accepted", sum(a and u["wrong"] for u, a in zip(units, acc)))


if __name__ == "__main__":
    main()
