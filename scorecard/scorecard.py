#!/usr/bin/env python3
"""The API scorecard: what a user of an Ekbasis endpoint gets, measured the same way every time, so every change to the
model, the server, the gateway or the client can be compared with the last run.

    python3 scorecard/scorecard.py fetch                      # the fixed items (published sets, fixed seeds) -> scorecard/items/
    python3 scorecard/scorecard.py run [--url URL] [--engine ekbasis|subq] [--tag TAG] [--n N]
    python3 scorecard/scorecard.py report                     # every run in scorecard/history.jsonl, side by side

What it measures, per suite and in total:
- quality: accuracy, confident errors (wrong at >= 0.9) per 100, Brier score, ECE;
- time: end-to-end latency p50 / p90 / p99 as the client sees it, and the server's own split when it sends
  `server-timing` (auth, queue, model);
- cost: input tokens per check (the response's usage, or the X-Ekbasis-Metered-Tokens header) and US$ per 1,000 checks at
  the price given with --price (US$ per 1M input tokens);
- reliability: requests that failed after retries.
Chains (`simulate` with `observe`): exact final states, looks per 100 actions, seconds and tokens per action.

Suites (items never used in training; the release's evaluation sets): git3_known, git3_held, guard_held (the larger guard
set, held-out command types), worlds (families never trained), intent (agent steps from the published-attack replay),
chains (two small worlds, 15 actions each, simulated against an exact simulator).
Keys come from EKBASIS_API_KEY or ~/.config/ekbasis/study_api_key (Ekbasis) and ~/.config/subq/api_key (SubQ); never
printed or stored in the results."""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime
import json
import os
import random
import statistics as st
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ITEMS, HIST = os.path.join(HERE, "items"), os.path.join(HERE, "history.jsonl")
INTENT_URL = ("https://raw.githubusercontent.com/OpenInterpretability/ekbasis-cookbook/main/studies/llm-judge-intent/"
              "items.jsonl")
SUITES = {"git3_known": ("git3_test_known", 400), "git3_held": ("git3_test_held", 400), "guard_held": ("guard_held", 400),
          "worlds": ("ftest_family", 400)}


# ------------------------------------------------------------------------------------------------ items
def fetch():
    from huggingface_hub import hf_hub_download
    os.makedirs(ITEMS, exist_ok=True)
    for name, (src, n) in SUITES.items():
        rows = [json.loads(l) for l in open(hf_hub_download("caiovicentino1/ekbasis-data", f"raw/{src}.jsonl",
                                                             repo_type="dataset"))]
        rows = random.Random(f"scorecard|{name}").sample(rows, min(n, len(rows)))
        with open(os.path.join(ITEMS, name + ".jsonl"), "w") as f:
            for i, r in enumerate(rows):
                f.write(json.dumps({"i": i, "state": r["floor"], "question": r["question"], "gold": r["gold"]}) + "\n")
        print(name, len(rows))
    raw = urllib.request.urlopen(INTENT_URL, timeout=60).read().decode().splitlines()
    rows = random.Random("scorecard|intent").sample([json.loads(l) for l in raw], 300)
    with open(os.path.join(ITEMS, "intent.jsonl"), "w") as f:
        for i, r in enumerate(rows):
            f.write(json.dumps({"i": i, "state": r["state"], "question": r["question"], "gold": r["kind"] == "attack"}) + "\n")
    print("intent", len(rows))


