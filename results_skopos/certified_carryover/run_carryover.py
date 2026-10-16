"""Certified-mode carry-over to Ekbasis-Skopos-27B (PREREG_CERTIFIED_CARRYOVER.md). Adapted from WS-MAC T2's run_t2.py
(mission/MAC/t2, the MLX check of docs/VERIFY.md); the calls are the same, only how they are dispatched changed:
confirm-3's fresh scenarios (T2's stratified subset, data/subset_requests.jsonl, all 1,400 scenarios, no time cap) asked
to the server at EKBASIS_URL with the installed ekbasis client. Per scenario: one direct request with all its questions;
the unit = one confident (>= 0.9) question chosen with random.Random("63|<suite>|<req>"); for the unit, the certified
mode's extra requests exactly as ekbasis.verify builds them: the two perturbed variants in one request (verify.perturbed)
and, except for git and shell, the self-check (verify.SELF_CHECK). Scenarios run in parallel (WORKERS); the analysis
orders the family-rate stream by hash, so the dispatch order does not enter any number. Resumable.
Scenarios listed in data/overlap_excluded.json (the D8-style audit of these items, run before any request) are skipped.
    EKBASIS_URL=http://127.0.0.1:8000 TAG=skopos-int4 python3 run_carryover.py   -> results/<TAG>_raw.jsonl
Environment: EKBASIS_URL (required), EKBASIS_API_KEY (optional), TAG (required), WORKERS (8), EXPECT_MODEL ("Skopos":
a substring the server's /health model name must contain), CLIENT_VERSION ("0.1.41")."""
import hashlib
import json
import os
import random
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

import ekbasis
from ekbasis import verify as V
from ekbasis.client import Ekbasis

HERE = os.path.dirname(os.path.abspath(__file__))
URL = os.environ.get("EKBASIS_URL") or sys.exit("EKBASIS_URL is required")
TAG = os.environ.get("TAG") or sys.exit("TAG is required (e.g. skopos-int4, skopos-bf16)")
WORKERS = int(os.environ.get("WORKERS", "8"))
EXPECT_MODEL = os.environ.get("EXPECT_MODEL", "Skopos")
CLIENT_VERSION = os.environ.get("CLIENT_VERSION", "0.1.41")
# the client code the certificate lives in, frozen (verify.py and verify_policy.json unchanged since client 0.1.5)
VERIFY_SHA = {"verify.py": "f85aec3e85538adc0b610ffd1dbf8b8e43015a09af70186da73b2b73850815f5",
              "verify_policy.json": "58e9ea935dfa8475eff4ba2ce0af2cdcf9233897e3eb38a40af06f92ed41b88b"}
REQ = os.path.join(HERE, "data", "subset_requests.jsonl")
EXCL = os.path.join(HERE, "data", "overlap_excluded.json")
OUT = os.path.join(HERE, "results", f"{TAG}_raw.jsonl")
NO_SELF = {"git_wild", "shell_wild"}
_local = threading.local()
_lock = threading.Lock()


def client():
    if not hasattr(_local, "c"):
        _local.c = Ekbasis(url=URL, timeout=900)
    return _local.c


def health():
    for i in range(30):
        try:
            req = urllib.request.Request(URL + "/health")
            if os.environ.get("EKBASIS_API_KEY"):
                req.add_header("Authorization", "Bearer " + os.environ["EKBASIS_API_KEY"])
            j = json.load(urllib.request.urlopen(req, timeout=60))
            if j.get("ok"):
                return j
        except Exception:  # noqa: BLE001
            pass
        print(f"health failed (try {i + 1}); waiting 60 s", flush=True)
        time.sleep(60)
    raise SystemExit("the model server stayed down for 30 minutes")


def ask(state, qs):
    err = None
    for _ in range(3):
        try:
            t0 = time.time()
            a = client().ask(state, qs)
            return a, time.time() - t0
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {e}"
            print(f"request failed ({err[:160]}); checking health", flush=True)
            health()
    raise RuntimeError(err)


def probs_of(q, a):
    if q.get("type") in ("noul", "boolean"):
        return {"yes": float(a.p_yes), "no": 1.0 - float(a.p_yes)}
    return {str(k): float(v) for k, v in (a.probabilities or {}).items()}


