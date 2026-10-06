"""WS-U confirmatory test, secondary suite: fresh planning one-step probe items. The dev probe enumerated every
(state, action) pair of the small worlds, so new seeds can only make new pairs in the SAMPLED worlds; this file uses the
dev recipe of those worlds (plan.probe_items / plan.instances, WS-P's vendored copy) with new seeds:
  Hanoi 6 disks: 150 legal moves + 150 onto a smaller disk (random states);  Lights Out 4x4: 20 random states per press;
  12 random jug worlds (the dev recipe), 6 pairs per kind of move;  16 Sokoban levels (12 with 1 box, 4 with 2 boxes,
  the dev recipe), 10 pairs per kind of move.
Questions and prompts exactly as the dev probe (ek.world_prompt / ek.world_qs); one request per pair.
python3 fresh_planning.py make|check|ask   (ask: EKBASIS_URL must be :8544, 16 in flight; resumable)
check = the same code with the dev seeds must give the dev pairs of Hanoi 6 and Lights Out 4x4, and the dev jug worlds
and Sokoban levels."""
import collections
import concurrent.futures as cf
import json
import os
import random
import sys

sys.path.insert(0, "/root/decis/mission/P/vendor_planning")
sys.path.insert(0, "/root/decis/capability/client")
import plan  # noqa: E402
from worlds import Hanoi, Jugs, LightsOut, distances, make_sokoban, reachable  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "cap", "planning")
FRESH = 9100604


def jug_worlds(rng):
    """plan.instances()'s random jug recipe: 12 worlds of 2-3 jugs with a goal at distance 4-9."""
    out, k = [], 0
    while k < 12:
        nj = rng.choice([2, 2, 3])
        caps = dict(zip("ABC", rng.sample(range(3, 14), nj)))
        w = Jugs(caps)
        s0 = {x: "0" for x in caps}
        dist = {}
        for s, d in distances(w, s0).values():
            for x in caps:
                if s[x] not in ("0", str(caps[x])):
                    dist[(x, s[x])] = min(dist.get((x, s[x]), 99), d)
        ds = sorted({d for d in dist.values() if 4 <= d <= 9})
        if not ds:
            continue
        d = rng.choice(ds)
        rng.choice(sorted(g for g, dd in dist.items() if dd == d))  # the goal draw, kept so the stream matches the recipe
        out.append((f"random{k}-" + "-".join(map(str, caps.values())), w, s0))
        k += 1
    return out


def sokoban_levels(rng1, rng2):
    out = []
    for lo, hi in ((3, 5), (6, 9), (10, 14), (15, 20)):
        for j in range(3):
            w, s0, _ = make_sokoban(rng1, 1, lo, hi)
            out.append((f"1box-{lo}-{hi}-{j}", w, s0))
    for lo, hi in ((6, 10), (11, 16)):
        for j in range(2):
            w, s0, _ = make_sokoban(rng2, 2, lo, hi)
            out.append((f"2box-{lo}-{hi}-{j}", w, s0))
    return out


def by_kind(w, s0, n, rng):
    pool = collections.defaultdict(list)
    for s in reachable(w, s0):
        for a in w.actions():
            pool[w.kind(s, a)].append((s, a))
    out = []
    for kind, xs in sorted(pool.items()):
        out += rng.sample(xs, min(n, len(xs)))
    return out


def items(base):
    """[(world id, world, state, action, how)] for seeds derived from `base` (base = 0 gives the dev seeds)."""
    out = []
    w6, rng = Hanoi(6), random.Random(base + 66)
    legal, bad = [], []
    while len(legal) < 150 or len(bad) < 150:
        s, a = {k: rng.choice("ABC") for k in w6.keys}, rng.choice(w6.actions())
        kd = w6.kind(s, a)
        (legal if kd == "legal move" else bad if kd.startswith("onto") else []).append((s, a))
    out += [("hanoi/6-probe", w6, s, a, "sampled") for s, a in legal[:150] + bad[:150]]
    w4, rng = LightsOut(4), random.Random(base + 41)
    for a in w4.actions():
        for _ in range(20):
            out.append(("lightsout/4x4", w4, {k: rng.choice(("on", "off")) for k in w4.keys}, a, "sampled"))
    for tag, w, s0 in jug_worlds(random.Random(base + 300)):
        out += [(f"jugs/{tag}", w, s, a, "sampled") for s, a in by_kind(w, s0, 6, random.Random(f"{base}-jugs-{tag}"))]
    for tag, w, s0 in sokoban_levels(random.Random(base + 600), random.Random(base + 700)):
        out += [(f"sokoban/{tag}", w, s, a, "sampled") for s, a in by_kind(w, s0, 10, random.Random(f"{base}-sok-{tag}"))]
    return out


