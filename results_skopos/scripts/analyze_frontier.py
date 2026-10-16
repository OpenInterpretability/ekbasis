"""Frontier test analysis (ADDENDUM_FRONTIER, Addendum B): AgentWorld vs Ekbasis base and R1 on the same indices.
Accuracy with unparsed = wrong (the rule), accuracy among parsed (descriptive; truncation may pick the harder items),
paired bootstrap by item (2,000, seed 20261015), tokens and seconds per answer.
    python3 analyze_frontier.py /root/v50p"""
import json, random, statistics as st, sys
D = sys.argv[1]
L = lambda p: [json.loads(l) for l in open(p)]


def boot(d):
    rng = random.Random(20261015); n = len(d)
    v = sorted(sum(d[rng.randrange(n)] for _ in range(n)) / n for _ in range(2000))
    return round(v[50], 3), round(v[1949], 3)


out = {}
for s in ["git_long", "guard_known", "fhorizon", "latent_test"]:
    try:
        aw = L(f"{D}/frontier/aw_{s}.jsonl")
    except FileNotFoundError:
        continue
    base, r1 = L(f"{D}/base_probs/preds_{s}_floor.jsonl"), L(f"{D}/run_r1/preds_{s}_floor.jsonl")
    idx = [a["i"] for a in aw]
    awok = [int(a["ok"]) for a in aw]
    res = {"n": len(aw), "parsed": sum(a["pred"] is not None for a in aw),
           "truncated": sum(a.get("finish") == "length" for a in aw),
           "aw": round(sum(awok) / len(aw), 3),
           "aw_parsed_only": round(sum(a["ok"] for a in aw if a["pred"] is not None) / max(1, sum(a["pred"] is not None for a in aw)), 3),
           "base": round(sum(base[i]["ok"] for i in idx) / len(idx), 3),
           "r1": round(sum(r1[i]["ok"] for i in idx) / len(idx), 3),
           "base_on_aw_parsed": round(sum(base[a["i"]]["ok"] for a in aw if a["pred"] is not None) / max(1, sum(a["pred"] is not None for a in aw)), 3),
           "aw_tokens_median": st.median(a["tokens"] or 0 for a in aw), "aw_s_median": st.median(a["s"] for a in aw)}
    d = [int(base[i]["ok"]) - o for i, o in zip(idx, awok)]
    res["base_minus_aw"] = (round(sum(d) / len(d), 3), boot(d))
    d = [int(r1[i]["ok"]) - o for i, o in zip(idx, awok)]
    res["r1_minus_aw"] = (round(sum(d) / len(d), 3), boot(d))
    pa = [a for a in aw if a["pred"] is not None]
    d = [int(base[a["i"]]["ok"]) - int(a["ok"]) for a in pa]
    res["base_minus_aw_parsed_only"] = (round(sum(d) / max(1, len(d)), 3), boot(d) if d else None)
    if s in ("git_long", "fhorizon"):
        by = {}
        for a in aw:
            k = str(base[a["i"]]["steps"])
            by.setdefault(k, []).append((a, base[a["i"]], r1[a["i"]]))
        res["by_steps"] = {k: {"n": len(v), "aw": round(sum(x[0]["ok"] for x in v) / len(v), 3),
                               "aw_trunc": sum(x[0].get("finish") == "length" for x in v),
                               "base": round(sum(x[1]["ok"] for x in v) / len(v), 3), "r1": round(sum(x[2]["ok"] for x in v) / len(v), 3)}
                           for k, v in sorted(by.items(), key=lambda t: int(t[0]))}
    out[s] = res
print(json.dumps(out, indent=1))
