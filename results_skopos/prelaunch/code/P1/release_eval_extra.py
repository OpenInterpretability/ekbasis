# PRELAUNCH PORT (P1) of _orig/release_eval_extra.py: every changed line is marked PORT; the full diff is CHANGES.diff in this folder.
"""Pre-registered release evaluation, the parts release_eval.py left out (server side, exact release weights through the
System One API): ftest_family (primary 3; one question per state, so one prompt per question; scored on the answers the
actions change, with the pre-action answers of fac/gold0_ftest_family.jsonl, and on all answers), and the same 240 git
questions the Claude and Qwen models answered (git_llm_large.pick, seed 11), for the comparison. Writes every
prediction. env: URL (http://127.0.0.1:8503), PAR (48), OUT (/dev/shm/conseq/release_eval)."""
import collections, concurrent.futures as cf, json, os, sys, time
from pathlib import Path

sys.argv = [sys.argv[0]]
LIB = os.environ.get("LIB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))  # PORT: the rig folder /root/decis/conseq -> lib/ (identical copies)
DATA = os.environ.get("DATA", "/root/prelaunch_data")  # PORT: the rig folder /dev/shm/conseq -> $DATA
sys.path.insert(0, LIB)  # PORT
import git_llm_large as G
G.D = Path(DATA)  # PORT: pick() reads $DATA/fac/<split>.jsonl (it read /dev/shm/conseq/fac)

URL, PAR = os.environ.get("URL", "http://127.0.0.1:8503"), int(os.environ.get("PAR", "48"))
OUT = Path(os.environ.get("OUT", "/dev/shm/conseq/release_eval"))
src = open(os.path.join(LIB, "release_eval.py")).read()  # PORT
ns = {"__name__": "helpers"}
exec(compile(src[:src.index("report = {}")], "release_eval.py", "exec"), ns)  # post, answer, boot (no evaluation run)
post, answer, boot, norm = ns["post"], ns["answer"], ns["boot"], G.norm


def ask(r):
    a = post({"state": r["floor"], "questions": {"q": r["question"]}})["answers"]["q"]
    return {"pred": answer(a, r["question"]), "conf": a["confidence"]}


report = {}
rows = [json.loads(l) for l in open(f"{DATA}/fac/ftest_family.jsonl")]
t0 = time.time()
with cf.ThreadPoolExecutor(PAR) as ex:
    preds = list(ex.map(ask, rows))
ok = [p["pred"] == norm(r["gold"]) for r, p in zip(rows, preds)]
with open(OUT / "preds_ftest_family.jsonl", "w") as f:
    for r, p, o in zip(rows, preds, ok):
        f.write(json.dumps({**p, "gold": norm(r["gold"]), "world": r["world"], "qtype": r["qtype"], "steps": r["steps"], "ok": o}) + "\n")
per = collections.defaultdict(list)
for r, o in zip(rows, ok):
    per[r["world"]].append(o)
report["ftest_family (all answers)"] = {"n": len(ok), "acc": 100 * sum(ok) / len(ok), "ci95": boot(ok),
                                        "per_world": {w: f"{sum(v)}/{len(v)}" for w, v in sorted(per.items())},
                                        "seconds": time.time() - t0}
print("ftest_family", json.dumps(report["ftest_family (all answers)"]), flush=True)
g0 = [json.loads(l) for l in open(f"{DATA}/fac/gold0_ftest_family.jsonl")]
ch = [i for i, (r, g) in enumerate(zip(rows, g0)) if g["known"] and norm(g["gold0"]) != norm(r["gold"])]
un = [i for i, (r, g) in enumerate(zip(rows, g0)) if g["known"] and norm(g["gold0"]) == norm(r["gold"])]
per = collections.defaultdict(list)
for i in ch:
    per[rows[i]["world"]].append(ok[i])
report["ftest_family (answers the actions change)"] = {
    "n_known": sum(g["known"] for g in g0), "n_changed": len(ch), "acc_changed": 100 * sum(ok[i] for i in ch) / len(ch),
    "ci95_changed": boot([ok[i] for i in ch]), "acc_unchanged": 100 * sum(ok[i] for i in un) / max(1, len(un)),
    "per_world_changed": {w: f"{sum(v)}/{len(v)}" for w, v in sorted(per.items())}}
print("ftest_family changed", json.dumps(report["ftest_family (answers the actions change)"]), flush=True)

for split in ("git2_test_known", "git2_test_held"):
    rows, idx = G.pick(split)
    with cf.ThreadPoolExecutor(PAR) as ex:
        preds = list(ex.map(lambda i: ask(rows[i]), idx))
    ok = {i: p["pred"] == norm(rows[i]["gold"]).lower() for i, p in zip(idx, preds)}
    with open(OUT / f"preds_{split}_240.jsonl", "w") as f:
        for i, p in zip(idx, preds):
            f.write(json.dumps({"row": i, **p, "gold": norm(rows[i]["gold"]), "qtype": rows[i]["qtype"], "ok": ok[i]}) + "\n")
    groups = {"lost": [i for i in idx if rows[i]["qtype"] == "lost"], "fails": [i for i in idx if rows[i]["qtype"] == "fails"],
              "state (changed)": [i for i in idx if rows[i]["qtype"] not in ("lost", "fails")], "all": idx}
    report[f"{split} (the 240-question comparison)"] = {g: f"{sum(ok[i] for i in v)}/{len(v)}" for g, v in groups.items()}
    print(split, "240-question comparison:", json.dumps(report[f"{split} (the 240-question comparison)"]), flush=True)
json.dump(report, open(OUT / "report_server_side_extra.json", "w"), indent=1)
