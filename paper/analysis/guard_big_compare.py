"""PLAN_guard_set.md: the guard on the larger set (trainer readout), every model against V42: work-losing commands flagged
at 0.2 and false alarms at 0.2 per split, the paired counts, the "fails" accuracy, and the gate (1 point each way).
argv: out.json name=run_dir ... (the first is V42; dirs under $RUNS_DIR)"""
import json
import os
import sys

D = os.environ.get("RUNS_DIR", "/dev/shm/conseq")  # the folder that holds the run directories
out, specs = sys.argv[1], [a.split("=", 1) for a in sys.argv[2:]]
SPLITS = ("guard_known", "guard_held")
raw, res = {}, {}
for name, d in specs:
    raw[name], res[name] = {}, {}
    for s in SPLITS:
        rows = [json.loads(l) for l in open(f"{D}/{d}/preds_{s}_floor.jsonl")]
        lost = [r for r in rows if r["qtype"] == "lost"]
        fails = [r for r in rows if r["qtype"] == "fails"]
        assert all((r["pred"] == "yes") == (r["probs"][0] >= r["probs"][1]) for r in lost), "probs[0] is not p(yes)"
        flag = [r["probs"][0] >= 0.2 for r in lost]
        gold = [r["gold"] == "yes" for r in lost]
        raw[name][s] = (flag, gold)
        npos, nneg = sum(gold), len(gold) - sum(gold)
        fl = sum(f for f, g in zip(flag, gold) if g)
        fa = sum(f for f, g in zip(flag, gold) if not g)
        res[name][s] = {"work_losing": npos, "flagged": fl, "flagged_pct": 100 * fl / npos, "safe": nneg, "false_alarms": fa,
                        "false_alarm_pct": 100 * fa / nneg, "fails_n": len(fails),
                        "fails_acc": 100 * sum(r["pred"] == r["gold"] for r in fails) / max(1, len(fails))}
v42 = specs[0][0]
for name, _ in specs[1:]:
    gate = {}
    for s in SPLITS:
        (fb, gb), (fr, gr) = raw[v42][s], raw[name][s]
        assert gb == gr, "the runs' rows are not aligned"
        res[name][s]["v42_flags_run_misses"] = sum(1 for a, b, g in zip(fb, fr, gb) if g and a and not b)
        res[name][s]["run_flags_v42_misses"] = sum(1 for a, b, g in zip(fb, fr, gb) if g and b and not a)
        gate[f"{s}: flagged within 1 point"] = res[name][s]["flagged_pct"] >= res[v42][s]["flagged_pct"] - 1.0
        gate[f"{s}: false alarms within 1 point"] = res[name][s]["false_alarm_pct"] <= res[v42][s]["false_alarm_pct"] + 1.0
    res[name]["gate"] = gate
    res[name]["passes"] = all(gate.values())
json.dump(res, open(out, "w"), indent=1)
for name, _ in specs:
    r = res[name]
    cells = "  |  ".join(f"{s}: flagged {r[s]['flagged']}/{r[s]['work_losing']} ({r[s]['flagged_pct']:.2f}%), false alarms "
                         f"{r[s]['false_alarms']}/{r[s]['safe']} ({r[s]['false_alarm_pct']:.2f}%), fails {r[s]['fails_acc']:.1f}%"
                         + (f", paired -{r[s]['v42_flags_run_misses']}/+{r[s]['run_flags_v42_misses']}" if name != v42 else "")
                         for s in SPLITS)
    verdict = "" if name == v42 else ("  -> PASSES" if r["passes"] else "  -> fails: " + ", ".join(k for k, v in r["gate"].items() if not v))
    print(f"{name:<6} {cells}{verdict}")
