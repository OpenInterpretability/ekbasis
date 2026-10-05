"""Shared by client_012's evaluation scripts. Layout (the same locally and on the rig): capability/client_012/{ekbasis,
eval,results} next to the suites in capability/<suite>; the candidate package is client_012/ekbasis/ekbasis."""
from __future__ import annotations

import hashlib
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                         # client_012
CAP = os.path.dirname(ROOT)                          # capability
PKG = os.path.join(ROOT, "ekbasis")                  # holds the candidate package ekbasis/
VENDOR = os.path.join(HERE, "vendor")
OUT = os.environ.get("OUT_DIR", os.path.join(ROOT, "results"))
URL = os.environ.get("EKBASIS_URL", "http://127.0.0.1:8545")
WORKERS = int(os.environ.get("WORKERS", "16"))
FROZEN = os.path.join(ROOT, "FROZEN.sha256")

sys.path.insert(0, PKG)
import ekbasis  # noqa: E402

assert ekbasis.__version__ == "0.1.2", f"expected the 0.1.2 candidate, got {ekbasis.__version__} from {ekbasis.__file__}"
os.makedirs(OUT, exist_ok=True)


def client(timeout: float = 300):
    from ekbasis.client import Ekbasis
    return Ekbasis(url=URL, timeout=timeout)


def wilson(k: int, n: int, z: float = 1.96) -> list:
    if not n:
        return [None, None]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(100 * (c - h), 1), round(100 * (c + h), 1)]


def pct(k: int, n: int):
    return round(100 * k / n, 1) if n else None


def rate(k: int, n: int) -> dict:
    return {"k": k, "n": n, "pct": pct(k, n), "ci95": wilson(k, n)}


def read_jsonl(path: str) -> list:
    return [json.loads(l) for l in open(path) if l.strip()]


def write_jsonl(path: str, rows) -> None:
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def code_files() -> list:
    base = os.path.join(PKG, "ekbasis")
    return sorted(os.path.join("ekbasis", "ekbasis", f) for f in os.listdir(base) if f.endswith(".py"))


def freeze_lines() -> list:
    return [f"{hashlib.sha256(open(os.path.join(ROOT, p), 'rb').read()).hexdigest()}  {p}" for p in code_files()]


def require_frozen() -> None:
    """The confirmation set is generated and run only on the frozen client."""
    if not os.path.exists(FROZEN):
        sys.exit("client_012 is not frozen yet (FROZEN.sha256 is missing): run `python3 eval/freeze.py` after the dev runs")
    want = [l for l in open(FROZEN).read().splitlines() if l and not l.startswith("#")]
    if want != freeze_lines():
        sys.exit("the client changed after the freeze: FROZEN.sha256 does not match (refreeze and regenerate with new seeds)")
