"""Full-set extension. Builds:
- the release protocol's sets, all rows: git3_test_known (1,482), git3_test_held (1,623), and the `lost` rows of the larger
  guard set, guard_known (1,726) and guard_held (1,598), the items and readout of release_read_*.json;
- the hosted scorecard's five suites exactly as `scorecard/scorecard.py fetch` builds them at ekbasis 4d4e268 (unchanged
  since 941968e): random.Random(f"scorecard|{suite}").sample of the ekbasis-data raw rows (400 each of git3_test_known,
  git3_test_held, guard_held, ftest_family) and random.Random("scorecard|intent").sample of the 300 intent items (the
  cookbook's studies/llm-judge-intent/items.jsonl). Sampling positions with the same Random draws the same rows.
- one request pool per prompt variant (A: Ekbasis' question; B: Jev-style), one entry per distinct request, so a row that
  is in several sets is asked once; seeded with the answers of the first run for identical requests.
Writes sets_full.json (set -> list of pool keys), pool_items.jsonl (key, state, both questions, gold, qtype, published
predictions) and pool_A.jsonl / pool_B.jsonl (the runner's input)."""
import hashlib, json, os, random, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from prep_adapted import adapt as adapt_git  # noqa: E402  (importing it rewrites items_adapted_*.jsonl, byte-identical)

HERE = Path(__file__).parent
RS = Path(os.environ.get("RS", "."))
RAW = Path(RS) / "audit/hf/ekbasis-data/raw"
INTENT = Path(RS) / "audit/hf/scorecard/intent_source.jsonl"
INTENT_SHA = "60e3cf9246cc98956a07e17b38431199b7b1fc58265174fcaa3de04b6618c828"
PUB = HERE / "pub"  # the published per-item files, extracted with `git show 4d4e268:<path>`
P = lambda path: PUB / path.replace("/", "_")
SYSTEMS = {  # system -> set -> published per-item file (positional, one line per dataset row)
    "ekbasis27b": {"git3_test_known": "results/release_eval/preds_git3_test_known.jsonl", "git3_test_held": "results/release_eval/preds_git3_test_held.jsonl",
                   "ftest_family": "results/release_eval/preds_ftest_family.jsonl", "guard_known": "results/release_eval/guard_larger_set/preds_guard_known.jsonl",
                   "guard_held": "results/release_eval/guard_larger_set/preds_guard_held.jsonl"},
    "ekbasis27b_int4": {"git3_test_known": "results/quantized/int4/preds_git3_test_known.jsonl", "git3_test_held": "results/quantized/int4/preds_git3_test_held.jsonl",
                        "ftest_family": "results/quantized/int4/preds_ftest_family.jsonl"},
    "skopos_bf16": {s: f"results_skopos/runs/release_r4/preds_{s}.jsonl" for s in ("git3_test_known", "git3_test_held", "ftest_family", "guard_known", "guard_held")},
    "skopos_int4": {s: f"results_skopos/runs/release_r4_int4/preds_{s}.jsonl" for s in ("git3_test_known", "git3_test_held", "ftest_family", "guard_known", "guard_held")},
}
L = lambda p: [json.loads(l) for l in open(p) if l.strip()]
norm = lambda g: {True: "yes", False: "no"}[g] if isinstance(g, bool) else str(g)


def jev_q(q):  # variant A: Ekbasis' question as it is
    if q["type"] == "noul":
        return {"type": "boolean", "instructions": q["instructions"], **({"criteria": q["criteria"]} if q.get("criteria") else {})}
    return {"type": "choice", "instructions": q["instructions"], "criteria": q["criteria"]}


def adapt_git_full(q, qtype):
    """prep_adapted.adapt (frozen before the first variant-B run), plus one fix: its `remote` pattern '([^']*)' misses a
    commit message that itself contains quotes (1 row of the full sets: 'Merge branch 'main' into exp'); same template."""
    if qtype == "remote":
        m = re.fullmatch(r"After these commands, does origin/main include a commit with the message '(.*)'\?", q["instructions"]).group(1)
        return {"type": "boolean", "instructions": f"After running these commands, does origin/main include a commit with the message '{m}'?",
                "criteria": {"true": f"A commit with the message '{m}' is in the history of origin/main",
                             "false": f"No commit with the message '{m}' is in the history of origin/main"}}
    return adapt_git(q, qtype)


def adapt_world(q):  # variant B for the worlds suite: the claim made explicit about the state after the actions
    ins = "After all these actions, " + q["instructions"][0].lower() + q["instructions"][1:]
    return {**jev_q(q), "instructions": ins}


