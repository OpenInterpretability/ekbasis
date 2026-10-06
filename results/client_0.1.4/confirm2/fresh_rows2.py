"""WS-U confirm-2: one row per fresh question (WS-P's build_dataset.py functions, through confirm/fresh_rows.py), then
the overlap check against EVERY analysed item: a row is excluded if the sha256 of its prompt or of its evidence equals
that of any dev row (confirm/dev_hashes.json) or any confirm-1 row (every row confirm-1 built, kept or not, any suite).
Within confirm-2, a repeated prompt keeps its first copy (rows ordered by row id).
python3 fresh_rows2.py  ->  fresh_rows.jsonl, fresh_rows_summary.json (in confirm2/)"""
import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
U = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(U, "confirm"))
import fresh_rows as FR  # noqa: E402  (confirm-1's frozen builder; only its folder constants are redirected)

FR.FRESH_CAP = os.path.join(HERE, "cap")


def main():
    dev_p, dev_e, _ = FR.dev_hashes()  # cached in confirm/dev_hashes.json
    c1_p, c1_e = set(), set()
    for l in open(os.path.join(U, "confirm", "fresh_rows.jsonl")):
        r = json.loads(l)
        c1_p.add(r["ph"])
        c1_e.add(r["eh"])
    cleaned = FR.clean_results()
    FR.B.CAP = FR.FRESH_CAP
    rows = []
    for suite in FR.PRIMARY:
        need = [f for (s, f) in FR.NEED if s == suite]
        if all(os.path.exists(os.path.join(FR.FRESH_CAP, suite, f)) for f in need):
            rows += FR.B.SUITES[suite]()
    for r in rows:
        r["rid"] = f"{r['suite']}|{r['req']}|{r['key']}"
        r["ph"], r["eh"] = FR.h(r["prompt"]), FR.h(FR.evidence_of(r["prompt"]))
    rows.sort(key=lambda r: r["rid"])
    seen, summary = set(), collections.defaultdict(collections.Counter)
    for r in rows:
        if r["ph"] in dev_p or r["eh"] in dev_e:
            r["exclude"] = "dev_overlap"
        elif r["ph"] in c1_p or r["eh"] in c1_e:
            r["exclude"] = "confirm1_overlap"
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
    out = {"runner_rows": cleaned, "per_suite": {k: dict(v) for k, v in summary.items()},
           "excluded_against": {"dev_prompts": len(dev_p), "dev_evidences": len(dev_e),
                                "confirm1_prompts": len(c1_p), "confirm1_evidences": len(c1_e)}}
    json.dump(out, open(os.path.join(HERE, "fresh_rows_summary.json"), "w"), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