# ------------------------------------------------------------------------------------------------ one request
class Endpoint:
    def __init__(self, url, engine, key, model=None):
        self.url, self.engine, self.key, self.model = url.rstrip("/"), engine, key, model

    def ask(self, state, questions):
        body = {"state": state, "questions": questions}
        if self.model:
            body["model"] = self.model
        req = urllib.request.Request(self.url + "/v1/systemone", json.dumps(body).encode(), method="POST", headers={
            "Content-Type": "application/json", "Authorization": f"Bearer {self.key}", "User-Agent": "ekbasis-scorecard/1.0"})
        last = None
        for attempt in range(5):
            t0 = time.time()
            try:
                with urllib.request.urlopen(req, timeout=180) as r:
                    d = json.loads(r.read())
                    timing = {}
                    for part in (r.headers.get("server-timing") or "").split(","):
                        bits = [b.strip() for b in part.split(";")]
                        dur = next((b[4:] for b in bits if b.startswith("dur=")), None)
                        if bits and bits[0] and dur:
                            timing[bits[0]] = float(dur)
                    tok = (d.get("usage") or {}).get("input_tokens") or r.headers.get("X-Ekbasis-Metered-Tokens")
                return d, {"ms": round(1000 * (time.time() - t0)), "timing": timing, "tokens": int(tok) if tok else None}
            except urllib.error.HTTPError as e:
                last = f"HTTP {e.code}"
                if e.code not in (429, 500, 502, 503, 504):
                    break
            except Exception as e:  # noqa: BLE001
                last = type(e).__name__
            time.sleep(3 * (attempt + 1))
        return None, {"error": last}


def readout(a, q):
    if q["type"] == "noul":
        p = float(a.get("probability", a.get("noul")))
        return p >= 0.5, {True: p, False: 1 - p}
    return str(a.get("choice")), {str(k): float(v) for k, v in (a.get("probabilities") or {}).items()}


# ------------------------------------------------------------------------------------------------ chains
def chain_worlds():
    def jugs_step(s, a):
        A, B = int(s["a"]), int(s["b"])
        if a == "fill A":
            A = 5
        elif a == "fill B":
            B = 3
        elif a == "empty A":
            A = 0
        elif a == "empty B":
            B = 0
        elif a == "pour A into B":
            m = min(A, 3 - B)
            A, B = A - m, B + m
        elif a == "pour B into A":
            m = min(B, 5 - A)
            A, B = A + m, B - m
        return {"a": str(A), "b": str(B)}

    def lift_step(s, a):
        f, d, n = int(s["floor"]), s["door"], int(s["riders"])
        if a.startswith("press ") and d == "closed":
            f = int(a.split()[1])
        elif a == "open door":
            d = "open"
        elif a == "close door":
            d = "closed"
        elif a == "one rider gets on" and d == "open" and n < 4:
            n += 1
        elif a == "one rider gets off" and d == "open" and n > 0:
            n -= 1
        return {"floor": str(f), "door": d, "riders": str(n)}

    return {
        "jugs": dict(
            rules="World: two jugs; A holds up to 5 liters and B up to 3. 'fill A' and 'fill B' fill a jug, 'empty A' and "
                  "'empty B' empty it, 'pour A into B' and 'pour B into A' pour until the source is empty or the target "
                  "is full.",
            vars={"a": ("How many liters are in A?", [str(i) for i in range(6)]),
                  "b": ("How many liters are in B?", [str(i) for i in range(4)])},
            render=lambda s: f"A holds {s['a']} liters; B holds {s['b']} liters.",
            start=lambda rng: {"a": str(rng.randint(0, 5)), "b": str(rng.randint(0, 3))},
            actions=["fill A", "fill B", "empty A", "empty B", "pour A into B", "pour B into A"], step=jugs_step),
        "elevator": dict(
            rules="World: an elevator in a building with floors 1 to 9; its door is open or closed; it carries 0 to 4 "
                  "riders. 'press k' sends it to floor k only if the door is closed. 'open door' and 'close door' do what "
                  "they say. 'one rider gets on' adds a rider only if the door is open and there are fewer than 4. 'one "
                  "rider gets off' removes one only if the door is open and there is at least one.",
            vars={"floor": ("On which floor is the elevator?", [str(i) for i in range(1, 10)]),
                  "door": ("Is the door open or closed?", ["open", "closed"]),
                  "riders": ("How many riders are in the elevator?", [str(i) for i in range(5)])},
            render=lambda s: f"The elevator is at floor {s['floor']}, its door is {s['door']}, it carries {s['riders']} riders.",
            start=lambda rng: {"floor": str(rng.randint(1, 9)), "door": rng.choice(["open", "closed"]),
                               "riders": str(rng.randint(0, 4))},
            actions=[f"press {k}" for k in range(1, 10)] + ["open door", "close door", "one rider gets on",
                                                            "one rider gets off"], step=lift_step)}


