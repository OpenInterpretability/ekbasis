"""Factory quality (QUALITY.md numbers): balance, coverage, informative share, changed share, twins, determinism.
python3 quality.py <data_dir> <out.json> [--determinism]"""
import collections
import importlib
import json
import os
import random
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
data_dir, out_path = sys.argv[1], sys.argv[2]
FAM_MOD = {"shell": "shell", "sql": "sqlfam", "python": "pyfam", "git": "gitfam"}
rep = {}
for fam in ["shell", "sql", "python", "git", "gui"]:
    p = os.path.join(data_dir, f"{fam}.jsonl")
    if not os.path.exists(p):
        continue
    rows = [json.loads(l) for l in open(p)]
    st = json.load(open(p.replace(".jsonl", ".stats.json"))) if os.path.exists(p.replace(".jsonl", ".stats.json")) else {}
    by_q = collections.defaultdict(list)
    for r in rows:
        by_q[r["qtype"]].append(r)
    bal = {}
    for qt, rs in by_q.items():
        if rs[0]["question"]["type"] == "noul":
            y = sum(1 for r in rs if r["gold"] is True)
            bal[qt] = {"n": len(rs), "yes": y, "yes_share": round(y / len(rs), 3)}
        else:
            first = sum(1 for r in rs if list(r["question"]["criteria"])[0] == r["gold"])
            nopt = statistics.mean(len(r["question"]["criteria"]) for r in rs)
            bal[qt] = {"n": len(rs), "gold_is_first_option": round(first / len(rs), 3), "mean_options": round(nopt, 2),
                       "distinct_golds": len({r["gold"] for r in rs})}
    tmpl = collections.Counter(r["template"].split("+")[0] for r in rows)
    outcome = collections.Counter((r["template"].split("+")[0], r["qtype"], str(r["gold"])) for r in rows)
    with_face = [r for r in rows if r.get("face") is not None]
    inf = sum(1 for r in with_face if str(r["face"]) != str(r["gold"]))
    inf_q = {qt: round(sum(1 for r in rs if r.get("face") is not None and str(r["face"]) != str(r["gold"])) /
                       max(1, sum(1 for r in rs if r.get("face") is not None)), 3) for qt, rs in by_q.items()}
    known = [r for r in rows if r["known0"]]
    changed = sum(1 for r in known if str(r["gold0"]) != str(r["gold"]))
    twins = sum(1 for r in rows if r.get("twin"))
    rep[fam] = {"rows": len(rows), "scenarios": st.get("scenarios"), "scenarios_with_twin": st.get("twins"),
                "rows_in_a_twin_pair": twins, "templates": len(tmpl),
                "rows_per_template": {"min": min(tmpl.values()), "median": statistics.median(tmpl.values()), "max": max(tmpl.values())},
                "template_outcome_cells": len(outcome), "balance": bal,
                "informative_share": round(inf / max(1, len(with_face)), 3), "informative_by_qtype": inf_q,
                "changed_share_when_defined": round(changed / max(1, len(known)), 3), "n_known0": len(known),
                "rows_per_cpu_hour": st.get("rows_per_cpu_hour"), "cpu_s": st.get("cpu_s"), "errors": st.get("error", 0),
                "invalid_or_failed": st.get("invalid", 0) + st.get("exec_fail", 0) + st.get("build_fail", 0),
                "quarantined": any(r.get("quarantined") for r in rows[:50])}
    if "--determinism" in sys.argv and fam in FAM_MOD:
        mod = importlib.import_module(FAM_MOD[fam])
        by_seed = collections.defaultdict(list)
        for r in rows:
            by_seed[int(r["id"].split("-")[1])].append(r)
        seeds = sorted(by_seed)
        random.Random(7).shuffle(seeds)
        sample = seeds[: max(20, len(seeds) // 50)]
        same = 0
        diffs = []
        for s in sample:
            new, _ = mod.make_items(s)
            a = sorted(json.dumps(r, sort_keys=True) for r in by_seed[s])
            b = sorted(json.dumps(r, sort_keys=True) for r in new)
            if a == b:
                same += 1
            elif len(diffs) < 3:
                diffs.append(s)
        rep[fam]["determinism"] = {"seeds_rerun": len(sample), "identical": same, "share": round(same / len(sample), 3),
                                   "first_differing_seeds": diffs}
json.dump(rep, open(out_path, "w"), indent=1)
print(json.dumps(rep, indent=1)[:6000])
