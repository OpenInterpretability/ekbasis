"""Multi-question items for the 'all questions in one pass' readout: one state + 1-3 actions, and 3-6 different typed
questions about the outcome (each with gold, and gold0/known0 about the initial state for the honest metric).
  multi_train            training families (factory 1), the families' held question types left out
  multi_test_trainfam    new items of the training families
  multi_test_testfam     never-trained families (cards, timers, machines)
argv: out dir."""
import json, os, random, sys
sys.path.insert(0, "/root/decis/conseq")
from worldgen import TEST, TRAIN

OUT = sys.argv[1]


def item(F, rng, allow_held):
    w = F(rng)
    w.name = F.family
    for _ in range(200):
        s0 = s = w.sample_state(rng)
        acts, events, ok = [], [], True
        for _ in range(rng.randint(1, 3)):
            a = w.sample_action(rng, s)
            ns, ev = w.step(s, a)
            if ns is None:
                ok = False
                break
            acts.append(a)
            events.append(ev)
            s = ns
        if ok:
            break
    else:
        return None
    qtypes = [q for q in F.QTYPES if allow_held or q != getattr(F, "HELD_Q", None)]
    qs, golds, gold0s, known0s, kinds, seen = [], [], [], [], [], set()
    for _ in range(rng.randint(3, 6) * 3):
        if len(qs) >= 6:
            break
        qt = rng.choice(qtypes)
        st = rng.getstate()
        try:
            q, gold = w.ask(rng, s, events, qt)
        except Exception:
            continue
        if q["instructions"] in seen:
            continue
        r0 = random.Random()
        r0.setstate(st)
        try:
            q0, g0 = w.ask(r0, s0, [], qt)
            k0 = q0["instructions"] == q["instructions"]
        except Exception:
            g0, k0 = None, False
        seen.add(q["instructions"])
        qs.append(q)
        golds.append(gold)
        gold0s.append(g0 if k0 else None)
        known0s.append(k0)
        kinds.append(qt)
    if len(qs) < 3:
        return None
    act_text = "\n".join(f"{i + 1}. {w.render_action(a)}" for i, a in enumerate(acts))
    floor = f"{w.rules}\n\nCurrent state:\n{w.render(s0)}\n\nActions, in order:\n{act_text}\n\n{w.floor_note()}"
    return {"kind": "multi", "world": w.name, "steps": len(acts), "floor": floor, "questions": qs, "golds": golds,
            "gold0s": gold0s, "known0s": known0s, "qtypes": kinds}


def build(fams, n, seed, allow_held):
    rng, out = random.Random(seed), []
    while len(out) < n:
        x = item(rng.choice(fams), rng, allow_held)
        if x:
            out.append(x)
    return out


os.makedirs(OUT, exist_ok=True)
for name, fams, n, seed, held in (("multi_train", TRAIN, 24000, 1, False), ("multi_test_trainfam", TRAIN, 600, 2, False),
                                  ("multi_test_testfam", TEST, 600, 3, True)):
    rows = build(fams, n, seed, held)
    with open(f"{OUT}/{name}.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    nq = sum(len(r["questions"]) for r in rows)
    print(f"{name}: {len(rows)} items, {nq} questions ({nq / len(rows):.1f} per item)", flush=True)