def run_chains(ep, n_per_world=8, length=15):
    sys.path.insert(0, os.path.dirname(HERE))
    from ekbasis import prompts as P
    from ekbasis.client import Ekbasis
    from ekbasis.simulate import simulate
    client = Ekbasis(url=ep.url, api_key=ep.key, timeout=180)
    out = []
    for name, w in chain_worlds().items():
        qs = {k: P.choice(q, opts) for k, (q, opts) in w["vars"].items()}
        for i in range(n_per_world):
            rng = random.Random(f"scorecard|chain|{name}|{i}")
            s0 = w["start"](rng)
            acts = [rng.choice(w["actions"]) for _ in range(length)]
            truth, s = [], s0
            for a in acts:
                s = w["step"](s, a)
                truth.append(s)
            t0 = time.time()
            try:
                sim = simulate(client, w["rules"], s0, acts, qs, w["render"], observe=lambda t: truth[t - 1])
                out.append({"world": name, "exact": sim.final == truth[-1], "looks": len(sim.looks),
                            "secs": time.time() - t0, "actions": length})
            except Exception as e:  # noqa: BLE001
                out.append({"world": name, "error": type(e).__name__, "actions": length})
    return out


# ------------------------------------------------------------------------------------------------ run and score
def score(rows, answers):
    n = ok = conf_err = 0
    brier = 0.0
    bins = [[0, 0.0, 0] for _ in range(10)]
    for r in rows:
        a = answers.get(r["i"])
        if not a or not a.get("answer"):
            continue
        n += 1
        gold = r["gold"] if r["question"]["type"] == "noul" else str(r["gold"])
        pred, probs = readout(a["answer"], r["question"])
        conf, right = (max(probs.values()) if probs else 0.0), pred == gold
        ok += right
        conf_err += (not right) and conf >= 0.9
        brier += (1 - probs.get(gold, 0.0)) ** 2 + sum(v ** 2 for k, v in probs.items() if k != gold)
        b = min(9, int(conf * 10))
        bins[b][0] += 1
        bins[b][1] += conf
        bins[b][2] += right
    if not n:
        return {"answered": 0}
    return {"answered": n, "accuracy": round(100 * ok / n, 2), "confident_errors_per_100": round(100 * conf_err / n, 2),
            "brier": round(brier / n, 4), "ece": round(sum(abs(c - r) for k, c, r in bins if k) / n, 4)}


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(p * len(xs)))] if xs else None


