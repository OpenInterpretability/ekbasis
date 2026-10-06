"""WS-PI, extra recomputations with the paper's own analysis scripts (unchanged):
  1. the release (w4a5) on the 15,008 questions, all items and without the items that overlap its lineage's training
     rows (the card and results/confident_errors/REPORT.md: 48.4% / 25.1%, 23.3 points, 95% interval 16.8 to 30.1);
  2. V42 and its parent without the 104 items that repeat a training row's prompt AND question (same_item_104.json;
     the published note counted 88), the primary statistic and the parent comparison.
usage: python pi_extra.py   (in /root/decis/mission/PI; writes extra.json)"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))


def jl(p):
    return [json.loads(l) for l in open(p)]


def run(script, args):
    p = subprocess.run([sys.executable, os.path.join(HERE, "analysis", script)] + args, capture_output=True, text=True)
    if p.returncode:
        raise SystemExit(p.stderr[-2000:])


items = jl(os.path.join(HERE, "served", "items_local.jsonl"))
P = {m: jl(os.path.join(HERE, "served", m, "preds.jsonl")) for m in ("w4a5", "v42", "eikos")}
fl = json.load(open(os.path.join(HERE, "overlap_public.json")))["flags"]["ce_items"]  # the lineage = the release's rows
assert len(fl) == len(items) == len(P["w4a5"])
lineage = {f["i"] for f in fl if f["identical"] or f["near"]}
same104 = set(json.load(open(os.path.join(HERE, "same_item_104.json"))))
res = {}
with tempfile.TemporaryDirectory() as d:
    def analyze(m, keep, tag):
        pf = os.path.join(d, f"{m}_{tag}.jsonl")
        with open(pf, "w") as f:
            for i in keep:
                f.write(json.dumps(P[m][i]) + "\n")
        out = os.path.join(d, f"rep_{m}_{tag}.json")
        run("confident_errors_analyze.py", [pf, out])
        r = json.load(open(out))
        return pf, {"primary": r["primary"], "secondary_changed": r["secondary_changed"],
                    "n": {g: r["groups"][g]["all"]["n"] for g in ("T", "H", "U")}}

    for tag, ex in (("all", set()), ("lineage_overlap_removed", lineage)):
        keep = [i for i in range(len(items)) if i not in ex]
        res[f"w4a5_{tag}"] = analyze("w4a5", keep, tag)[1]
    keep = [i for i in range(len(items)) if i not in same104]
    pv, res["v42_same_item_104_removed"] = analyze("v42", keep, "s104")
    pe, res["eikos_same_item_104_removed"] = analyze("eikos", keep, "s104")
    out = os.path.join(d, "cmp.json")
    run("confident_errors_compare.py", [pv, pe, out])
    c = json.load(open(out))
    res["compare_same_item_104_removed"] = {"D": c["D"], "D_ci95": c["D_ci95"], "verdict": c["verdict"]}
json.dump(res, open(os.path.join(HERE, "extra.json"), "w"), indent=1)
for k, v in res.items():
    print(k, json.dumps(v)[:500])
