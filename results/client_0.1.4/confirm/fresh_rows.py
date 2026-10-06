"""WS-U confirmatory test: one row per fresh question, built with WS-P's own dataset code (build_dataset.py: the same
prompts as the server saw, the same family labels), then the overlap check:
  - a fresh row is EXCLUDED if its prompt's sha256 or its evidence's sha256 equals that of ANY dev row (every question
    the capability suites ever ran, uncapped, plus WS-P's dataset);
  - within the fresh rows, a repeated prompt keeps only its first copy (rows ordered by row id).
Runner rows with an error, a skip or missing fields are set aside and counted (dev had none).
python3 fresh_rows.py  ->  fresh_rows.jsonl, fresh_rows_summary.json   (dev_hashes.json is cached)"""
import collections
import hashlib
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEV_CAP = "/root/decis/capability"
FRESH_CAP = os.path.join(HERE, "cap")
os.environ["CAP"] = DEV_CAP
sys.path.insert(0, "/root/decis/mission/P")
sys.path.insert(0, HERE)
import build_dataset as B  # noqa: E402
import fresh_planning as FP  # noqa: E402

PRIMARY = ["rules_stress", "sql_wild", "shell_wild", "git_wild", "accumulation"]
NEED = {("rules_stress", "results.jsonl"): ("answer",), ("rules_stress", "results_addendum.jsonl"): ("answer",),
        ("sql_wild", "results.jsonl"): ("answers",), ("shell_wild", "results.jsonl"): ("answers",),
        ("git_wild", "results.jsonl"): ("model", "truth", "state"), ("accumulation", "results.jsonl"): ("id",)}


def h(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def evidence_of(prompt):
    user = prompt.split("<|im_start|>user\n", 1)[1].split("<|im_end|>", 1)[0]
    return json.loads(user)["evidence"]


def dev_hashes():
    path = os.path.join(HERE, "dev_hashes.json")
    if os.path.exists(path):
        d = json.load(open(path))
        return set(d["prompt"]), set(d["evidence"]), d["counts"]
    ph, eh, counts = set(), set(), {}
    B.CAP = DEV_CAP
    for name, fn in B.SUITES.items():
        rs = fn()
        counts[name] = len(rs)
        for r in rs:
            ph.add(h(r["prompt"]))
            eh.add(h(evidence_of(r["prompt"])))
    n = 0
    for l in open("/root/decis/mission/P/data/dataset.jsonl"):
        r = json.loads(l)
        ph.add(h(r["prompt"]))
        eh.add(h(evidence_of(r["prompt"])))
        n += 1
    counts["wsp_dataset"] = n
    json.dump({"prompt": sorted(ph), "evidence": sorted(eh), "counts": counts}, open(path, "w"))
    return ph, eh, counts


def clean_results():
    """Set aside runner rows that cannot be scored (error, skip, missing fields); returns counts per file."""
    out = {}
    for (suite, fn), need in NEED.items():
        path = os.path.join(FRESH_CAP, suite, fn)
        if not os.path.exists(path):
            continue
        src = path + ".raw" if os.path.exists(path + ".raw") else path  # a second run counts from the runner's own file
        rs = [json.loads(l) for l in open(src) if l.strip()]
        good = [r for r in rs if not r.get("error") and not r.get("skipped") and all(k in r for k in need)]
        if len(good) < len(rs):
            if src == path:
                shutil.copy(path, path + ".raw")
            with open(path, "w") as f:
                for r in good:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
        out[f"{suite}/{fn}"] = {"rows": len(rs), "set_aside": len(rs) - len(good)}
    return out


def planning_rows():
    path = os.path.join(FRESH_CAP, "planning", "probe.jsonl")
    if not os.path.exists(path):
        return []
    W = FP.worlds_by_id()
    out = []
    for r in map(json.loads, open(path)):
        w = W[r["world"]]
        text = B.P.world_state(w.rules, w.render(r["state"]), [r["action"]])
        for k, qtext, opts in w.vars():
            q = B.P.choice(qtext, opts)
            ans, truth = str(r["pred"][k]), str(r["truth"][k])
            out.append(B.row("planning_probe", f"{r['fam']}|{r['kind']}",
                             f"{r['world']}|{json.dumps(r['state'], sort_keys=True)}|{r['action']}", k, text, q, ans,
                             r["probs"][k], truth, ans == truth))
    return out


def main():
    dev_p, dev_e, dev_counts = dev_hashes()
    cleaned = clean_results()
    B.CAP = FRESH_CAP
    rows = []
    for suite in PRIMARY:
        need = [f for (s, f) in NEED if s == suite]
        if all(os.path.exists(os.path.join(FRESH_CAP, suite, f)) for f in need):
            rows += B.SUITES[suite]()
    rows += planning_rows()
    for r in rows:
        r["rid"] = f"{r['suite']}|{r['req']}|{r['key']}"
        r["ph"], r["eh"] = h(r["prompt"]), h(evidence_of(r["prompt"]))
    rows.sort(key=lambda r: r["rid"])
    seen, summary = set(), collections.defaultdict(collections.Counter)
    for r in rows:
        if r["ph"] in dev_p or r["eh"] in dev_e:
            r["exclude"] = "dev_overlap"
        elif r["ph"] in seen:
            r["exclude"] = "fresh_duplicate"
        else:
            r["exclude"] = None
            seen.add(r["ph"])
        s = summary[r["suite"]]
        s["built"] += 1
        s[r["exclude"] or "kept"] += 1
        if not r["exclude"]:
            s["kept_confident"] += (r["conf"] or 0) >= 0.9
            s["kept_confident_errors"] += (r["conf"] or 0) >= 0.9 and not r["correct"]
    with open(os.path.join(HERE, "fresh_rows.jsonl"), "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    out = {"dev_rows_hashed": dev_counts, "dev_prompt_hashes": len(dev_p), "dev_evidence_hashes": len(dev_e),
           "runner_rows": cleaned, "per_suite": {k: dict(v) for k, v in summary.items()}}
    json.dump(out, open(os.path.join(HERE, "fresh_rows_summary.json"), "w"), indent=1)
    print(json.dumps(out["per_suite"], indent=1))


if __name__ == "__main__":
    main()
