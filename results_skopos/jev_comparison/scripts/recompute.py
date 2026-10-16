"""Recomputes results.json from this package's per-item files with the unchanged analyze_full.py and checks that every
number matches the published results.json. Run from the package root: python3 -I scripts/recompute.py"""
import json, shutil, subprocess, sys, tempfile
from pathlib import Path

PKG = Path(__file__).resolve().parent.parent
L = lambda p: [json.loads(l) for l in open(p) if l.strip()]
with tempfile.TemporaryDirectory() as t:
    t = Path(t)
    shutil.copy(PKG / "items.jsonl", t / "pool_items.jsonl")
    shutil.copy(PKG / "sets.json", t / "sets_full.json")
    for v in ("A", "B"):
        with open(t / f"pool_preds_{v}.jsonl", "w") as out:  # the runner's row layout, which analyze_full.py reads
            for r in L(PKG / "preds" / f"jev_{v}.jsonl"):
                out.write(json.dumps({"idx": r["key"], "answer": r["answer"], "latency_ms": r["latency_ms"],
                                      "usage": {"inputTokens": r["input_tokens"]}, "seeded_from_first_run": r.get("from_first_run", False)}) + "\n")
    subprocess.run([sys.executable, "-I", str(PKG / "scripts" / "analyze_full.py"), str(t)], check=True, stdout=subprocess.DEVNULL)
    got = json.load(open(t / "results_full.json"))
pub = json.load(open(PKG / "results.json"))
pub.pop("meta", None)
print("recomputed results match results.json:", got == pub)
sys.exit(0 if got == pub else 1)
