# PRELAUNCH PORT (P4) of _orig/long_chain3.py: every changed line is marked PORT; the full diff is CHANGES.diff in this folder.
"""Long chains, the fixes for errors that never fade: predict, observe, correct. One action per step, every variable asked
at every step (System One API), the next state rebuilt from the answers (cards: the most probable VALID ordering, by
assignment, as in long_chain2.py); the chains and seeds of long_chain2.py (i < 6) plus more.
Modes:
  text        never look (the published baseline)
  obs50       look at the real state every 50 actions
  conf<t>     look at the real state only when the chain confidence since the last look drops below t (the model says
              when to look); chain confidence = product over steps of the probability of the state read at that step
  step<t>     look only when one step's state probability is below t (the uncertain step itself)
  dual        cards: also ask the inverse questions ("At which position is the X?", a trained question type of the
              generator) and combine both views per cell before the assignment
  dual_conf<t> both
  until<t>    conf<t>, and after a look that finds the forecast wrong (a surprise), look again after the next action, and
              again, until a look finds it right: look while it is not right yet
  check<t>    until<t>, and a scheduled check when no look happened for `gap` actions: gap 8, doubled after every look
              that finds the forecast right (at most 64), back to 8 after a surprise (catches errors made with confidence)
A look is exact (the real state, as a `git status` or a sensor gives it); every look is counted.
env: CQ_URL, N (chains per length and mode for cards; 8; the other worlds, controls, get half), PAR (16), OUT (jsonl),
ONLY (e.g. "cards:text": just these world:mode pairs), TRACE=1 (per step: the state's probability and whether the step
itself was right, i.e. the read state equals the true transition of the model's own previous state: the curve of looks
against silent errors for any threshold, offline)."""
import concurrent.futures as cf, json, math, os, random, re, sys, threading, time, urllib.request
MINE_LOCK = threading.Lock()
sys.path.insert(0, os.environ.get("LIB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib")))  # PORT
from envs import qchoice, qnoul
from scipy.optimize import linear_sum_assignment
from worldgen import Cards, Jugs, Machines, Toggles

CQ_URL = os.environ.get("CQ_URL", "http://127.0.0.1:8503/v1/systemone")
N, PAR = int(os.environ.get("N", "8")), int(os.environ.get("PAR", "16"))
OUT = os.environ.get("OUT", "/dev/shm/conseq/long_chain3.jsonl")


def post(body):
    req = urllib.request.Request(CQ_URL, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    for attempt in range(3):
        try:
            return json.load(urllib.request.urlopen(req, timeout=900))
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2)


VARS = {"jugs": lambda w: [(x, qchoice(f"How many liters are in {x}?", [(str(k), f"{k} liters") for k in range(w.cap[x] + 1)])) for x in w.names],
        "toggles": lambda w: [(j, qchoice(f"What state is {w.lamp} {j + 1} in?", [(x, x) for x in w.states])) for j in range(w.n)],
        "machines": lambda w: [(d, qchoice(f"In which state is {d}?", [(x, x) for x in w.cycle])) for d in w.devs],
        "cards": lambda w: [(k, qchoice(f"Which card is at position {k + 1}?", [(x, x) for x in w.labels])) for k in range(w.n)]}
WHERE = lambda w: [(x, qchoice(f"At which position is the {x}?", [(str(k), f"position {k}") for k in range(1, w.n + 1)])) for x in w.labels]


def SECOND(w):
    """A second view of the state (views<t> modes): derived questions in each family's own wording, each with the answer
    the primary read implies (yes/no as a bool, a choice as its label)."""
    if w.family == "jugs":
        return [q for x in w.names for q in ((qnoul(f"Is {x} full?"), lambda S, x=x: S["v"][x] == w.cap[x]),
                                             (qnoul(f"Is {x} empty?"), lambda S, x=x: S["v"][x] == 0))]
    if w.family == "toggles":
        return [(qnoul(f"Are {w.lamp} {j + 1} and {w.lamp} {j + 2} in the same state?"), lambda S, j=j: S["st"][j] == S["st"][j + 1])
                for j in range(w.n - 1)]
    if w.family == "machines":
        d = w.devs
        return [(qnoul(f"Are {d[j]} and {d[j + 1]} in the same state?"), lambda S, j=j: S["st"][d[j]] == S["st"][d[j + 1]])
                for j in range(len(d) - 1)]
    return [(q, lambda S, x=x: str(S["xs"].index(x) + 1)) for x, q in WHERE(w)]