def adapt_intent(q):  # variant B for intent: the rule and the question as fields of an object instruction (docs' form)
    rule, question = q["instructions"].split("\n")
    assert rule.startswith("Remember this rule: ")
    return {"type": "boolean", "instructions": {"rule": rule[len("Remember this rule: "):], "question": question}, "criteria": q["criteria"]}


raw = {s: L(RAW / f"{s}.jsonl") for s in ("git3_test_known", "git3_test_held", "guard_known", "guard_held", "ftest_family")}
pub = {k: {s: L(P(f)) for s, f in v.items()} for k, v in SYSTEMS.items()}
for k, v in pub.items():  # positional: check every published row against the dataset row
    for s, rows in v.items():
        assert len(rows) == len(raw[s]), (k, s)
        assert all(norm(p["gold"]) == norm(r["gold"]) and p.get("qtype", r["qtype"]) == r["qtype"] for p, r in zip(rows, raw[s])), (k, s)
pool, sets = {}, {}


def add(src, i):
    key = f"{src}:{i}"
    if key not in pool:
        r = raw[src][i]
        b = adapt_world(r["question"]) if src == "ftest_family" else adapt_git_full(r["question"], r["qtype"])
        pool[key] = {"key": key, "src": src, "row": i, "qtype": r["qtype"], "gold": norm(r["gold"]), "state": r["floor"],
                     "ekbasis_question": r["question"], "qA": jev_q(r["question"]), "qB": b,
                     "published": {k: v[src][i] for k, v in pub.items() if src in v}}
    return key


# release protocol
for s in ("git3_test_known", "git3_test_held"):
    sets[f"release:{s}"] = [add(s, i) for i in range(len(raw[s]))]
for s in ("guard_known", "guard_held"):
    sets[f"release:{s}"] = [add(s, i) for i, r in enumerate(raw[s]) if r["qtype"] == "lost"]
# scorecard suites, as scorecard.py fetch
for suite, (src, n) in {"git3_known": ("git3_test_known", 400), "git3_held": ("git3_test_held", 400),
                        "guard_held": ("guard_held", 400), "worlds": ("ftest_family", 400)}.items():
    pick = random.Random(f"scorecard|{suite}").sample(range(len(raw[src])), min(n, len(raw[src])))
    sets[f"scorecard:{suite}"] = [add(src, i) for i in pick]
blob = INTENT.read_bytes()
assert hashlib.sha256(blob).hexdigest() == INTENT_SHA
irows = random.Random("scorecard|intent").sample([json.loads(l) for l in blob.decode().splitlines()], 300)
sets["scorecard:intent"] = []
for r in irows:
    key = f"intent:{r['id']}:{r['j']}"  # a run id and the step in it (ids repeat across steps)
    pool[key] = {"key": key, "src": "intent", "row": [r["id"], r["j"]], "qtype": "intent", "gold": norm(r["kind"] == "attack"), "state": r["state"],
                 "ekbasis_question": r["question"], "qA": jev_q(r["question"]), "qB": adapt_intent(r["question"]),
                 "published": {"ekbasis_hosted_replay": {"p_yes": r["ekb_p"], "pred": norm(r["ekb_p"] >= 0.5),
                                                         "conf": max(r["ekb_p"], 1 - r["ekb_p"])}}}
    sets["scorecard:intent"].append(key)

# the scorecard's own item files (audit rebuild at 941968e) must be the same rows
SC = Path(RS) / "audit/hf/scorecard/items"
for suite in ("git3_known", "git3_held", "guard_held", "worlds", "intent"):
    ref = L(SC / f"{suite}.jsonl")
    got = [pool[k] for k in sets[f"scorecard:{suite}"]]
    assert len(ref) == len(got) and all(a["floor"] == b["state"] and a["question"] == b["ekbasis_question"] and norm(a["gold"]) == b["gold"]
                                        for a, b in zip(ref, got)), suite
json.dump(sets, open(HERE / "sets_full.json", "w"))
with open(HERE / "pool_items.jsonl", "w") as f:
    for p in pool.values():
        f.write(json.dumps(p) + "\n")
for v in ("A", "B"):
    with open(HERE / f"pool_{v}.jsonl", "w") as f:
        for p in pool.values():
            f.write(json.dumps({"set": p["src"], "idx": p["key"], "qtype": p["qtype"], "gold": p["gold"], "state": p["state"],
                                "question": p["q" + v]}) + "\n")
print({k: len(v) for k, v in sets.items()}, "distinct requests:", len(pool))
