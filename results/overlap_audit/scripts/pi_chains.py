"""WS-PI, part 4: the chain, speed, image-chain and planning numbers (RELEASE_EVAL.md, the model card, the paper's loop
sections, the site's chain numbers).
Every public item is rebuilt from its seed exactly as its script builds it (long_chain3.py and long_chain.py: world,
start state and actions from Random(family * 100000 + length * 100 + i); speed_bench.py: item(i), Random(5000 + i);
image_chain.py: item(i), Random(7000 + i); search_eval.py: the puzzles of puzzles.pkl). The prompt the model gets at a
step (rules, the state before the action, one action) is checked against the release lineage's training rows
(ftrain_mixG3, mined_wide, mined_chain) by the same rules as every other set (pi_overlap.py: identical floor, or word
8-gram Jaccard >= 0.5 against a single training row after removing the set's own layout). The step prompt is written
with the TRUE state before the action: the model's own state differs from it only after an error a look has not yet
corrected (under 1 step in 100 in the published counts), which the records do not let us rebuild. Planning: the first
layer of the search (the start state with every valid action), all a puzzle needs when its shortest plan is one action
(the median).
Then, wherever outcomes were kept per step or per item, the published numbers on the steps or items that do not
overlap.
usage: PYTHONHASHSEED=0 python pi_chains.py   (in /root/decis/mission/PI; reads served/release_eval/, served/release_eval_v42/
and the loop tests' records in /dev/shm/conseq; writes chains.json and chain_flags.json)"""
from __future__ import annotations

import collections
import json
import multiprocessing as mp
import os
import pickle
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from pi_overlap import TRAIN, load, norm, paragraphs, shard_worker, shingles, text  # noqa: E402

C = "/root/decis/conseq"
sys.path[:0] = [C, "/root/decis/serve_v13/eikos"]
os.environ.setdefault("PROMPT_STYLE", "semif")
os.environ.setdefault("OUT", "/dev/null")
REL = os.path.join(HERE, "served", "release_eval")  # copies of the public results/release_eval files


def prefix(path, stop):
    """A script's definitions only (everything before `stop`), so nothing runs."""
    src = open(path).read()
    ns = {"__name__": os.path.basename(path)}
    exec(compile(src[:src.index(stop)], path, "exec"), ns)
    return ns


LC = prefix(f"{C}/long_chain3.py", "def run(job):")
SP = prefix(f"{C}/speed_bench.py", "def answer_of(")
IM = prefix(f"{C}/image_chain.py", "def value(")
from llm_agent_gen_lib import all_actions  # noqa: E402


def step_text(w, s, a):  # the step prompt of long_chain3.py, long_chain.py, speed_bench.py (cq) and image_chain.py
    return f"{w.rules}\n\nCurrent state:\n{w.render(s)}\n\nActions, in order:\n1. {w.render_action(a)}\n\n{w.floor_note()}"


def walk(w, s, acts):
    out = []
    for a in acts:
        out.append(step_text(w, s, a))
        s, _ = w.step(s, a)
    return out


_chains = {}


def chain_steps(fam, length, i):  # long_chain3.py run() (= long_chain.py, long_chain2.py): the same rng calls, in order
    if (fam, length, i) not in _chains:
        rng = random.Random({"jugs": 1, "toggles": 2, "machines": 3, "cards": 4}[fam] * 100000 + length * 100 + i)
        w = LC["world"](fam, rng)
        s0 = w.sample_state(rng)
        acts, s = [], s0
        for _ in range(length):
            a = w.sample_action(rng, s)
            s, _ = w.step(s, a)
            acts.append(a)
        _chains[(fam, length, i)] = walk(w, s0, acts)
    return _chains[(fam, length, i)]


def jl(p):
    return [json.loads(l) for l in open(p)]


CHAIN_FILES = {"long_chain3": "long_chain3.jsonl", "fresh": "long_chain3_fresh.jsonl", "fresh_text": "long_chain3_fresh_text.jsonl",
               "loop_fresh_w4a5": "selection/loop_fresh_chains_release.jsonl", "loop_fresh_v42": "selection/loop_fresh_chains_v42.jsonl"}