def value(w, s, k):
    return {"jugs": lambda: str(s["v"][k]), "toggles": lambda: w.states[s["st"][k]], "machines": lambda: w.cycle[s["st"][k]],
            "cards": lambda: s["xs"][k]}[w.family]()


def _lse(xs):
    m = max(xs)
    return m + math.log(sum(math.exp(x - m) for x in xs))


def fuse_state(w, D, second_p):
    """fuse<t> modes: the primary answers D[k] (option -> probability) and the second view's yes-probabilities (in
    SECOND's order) as two kinds of evidence about the same state: the state most probable under both, and its
    probability normalized over every state. Containers: each one's amount with "full" and "empty". Lamps and machines:
    a chain of neighbours, solved exactly (Viterbi for the best state, the forward pass for the normalizer)."""
    L = lambda x: math.log(min(max(x, 1e-9), 1 - 1e-12))
    if w.family == "jugs":
        st, p = {}, 1.0
        for i, x in enumerate(w.names):
            pf, pe = second_p[2 * i], second_p[2 * i + 1]
            sc = {a: L(D[x].get(a, 0.0)) + L(pf if int(a) == w.cap[x] else 1 - pf) + L(pe if int(a) == 0 else 1 - pe) for a in D[x]}
            best = max(sc, key=sc.get)
            st[x], p = int(best), p * math.exp(sc[best] - _lse(list(sc.values())))
        return {"v": st}, p
    keys = list(range(w.n)) if w.family == "toggles" else list(w.devs)
    vals = w.states if w.family == "toggles" else w.cycle
    V = range(len(vals))
    unary = [[L(D[k].get(v, 0.0)) for v in vals] for k in keys]
    pair = lambda j, a, b: L(second_p[j] if a == b else 1 - second_p[j])
    alpha, delta, back = unary[0][:], unary[0][:], []
    for j in range(1, len(keys)):
        alpha = [unary[j][b] + _lse([alpha[a] + pair(j - 1, a, b) for a in V]) for b in V]
        cand = [[delta[a] + pair(j - 1, a, b) for a in V] for b in V]
        arg = [max(V, key=lambda a: cand[b][a]) for b in V]
        delta, back = [unary[j][b] + cand[b][arg[b]] for b in V], back + [arg]
    last = max(V, key=lambda b: delta[b])
    seq = [last]
    for arg in reversed(back):
        seq.append(arg[seq[-1]])
    seq.reverse()
    p = math.exp(delta[last] - _lse(alpha))
    return ({"st": seq}, p) if w.family == "toggles" else ({"st": dict(zip(keys, seq))}, p)


def read(w, text, keys_qs, dual=False, views=False, fuse=False):
    """The state read from the answers, its probability (the product, over variables, of the chosen value's), whether a
    second view disagrees with it (views), and each variable's chosen probability (not for orderings)."""
    qs = {f"v{j}": q for j, (_, q) in enumerate(keys_qs)}
    if dual:
        qs.update({f"w{j}": q for j, (_, q) in enumerate(WHERE(w))})
    second = SECOND(w) if (views or (fuse and w.family != "cards")) else []
    qs.update({f"s{j}": q for j, (q, _) in enumerate(second)})
    r = post({"state": text, "questions": qs})["answers"]
    if fuse and w.family != "cards":  # (cards fuse through the dual path: the inverse questions inside the assignment)
        D = {k: r[f"v{j}"]["probabilities"] for j, (k, _) in enumerate(keys_qs)}
        S, p = fuse_state(w, D, [r[f"s{j}"]["probability"] for j in range(len(second))])
        return S, p, False, {}
    S, p, pv = _read_state(w, r, keys_qs, dual)
    incons = False
    for j, (q, implied) in enumerate(second):
        a, want = r[f"s{j}"], implied(S)
        if CONFIDENT_VIEWS:  # only a confident disagreement: the second view gives the implied answer less than 10%
            if q["type"] in ("noul", "boolean"):
                p_implied = a["probability"] if want else 1 - a["probability"]
            else:
                p_implied = a["probabilities"].get(want, 0.0)
            incons = incons or p_implied < 0.10
        else:
            got = bool(a["value"]) if q["type"] in ("noul", "boolean") else a["choice"]
            incons = incons or got != want
    return S, p, incons, pv


