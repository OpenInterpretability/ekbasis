#!/usr/bin/env python3
"""D8: overlap of every evaluation set behind an Ekbasis-Skopos-27B number with EVERY training row of its lineage.

Lineage (each stage's training files, every row counted as seen, although the LoRA stages sampled only part of them):
  Ekbasis-27B   ftrain_mixG3 (V42's file, which holds every earlier stage's rows) + r4a's mined_wide and mined_chain
  v49f          the machine's full ftrain_mixG3 (198,276 rows, incl. 7,423 replay rows not in the public file)
                + TRAIN_EXTRA: v45_v44git, v45rx_shell, v45rx_git, v45rx_sql, mined_chain, v46_anchor, v49_anchor2, v49_fx
  first Skopos  WiSE 0.5 between Ekbasis-27B and v49f (no data)
  R4 (release)  ftrain_r2 = ftrain_v50p (public ftrain_mixG3 + floorPL) + git_plan_train (floorPLG) + fac_rx (floorRX)
Eikos-27B's own training data (decision/preference data, not consequence prompts) is out of scope, except its replay rows,
which are in ftrain_mixG3.

Rules (Ekbasis-27B's audit of 2026-10-06, results/overlap_audit/scripts/pi_overlap.py in the ekbasis repository; same
tokenizer, shingles, layout and thresholds, PYTHONHASHSEED=0):
  identical   the evaluation prompt (floor), whitespace-normalized and lower-cased, equals a training row's floor or its
              hindsight prompt (ceiling).
  near        the floor's word 8-grams minus the set's own layout (8-grams in >= 20% of a sample of its floors, plus the
              8-grams of its question texts), at least 10 of them, reach Jaccard >= 0.5 against ONE training text:
              J = |s & t| / (|s| + |t| - |s & t|), s = evaluation shingles minus layout, t = all of the training text's
              shingles (as in pi_overlap.py).
Differences from pi_overlap.py, all in the conservative direction (more items flagged, never fewer):
  * EXACT best training text: the Jaccard is computed against every training text that shares a shingle (sparse
    product over an inverted index), not the 20 texts sharing the most shingles; the top-20 value is reported too.
  * near-duplicates are also searched among the ceilings (hindsight prompts), not only the floors ("near_ekbasis" keeps
    the floors-only rule for comparability).
  * sensitivity rule "near_symmetric": the set's layout is removed from the training text as well
    (J' = |s & t| / (|s| + |t - layout| - |s & t|)), so a long shared rules paragraph cannot hide an item-level copy.
Also reported: same prompt + same question (+ same answer) (pi_sameitem.py's test), and "identical up to numbers"
(every digit run replaced by 0 before comparing), a template-level signal, not an exclusion rule.

usage: python3 audit_overlap_skopos.py            (writes out/overlap.json; ~10-20 min on 8 cores, ~6 GB RAM)
       python3 audit_overlap_skopos.py --check    (also re-derives J of every flagged item from raw text)"""
from __future__ import annotations

import os
import sys

if os.environ.get("PYTHONHASHSEED") != "0":  # hash() of str must be the same in every process and every run
    os.environ["PYTHONHASHSEED"] = "0"
    os.execv(sys.executable, [sys.executable] + sys.argv)

import collections
import hashlib
import json
import multiprocessing as mp
import random
import re
import time

import numpy as np
import scipy.sparse as sp

HERE = os.path.dirname(os.path.abspath(__file__))
RS = os.path.dirname(HERE)  # .../mission/V50R/release_skopos
DM = os.path.dirname(os.path.dirname(os.path.dirname(RS)))  # .../decision_model
HF = os.path.join(HERE, "hf")  # read-only downloads: ekbasis-v50-research@6bfd3c9dc7 rtx/, ekbasis-data@b455316fce raw/
V49F = os.path.join(RS, "dataset", "facdata_v49f")  # ekbasis-fac-data@ee92bd6e60
OUT = os.path.join(HERE, "out")
NPROC = int(os.environ.get("NPROC", "8"))
LIMIT = int(os.environ.get("LIMIT", "0"))  # rows per training file, for a dry run only (0 = every row)