recs = {k: jl(os.path.join(REL, f)) for k, f in CHAIN_FILES.items()}
# the paper's chains: V42's public files (results_v42/release_eval) and the loop tests' records kept on the rig
V42R = os.path.join(HERE, "served", "release_eval_v42")
for f in ("long_chain3", "long_chain3_fresh", "long_chain3_controls", "long_chain3_controls05", "long_chain3_controls_trace",
          "long_chain3_trace", "long_chain3_until"):
    recs["v42:" + f] = jl(os.path.join(V42R, f + ".jsonl"))
for f in ("eikos_base", "r2err", "r2hard", "r3w20", "r4a", "r4b", "confirm_v42", "confirm_r4a", "confirm_r4b", "r5_v42", "r5_r4c",
          "wise_v42", "wise_w4a5", "v42more", "ideas", "ideas2", "ideas3", "ideas4"):
    recs["runs:" + f] = [r for r in jl(f"/dev/shm/conseq/long_chain3_{f}.jsonl") if "i" in r]
old = jl(os.path.join(REL, "release_long_chain.jsonl"))  # RELEASE_EVAL "Long chains": 6 chains per cell, i = 0..5 (no i kept)
old_cells = sorted({(r["fam"], r["len"]) for r in old})

sets = {"chains": [], "speed": [], "image_chain": [], "planning": []}
owner = {k: [] for k in sets}  # what each prompt belongs to
for (fam, L, i) in sorted({(r["fam"], r["len"], r["i"]) for v in recs.values() for r in v} | {(f, L, i) for f, L in old_cells for i in range(6)}):
    for t, s in enumerate(chain_steps(fam, L, i)):
        sets["chains"].append(s)
        owner["chains"].append((fam, L, i, t))
for i in range(80):
    kind, w, s0, acts, *_ = SP["item"](i)
    for t, s in enumerate(walk(w, s0, acts)):
        sets["speed"].append(s)
        owner["speed"].append((kind, i, t))
for i in range(60):
    w, s0, acts, *_ = IM["item"](i)
    for t, s in enumerate(walk(w, s0, acts)):
        sets["image_chain"].append(s)
        owner["image_chain"].append((w.family, i, t))
PUZ = {}
for d in ("agent", "agent_hard"):
    PUZ[d] = pickle.load(open(f"/dev/shm/conseq/{d}/puzzles.pkl", "rb"))
    for i, p in enumerate(PUZ[d]):
        for a in all_actions(p["fam"], p["w"]).values():
            sets["planning"].append(step_text(p["w"], p["s0"], a))
            owner["planning"].append((p["fam"], d, i))
print({k: len(v) for k, v in sets.items()}, flush=True)