def run(a):
    key = os.environ.get("EKBASIS_API_KEY") or open(os.path.expanduser(
        "~/.config/subq/api_key" if a.engine == "subq" else "~/.config/ekbasis/study_api_key")).read().strip()
    url = a.url or ("https://api.subq.ai" if a.engine == "subq" else "https://openinterp.org/api/v1")
    ep = Endpoint(url, a.engine, key, model="subq-snap-preview" if a.engine == "subq" else None)
    health = {}
    if a.engine == "ekbasis":
        try:
            req = urllib.request.Request(ep.url + "/health", headers={"Authorization": f"Bearer {key}",
                                                                     "User-Agent": "ekbasis-scorecard/1.0"})
            health = json.loads(urllib.request.urlopen(req, timeout=30).read())
        except Exception as e:  # noqa: BLE001
            health = {"error": type(e).__name__}
    res = {"t": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z", "engine": a.engine, "url": url, "tag": a.tag,
           "health": health, "price_per_1m_input": a.price, "suites": {}}
    allm, alltok, allfail, timing = [], [], 0, {}
    for fn in sorted(os.listdir(ITEMS)):
        suite = fn[:-6]
        rows = [json.loads(l) for l in open(os.path.join(ITEMS, fn))][: a.n or None]

        def one(r):
            d, meta = ep.ask(r["state"], {"q": r["question"]})
            return r["i"], ({"answer": d["answers"]["q"], **meta} if d else meta)
        with cf.ThreadPoolExecutor(a.conc) as ex:
            answers = dict(ex.map(one, rows))
        ms = [v["ms"] for v in answers.values() if v.get("ms")]
        tok = [v["tokens"] for v in answers.values() if v.get("tokens")]
        fails = sum(1 for v in answers.values() if v.get("error"))
        for v in answers.values():
            for k, x in (v.get("timing") or {}).items():
                timing.setdefault(k, []).append(x)
        s = score(rows, answers)
        s.update({"n": len(rows), "failed": fails, "p50_ms": pct(ms, .5), "p90_ms": pct(ms, .9),
                  "tokens_per_check": round(st.mean(tok)) if tok else None})
        res["suites"][suite] = s
        allm += ms
        alltok += tok
        allfail += fails
        print(suite, json.dumps(s), flush=True)
    if not a.no_chains and a.engine == "ekbasis":
        ch = run_chains(ep)
        good = [c for c in ch if "error" not in c]
        acts = sum(c["actions"] for c in good)
        res["chains"] = {"chains": len(ch), "failed": len(ch) - len(good), "exact": sum(c["exact"] for c in good),
                         "looks_per_100_actions": round(100 * sum(c["looks"] for c in good) / acts, 1) if acts else None,
                         "seconds_per_action": round(sum(c["secs"] for c in good) / acts, 3) if acts else None}
        print("chains", json.dumps(res["chains"]), flush=True)
    res["total"] = {"checks": len(allm) + allfail, "failed": allfail, "p50_ms": pct(allm, .5), "p90_ms": pct(allm, .9),
                    "p99_ms": pct(allm, .99), "tokens_per_check": round(st.mean(alltok)) if alltok else None,
                    "usd_per_1000_checks": round(st.mean(alltok) * a.price / 1000, 4) if alltok and a.price else None,
                    "server_timing_p50_ms": {k: pct(v, .5) for k, v in timing.items()}}
    print("total", json.dumps(res["total"]), flush=True)
    with open(HIST, "a") as f:
        f.write(json.dumps(res) + "\n")


def report():
    runs = [json.loads(l) for l in open(HIST)]
    suites = sorted({s for r in runs for s in r["suites"]})
    head = ["metric"] + [f"{r['engine']} {r['tag'] or ''} {r['t'][:10]}".strip() for r in runs]
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for s in suites:
        for m in ("accuracy", "confident_errors_per_100", "brier"):
            lines.append("| " + " | ".join([f"{s} {m}"] + [str(r["suites"].get(s, {}).get(m, "")) for r in runs]) + " |")
    for m in ("p50_ms", "p90_ms", "p99_ms", "tokens_per_check", "usd_per_1000_checks", "failed"):
        lines.append("| " + " | ".join([f"total {m}"] + [str(r["total"].get(m, "")) for r in runs]) + " |")
    lines.append("| " + " | ".join(["server timing p50 (ms)"] + [json.dumps(r["total"].get("server_timing_p50_ms"))
                                                                   for r in runs]) + " |")
    lines.append("| " + " | ".join(["chains exact / looks per 100 / s per action"] + [
        (f"{r['chains']['exact']}/{r['chains']['chains']} · {r['chains']['looks_per_100_actions']} · "
         f"{r['chains']['seconds_per_action']}") if r.get("chains") else "" for r in runs]) + " |")
    print("\n".join(lines))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["fetch", "run", "report"])
    ap.add_argument("--url")
    ap.add_argument("--engine", default="ekbasis", choices=["ekbasis", "subq"])
    ap.add_argument("--tag", default="")
    ap.add_argument("--n", type=int, default=0, help="items per suite (0: all)")
    ap.add_argument("--conc", type=int, default=3)
    ap.add_argument("--price", type=float, default=0.30, help="US$ per 1M input tokens")
    ap.add_argument("--no-chains", action="store_true")
    a = ap.parse_args()
    {"fetch": fetch, "run": lambda: run(a), "report": report}[a.cmd]()
