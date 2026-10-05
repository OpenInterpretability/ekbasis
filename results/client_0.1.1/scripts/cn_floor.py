"""No-regression check on the release's git sets (SPEC.md, criterion 4): git3_test_known + git3_test_held (3,105 questions,
the requests of release_eval.py) and guard_known + guard_held (the larger guard set, the requests of guard_big_served.py).
Their prompts are pre-rendered in the training layout, so the client's facts cannot reach them; the candidate's notes are
applied to them exactly as the client would (commands parsed from the prompt; the repository facts the notes use are
read from the prompt: commit-like targets, file arguments). Every prompt whose transformation leaves it unchanged is
asked once (its answer is both C0's and the candidate's); a changed prompt is asked in both forms.
python3 cn_floor.py <out dir>   (PYTHONPATH: ./pkg for ekbasis_next; EKBASIS_URL)"""
import concurrent.futures as cf
import json
import os
import random
import re
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "pkg"))
from ekbasis_next import prompts as P  # noqa: E402

URL = os.environ.get("EKBASIS_URL", "http://127.0.0.1:8542")
FAC = os.environ.get("EKBASIS_FAC", "fac")  # git3_test_{known,held}.jsonl, guard_{known,held}.jsonl (fields floor, question, gold, qtype)
OUT = sys.argv[1]
os.makedirs(OUT, exist_ok=True)
norm = lambda g: {True: "yes", False: "no"}[g] if isinstance(g, bool) else str(g)  # noqa: E731
COMMITISH = re.compile(r"^(HEAD([~^]\d*)*|[0-9a-f]{7,40}|origin/\S+)$")


def split_prompt(floor):
    head, rest = floor.split("\n\nState before:\n", 1)
    state, rest = rest.split("\n\nCommands, in order:\n", 1)
    cmds_txt, note = rest.split("\n\n", 1)
    cmds = [re.sub(r"^\d+\. ", "", l) for l in cmds_txt.splitlines()]
    assert head == P.GIT_RULES and note == P.GIT_NOTE, "not the training layout"
    assert P.git_state(state, cmds) == floor, "the layout does not round-trip"
    return state, cmds


def info_from(state, cmds):
    branches = set()
    for l in state.splitlines():
        if l.startswith("Branches ("):
            branches = set(re.findall(r"(?:^|, )([^\s,()]+) \(", l.split(": ", 1)[1]))
    targets, paths = set(), set()
    for c in cmds:
        sub, args = P.parse_git(c)
        for a in args:
            if a.startswith("-"):
                continue
            if COMMITISH.match(a) and a not in branches:
                targets.add(a)
            elif f"{a} (" in state or re.search(r"\.\w+$", a):
                paths.add(a)
    return {"nonbranch_targets": sorted(targets), "path_args": sorted(paths), "pull_config": {}, "ignored_overwrite": False}


def post(body):
    req = urllib.request.Request(f"{URL}/v1/systemone", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    for attempt in range(3):
        try:
            return json.load(urllib.request.urlopen(req, timeout=900))
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2)


def ask(prompt, question):
    a = post({"state": prompt, "questions": {"q": question}})["answers"]["q"]
    pred = ("yes" if a["value"] else "no") if question["type"] in ("noul", "boolean") else a["choice"]
    return {"pred": pred, "conf": a["confidence"], "p_yes": a.get("probability")}


def boot(xs, n=2000, seed=0):
    rng = random.Random(seed)
    m = sorted(sum(rng.choice(xs) for _ in xs) / len(xs) for _ in range(n))
    return round(100 * m[int(0.025 * n)], 2), round(100 * m[int(0.975 * n)], 2)


report = {}
DRY = os.environ.get("DRY") == "1"  # only count the prompts the candidate changes (no request)
for split in ("git3_test_known", "git3_test_held", "guard_known", "guard_held"):
    rows = [json.loads(l) for l in open(f"{FAC}/{split}.jsonl")]
    new, changed = [], 0
    for r in rows:
        state, cmds = split_prompt(r["floor"])
        notes = P.git_notes(cmds, info_from(state, cmds))
        p = P.git_state(state, cmds, notes=notes)
        new.append(p)
        changed += p != r["floor"]
    if DRY:
        ex = [split_prompt(rows[i]["floor"])[1] for i in range(len(rows)) if new[i] != rows[i]["floor"]]
        print(split, len(rows), "rows,", changed, "prompts changed; e.g.", ex[:6], flush=True)
        continue
    jobs = [("c0", i, r["floor"]) for i, r in enumerate(rows)] + [("cand", i, new[i]) for i, r in enumerate(rows) if new[i] != r["floor"]]
    t0 = time.time()
    with cf.ThreadPoolExecutor(24) as ex:
        res = list(ex.map(lambda j: ask(j[2], rows[j[1]]["question"]), jobs))
    pred = {"c0": {}, "cand": {}}
    for (k, i, _), a in zip(jobs, res):
        pred[k][i] = a
    for i in range(len(rows)):
        pred["cand"].setdefault(i, pred["c0"][i])
    with open(f"{OUT}/preds_{split}.jsonl", "w") as f:
        for i, r in enumerate(rows):
            f.write(json.dumps({"c0": pred["c0"][i], "cand": pred["cand"][i], "changed": new[i] != r["floor"],
                                "gold": norm(r["gold"]), "qtype": r["qtype"]}) + "\n")
    rep = {"rows": len(rows), "prompts_changed_by_the_candidate": changed, "seconds": round(time.time() - t0, 1)}
    for k in ("c0", "cand"):
        ok = [pred[k][i]["pred"] == norm(r["gold"]) for i, r in enumerate(rows)]
        if split.startswith("git3"):
            rep[k] = {"accuracy": round(100 * sum(ok) / len(ok), 3), "ci95": boot(ok)}
            for q in ("lost", "fails", "in_progress"):
                sel = [o for o, r in zip(ok, rows) if r["qtype"] == q]
                rep[k][q] = round(100 * sum(sel) / len(sel), 3) if sel else None
        else:
            pos = [pred[k][i] for i, r in enumerate(rows) if r["qtype"] == "lost" and r["gold"]]
            neg = [pred[k][i] for i, r in enumerate(rows) if r["qtype"] == "lost" and not r["gold"]]
            fl = [(pred[k][i], r) for i, r in enumerate(rows) if r["qtype"] == "fails"]
            rep[k] = {"work_losing": len(pos), "flagged_at_0.2": sum(p["p_yes"] >= 0.2 for p in pos), "safe": len(neg),
                      "false_alarms_at_0.2": sum(p["p_yes"] >= 0.2 for p in neg), "fails_n": len(fl),
                      "fails_right": sum(p["pred"] == norm(r["gold"]) for p, r in fl)}
    report[split] = rep
    print(split, json.dumps(rep), flush=True)
if DRY:
    sys.exit(0)
k3 = [json.loads(l) for s in ("git3_test_known", "git3_test_held") for l in open(f"{OUT}/preds_{s}.jsonl")]
for k in ("c0", "cand"):
    ok = [x[k]["pred"] == x["gold"] for x in k3]
    report[f"git3_all_{k}"] = {"n": len(ok), "accuracy": round(100 * sum(ok) / len(ok), 3), "ci95": boot(ok)}
json.dump(report, open(f"{OUT}/report.json", "w"), indent=1)
print(json.dumps({k: v for k, v in report.items() if k.startswith("git3_all")}), flush=True)