E27 = "Ekbasis-27B lineage (27s1..V42, r4a)"
TRAIN = [  # (name, path, stages)
    ("ftrain_mixG3_full", f"{V49F}/ftrain_mixG3.jsonl", [E27, "v49f"]),
    ("mined_wide", f"{HF}/ekbasis-data/raw/mined_wide.jsonl", [E27]),
    ("mined_chain", f"{V49F}/mined_chain.jsonl", [E27, "v49f"]),
    ("v45_v44git", f"{V49F}/v45_v44git.jsonl", ["v49f"]),
    ("v45rx_shell", f"{V49F}/v45rx_shell.jsonl", ["v49f"]),
    ("v45rx_git", f"{V49F}/v45rx_git.jsonl", ["v49f"]),
    ("v45rx_sql", f"{V49F}/v45rx_sql.jsonl", ["v49f"]),
    ("v46_anchor", f"{V49F}/v46_anchor.jsonl", ["v49f"]),
    ("v49_anchor2", f"{V49F}/v49_anchor2.jsonl", ["v49f"]),
    ("v49_fx", f"{V49F}/v49_fx.jsonl", ["v49f"]),
    ("ftrain_v50p", f"{DM}/mission/V50P/data/ftrain_v50p.jsonl", ["R4"]),
    ("git_plan_train", f"{HF}/rtx/v50p/data/git_plan_train.jsonl", ["R4"]),
    ("fac_rx", f"{HF}/rtx/v50p/data/fac_rx.jsonl", ["R4"]),
]
GROUPS = {  # stage groups for attribution (a text belongs to every group of every file that holds it)
    "ekbasis27b": {"ftrain_mixG3_full", "mined_wide", "mined_chain"},
    "v49f_extra": {"v45_v44git", "v45rx_shell", "v45rx_git", "v45rx_sql", "v46_anchor", "v49_anchor2", "v49_fx"},
    "r4_extra": {"ftrain_v50p", "git_plan_train", "fac_rx"},
}
V50 = f"{HF}/rtx/v50p/data"
RAW = f"{HF}/ekbasis-data/raw"
EVAL = [  # (name, path or None for generated) — every set any Skopos document cites
    ("git3_test_known", f"{V50}/git3_test_known.jsonl"), ("git3_test_held", f"{V50}/git3_test_held.jsonl"),
    ("guard_known", f"{V50}/guard_known.jsonl"), ("guard_held", f"{RAW}/guard_held.jsonl"),
    ("multi_test_trainfam", f"{RAW}/multi_test_trainfam.jsonl"), ("multi_test_testfam", f"{V50}/multi_test_testfam.jsonl"),
    ("ftest_family", f"{V50}/ftest_family.jsonl"), ("ftest_fresh", f"{V50}/ftest_fresh.jsonl"),
    ("fac_val", f"{V50}/fac_val.jsonl"), ("git_long", f"{V50}/git_long.jsonl"), ("git_long_val", f"{V50}/git_long_val.jsonl"),
    ("sess_val", f"{V50}/sess_val.jsonl"), ("fhorizon", f"{V50}/fhorizon.jsonl"), ("latent_test", f"{V50}/latent_test.jsonl"),
    ("awb_neutral", f"{V50}/awb_neutral.jsonl"), ("fval_git3", f"{V50}/fval_git3.jsonl"), ("m3val", f"{V50}/m3val.jsonl"),
    ("ce_items", f"{RAW}/ce_items.jsonl"), ("image_fresh", None),
    # PREREG_CERTIFIED_CARRYOVER.md step 1: one row per question, floor = the text the client sends (overlap_step.py export)
    ("certified_carryover", f"{RS}/certified_carryover/data/carryover_audit_items.jsonl"),
    # the hosted-API scorecard (ekbasis repository scorecard/scorecard.py at 941968e), rebuilt by build_scorecard_items.py
    *[(f"scorecard_{x}", f"{HF}/scorecard/items/{x}.jsonl")
      for x in ("git3_known", "git3_held", "guard_held", "worlds", "intent", "chains")],
]
# Where each set comes from (task 3 of D8; generator code read in DM/conseq, DM/mission/V50P|V50R/scripts, the RTX copies under
# audit/hf/rtx, and checked against the training files above). in_distribution = same generator as training rows, unseen seeds.
DISTRIBUTION = {
    "git3_test_known": (True, "gitbox3 (conseq/gen_git3.py, seeds 1910000+), the generator of floorG3 (Ekbasis-27B) and floorPLG (R4); known command types"),
    "git3_test_held": (False, "gitbox3 with the held command types (git rebase <branch>, git restore --source=HEAD~1 <file>), never in gitbox3 training rows; "
                              "BUT Skopos' later stages trained the same command types through the shell/git factory (v45rx_git, v49_fx, fac_rx: "
                              "'git rebase <branch>' in 945 rows, 'git restore --source=<branch> <file>' in 815 rows)"),
    "guard_known": (True, "gitbox3 (conseq/gen_guard_big.py, seeds 2910000+), known command types: the generator of floorG3/floorGA/floorPLG"),
    "guard_held": (False, "gitbox3 held command types (as git3_test_held, same caveat: the command types are in the factory rows of v49f and R4)"),
    "multi_test_trainfam": (True, "conseq/gen_multi.py, trained families (seed 2; training multi rows seed 1)"),
    "multi_test_testfam": (False, "conseq/gen_multi.py, never-trained families (cards, timers, machines appear in no training file)"),
    "ftest_family": (False, "conseq/gen_factory.py TEST families (cards, timers, machines), never trained"),
    "ftest_fresh": (False, "V50R/scripts/gen_ftest_fresh.py, the same never-trained families, fresh seed, firewalled against every v50p file"),
    "fac_val": (True, "the factory of fac_rx (run_family.py, seeds 200000+ vs 100000+), byte-identical to the F factory of v45rx_*; "
                      "rows whose floor is in fac_rx dropped, NOT checked against v45rx_*/v49_fx"),
    "git_long": (True, "V50P gen_git_long.py, gitbox3 sequences of 5/8/12 commands; floorPLG (R4) is gitbox3 sequences of 4-16 commands"),
    "git_long_val": (True, "V50R gen_git_val.py, gitbox3 5/8/12 commands, the validation twin of git_long (floorPLG's generator)"),
    "sess_val": (True, "fac_val's 1-command shell rows rendered as agent sessions (gen_session.py); content from the factory generator, "
                       "session layout trained only by the R3 sibling, not by R4"),
    "fhorizon": (True, "V50P build_data.py = conseq/gen_horizon.py: the training families of worldgen (kind floor, 1-3 actions) and floorPL "
                       "(5/8/12 actions); 20 actions never trained"),
    "latent_test": (False, "DM/mission/LATENT worlds (Tetris, Robot, Stock, Switches, Files; held-out Columns, Boxes, Stack, Bank): no Ekbasis "
                           "training kind uses them ('trainworld' refers to the LATENT predictor's split)"),
    "awb_neutral": (False, "Qwen/AgentWorldBench trajectories (external), labels from the real observation"),
    "fval_git3": (True, "MIXED validation set (checkpoint selection and calibration fit): gitbox3 known types 774 + factory-3 m3val 300 "
                        "(in-distribution) + Track/Tally 450 (never-trained families)"),
    "m3val": (True, "conseq/gen_m3only.py, factory-3 items like floor3 (seed 71 vs 65)"),
    "ce_items": (True, "MIXED: group T trained families (in-distribution), H trained families with the held question type, U never-trained "
                       "families (conseq/confident_errors.py)"),
    "certified_carryover": (False, "confirm-3's frozen fresh items (capability suites shell_wild, git_wild, sql_wild, rules_stress, "
                                   "accumulation; PREREG_CERTIFIED_CARRYOVER.md), firewalled at build against Ekbasis-27B's lineage only; "
                                   "no training generator makes them (the F factory was firewalled against these suites, F/OVERLAP.md)"),
    "scorecard_git3_known": (True, "400 of git3_test_known (scorecard.py's sample): gitbox3 known types, as git3_test_known"),
    "scorecard_git3_held": (False, "400 of git3_test_held: held out of the gitbox3 rows; the command types are in Skopos' factory rows"),
    "scorecard_guard_held": (False, "400 of guard_held: as guard_held"),
    "scorecard_worlds": (False, "400 of ftest_family: never-trained families (cards, timers, machines)"),
    "scorecard_intent": (False, "300 agent steps of the published-attack replay (ekbasis-cookbook studies/llm-judge-intent, 250 attack / "
                                "250 benign source rows); no training kind of the lineage uses this agent-step layout"),
    "scorecard_chains": (True, "MIXED: simulate's step prompts on two hand-written worlds; jugs is a trained worldgen family "
                               "(other wording), the elevator resembles worldgen Track (a never-trained family)"),
    "image_fresh": (True, "worldgen Toggles/Jugs = trained families (kind floor), 1-3 actions; the image modality was not in V45-R4 training"),
}
LABEL = {n: ("mixed" if n in ("fval_git3", "ce_items", "image_fresh", "scorecard_chains") else
             "held_out_of_the_generator_not_of_training" if n in ("git3_test_held", "guard_held", "scorecard_git3_held",
                                                                  "scorecard_guard_held") else
             "in_distribution" if v[0] else "held_out") for n, v in DISTRIBUTION.items()}