def flag_sets(sets):
    """pi_overlap.py's rules for every set; flags per distinct prompt."""
    train = {n: load(n) for n in TRAIN}
    long_h = collections.defaultdict(list)
    universe = set()
    for n, rows in train.items():
        for i, r in enumerate(rows):
            long_h[hash(norm(text(r.get("floor", ""))))].append((n, i))
            if r.get("ceiling"):
                long_h[hash(norm(text(r["ceiling"])))].append((n, i))
            universe |= shingles(text(r.get("floor", "")))
    sizes_by_file = {n: len(rows) for n, rows in train.items()}
    del train
    uniq, cands = {}, {}
    for sp, texts in sets.items():
        u = sorted(set(texts))
        step = max(1, len(u) // 1500)
        c = collections.Counter()
        for t in u[::step]:
            c.update(shingles(t))
        lay = {g for g, k in c.items() if k >= 0.2 * len(u[::step])}
        fl, cand = {}, []
        for t in u:
            ident = long_h.get(hash(norm(t)), [])
            fl[t] = {"identical": bool(ident), "ref": ident[0] if ident else None, "J": None, "near": False}
            if not ident:
                s = shingles(t) - lay
                if len(s) >= 10 and sum(g in universe for g in s) / len(s) >= 0.5:
                    cand.append((t, s))
        uniq[sp], cands[sp] = fl, cand
        print(sp, "distinct prompts", len(u), "identical", sum(f["identical"] for f in fl.values()), "near candidates", len(cand), flush=True)
    want = set()
    for cand in cands.values():
        for _, s in cand:
            want |= s
    jobs = []
    for n, size_n in sizes_by_file.items():
        size = (size_n + 63) // 64
        jobs += [(n, a, min(size_n, a + size), want) for a in range(0, size_n, size)]
    with mp.Pool(64) as pool:
        parts = pool.map(shard_worker, jobs, chunksize=1)
    index, sizes, keys = collections.defaultdict(list), [], []
    for part in parts:
        for n, i, size, hit in part:
            k = len(sizes)
            sizes.append(size)
            keys.append((n, i))
            for g in hit:
                index[g].append(k)
    for sp, cand in cands.items():
        for t, s in cand:
            cnt = collections.Counter(k for g in s for k in index.get(g, []))
            best, bk = 0.0, None
            for k, inter in cnt.most_common(20):
                j = inter / (len(s) + sizes[k] - inter)
                if j > best:
                    best, bk = j, k
            uniq[sp][t]["J"] = round(best, 4)
            if best >= 0.5:
                uniq[sp][t]["near"] = True
                uniq[sp][t]["ref"] = keys[bk]
    need = collections.defaultdict(set)  # structural comparison with the matched training row
    for fl in uniq.values():
        for f in fl.values():
            if f["ref"]:
                need[f["ref"][0]].add(f["ref"][1])
    rows = {}
    for n, idx in need.items():
        with open(f"/dev/shm/conseq/fac/{n}.jsonl") as fh:
            for i, line in enumerate(fh):
                if i in idx:
                    rows[(n, i)] = json.loads(line)
    for fl in uniq.values():
        for t, f in fl.items():
            if f["ref"]:
                r = rows[tuple(f["ref"])]
                pe, pt = paragraphs(t), paragraphs(text(r.get("floor", "")))
                f.update({"train_file": f["ref"][0], "train_kind": r.get("kind"), "same_rules": pe["rules"] == pt["rules"],
                          "same_state": pe["state"] == pt["state"], "same_actions": pe["actions"] == pt["actions"]})
    return uniq


U = flag_sets(sets)


def hit(sp, t):
    f = U[sp][t]
    return f["identical"] or f["near"]


res = {"rules": "pi_overlap.py (WS-F eval_masks): identical floor; near duplicate, word 8-gram Jaccard >= 0.5 vs one training row",
       "training": TRAIN, "overlap": {}}
for sp in sets:
    by = collections.defaultdict(collections.Counter)
    for t, o in zip(sets[sp], owner[sp]):
        fam = o[0]
        f = U[sp][t]
        by[fam]["prompts"] += 1
        by[fam]["identical"] += f["identical"]
        by[fam]["near"] += f["near"]
        if f["identical"] or f["near"]:
            by[fam]["same_rules_state_action" if f["same_rules"] and f["same_state"] and f["same_actions"] else
                    "same_rules_state" if f["same_rules"] and f["same_state"] else
                    "same_rules" if f["same_rules"] else "other_rules"] += 1
            by[fam]["file:" + f["train_file"]] += 1
    res["overlap"][sp] = {fam: dict(c) for fam, c in sorted(by.items())}


# chains with per-step traces: errors made per 100 steps on all and on clean steps; published metrics on all chains and
# on the chains with no overlapping step
def chain_stats(rs):
    a = collections.Counter()
    for r in rs:
        steps = chain_steps(r["fam"], r["len"], r["i"])
        flag = [hit("chains", s) for s in steps]
        if "trace" not in r:  # no per-step trace kept: the published metrics only
            r = dict(r, trace=[])
            a["chains_without_trace"] += 1
        else:
            assert len(steps) == r["len"] == len(r["trace"])
        a["chains"] += 1
        a["steps"] += r["len"]
        a["steps_clean"] += r["len"] - sum(flag)
        a["errors_made"] += sum(not ok for _, ok in r["trace"])
        a["errors_made_ge0.9"] += sum((not ok) and p >= 0.9 for p, ok in r["trace"])
        a["errors_made_clean"] += sum((not ok) and not f for (p, ok), f in zip(r["trace"], flag))
        a["errors_made_clean_ge0.9"] += sum((not ok) and p >= 0.9 and not f for (p, ok), f in zip(r["trace"], flag))
        a["carried_wrong"] += r["wrong_steps"]
        a["looks"] += r["looks"]
        a["exact"] += r["state_ok"]
        if not any(flag):
            a["chains_clean"] += 1
            a["steps_in_clean_chains"] += r["len"]
            a["carried_wrong_clean_chains"] += r["wrong_steps"]
            a["looks_clean_chains"] += r["looks"]
            a["exact_clean_chains"] += r["state_ok"]
    out = dict(a)
    if not a["chains_without_trace"]:
        out["errors_made_per_100"] = 100 * a["errors_made"] / a["steps"]
        out["errors_made_per_100_clean_steps"] = 100 * a["errors_made_clean"] / max(1, a["steps_clean"])
    out["carried_wrong_per_100"] = 100 * a["carried_wrong"] / a["steps"]
    out["looks_per_100"] = 100 * a["looks"] / a["steps"]
    if a["chains_clean"]:
        out["carried_wrong_per_100_clean_chains"] = 100 * a["carried_wrong_clean_chains"] / a["steps_in_clean_chains"]
        out["looks_per_100_clean_chains"] = 100 * a["looks_clean_chains"] / a["steps_in_clean_chains"]
    return out


res["chains"] = {}
for k, rs in recs.items():
    g = collections.defaultdict(list)
    for r in rs:
        g[(r["fam"], r["mode"])].append(r)
        g[("all", r["mode"])].append(r)
        g[(r["fam"], "all")].append(r)
    res["chains"][k] = {f"{fam}/{mode}": chain_stats(v) for (fam, mode), v in sorted(g.items())}

res["release_long_chain_cells"] = {}  # no per-chain record of i: overlap share of its chains (i = 0..5) only
for fam, L in old_cells:
    st = [s for i in range(6) for s in chain_steps(fam, L, i)]
    res["release_long_chain_cells"][f"{fam}/{L}"] = {"steps": len(st), "overlap": sum(hit("chains", s) for s in st),
                                                     "chains_with_overlap": sum(any(hit("chains", s) for s in chain_steps(fam, L, i)) for i in range(6))}

# speed: items whose step prompts never overlap
item_hit = collections.defaultdict(bool)
for t, (kind, i, _) in zip(sets["speed"], owner["speed"]):
    item_hit[i] |= hit("speed", t)
res["speed"] = {}
for mode in ("cq_par16", "cqm_par16"):
    P = jl(os.path.join(REL, "speed_bf16", f"{mode}.jsonl"))
    P = {p["i"]: p for p in P}
    assert sorted(P) == list(range(80))
    clean = [i for i in range(80) if not item_hit[i]]
    res["speed"][mode] = {"all": [len(P), 100 * sum(P[i]["ok"] for i in P) / len(P)],
                          "clean": [len(clean), 100 * sum(P[i]["ok"] for i in clean) / max(1, len(clean))],
                          "items_with_overlap_by_kind": dict(collections.Counter(P[i]["kind"] for i in range(80) if item_hit[i]))}

# image chains: all final answers were right, so every subset is too; overlap share only
img_hit = collections.defaultdict(bool)
for t, (fam, i, _) in zip(sets["image_chain"], owner["image_chain"]):
    img_hit[(fam, i)] |= hit("image_chain", t)
res["image_chain"] = {"items_with_overlap": sum(img_hit.values()), "items": 60}

# planning: puzzles whose first search layer never overlaps
res["planning"] = {}
for d, f in (("agent", "search_w4a5rel_agent.json"), ("agent_hard", "search_w4a5rel_agent_hard.json")):
    ok = json.load(open(os.path.join(REL, f)))["Ekbasis (release)"]["ok"]
    ph = collections.defaultdict(bool)
    for t, (fam, dd, i) in zip(sets["planning"], owner["planning"]):
        if dd == d:
            ph[i] |= hit("planning", t)
    clean = [i for i in range(len(ok)) if not ph[i]]
    res["planning"][d] = {"all": [len(ok), 100 * sum(ok) / len(ok)], "clean": [len(clean), 100 * sum(ok[i] for i in clean) / max(1, len(clean))],
                          "puzzles_with_overlap_by_fam": dict(collections.Counter(PUZ[d][i]["fam"] for i in range(len(ok)) if ph[i]))}

json.dump({f"{fam}/{L}/{i}": [t for t, s in enumerate(st) if hit("chains", s)] for (fam, L, i), st in _chains.items()},
          open(os.path.join(HERE, "chain_flags.json"), "w"))
json.dump(res, open(os.path.join(HERE, "chains.json"), "w"), indent=1)
print(json.dumps({k: res[k] for k in ("overlap", "release_long_chain_cells", "speed", "image_chain", "planning")}, indent=1))
for k, v in res["chains"].items():
    for cell, s in v.items():
        print(k, cell, {x: (round(y, 3) if isinstance(y, float) else y) for x, y in s.items()})