def check():
    """Dev seeds (base 0) reproduce the dev Hanoi-6 and Lights Out 4x4 pairs, and the dev jug worlds and Sokoban levels."""
    dev = {}
    for l in open("/root/decis/capability/planning/runs/probe.jsonl"):
        r = json.loads(l)
        if r.get("part", "part1_probe") == "part1_probe" and "pred" in r:
            dev.setdefault(r["world"], set()).add((json.dumps(r["state"], sort_keys=True), r["action"]))
    mine = collections.defaultdict(set)
    for wid, w, s, a, _ in items(0):
        mine[wid].add((json.dumps(s, sort_keys=True), w.say(a)))
    ok = True
    for wid in ("hanoi/6-probe", "lightsout/4x4"):
        devk = [k for k in dev if k == wid or (wid == "lightsout/4x4" and k.startswith("lightsout/4x4"))]
        d = set().union(*(dev[k] for k in devk))
        same = mine[wid] == d
        ok &= same
        print(wid, "pairs", len(mine[wid]), "dev", len(d), "identical:", same)
    insts = plan.instances()
    dev_jugs = sorted(i["w"].rules for i in insts if i["fam"] == "jugs" and "random" in i["id"])
    my_jugs = sorted(w.rules for _, w, _ in jug_worlds(random.Random(300)))
    dev_sok = sorted(i["w"].rules + json.dumps(i["s0"], sort_keys=True) for i in insts if i["fam"] == "sokoban")
    my_sok = sorted(w.rules + json.dumps(s0, sort_keys=True) for _, w, s0 in sokoban_levels(random.Random(600), random.Random(700)))
    print("jug worlds identical:", dev_jugs == my_jugs, "| sokoban levels identical:", dev_sok == my_sok)
    ok &= dev_jugs == my_jugs and dev_sok == my_sok
    print("PLANNING CHECK", "OK" if ok else "MISMATCH")


def ask():
    from ekbasis import prompts as P
    from ekbasis.client import Ekbasis
    url = os.environ["EKBASIS_URL"]
    assert url.rstrip("/").endswith(":8544"), url
    client = Ekbasis(url=url, timeout=900)
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, "probe.jsonl")
    done = set()
    if os.path.exists(path):
        done = {(r["world"], json.dumps(r["state"], sort_keys=True), r["action"]) for r in map(json.loads, open(path))}
    todo = [(wid, w, s, a, how) for wid, w, s, a, how in items(FRESH)
            if (wid, json.dumps(s, sort_keys=True), w.say(a)) not in done]
    print(f"{len(todo)} pairs to ask ({len(done)} done) on {url}", flush=True)

    def one(x):
        wid, w, s, a, how = x
        qs = {k: P.choice(q, opts) for k, q, opts in w.vars()}
        for attempt in range(5):
            try:
                ans = client.ask(P.world_state(w.rules, w.render(s), [w.say(a)]), qs)
                break
            except Exception:  # noqa: BLE001
                if attempt == 4:
                    raise
        t = w.step(s, a)
        return {"part": "part1_probe", "world": wid, "fam": w.fam, "size": w.size, "how": how, "state": s,
                "action": w.say(a), "kind": w.kind(s, a), "truth": t, "pred": {k: str(ans[k].value) for k in w.keys},
                "conf": {k: float(ans[k].confidence) for k in w.keys},
                "probs": {k: {str(o): float(p) for o, p in ans[k].probabilities.items()} for k in w.keys}}

    with cf.ThreadPoolExecutor(16) as ex, open(path, "a") as f:
        for n, rec in enumerate(ex.map(one, todo), 1):
            f.write(json.dumps(rec, default=list) + "\n")
            if n % 200 == 0:
                f.flush()
                print(f"{n}/{len(todo)}", flush=True)
    print("PLANNING ASK DONE", flush=True)


def worlds_by_id(base=FRESH):
    return {wid: w for wid, w, _, _, _ in items(base)}


if __name__ == "__main__":
    stage = sys.argv[1]
    if stage == "make":
        its = items(FRESH)
        print(len(its), "fresh pairs", collections.Counter(i[0].split("/")[0] for i in its))
    elif stage == "check":
        check()
    elif stage == "ask":
        ask()