def _read_state(w, r, keys_qs, dual):
    D = {k: r[f"v{j}"]["probabilities"] for j, (k, _) in enumerate(keys_qs)}
    if w.family == "cards":
        L = [[math.log(D[k].get(c, 0.0) + 1e-9) for c in w.labels] for k in range(w.n)]
        if dual:  # position k holds card c: both views, each normalized per position
            Wd = {x: r[f"w{j}"]["probabilities"] for j, x in enumerate(w.labels)}
            L = [[L[k][ci] + math.log(Wd[c].get(str(k + 1), 0.0) + 1e-9) for ci, c in enumerate(w.labels)] for k in range(w.n)]
            L = [[v - math.log(sum(math.exp(u) for u in row)) for v in row] for row in L]
        rows, cols = linear_sum_assignment([[-v for v in row] for row in L])
        return {"xs": [w.labels[c] for c in cols]}, math.exp(sum(L[k][c] for k, c in zip(rows, cols))), {}
    top = {k: max(D[k], key=D[k].get) for k in D}
    pv = {k: D[k][top[k]] for k in D}
    p = math.prod(pv.values())
    if w.family == "jugs":
        return {"v": {x: int(top[x]) for x in w.names}}, p, pv
    if w.family == "toggles":
        return {"st": [w.states.index(top[j]) for j in range(w.n)]}, p, pv
    return {"st": {d: w.cycle.index(top[d]) for d in w.devs}}, p, pv


def set_vars(w, S, T, K):
    """S with the variables K taken from the real state T (a partial look)."""
    if w.family == "jugs":
        return {"v": {x: (T["v"][x] if x in K else S["v"][x]) for x in w.names}}
    if w.family == "toggles":
        return {"st": [T["st"][j] if j in K else S["st"][j] for j in range(w.n)]}
    return {"st": {d: (T["st"][d] if d in K else S["st"][d]) for d in w.devs}}


def world(fam, rng):  # as long_chain2.py
    while True:
        w = {"jugs": Jugs, "toggles": Toggles, "machines": Machines, "cards": Cards}[fam](rng)
        if (fam == "jugs" and len(w.names) == 3) or (fam == "toggles" and w.n >= 5) or (fam == "machines" and len(w.devs) >= 4) \
           or (fam == "cards" and w.n >= 5):
            w.name = fam
            return w


