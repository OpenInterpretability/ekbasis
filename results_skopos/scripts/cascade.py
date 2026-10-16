"""Exploratory (post hoc, not pre-registered): a cascade on the frontier items. Ekbasis answers in one pass; if its
temperature-refit confidence is below tau, ask the reasoning model (AgentWorld here); if that one does not finish,
keep Ekbasis' answer. Reports escalation rate, accuracy and mean seconds per item, per suite.
    python3 cascade.py /root/v50p T_base"""
import json, math, sys
D, T = sys.argv[1], float(sys.argv[2])
L = lambda p: [json.loads(l) for l in open(p)]
EK_S = 0.15  # Ekbasis seconds per answer (one forward pass; generous)
for s in ["git_long", "guard_known", "fhorizon", "latent_test"]:
    aw, base = L(f"{D}/frontier/aw_{s}.jsonl"), L(f"{D}/base_probs/preds_{s}_floor.jsonl")
    rows = []
    for a in aw:
        b = base[a["i"]]
        lp = [math.log(max(p, 1e-12)) / T for p in b["probs"]]; m = max(lp); q = [math.exp(x - m) for x in lp]
        conf = max(q) / sum(q)
        rows.append((conf, b["ok"], a["ok"], a["pred"] is not None, a["s"]))
    print(f"== {s}  n={len(rows)}  Ekbasis {sum(r[1] for r in rows)/len(rows):.3f}  AW {sum(r[2] for r in rows)/len(rows):.3f}")
    for tau in (0.0, 0.7, 0.8, 0.9, 0.95, 0.99, 1.01):
        esc = [r for r in rows if r[0] < tau]
        acc = sum((r[2] if (r[0] < tau and r[3]) else r[1]) for r in rows) / len(rows)
        sec = sum(EK_S + (r[4] if r[0] < tau else 0) for r in rows) / len(rows)
        print(f"   tau {tau:4.2f}  escala {len(esc)/len(rows):5.1%}  acerto {acc:.3f}  s/item {sec:6.1f}")