SETS = [n for n, _ in EVAL]
SID = {n: i for i, n in enumerate(SETS)}

# ------------------------------------------------------------------ the rules' text functions (as pi_overlap.py)
W_RE = re.compile(r"[a-z0-9_]+(?:[.\-'][a-z0-9_]+)*")


def words(t):
    return W_RE.findall(t.lower())


def shingles(t, n=8):
    w = words(t)
    return {hash(" ".join(w[i:i + n])) for i in range(len(w) - n + 1)}


def norm(t):
    return re.sub(r"\s+", " ", t).strip().lower()


def masked(t):
    return re.sub(r"\d+", "0", norm(t))


def text(x):
    return x if isinstance(x, str) else json.dumps(x, ensure_ascii=False)


def paragraphs(fl):
    out = {"rules": [], "state": [], "actions": [], "other": []}
    for p in re.split(r"\n\s*\n", fl.strip()):
        h = p.strip().split("\n", 1)[0].lower()
        if h.startswith(("current state", "state before", "estado atual")):
            out["state"].append(p.strip())
        elif h.startswith(("actions", "commands", "ações", "acoes")):
            out["actions"].append(p.strip())
        elif h.startswith(("the questions", "as perguntas")):
            out["other"].append(p.strip())
        else:
            out["rules"].append(p.strip())
    return {k: "\n\n".join(v) for k, v in out.items()}


def gold_key(g):
    s = str(g).strip().lower()
    return {"true": "yes", "false": "no"}.get(s, s)


def qkey(q):
    return norm(q) if isinstance(q, str) else norm(json.dumps(q, sort_keys=True, ensure_ascii=False))


def row_questions(r):
    """(question key, answer) pairs of a row; a question is its whole typed JSON (pi_sameitem.py)."""
    if "questions" in r:
        qs, gs = r.get("questions") or [], list(r.get("golds") or [])
    else:
        qs, gs = [r.get("question")], [r.get("gold")]
    gs += [None] * (len(qs) - len(gs))
    return [(qkey(q), gold_key(g)) for q, g in zip(qs, gs) if q is not None]


def q_instructions(r):
    qs = r.get("questions") if "questions" in r else [r.get("question")]
    return [q.get("instructions", "") if isinstance(q, dict) else "" for q in (qs or [])]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 24), b""):
            h.update(b)
    return h.hexdigest()


