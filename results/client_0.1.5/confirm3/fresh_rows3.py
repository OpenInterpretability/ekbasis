"""WS-U confirm-3: one row per fresh question (WS-P's build_dataset.py through confirm/fresh_rows.py), then the overlap
check against EVERY analysed item: a row is excluded if the sha256 of its prompt or of its evidence equals that of any
dev row (confirm/dev_hashes.json), any confirm-1 row or any confirm-2 row (every row they built, kept or not).
Within confirm-3, a repeated prompt keeps its first copy (rows ordered by row id).
python3 fresh_rows3.py  ->  fresh_rows.jsonl, fresh_rows_summary.json (in confirm3/)"""
import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
U = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(U, "confirm"))
import fresh_rows as FR  # noqa: E402  (confirm-1's frozen builder; only its folder constant is redirected)

FR.FRESH_CAP = os.path.join(HERE, "cap")
EARLIER = [os.path.join(U, "confirm", "fresh_rows.jsonl"), os.path.join(U, "confirm2", "fresh_rows.jsonl")]


def main():
    dev_p, dev_e, _ = FR.dev_hashes()
    old_p, old_e = set(), set()
    for path in EARLIER:
        for l in open(path):
            r = json.loads(l)
            old_p.add(r["ph"])
            old_e.add(r["eh"])
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
        elif r["ph"] in old_p or r["eh"] in old_e:
            r["exclude"] = "earlier_confirm_overlap"
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
                                "confirm1_2_prompts": len(old_p), "confirm1_2_evidences": len(old_e)}}
    json.dump(out, open(os.path.join(HERE, "fresh_rows_summary.json"), "w"), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
