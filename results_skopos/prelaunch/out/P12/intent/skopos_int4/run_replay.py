"""Judges every call of every replay run (runs.jsonl) with intent_check 0.1.19 (shield=True), in two variants: base
(the default) and delegation=True. Identical states are asked once. Concurrency 3 (one run per worker), resumable.
On an HTTP error it waits and retries. Never prints the key.

usage: run_replay.py runs.jsonl out_dir
"""
import hashlib
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ekbasis.client import CannotJudge, Ekbasis
from ekbasis.intent import intent_check

WORKERS = 3
LOCK = threading.Lock()


class CachingClient(Ekbasis):
    cache: dict = {}
    calls_path: Path = None

    def ask(self, state, questions, **kw):
        key = hashlib.sha256((state + json.dumps(questions, sort_keys=True)).encode()).hexdigest()
        with LOCK:
            if key in self.cache:
                p = self.cache[key]
                return {"third_party": type("A", (), {"p_yes": p})}
        for attempt in range(40):
            try:
                t0 = time.time()
                ans = super().ask(state, questions)
                break
            except CannotJudge as e:
                wait = min(30 * (attempt + 1), 300)
                print(f"  retry {attempt + 1} in {wait}s: {str(e)[:80]}", flush=True)
                time.sleep(wait)
        else:
            raise SystemExit("Ekbasis did not answer after 40 attempts")
        p = ans["third_party"].p_yes
        with LOCK:
            self.cache[key] = p
            with self.calls_path.open("a") as f:
                f.write(json.dumps({"key": key, "p": p, "latency_s": round(time.time() - t0, 3),
                                    "usage": self.last_usage, "t": time.time()}) + "\n")
        return {"third_party": type("A", (), {"p_yes": p})}


def judge_run(run, ans_path):
    client = CachingClient(surface="intent-check")
    lines = []
    for j, c in enumerate(run["calls"]):
        for dele in (False, True):
            v = intent_check(run["request"], c["events"], c["action"], client=client, delegation=dele)
            lines.append({"id": run["id"], "j": j, "delegation": dele, "p": v.p, "verdict": v.verdict,
                          "delegated": list(v.delegated)})
    with LOCK:
        with ans_path.open("a") as f:
            for l in lines:
                f.write(json.dumps(l) + "\n")


def main():
    runs = [json.loads(l) for l in open(sys.argv[1])]
    out = Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    CachingClient.calls_path = out / "calls.jsonl"
    if CachingClient.calls_path.exists():
        for l in CachingClient.calls_path.open():
            d = json.loads(l)
            CachingClient.cache[d["key"]] = d["p"]
    ans_path = out / "answers.jsonl"
    done = {json.loads(l)["id"] for l in ans_path.open()} if ans_path.exists() else set()
    todo = [r for r in runs if r["id"] not in done]
    t0 = time.time()
    with ThreadPoolExecutor(WORKERS) as ex:
        for n, _ in enumerate(ex.map(lambda r: judge_run(r, ans_path), todo)):
            if n % 50 == 0:
                print(f"{n + 1}/{len(todo)} runs, {len(CachingClient.cache)} states, {time.time() - t0:.0f}s", flush=True)
    print("done")


if __name__ == "__main__":
    main()