# ------------------------------------------------------------------ evaluation sets
def image_fresh_rows():
    """The 400 items of PREREG_IMAGE.md, regenerated exactly as image_served.py builds them (conseq/worldgen.py is
    byte-identical to the RTX copy rtx/v50p/worldgen/worldgen.py); the text prompt (state as text) is the one audited:
    the image and read prompts carry the same rules and actions and no state text."""
    os.environ["PROMPT_STYLE"] = "semif"
    sys.path.insert(0, f"{DM}/conseq")
    from worldgen import Jugs, Toggles
    label = lambda g: ("yes" if g else "no") if isinstance(g, bool) else str(g)
    N, rng, rows = 200, random.Random("image-fresh-20261015"), []
    for F in (Toggles, Jugs):
        got = {True: 0, False: 0}
        while got[True] + got[False] < N:
            w = F(rng)
            w.name = F.family
            s0 = s = w.sample_state(rng)
            acts = []
            for _ in range(rng.randint(1, 3)):
                a = w.sample_action(rng, s)
                s, _ = w.step(s, a)
                acts.append(a)
            qtype = rng.choice(F.QTYPES)
            st = rng.getstate()
            q, gold = w.ask(rng, s, [], qtype)
            r0 = random.Random()
            r0.setstate(st)
            changed = label(w.ask(r0, s0, [], qtype)[1]) != label(gold)
            if got[changed] >= N // 2:
                continue
            got[changed] += 1
            act = "\n".join(f"{i + 1}. {w.render_action(a)}" for i, a in enumerate(acts))
            rows.append({"world": F.family, "qtype": qtype, "steps": len(acts), "changed": changed, "question": q,
                         "gold": label(gold),
                         "floor": f"{w.rules}\n\nCurrent state:\n{w.render(s0)}\n\nActions, in order:\n{act}\n\n{w.floor_note()}"})
    ref = json.load(open(f"{HF}/rtx/v50p/image_skopos_int4.json"))
    assert [(r["fam"], r["changed"], r["gold"]) for r in ref] == [(r["world"], r["changed"], r["gold"]) for r in rows], \
        "regenerated image items differ from the served run"
    return rows


def load_eval():
    ev = {}
    for name, path in EVAL:
        rows = image_fresh_rows() if path is None else [json.loads(l) for l in open(path)]
        ev[name] = rows
    return ev