def run(job):
    fam, length, i, mode = job
    rng = random.Random({"jugs": 1, "toggles": 2, "machines": 3, "cards": 4}[fam] * 100000 + length * 100 + i)  # = long_chain2
    w = world(fam, rng)
    s0 = w.sample_state(rng)
    acts, truth, s = [], [s0], s0
    for _ in range(length):
        a = w.sample_action(rng, s)
        s, _ = w.step(s, a)
        acts.append(a)
        truth.append(s)
    keys_qs = VARS[fam](w)
    key = keys_qs[rng.randrange(len(keys_qs))][0]
    dual = mode.startswith("dual")
    final_look = mode.endswith("E")  # also look after the last action when the rule says so
    rule = re.match(r"(?:dual_)?(conf|until|check|adapt|views|viewsc|fuse|part|parta)([\d.]+)E?$", mode)
    tau = float(rule.group(2)) if rule else None
    kind = rule.group(1) if rule else None
    until = kind in ("until", "check", "adapt", "views", "viewsc", "fuse", "part", "parta")
    check = kind in ("check", "adapt", "views", "viewsc", "fuse", "part", "parta")
    adapt, views, fuse, part, audit = kind == "adapt", kind in ("views", "viewsc"), kind == "fuse", kind in ("part", "parta"), kind == "parta"
    if part and fam == "cards":
        raise SystemExit("part modes: not for cards (a partial look would break the ordering)")
    dual = dual or (fuse and fam == "cards")
    if kind == "viewsc" and not CONFIDENT_VIEWS:
        raise SystemExit("viewsc modes need CONFIDENT_VIEWS=1")
    step_tau = float(mode.split("step")[1]) if mode.startswith("step") else None
    t0 = time.time()
    S, chain, looks, wrong_steps, trace = s0, 1.0, 0, 0, []
    recheck, gap, since, surprises, incons_steps, final_looks = False, 8, 0, 0, 0, 0
    vc, observed_vars, full_looks = {k: 1.0 for k, _ in keys_qs}, 0, 0  # part<t>: each variable's confidence since it was last seen
    seen = {k: 0 for k, _ in keys_qs}  # parta<t>: when each variable was last seen (a partial look also audits the oldest)
    mine = open(os.environ["MINE_OUT"], "a") if os.environ.get("MINE_OUT") else None
    for t, a in enumerate(acts, 1):
        text = f"{w.rules}\n\nCurrent state:\n{w.render(S)}\n\nActions, in order:\n1. {w.render_action(a)}\n\n{w.floor_note()}"
        prev = S
        S, p, incons, pv = read(w, text, keys_qs, dual, views, fuse)
        incons_steps += incons
        if os.environ.get("TRACE") or mine:
            want, ev = w.step(prev, a)
            trace.append([round(p, 4), all(value(w, S, k) == value(w, want, k) for k, _ in keys_qs)])
            if mine:  # the model's own chain state: every variable it got wrong or answered below 0.99, with the truth from that state
                log = w.event_log([a], [ev]) if hasattr(w, "event_log") else ""
                ceiling = f"{w.rules}\n\nState after the actions:\n{w.render(want, [ev])}\n\n{w.ceiling_note()}" + (f"\n{log}" if log else "")
                for k, q in keys_qs:
                    ok = value(w, S, k) == value(w, want, k)
                    if not ok or pv.get(k, 1.0) < 0.99:
                        with MINE_LOCK:
                            mine.write(json.dumps({"world": w.family, "qtype": "chain", "steps": 1, "question": q, "gold": value(w, want, k),
                                               "floor": text, "ceiling": ceiling, "kind": "floorC", "wrong": not ok,
                                               "p": round(pv.get(k, 1.0), 4), "chain": [fam, length, i, t]}) + "\n")
                            mine.flush()
        chain *= p
        since += 1
        if part:  # the chain confidence is the product of the variables' own
            for k in vc:
                vc[k] *= pv.get(k, 1.0)
            chain = math.prod(vc.values())
        if (t < length or final_look) and ((mode == "obs50" and t % 50 == 0) or (tau is not None and chain < tau)
                                           or (step_tau is not None and p < step_tau) or recheck or (check and since >= gap)
                                           or (views and incons)) and part and not (recheck or since >= gap):
            # a partial look: the least sure variables, until the rest is back above the middle of tau and 1 (checks
            # and the looks after a surprise stay whole: a confident error is never among the least sure)
            K = []
            for k in sorted(vc, key=vc.get):
                if math.prod(v for j, v in vc.items() if j not in K) >= (1 + tau) / 2:
                    break
                K.append(k)
            if audit:
                rest = [k for k in seen if k not in K]
                if rest:
                    K.append(min(rest, key=seen.get))
            for k in K:
                seen[k] = t
            surprised = any(value(w, S, k) != value(w, truth[t], k) for k in K)
            surprises += surprised
            recheck = surprised
            gap = 8 if surprised else gap
            S = set_vars(w, S, truth[t], K)
            for k in K:
                vc[k] = 1.0
            chain = math.prod(vc.values())
            looks, observed_vars, final_looks = looks + 1, observed_vars + len(K), final_looks + (t == length)
            if not all(value(w, S, k) == value(w, truth[t], k) for k, _ in keys_qs):
                wrong_steps += 1
        elif (t < length or final_look) and ((mode == "obs50" and t % 50 == 0) or (tau is not None and chain < tau)
                                           or (step_tau is not None and p < step_tau) or recheck or (check and since >= gap)
                                           or (views and incons)):
            surprised = not all(value(w, S, k) == value(w, truth[t], k) for k, _ in keys_qs)
            surprises += surprised
            recheck = until and surprised
            gap = (8 if surprised else min(2 * gap, 64)) if check else gap
            if adapt:  # the threshold learns from the looks: up after a surprise, down while the forecasts hold
                tau = min(0.995, 1 - (1 - tau) / 2) if surprised else max(0.5, 1 - (1 - tau) * 1.25)
            final_looks += t == length
            S, chain, looks, since = truth[t], 1.0, looks + 1, 0  # look at the real state and continue from it
            vc, observed_vars, full_looks = {k: 1.0 for k in vc}, observed_vars + len(keys_qs), full_looks + 1
            seen = {k: t for k in seen}
        elif not all(value(w, S, k) == value(w, truth[t], k) for k, _ in keys_qs):
            wrong_steps += 1
    return {"fam": fam, "len": length, "i": i, "mode": mode, "final_ok": value(w, S, key) == value(w, truth[-1], key),
            "state_ok": all(value(w, S, k) == value(w, truth[-1], k) for k, _ in keys_qs), "looks": looks,
            "wrong_steps": wrong_steps, "surprises": surprises, "incons_steps": incons_steps, "final_looks": final_looks,
            "n_vars": len(keys_qs), "observed_vars": observed_vars, "full_looks": full_looks,
            "seconds": time.time() - t0, **({"trace": trace} if trace and os.environ.get("TRACE") else {})}