def scenario(it):
    t0 = time.time()
    rec = {"i": it["i"], "part": it["part"], "suite": it["suite"], "req": it["req"], "rows": []}
    try:
        ans, dt = ask(it["state"], it["questions"])
        rec["direct_s"] = round(dt, 3)
        conf_rows = []
        for row in it["rows"]:
            q, a = it["questions"][row["qk"]], ans[row["qk"]]
            probs = probs_of(q, a)          # the raw probabilities: the client's verify reads these, not `calibrated`
            label = V.label_of(q, a)
            r = {"rid": row["rid"], "qk": row["qk"], "answer": label, "probs": probs, "conf": max(probs.values()),
                 "correct": label == str(row["truth"])}
            rec["rows"].append(r)
            if r["conf"] >= 0.9:
                conf_rows.append(r)
        if conf_rows:
            u = random.Random(f"63|{it['suite']}|{it['req']}").choice(sorted(conf_rows, key=lambda r: r["rid"]))
            q = it["questions"][u["qk"]]
            pa, dt2 = ask(it["state"], V.perturbed(q))
            p_re = float((pa["reorder"].probabilities or {}).get(u["answer"], 0.0))
            p_pa = V.prob_of(q, pa["para"], u["answer"])
            unit = {"rid": u["rid"], "p_reorder": p_re, "p_para": p_pa, "stability": 1.0 - min(p_re, p_pa),
                    "perturb_s": round(dt2, 3)}
            if it["suite"] not in NO_SELF:
                text = V.SELF_CHECK.format(question=q["instructions"], answer=V.answer_text(q, u["answer"]))
                sa, dt3 = ask(it["state"], {"q": V.choice(text, ["yes", "no"])})
                unit["self_check_no"] = float((sa["q"].probabilities or {}).get("no", 0.0))
                unit["self_check_s"] = round(dt3, 3)
            rec["unit"] = unit
    except Exception as e:  # noqa: BLE001
        rec["error"] = f"{type(e).__name__}: {str(e)[:300]}"
    rec["wall_s"] = round(time.time() - t0, 3)
    return rec


def main():
    if ekbasis.__version__ != CLIENT_VERSION:
        sys.exit(f"ekbasis {ekbasis.__version__} installed; the pre-registration pins {CLIENT_VERSION}")
    pkg = os.path.dirname(ekbasis.__file__)
    for f, want in VERIFY_SHA.items():
        got = hashlib.sha256(open(os.path.join(pkg, f), "rb").read()).hexdigest()
        if got != want:
            sys.exit(f"{f} of the installed client differs from the frozen one ({got[:12]} != {want[:12]})")
    h = health()
    if EXPECT_MODEL not in str(h.get("model", "")):
        sys.exit(f"the server reports model {h.get('model')!r}, not {EXPECT_MODEL!r}: wrong endpoint?")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    excluded = set(map(tuple, json.load(open(EXCL))["scenarios"])) if os.path.exists(EXCL) else None
    if excluded is None:
        sys.exit(f"{EXCL} is missing: the overlap audit of these items runs before any request (pre-registration step 1)")
    done = set()
    if os.path.exists(OUT):
        done = {(j["i"], j["part"]) for j in map(json.loads, open(OUT)) if "error" not in j}
    items = [json.loads(l) for l in open(REQ)]
    todo = [it for it in items if (it["i"], it["part"]) not in done and (it["suite"], it["req"]) not in excluded]
    print(f"{len(items)} requests, {len(done)} done, {len(todo)} to run ({len(excluded)} scenarios excluded by the audit); "
          f"server {h}; client {ekbasis.__version__}; {WORKERS} workers", flush=True)
    meta = {"tag": TAG, "url_host": URL.split("//")[-1].split("/")[0], "health": h, "client": ekbasis.__version__,
            "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    json.dump(meta, open(os.path.join(HERE, "results", f"{TAG}_meta.json"), "w"), indent=1)
    n = 0
    with ThreadPoolExecutor(WORKERS) as ex:
        for fut in as_completed([ex.submit(scenario, it) for it in todo]):
            rec = fut.result()
            with _lock, open(OUT, "a") as f:
                f.write(json.dumps(rec) + "\n")
            n += 1
            if n % 100 == 0:
                print(f"{n}/{len(todo)} scenarios", flush=True)
    print("CARRYOVER RUN DONE", flush=True)


if __name__ == "__main__":
    main()
