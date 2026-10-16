"""Offline identity checks (no model, no GPU): the items the ported runners regenerate from seeds are the items of
Ekbasis-27B's published run, checked against whatever that run left that does not depend on the model.
  P1  pick(seed 11) on ekbasis-data raw/ git2_test_*: the published per-item files' row order and golds; the questions'
      repository states in the hand-off of the same 240 questions to Claude (eval_handoff/claude_eval/git_*.txt).
  P3  per cell, how many chains have a final answer that depends on the start (decided by the simulator alone).
  P4  every published chain (world, length, seed index): the number of variables of its world.
  P5  each of the 80 forecasts: its world and number of actions (published cq_par16.jsonl).
  P6  the example item the published run printed (release_pt.out).
  P7  each of the 60 image items: its world and number of actions (the release run's image_chain.json).
  P8  the 120 original-wording short checks: text, question and options equal the Claude hand-off (short.txt).
  P9  the regenerated puzzles: 180 per set, and every published question count is a multiple of (valid actions x
      variables) of its puzzle, as the beam search asks every action for every variable of every beam state.
  python3 identity_offline.py <out.json> [--data <ekbasis-data raw dir>] [--handoff <eval_handoff/claude_eval>]"""
import argparse
import collections
import io
import json
import os
import random
import re
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

PRE = Path(__file__).resolve().parents[1]
LIB = PRE / "lib"
REF = PRE / "ref"
sys.path.insert(0, str(LIB))
os.environ.setdefault("MODEL_DIR", "/nonexistent")
ap = argparse.ArgumentParser()
ap.add_argument("out")
ap.add_argument("--data", help="folder with git2_test_known.jsonl / git2_test_held.jsonl (ekbasis-data raw/)")
ap.add_argument("--handoff", help="eval_handoff/claude_eval of the release (git_known.txt, git_held.txt, short.txt)")
a = ap.parse_args()
L = lambda p: [json.loads(x) for x in open(p)]
res = {}


def head(path, marker):
    src = open(path).read()
    return src[:src.index(marker)]


def ns_of(path, marker, argv=None):
    keep = sys.argv
    sys.argv = argv or [str(path)]
    ns = {"__name__": "identity", "__file__": str(path)}
    exec(compile(head(path, marker), str(path), "exec"), ns)
    sys.argv = keep
    return ns


blocks = lambda text: re.findall(r"=== ITEM (\S+) ===\n(.*?)\n=== END ===", text, re.S)

# P1
if a.data:
    import git_llm_large as G
    tmp = Path(tempfile.mkdtemp())
    (tmp / "fac").mkdir()
    for s in ("git2_test_known", "git2_test_held"):
        (tmp / "fac" / f"{s}.jsonl").symlink_to(Path(a.data).resolve() / f"{s}.jsonl")
    G.D = tmp
    p1 = {}
    for s, h in (("git2_test_known", "git_known"), ("git2_test_held", "git_held")):
        rows, idx = G.pick(s)
        ek = L(REF / "release_eval" / f"preds_{s}_240.jsonl")
        p1[s] = {"rows_as_published": [r["row"] for r in ek] == list(idx),
                 "golds_as_published": all(G.norm(rows[r["row"]]["gold"]) == r["gold"] for r in ek)}
        if a.handoff:
            texts = {b.split("\n\nQuestion:")[0].strip() for _, b in blocks(open(Path(a.handoff) / f"{h}.txt").read())}
            p1[s]["states_in_claude_handoff"] = f"{sum(rows[i]['floor'].strip() in texts for i in idx)}/{len(idx)}"
    res["P1"] = p1

# P3: long_chain2.py's chains (the generation part of its run(), verbatim)
ns = ns_of(PRE / "P3" / "long_chain2.py", "\njobs = [")
world, VARS, value = ns["world"], ns["VARS"], ns["value"]
dep = collections.Counter()
for L_ in (100, 200):
    for fam in ("jugs", "toggles", "machines", "cards"):
        for i in range(6):
            rng = random.Random({"jugs": 1, "toggles": 2, "machines": 3, "cards": 4}[fam] * 100000 + L_ * 100 + i)
            w = world(fam, rng)
            s0 = w.sample_state(rng)
            acts, truth, s = [], [s0], s0
            for _ in range(L_):
                act = w.sample_action(rng, s)
                s, _ = w.step(s, act)
                acts.append(act)
                truth.append(s)
            keys_qs = VARS[fam](w)
            key = keys_qs[rng.randrange(len(keys_qs))][0]
            so = w.sample_state(random.Random(i + 99))
            for act in acts:
                so, _ = w.step(so, act)
            dep[(fam, L_)] += value(w, so, key) != value(w, truth[-1], key)
pub = collections.Counter()
for r in L(REF / "release_eval" / "release_long_chain.jsonl"):
    pub[(r["fam"], r["len"])] += r["depends_on_start"]
modes = {"jugs": 3, "toggles": 3, "machines": 1, "cards": 1}   # each chain runs once per start mode
res["P3"] = {"depends_on_start_per_world_and_length": all(dep[k] * modes[k[0]] == pub[k] for k in dep),
             "detail [regenerated x modes, published]": {f"{k[0]} {k[1]}": [dep[k] * modes[k[0]], pub[k]] for k in sorted(dep)}}