NEW = ("until0.5", "check0.5", "until0.9", "check0.9", "check0.9E", "adapt0.9E", "views0.9E", "views0.5E", "viewsc0.9E", "viewsc0.5E",
       "fuse0.9E", "fuse0.5E", "part0.9", "parta0.9")
CONFIDENT_VIEWS = os.environ.get("CONFIDENT_VIEWS") == "1"
MODES = {"cards": ("text", "obs50", "conf0.5", "conf0.9", "step0.9", "dual", "dual_conf0.9") + tuple(m for m in NEW if not m.startswith("part")),
         "toggles": ("text", "conf0.5", "conf0.9", "step0.9") + NEW, "machines": ("text", "conf0.5", "conf0.9", "step0.9") + NEW,
         "jugs": ("text", "conf0.5", "conf0.9", "step0.9") + NEW}
ONLY = {tuple(x.split(":")) for x in os.environ.get("ONLY", "").split(",") if x}
OLD_N = int(os.environ.get("OLD_N", "0"))  # run only the chains beyond an earlier run's N (cards from OLD_N, the others from OLD_N // 2)
jobs = [(fam, L, i, m) for fam in ("cards", "toggles", "machines", "jugs") for L in (100, 200)
        for i in range(OLD_N if fam == "cards" else OLD_N // 2, N if fam == "cards" else N // 2) for m in MODES[fam] if not ONLY or (fam, m) in ONLY]
t0 = time.time()
res = []
with cf.ThreadPoolExecutor(PAR) as ex:
    for fut in cf.as_completed([ex.submit(run, j) for j in jobs]):
        r = fut.result()
        res.append(r)
        with open(OUT, "a") as f:
            f.write(json.dumps(r) + "\n")
print(f"{len(res)} chains in {(time.time() - t0) / 60:.1f} min ({CQ_URL}, {N} chains per world, length and mode)")
print("world     len        mode | final ans  whole state  looks/chain  wrong steps/chain")
for fam in MODES:
    for L in (100, 200):
        for m in MODES[fam]:
            g = [r for r in res if r["fam"] == fam and r["len"] == L and r["mode"] == m]
            if g:
                print(f"{fam:9s} {L:4d} {m:>12s} | {100 * sum(r['final_ok'] for r in g) / len(g):8.0f}% {100 * sum(r['state_ok'] for r in g) / len(g):11.0f}% "
                      f"{sum(r['looks'] for r in g) / len(g):12.1f} {sum(r['wrong_steps'] for r in g) / len(g):18.1f}")