def layout_of(rows):
    """pi_overlap.py: shingles in >= 20% of a sample (every k-th floor, k = len // 1500) + the question texts' shingles."""
    step = max(1, len(rows) // 1500)
    c = collections.Counter()
    sample = rows[::step]
    for r in sample:
        c.update(shingles(text(r["floor"])))
    lay = {g for g, k in c.items() if k >= 0.2 * len(sample)}
    for r in rows:
        for q in q_instructions(r):
            lay |= shingles(q)
    return lay


# ------------------------------------------------------------------ training pass (workers)
G = {}  # filled in the parent before the pool forks


def line_offsets(path):
    offs, pos = [], 0
    with open(path, "rb") as f:
        for line in f:
            offs.append(pos)
            pos += len(line)
    return np.array(offs + [pos], dtype=np.int64)


def train_worker(job):
    fid, path, lo, hi = job
    Wh, LH, LM = G["W"], G["LH"], G["LM"]
    ev_nh, ev_mh = G["ev_nh"], G["ev_mh"]
    offs = G["offs"][fid]
    nh_l, fb_l, row_l, size_l, lc_l, ptr, idx = [], [], [], [], [], [0], []
    seen = {}
    occ = []  # every (norm hash, field bit, row) occurrence, for file/field masks
    ident, mident, rowmd5, kinds = [], [], [], collections.Counter()
    with open(path, "rb") as f:
        f.seek(offs[lo])
        for row in range(lo, hi):
            line = f.readline()
            rowmd5.append(hashlib.md5(line.rstrip(b"\n")).hexdigest()[:16])
            r = json.loads(line)
            kinds[r.get("kind")] += 1
            fl = text(r.get("floor") or "")
            ce = text(r.get("ceiling") or "")
            docs = [(fl, 1)] if fl else []
            if ce and ce != fl:
                docs.append((ce, 2))
            elif ce and ce == fl and docs:
                docs = [(fl, 3)]
            rq = None
            for t, fb in docs:
                nt = norm(t)
                nh = hash(nt)
                occ.append((nh, fb, row))
                if nh in ev_nh:
                    rq = rq if rq is not None else row_questions(r)
                    ident.append((nh, fid, row, fb, rq))
                mh = hash(re.sub(r"\d+", "0", nt))
                if mh in ev_mh:
                    mident.append((mh, fid, row, fb))
                if nh in seen:
                    continue
                seen[nh] = 1
                full = np.fromiter(shingles(t), dtype=np.int64)
                full.sort()
                pos = np.searchsorted(Wh, full)
                pos[pos >= len(Wh)] = 0
                hit = pos[Wh[pos] == full]
                lp = np.searchsorted(LH, full)
                lp[lp >= len(LH)] = 0
                lm = LM[lp[LH[lp] == full]]
                lc = np.array([int(((lm >> b) & 1).sum()) for b in range(len(SETS))], dtype=np.int32)
                nh_l.append(nh)
                fb_l.append(fb)
                row_l.append(row)
                size_l.append(len(full))
                lc_l.append(lc)
                idx.append(hit.astype(np.int32))
                ptr.append(ptr[-1] + len(hit))
    return {"fid": fid, "nh": np.array(nh_l, dtype=np.int64), "fb": np.array(fb_l, dtype=np.int8),
            "row": np.array(row_l, dtype=np.int32), "size": np.array(size_l, dtype=np.int32),
            "lc": np.array(lc_l, dtype=np.int32).reshape(-1, len(SETS)), "ptr": np.array(ptr, dtype=np.int64),
            "idx": np.concatenate(idx) if idx else np.zeros(0, np.int32),
            "occ": np.array(occ, dtype=np.int64).reshape(-1, 3), "ident": ident, "mident": mident,
            "rowmd5": rowmd5, "kinds": kinds}


# ------------------------------------------------------------------ the exact Jaccard (block workers)
def block_worker(job):
    lo, hi = job
    E, TT = G["E"], G["TT"]
    s_size, s_set = G["s_size"], G["s_set"]
    size, lc, fmask, filemask, gmasks = G["size"], G["lc"], G["fmask"], G["filemask"], G["gmasks"]
    P = (E[lo:hi] @ TT).tocsr()
    res = []
    for k in range(hi - lo):
        a, b = P.indptr[k], P.indptr[k + 1]
        d = P.indices[a:b]
        inter = P.data[a:b].astype(np.float64)
        s = float(s_size[lo + k])
        out = {"JE_floor": 0.0, "JE_floor_doc": -1, "JE_top20": 0.0, "JE_all": 0.0, "JE_all_doc": -1,
               "JS_all": 0.0, "JS_all_doc": -1, "JE_group": {}, "n_share": int(b - a)}
        if b > a and s > 0:
            sz = size[d].astype(np.float64)
            je = inter / (s + sz - inter)
            js = inter / (s + sz - lc[d, s_set[lo + k]] - inter)
            fl = (fmask[d] & 1) > 0
            if fl.any():
                jf = np.where(fl, je, -1.0)
                i = int(np.argmax(jf))
                out["JE_floor"], out["JE_floor_doc"] = float(jf[i]), int(d[i])
                # pi_overlap.py: the best of the 20 floors sharing the most shingles (ties by index order there too)
                fi = np.nonzero(fl)[0]
                top = fi[np.argsort(-inter[fi], kind="stable")[:20]]
                out["JE_top20"] = float(je[top].max())
            i = int(np.argmax(je))
            out["JE_all"], out["JE_all_doc"] = float(je[i]), int(d[i])
            i = int(np.argmax(js))
            out["JS_all"], out["JS_all_doc"] = float(js[i]), int(d[i])
            for g, m in gmasks.items():
                sel = (filemask[d] & m) > 0
                out["JE_group"][g] = float(je[sel].max()) if sel.any() else 0.0
        res.append(out)
    return lo, res


# ------------------------------------------------------------------ main
def main():
    t0 = time.time()
    check = "--check" in sys.argv
    os.makedirs(OUT, exist_ok=True)
    ctx = mp.get_context("fork")

    # 1. evaluation sets, layouts, shingle sets
    ev = load_eval()
    print({k: len(v) for k, v in ev.items()}, flush=True)
    lay = {n: layout_of(rows) for n, rows in ev.items()}
    lay_mask = collections.defaultdict(int)
    for n, L in lay.items():
        for g in L:
            lay_mask[g] |= 1 << SID[n]
    LH = np.array(sorted(lay_mask), dtype=np.int64)
    LM = np.array([lay_mask[g] for g in LH.tolist()], dtype=np.int64)
    uniq = []  # unique (set, floor) prompts: (set, floor text, [row indices])
    uix = {}
    for n, rows in ev.items():
        for i, r in enumerate(rows):
            key = (n, text(r["floor"]))
            if key not in uix:
                uix[key] = len(uniq)
                uniq.append([n, key[1], []])
            uniq[uix[key]][2].append(i)
    s_sets, s_full = [], []
    for n, fl, _ in uniq:
        full = shingles(fl)
        s_full.append(len(full))
        s_sets.append(np.array(sorted(full - lay[n]), dtype=np.int64))
    Wh = np.unique(np.concatenate(s_sets)) if s_sets else np.zeros(0, np.int64)
    print(f"unique evaluation prompts {len(uniq)}; distinct non-layout shingles {len(Wh)}", flush=True)
    ev_nh = {hash(norm(fl)) for _, fl, _ in uniq}
    ev_mh = {hash(masked(fl)) for _, fl, _ in uniq}

    # 2. training pass
    offs = [line_offsets(p) for _, p, _ in TRAIN]
    G.update({"W": Wh, "LH": LH, "LM": LM, "ev_nh": ev_nh, "ev_mh": ev_mh, "offs": offs})
    jobs = []
    for fid, (name, path, _) in enumerate(TRAIN):
        n = len(offs[fid]) - 1 if not LIMIT else min(LIMIT, len(offs[fid]) - 1)
        k = max(1, min(64, n // 2000))
        step = (n + k - 1) // k
        jobs += [(fid, path, a, min(n, a + step)) for a in range(0, n, step)]
    with ctx.Pool(NPROC) as pool:
        parts = pool.map(train_worker, jobs, chunksize=1)
    print(f"training pass {time.time() - t0:.0f}s", flush=True)

    corpus = {}
    for fid, (name, path, stages) in enumerate(TRAIN):
        ps = [p for p in parts if p["fid"] == fid]
        md5s = [m for p in ps for m in p["rowmd5"]]
        assert LIMIT or len(md5s) == len(offs[fid]) - 1
        kinds = collections.Counter()
        for p in ps:
            kinds.update(p["kinds"])
        corpus[name] = {"path": os.path.relpath(path, RS), "sha256": sha256(path), "rows": len(md5s),
                        "stages": stages, "kinds": dict(kinds), "_md5": md5s}
    full_md5 = set(corpus["ftrain_mixG3_full"]["_md5"])
    v50 = corpus["ftrain_v50p"]["_md5"]
    corpus["ftrain_v50p"]["rows_not_in_full_ftrain_mixG3"] = sum(m not in full_md5 for m in v50)
    all_md5 = set()
    for c in corpus.values():
        all_md5 |= set(c.pop("_md5"))
    print("corpus rows", {k: v["rows"] for k, v in corpus.items()}, "distinct rows", len(all_md5), flush=True)

    # merge documents (unique normalized texts), file and field masks over every occurrence
    fids = np.concatenate([np.full(len(p["nh"]), p["fid"], np.int16) for p in parts])
    nh = np.concatenate([p["nh"] for p in parts])
    occ = np.concatenate([np.column_stack([p["occ"], np.full(len(p["occ"]), p["fid"], np.int64)]) for p in parts])
    first = np.unique(nh, return_index=True)[1]
    first.sort()  # earliest file / row first
    doc_nh = nh[first]
    order = np.argsort(doc_nh)
    oi = np.searchsorted(doc_nh[order], occ[:, 0])
    occ_doc = order[oi]
    filemask = np.zeros(len(first), np.int64)
    fmask = np.zeros(len(first), np.int64)
    np.bitwise_or.at(filemask, occ_doc, (1 << occ[:, 3]).astype(np.int64))
    np.bitwise_or.at(fmask, occ_doc, occ[:, 1])
    occ_count = np.bincount(occ_doc, minlength=len(first))
    # per document arrays (shard-local -> global)
    size = np.concatenate([p["size"] for p in parts])[first]
    lc = np.concatenate([p["lc"] for p in parts])[first]
    row = np.concatenate([p["row"] for p in parts])[first]
    dfid = fids[first]
    fb_first = np.concatenate([p["fb"] for p in parts])[first]
    gptr = []
    for p in parts:
        n = len(p["nh"])
        for j in range(n):
            gptr.append((p, j))
    sel_ptr = [0]
    sel_idx = []
    for g in first.tolist():
        p, j = gptr[g]
        seg = p["idx"][p["ptr"][j]:p["ptr"][j + 1]]
        sel_idx.append(seg)
        sel_ptr.append(sel_ptr[-1] + len(seg))
    del gptr
    T = sp.csr_matrix((np.ones(sel_ptr[-1], np.int32), np.concatenate(sel_idx), np.array(sel_ptr)),
                      shape=(len(first), len(Wh)))
    del sel_idx
    TT = T.transpose().tocsr()
    print(f"training texts: {len(nh)} (unique {len(first)}); shingle hits {T.nnz}", flush=True)

    # 3. evaluation matrix, cost estimate, exact Jaccard by blocks
    ecols = [np.searchsorted(Wh, s) for s in s_sets]
    eptr = np.cumsum([0] + [len(c) for c in ecols])
    E = sp.csr_matrix((np.ones(eptr[-1], np.int32), np.concatenate(ecols), eptr), shape=(len(uniq), len(Wh)))
    df = np.diff(TT.indptr)
    cost = E @ df
    print(f"sparse product cost (sum of postings) {int(cost.sum()):,}, max per prompt {int(cost.max()):,}", flush=True)
    gmasks = {g: sum(1 << i for i, (n, _, _) in enumerate(TRAIN) if n in names) for g, names in GROUPS.items()}
    G.update({"E": E, "TT": TT, "s_size": np.array([len(s) for s in s_sets]),
              "s_set": np.array([SID[u[0]] for u in uniq]), "size": size, "lc": lc, "fmask": fmask,
              "filemask": filemask, "gmasks": gmasks})
    B = 64
    with ctx.Pool(NPROC) as pool:
        parts2 = pool.map(block_worker, [(a, min(len(uniq), a + B)) for a in range(0, len(uniq), B)], chunksize=1)
    J = [None] * len(uniq)
    for lo, res in parts2:
        J[lo:lo + len(res)] = res
    print(f"jaccard {time.time() - t0:.0f}s", flush=True)

    # identical, same question / answer, identical up to numbers
    ident = collections.defaultdict(list)
    for p in parts:
        for nh_, fid, r_, fb, rq in p["ident"]:
            ident[nh_].append((fid, r_, fb, rq))
    mident = collections.defaultdict(list)
    for p in parts:
        for mh, fid, r_, fb in p["mident"]:
            mident[mh].append((fid, r_, fb))

    def read_row(fid, r_):
        with open(TRAIN[fid][1], "rb") as f:
            f.seek(offs[fid][r_])
            return json.loads(f.readline())

    def doc_ref(d):
        fid, r_ = int(dfid[d]), int(row[d])
        files = [TRAIN[i][0] for i in range(len(TRAIN)) if filemask[d] >> i & 1]
        return {"file": TRAIN[fid][0], "row": r_, "field": {1: "floor", 2: "ceiling", 3: "floor"}[int(fb_first[d])],
                "texts_with_this_prompt": int(occ_count[d]), "files": files}

    # 4. per set report
    report, flags_out = {}, {}
    pos_unique = {}
    for u, (n, fl, idxs) in enumerate(uniq):
        for i in idxs:
            pos_unique[(n, i)] = u
    for n, rows in ev.items():
        R = collections.defaultdict(list)
        examples = []
        structure = collections.Counter()
        hist_e, hist_s = collections.Counter(), collections.Counter()
        attrib = collections.Counter()
        for i, r in enumerate(rows):
            u = pos_unique[(n, i)]
            fl = uniq[u][1]
            s_n = len(s_sets[u])
            j = J[u]
            h = hash(norm(fl))
            idm = ident.get(h, [])
            if idm:
                R["identical"].append(i)
                tq = {(qk, g) for _, _, _, rq in idm for qk, g in (rq or [])}
                tk = {qk for qk, _ in tq}
                evq = row_questions(r)
                if any(qk in tk for qk, _ in evq):
                    R["same_prompt_same_question"].append(i)
                if any(x in tq for x in evq):
                    R["same_prompt_same_question_same_answer"].append(i)
                for fname in sorted({TRAIN[fid][0] for fid, _, _, _ in idm}):
                    attrib[("identical", fname)] += 1
            if hash(masked(fl)) in mident:
                R["identical_up_to_numbers"].append(i)
            if s_n < 10:
                R["near_rule_not_applicable"].append(i)
            else:
                if j["JE_floor"] >= 0.5:
                    R["near_ekbasis"].append(i)
                if j["JE_top20"] >= 0.5:
                    R["near_ekbasis_top20"].append(i)
                if j["JE_all"] >= 0.5:
                    R["near"].append(i)
                    for g, v in j["JE_group"].items():
                        if v >= 0.5:
                            attrib[("near", g)] += 1
                if j["JS_all"] >= 0.5:
                    R["near_symmetric"].append(i)
                hist_e[min(9, int(j["JE_all"] * 10))] += 1
                hist_s[min(9, int(j["JS_all"] * 10))] += 1
        # the earliest stage whose own rows hold the match (ftrain_v50p repeats ftrain_mixG3's public rows, so an R4
        # attribution means floorPL, git_plan_train or fac_rx only)
        stage_of = {}
        for i in sorted(set(R["identical"]) | set(R["near"])):
            u = pos_unique[(n, i)]
            files = {TRAIN[fid][0] for fid, _, _, _ in ident.get(hash(norm(uniq[u][1])), [])}
            for g in ("ekbasis27b", "v49f_extra", "r4_extra"):
                if (files & GROUPS[g]) or J[u]["JE_group"].get(g, 0) >= 0.5:
                    stage_of[i] = g
                    break
        first_stage = dict(collections.Counter(stage_of.values()))
        idset = set(R["identical"])
        attrib_first = collections.Counter((("identical" if i in idset else "near"), g) for i, g in stage_of.items())
        prim = sorted(set(R["identical"]) | set(R["near"]))
        sens = sorted(set(prim) | set(R["near_symmetric"]))
        R["flagged"] = prim
        R["flagged_sensitivity"] = sens
        R["flagged_ekbasis_top20"] = sorted(set(R["identical"]) | set(R["near_ekbasis_top20"]))
        R["flagged_ekbasis_exact"] = sorted(set(R["identical"]) | set(R["near_ekbasis"]))
        ident_set = set(R["identical"])
        # structure of each flagged item vs the training text it matches (sensitivity set, which contains the primary)
        for i in sens:
            u = pos_unique[(n, i)]
            j = J[u]
            fl = uniq[u][1]
            if i in ident_set:
                fid, r_, fb, _ = ident[hash(norm(fl))][0]
                tr = read_row(fid, r_)
                ref = {"file": TRAIN[fid][0], "row": r_, "field": "ceiling" if fb == 2 else "floor"}
                ttext = text(tr.get("ceiling") if fb == 2 else tr.get("floor"))
                how = "identical"
                jv = 1.0
            else:
                d = j["JE_all_doc"] if j["JE_all"] >= 0.5 else j["JS_all_doc"]
                ref = doc_ref(d)
                tr = read_row(int(dfid[d]), int(row[d]))
                ttext = text(tr.get("ceiling") if ref["field"] == "ceiling" else tr.get("floor"))
                how = "near" if j["JE_all"] >= 0.5 else "near_symmetric_only"
                jv = j["JE_all"] if how == "near" else j["JS_all"]
                if check:  # re-derive the Jaccard from the raw texts
                    s = shingles(fl) - lay[n]
                    t = shingles(ttext)
                    jj = len(s & t) / (len(s) + len(t) - len(s & t)) if how == "near" else \
                        len(s & t) / (len(s) + len(t - lay[n]) - len(s & t))
                    assert abs(jj - jv) < 1e-9, (n, i, jj, jv)
            pe, pt = paragraphs(fl), paragraphs(ttext)
            evq = row_questions(rows[i])
            trq = row_questions(tr)
            st = {"same_rules": pe["rules"] == pt["rules"], "same_state": pe["state"] == pt["state"],
                  "same_actions": pe["actions"] == pt["actions"],
                  "same_question": any(q in {k for k, _ in trq} for q, _ in evq),
                  "same_question_same_answer": any(x in set(trq) for x in evq)}
            for k, v in st.items():
                structure[(how, k)] += int(v)
            structure[(how, "items")] += 1
            if len(examples) < 6 and (how != "near_symmetric_only" or len(examples) < 3):
                examples.append({"i": i, "id": rows[i].get("id"), "world": rows[i].get("world"),
                                 "group": rows[i].get("group"), "how": how, "J": round(jv, 4), "train": ref,
                                 "train_id": tr.get("id"), "train_kind": tr.get("kind"), **st})
        by = {}
        gk = "group" if n == "ce_items" else "suite" if n == "certified_carryover" else "world"
        for g in sorted({str(r.get(gk)) for r in rows}):
            gi = [i for i, r in enumerate(rows) if str(r.get(gk)) == g]
            gs = set(gi)
            by[g] = {"rows": len(gi), "identical": len(gs & set(R["identical"])), "near": len(gs & set(R["near"])),
                     "flagged": len(gs & set(prim)), "flagged_sensitivity": len(gs & set(sens)),
                     "identical_up_to_numbers": len(gs & set(R["identical_up_to_numbers"]))}
        report[n] = {
            "rows": len(rows), "unique_prompts": len({pos_unique[(n, i)] for i in range(len(rows))}),
            "layout_shingles": len(lay[n]),
            **{k: len(R[k]) for k in ["identical", "same_prompt_same_question", "same_prompt_same_question_same_answer",
                                      "near_ekbasis_top20", "near_ekbasis", "near", "near_symmetric",
                                      "near_rule_not_applicable", "identical_up_to_numbers", "flagged_ekbasis_top20",
                                      "flagged_ekbasis_exact", "flagged", "flagged_sensitivity"]},
            "in_distribution": DISTRIBUTION[n][0], "distribution_note": DISTRIBUTION[n][1],
            # by the earliest stage whose own rows hold the match (ekbasis27b, v49f_extra, r4_extra = R4's new rows only)
            "attribution": {f"{a}:{b}": c for (a, b), c in sorted(attrib_first.items())},
            # every file / stage group holding a match (an item counts once per file or group; ftrain_v50p repeats the
            # public ftrain_mixG3 rows, so "near:r4_extra" here includes matches on replayed Ekbasis-27B rows)
            "attribution_files": {f"{a}:{b}": c for (a, b), c in sorted(attrib.items())},
            "flagged_by_first_stage": first_stage,
            "structure": {f"{a}:{b}": c for (a, b), c in sorted(structure.items())},
            "best_J_histogram": {"rule": {f"{k / 10:.1f}": hist_e[k] for k in sorted(hist_e)},
                                 "symmetric": {f"{k / 10:.1f}": hist_s[k] for k in sorted(hist_s)}},
            "by_" + gk: by, "examples": examples}
        R["first_stage_v49f"] = sorted(i for i, g in stage_of.items() if g == "v49f_extra")
        R["first_stage_r4"] = sorted(i for i, g in stage_of.items() if g == "r4_extra")
        flags_out[n] = {k: R[k] for k in ["first_stage_v49f", "first_stage_r4", "identical", "same_prompt_same_question", "same_prompt_same_question_same_answer",
                                          "near_ekbasis", "near", "near_symmetric", "identical_up_to_numbers",
                                          "near_rule_not_applicable", "flagged", "flagged_sensitivity"]}
        print(n, json.dumps({k: v for k, v in report[n].items() if isinstance(v, int)}), flush=True)

    # per-item best J (for the recompute and for readers): rounded, in row order
    best = {n: {"J_rule": [round(J[pos_unique[(n, i)]]["JE_all"], 4) for i in range(len(rows))],
                "J_symmetric": [round(J[pos_unique[(n, i)]]["JS_all"], 4) for i in range(len(rows))]}
            for n, rows in ev.items()}
    sets = {}
    for n in SETS:
        r = report[n]
        sets[n] = {
            "items": r["rows"], "identical": r["identical"], "near_dup": r["flagged"] - r["identical"], "flagged": r["flagged"],
            "flagged_sensitivity": r["flagged_sensitivity"], "same_prompt_same_question_same_answer":
                r["same_prompt_same_question_same_answer"], "in_distribution": DISTRIBUTION[n][0], "distribution": LABEL[n]}
    sets["image"] = sets["image_fresh"]  # the name an earlier card draft used
    fam = collections.Counter(str(r.get("world", "")).replace("fac_", "") for r in ev["fac_val"])
    out = {
        "rule": "identical prompts (also against the hindsight prompt), and near-duplicates at word 8-gram Jaccard >= 0.5 "
                "against one training text after removing each set's own layout (Ekbasis-27B's audit rule, exact best match)",
        "sets": sets, "by_family": {"fac_val": dict(fam), "fac_val_flagged": {
            k: v["flagged"] for k, v in report["fac_val"]["by_world"].items()}},
        "audit": "D8 overlap audit, Ekbasis-Skopos-27B (release_skopos/audit/audit_overlap_skopos.py)",
        "rules": {"identical": "normalized floor == a training floor or ceiling",
                  "near": "|s|>=10 and exact best Jaccard >= 0.5 vs one training floor or ceiling (s = floor 8-grams "
                          "minus the set's layout; t = all the training text's 8-grams)",
                  "near_ekbasis": "same, floors only (pi_overlap.py's rule, exact best row)",
                  "near_ekbasis_top20": "same, floors only, best of the 20 floors sharing the most 8-grams (pi_overlap.py as run)",
                  "near_symmetric": "sensitivity: the set's layout also removed from the training text",
                  "flagged": "identical OR near (the exclusion used for the clean numbers)",
                  "flagged_sensitivity": "flagged OR near_symmetric"},
        "training_corpus": corpus,
        "training_texts": {"occurrences": int(len(occ)), "unique_normalized": int(len(first)),
                           "shingle_hits_kept": int(T.nnz)},
        "evaluation_sources": {n: (os.path.relpath(p, RS) if p else "regenerated (image_served.py, seed image-fresh-20261015)")
                               for n, p in EVAL},
        "evaluation_sha256": {n: sha256(p) for n, p in EVAL if p},
        "report": report, "flags": flags_out, "best_J": best,
        "seconds": round(time.time() - t0)}
    json.dump(out, open(os.path.join(OUT, "overlap.json"), "w"))
    print("written", os.path.join(OUT, "overlap.json"), f"{time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
