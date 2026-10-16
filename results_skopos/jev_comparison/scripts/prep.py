"""Builds the Jev bench item files: the exact System One request Ekbasis saw (state = the item's `floor`, question =
the item's `question`), mapped to Jev's evaluate() (noul -> boolean, choice -> choice with the same criteria), plus the
published per-item predictions of Ekbasis-27B and Skopos (bf16 served, int4 served) on the same rows.
Samples (fixed seed 20261016, a fresh random.Random per set):
  git3_test_held  : 400 of 1,623 rows, simple random sample (all question types)
  guard_held      : the `lost` question only; 799 work-losing and 799 safe rows -> 200 + 200 (stratified by gold)
  git3_test_known : 300 of 1,482 rows, simple random sample
"""
import hashlib, json, os, random, sys
from pathlib import Path

RS = Path(os.environ.get("RS", "."))
DATA = RS / "audit/hf/ekbasis-data/raw"
GH = RS / "github/ekbasis"
SYS = {
    "ekbasis27b": {"git3_test_held": GH / "results/release_eval/preds_git3_test_held.jsonl",
                   "git3_test_known": GH / "results/release_eval/preds_git3_test_known.jsonl",
                   "guard_held": GH / "results/release_eval/guard_larger_set/preds_guard_held.jsonl"},
    "skopos_bf16": {s: GH / f"results_skopos/runs/release_r4/preds_{s}.jsonl" for s in ("git3_test_held", "git3_test_known", "guard_held")},
    "skopos_int4": {s: GH / f"results_skopos/runs/release_r4_int4/preds_{s}.jsonl" for s in ("git3_test_held", "git3_test_known", "guard_held")},
}
OUT = Path(__file__).parent
norm = lambda g: {True: "yes", False: "no"}[g] if isinstance(g, bool) else str(g)
L = lambda p: [json.loads(l) for l in open(p)]


def jev_question(q):
    if q["type"] == "noul":
        return {"type": "boolean", "instructions": q["instructions"]}
    assert q["type"] == "choice", q
    return {"type": "choice", "instructions": q["instructions"], "criteria": q["criteria"]}


prov = {}
for split, n in (("git3_test_held", 400), ("guard_held", 400), ("git3_test_known", 300)):
    path = DATA / f"{split}.jsonl"
    rows = L(path)
    prov[split] = {"file": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "rows": len(rows)}
    preds = {k: L(v[split]) for k, v in SYS.items()}
    for k, P in preds.items():  # the published predictions are positional: check they line up with the rows
        assert len(P) == len(rows), (k, split, len(P), len(rows))
        bad = sum(p["gold"] != norm(r["gold"]) or p["qtype"] != r["qtype"] for p, r in zip(P, rows))
        assert bad == 0, (k, split, bad)
        prov[split][k] = str(SYS[k][split])
    rng = random.Random(20261016)
    if split == "guard_held":
        pos = [i for i, r in enumerate(rows) if r["qtype"] == "lost" and r["gold"]]
        neg = [i for i, r in enumerate(rows) if r["qtype"] == "lost" and not r["gold"]]
        idx = sorted(rng.sample(pos, 200) + rng.sample(neg, 200))
        prov[split]["sample"] = f"lost rows only ({len(pos)} work-losing, {len(neg)} safe): random.Random(20261016).sample(pos, 200) then .sample(neg, 200)"
    else:
        idx = sorted(rng.sample(range(len(rows)), n))
        prov[split]["sample"] = f"random.Random(20261016).sample(range({len(rows)}), {n})"
    with open(OUT / f"items_{split}.jsonl", "w") as f:
        for i in idx:
            r = rows[i]
            f.write(json.dumps({"set": split, "idx": i, "qtype": r["qtype"], "gold": norm(r["gold"]),
                                "state": r["floor"], "question": jev_question(r["question"]),
                                "ekbasis_question": r["question"], "held_used": r.get("held_used"), "kinds": r.get("kinds"),
                                "published": {k: preds[k][i] for k in SYS}}) + "\n")
    print(split, len(idx), {q: sum(rows[i]["qtype"] == q for i in idx) for q in sorted({rows[i]["qtype"] for i in idx})})
json.dump(prov, open(OUT / "provenance.json", "w"), indent=1)