# P4: long_chain3.py's worlds
ns = ns_of(PRE / "P4" / "long_chain3.py", "\nNEW = (")
bad, n = [], 0
for f in ("long_chain3.jsonl", "long_chain3_fresh.jsonl", "long_chain3_fresh_text.jsonl"):
    for r in L(REF / "release_eval" / f):
        rng = random.Random({"jugs": 1, "toggles": 2, "machines": 3, "cards": 4}[r["fam"]] * 100000 + r["len"] * 100 + r["i"])
        n += 1
        if len(ns["VARS"][r["fam"]](ns["world"](r["fam"], rng))) != r["n_vars"]:
            bad.append((f, r["fam"], r["len"], r["i"], r["mode"]))
res["P4"] = {"chains_checked": n, "n_vars_as_published": not bad, "mismatches": bad[:10]}

# P5: speed_bench.py's items
import importlib.util  # noqa: E402
spec = importlib.util.spec_from_file_location("sb", PRE / "P5" / "speed_bench.py")
sb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sb)
pub = L(REF / "release_eval" / "speed_bf16" / "cq_par16.jsonl")
res["P5"] = {"items_as_published": all((lambda it: (it[0], len(it[3])))(sb.item(r["i"])) == (r["kind"], r["n_act"]) for r in pub), "n": len(pub)}

# P6: pt_eval.py's items (as pt_eval_api.py builds them, N = 60 per world)
with redirect_stdout(io.StringIO()):
    ns = ns_of(LIB / "pt_eval.py", "res = {}", argv=["pt_eval.py", "60"])
items = ns["items"]
printed = open(REF / "release_eval" / "release_pt.out").read()
example = printed.split("example (pt):\n", 1)[1].split("\n\nworld", 1)[0].strip()
mine = f"{items[1]['pt']}\nQ: {items[1]['qpt']['instructions']} -> {items[1]['gpt']}".strip()
res["P6"] = {"items": len(items), "changed": sum(it["changed"] for it in items), "printed_example_equal": mine == example}

# P7: image_chain.py's items
ns = ns_of(PRE / "P7" / "image_chain.py", "\nwith cf.ThreadPoolExecutor(PAR) as ex:")
pub = json.load(open(REF / "handoff" / "image_chain_w4a5.json"))
res["P7"] = {"items_as_release_run": all((lambda it: (it[0].family, len(it[2])))(ns["item"](i)) == (r["fam"], r["n_act"]) for i, r in enumerate(pub)), "n": len(pub)}

# P8: the short checks
if a.handoff:
    sys.argv = [sys.argv[0]]
    import robust_eval as R
    from worldgen import Jugs, Machines, Toggles
    R.BIG = False
    rng = random.Random(77)
    its = [(fam, gold, name, text, q) for F in (Machines, Toggles, Jugs) for fam, gold, v in R.items(F, rng, 40)
           for name, (text, q) in v.items() if name in ("orig", "para")]
    orig = [it for it in its if it[2] == "orig"]
    hb = blocks(open(Path(a.handoff) / "short.txt").read())
    same = sum(b.strip() == f"{it[3]}\n\nQuestion: {it[4]['instructions']}\nOptions: {', '.join(it[4]['criteria'])}".strip()
               for (_, b), it in zip(hb, orig))
    res["P8"] = {"items": len(its), "original_wording_equal_to_claude_handoff": f"{same}/{len(hb)}"}

# P9: the puzzles
from llm_agent_gen_lib import all_actions  # noqa: E402
tmp = tempfile.mkdtemp()
keep, sys.argv = sys.argv, ["gen_puzzles.py", tmp]
with redirect_stdout(io.StringIO()):
    exec(compile(open(PRE / "P9" / "gen_puzzles.py").read(), "gen_puzzles.py", "exec"),
         {"__name__": "gen", "__file__": str(PRE / "P9" / "gen_puzzles.py")})
sys.argv = keep
import pickle  # noqa: E402
nv = {"jugs": lambda w: len(w.names), "toggles": lambda w: w.n, "machines": lambda w: len(w.devs)}
p9 = {}
for d in ("agent", "agent_hard"):
    pz = pickle.load(open(f"{tmp}/{d}/puzzles.pkl", "rb"))
    asked = json.load(open(REF / "release_eval" / f"search_w4a5rel_{d}.json"))["Ekbasis (release)"]["asked"]
    unit = [len(all_actions(p["fam"], p["w"])) * nv[p["fam"]](p["w"]) for p in pz]
    p9[d] = {"puzzles": len(pz), "per_family_and_H": dict(collections.Counter(f"{p['fam']} H{p['H']}" for p in pz)),
             "question_counts_multiple_of_actions_x_variables": f"{sum(asked[str(i)] % u == 0 for i, u in enumerate(unit))}/{len(pz)}",
             "solved_at_first_depth_exactly": sum(asked[str(i)] == u for i, u in enumerate(unit))}
res["P9"] = p9
json.dump(res, open(a.out, "w"), indent=1)
print(json.dumps(res, indent=1))
