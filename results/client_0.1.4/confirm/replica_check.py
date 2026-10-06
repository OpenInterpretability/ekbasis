"""Replica check before the confirmatory run (dev items only, no fresh item): 400 WS-P dataset rows of the six suites,
asked on :8544 exactly as the dataset prompt was built; agreement of the answer and |conf - dev conf|; throughput."""
import concurrent.futures as cf
import json
import random
import sys
import time

sys.path.insert(0, "/root/decis/mission/P")
sys.argv = [sys.argv[0]]
import infer_baselines as IB  # noqa: E402  (rebuild(): the dataset prompt -> (state, question), byte-checked)
from ekbasis.client import Ekbasis  # noqa: E402

SUITES = {"rules_stress", "sql_wild", "shell_wild", "accumulation", "git_wild", "planning_probe"}
rows = [json.loads(l) for l in open("/root/decis/mission/P/data/dataset.jsonl")]
rows = [r for r in rows if r["suite"] in SUITES]
random.Random(5).shuffle(rows)
client = Ekbasis(url="http://127.0.0.1:8544", timeout=900)
print(client.health(), flush=True)
todo = []
for r in rows:
    rb = IB.rebuild(r)
    if rb:
        todo.append((r, rb))
    if len(todo) == 400:
        break


def one(x):
    r, (state, q) = x
    a = client.ask(state, {"q": q})["q"]
    probs = a.probabilities if r["qtype"] not in ("noul", "boolean") else {"yes": a.p_yes, "no": 1 - a.p_yes}
    ans = max(probs, key=probs.get)
    return r["answer"] == ans, abs(max(probs.values()) - r["conf"])


t0 = time.time()
with cf.ThreadPoolExecutor(16) as ex:
    res = list(ex.map(one, todo))
dt = time.time() - t0
d = sorted(x[1] for x in res)
print(f"{len(res)} requests in {dt:.0f} s = {len(res) / dt:.2f}/s; same answer {sum(x[0] for x in res)}/{len(res)}; "
      f"|dconf| median {d[len(d) // 2]:.5f} p95 {d[int(0.95 * len(d))]:.5f} max {d[-1]:.5f}")
