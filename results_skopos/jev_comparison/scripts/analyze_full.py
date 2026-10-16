"""Scores the full-set extension: the release protocol (git v3 known + held, all rows; the `lost` rows of guard_known and
guard_held) and the hosted scorecard's five suites, Jev (both prompt variants) against the published per-item
predictions on the same rows. Reads pool_items.jsonl, sets_full.json, pool_preds_A.jsonl, pool_preds_B.jsonl from the
folder given (default: this script's folder); writes results_full.json there.
python3 -I analyze_full.py [FOLDER]"""
import json, random, statistics, sys
from pathlib import Path

D = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent
L = lambda p: [json.loads(l) for l in open(p) if l.strip()]
PRICE = 0.042 / 1e6
JEV = ("jev_A", "jev_B")
NAMES_PUB = ("ekbasis27b", "ekbasis27b_int4", "skopos_bf16", "skopos_int4", "ekbasis_hosted_replay")
items = {r["key"]: r for r in L(D / "pool_items.jsonl")}
sets = json.load(open(D / "sets_full.json"))
runs = {}
for v in ("A", "B"):
    m = {}
    for r in L(D / f"pool_preds_{v}.jsonl"):
        if not r.get("error"):
            m[r["idx"]] = r  # a request that failed and was retried keeps its successful answer
    runs[f"jev_{v}"] = m


def jev_pred(row):
    a = row["answer"]
    if a["type"] == "boolean":
        p = a["probability"]
        return {"pred": "yes" if p >= 0.5 else "no", "conf": max(p, 1 - p), "p_yes": p, "probs": {"yes": p, "no": 1 - p}}
    ps = a["probabilities"]
    return {"pred": a["choice"], "conf": ps[a["choice"]], "p_yes": None, "probs": ps}


def pub_pred(p, qtype_noul):
    out = {"pred": p["pred"], "conf": p["conf"], "p_yes": p.get("p_yes")}
    if qtype_noul:  # binary: the full distribution follows from the answer and its confidence
        py = p["p_yes"] if p.get("p_yes") is not None else (p["conf"] if p["pred"] == "yes" else 1 - p["conf"])
        out.update(p_yes=py, probs={"yes": py, "no": 1 - py})
    return out


def preds(system, keys):
    out = []
    for k in keys:
        it = items[k]
        noul = it["ekbasis_question"]["type"] == "noul"
        out.append(jev_pred(runs[system][k]) if system in runs else pub_pred(it["published"][system], noul))
    return out


def has(system, keys):
    return system in runs or all(system in items[k]["published"] for k in keys)


def ece(conf, ok, bins):
    b = [[] for _ in range(bins)]
    for c, o in zip(conf, ok):
        b[min(bins - 1, int(c * bins))].append((c, o))
    return sum(len(v) / len(conf) * abs(sum(o for _, o in v) / len(v) - sum(c for c, _ in v) / len(v)) for v in b if v)


def auroc(pos, neg):  # Mann-Whitney with tied ranks
    allv = sorted([(x, 1) for x in pos] + [(x, 0) for x in neg])
    rank_sum, i = 0.0, 0
    while i < len(allv):
        j = i
        while j < len(allv) and allv[j][0] == allv[i][0]:
            j += 1
        r = (i + 1 + j) / 2
        rank_sum += r * sum(1 for t in range(i, j) if allv[t][1])
        i = j
    return (rank_sum - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))


def lost_metrics(P, G, fa_target=None):
    pos = [p for p, g in zip(P, G) if g == "yes"]
    neg = [p for p, g in zip(P, G) if g == "no"]
    m = {"n_work_losing": len(pos), "n_safe": len(neg), "auroc": auroc(pos, neg),
         "flagged_at_0.2": sum(p >= 0.2 for p in pos), "false_alarms_at_0.2": sum(p >= 0.2 for p in neg)}
    m["flagged_pct_at_0.2"] = 100 * m["flagged_at_0.2"] / len(pos)
    m["false_alarm_pct_at_0.2"] = 100 * m["false_alarms_at_0.2"] / len(neg)
    sneg = sorted(neg, reverse=True)
    thr = sneg[max(0, int(0.10 * len(sneg)) - 1)]
    m["caught_pct_at_10pct_false_alarm"] = 100 * sum(a > thr for a in pos) / len(pos)
    if fa_target is not None:
        ok = [t for t in sorted(set(P)) if 100 * sum(p >= t for p in neg) / len(neg) <= fa_target]
        t = ok[0] if ok else float("inf")
        m.update({"matched_fa_target_pct": fa_target, "matched_threshold": t,
                  "flagged_pct_at_matched_threshold": 100 * sum(p >= t for p in pos) / len(pos),
                  "false_alarm_pct_at_matched_threshold": 100 * sum(p >= t for p in neg) / len(neg)})
    return m


def boot_acc(a, b, n=2000, seed=20261015):
    rng, k = random.Random(seed), len(a)
    d = [x - y for x, y in zip(a, b)]
    m = sorted(sum(d[rng.randrange(k)] for _ in range(k)) / k for _ in range(n))
    return [100 * m[int(0.025 * n)], 100 * m[int(0.975 * n)]]


def boot_lost(Pa, Pb, G, n=2000, seed=20261015):
    rng = random.Random(seed)
    pi = [i for i, g in enumerate(G) if g == "yes"]; ni = [i for i, g in enumerate(G) if g == "no"]
    out = {"auroc": [], "flagged_pct_at_0.2": [], "false_alarm_pct_at_0.2": []}
    for _ in range(n):
        sp = [pi[rng.randrange(len(pi))] for _ in pi]; sn = [ni[rng.randrange(len(ni))] for _ in ni]
        g = ["yes"] * len(sp) + ["no"] * len(sn)
        ma, mb = lost_metrics([Pa[i] for i in sp + sn], g), lost_metrics([Pb[i] for i in sp + sn], g)
        for k in out:
            out[k].append(ma[k] - mb[k])
    return {k: [sorted(v)[int(0.025 * n)], sorted(v)[int(0.975 * n)]] for k, v in out.items()}


def scorecard_score(P, keys):
    """scorecard.py's score(): accuracy, wrong answers at confidence >= 0.9 per 100, Brier over the full distribution
    (None when a published file has only the chosen option's probability), ECE over 10 bins."""
    n = ok = ce = 0
    brier, full = 0.0, True
    bins = [[0, 0.0, 0] for _ in range(10)]
    for p, k in zip(P, keys):
        gold = items[k]["gold"]
        right = p["pred"] == gold
        n += 1; ok += right; ce += (not right) and p["conf"] >= 0.9
        if "probs" in p:
            brier += (1 - p["probs"].get(gold, 0.0)) ** 2 + sum(v ** 2 for o, v in p["probs"].items() if o != gold)
        else:
            full = False
        b = min(9, int(p["conf"] * 10)); bins[b][0] += 1; bins[b][1] += p["conf"]; bins[b][2] += right
    return {"answered": n, "accuracy": 100 * ok / n, "confident_errors_per_100": 100 * ce / n,
            "brier": brier / n if full else None, "ece": sum(abs(c - r) for k, c, r in bins if k) / n}


def jev_cost(system, keys):
    rows = [runs[system][k] for k in keys]
    lat = sorted(r["latency_ms"] for r in rows)
    tok = [r["usage"]["inputTokens"] for r in rows]
    return {"input_tokens_per_check": statistics.mean(tok), "usd_per_1000_checks": statistics.mean(tok) * PRICE * 1000,
            "latency_ms_p50": lat[min(len(lat) - 1, int(0.5 * len(lat)))], "latency_ms_p90": lat[min(len(lat) - 1, int(0.9 * len(lat)))],
            "seeded_from_first_run": sum(bool(r.get("seeded_from_first_run")) for r in rows)}


res = {"release_protocol": {}, "scorecard": {}}
# ---------------------------------------------------------------------------- release protocol
rp = res["release_protocol"]
for name, keys in (("git3_test_known", sets["release:git3_test_known"]), ("git3_test_held", sets["release:git3_test_held"]),
                   ("git_v3_all", sets["release:git3_test_known"] + sets["release:git3_test_held"])):
    G = [items[k]["gold"] for k in keys]
    systems = [s for s in (*JEV, *NAMES_PUB) if has(s, keys)]
    P = {s: preds(s, keys) for s in systems}
    ok = {s: [int(p["pred"] == g) for p, g in zip(P[s], G)] for s in systems}
    out = {"n": len(keys), "systems": {}}
    li = [i for i, k in enumerate(keys) if items[k]["qtype"] == "lost"]
    for s in systems:
        conf = [p["conf"] for p in P[s]]
        cat = {"lost": lambda k: items[k]["qtype"] == "lost", "fails": lambda k: items[k]["qtype"] == "fails",
               "in_progress": lambda k: items[k]["qtype"] == "in_progress", "changed state": lambda k: items[k]["changed_state"]}
        m = {"acc": 100 * sum(ok[s]) / len(keys), "ece10": ece(conf, ok[s], 10), "ece15": ece(conf, ok[s], 15), "mean_conf": statistics.mean(conf),
             "categories": {c: {"n": sum(f(k) for k in keys), "acc": 100 * sum(o for o, k in zip(ok[s], keys) if f(k)) / sum(f(k) for k in keys)}
                            for c, f in cat.items()},
             "acc_by_qtype": {q: 100 * sum(o for o, k in zip(ok[s], keys) if items[k]["qtype"] == q) / sum(items[k]["qtype"] == q for k in keys)
                              for q in sorted({items[k]["qtype"] for k in keys})}}
        m["lost"] = lost_metrics([P[s][i]["p_yes"] for i in li], [G[i] for i in li])
        out["systems"][s] = m
    out["qtype_n"] = {q: sum(items[k]["qtype"] == q for k in keys) for q in sorted({items[k]["qtype"] for k in keys})}
    hv = max(JEV, key=lambda v: out["systems"][v]["acc"])
    out["jev_headline"] = {"variant": hv, "rule": "accuracy", "values": {v: out["systems"][v]["acc"] for v in JEV}}
    out["paired"] = {f"{hv}_minus_{s}": {"acc_diff": out["systems"][hv]["acc"] - out["systems"][s]["acc"], "acc_diff_ci95": boot_acc(ok[hv], ok[s])}
                     for s in systems if s != hv}
    out["jev_cost"] = {v: jev_cost(v, keys) for v in JEV}
    rp[name] = out
    print(name, hv, {s: round(m["acc"], 2) for s, m in out["systems"].items()}, flush=True)

for name in ("guard_known", "guard_held"):
    keys = sets[f"release:{name}"]
    G = [items[k]["gold"] for k in keys]
    systems = [s for s in (*JEV, *NAMES_PUB) if has(s, keys)]
    P = {s: preds(s, keys) for s in systems}
    fa_e = 100 * sum(p["p_yes"] >= 0.2 for p, g in zip(P["ekbasis27b"], G) if g == "no") / G.count("no")
    out = {"n": len(keys), "systems": {}}
    for s in systems:
        ok = [int(p["pred"] == g) for p, g in zip(P[s], G)]
        m = lost_metrics([p["p_yes"] for p in P[s]], G, fa_e)
        m.update({"acc_at_0.5": 100 * sum(ok) / len(ok), "ece15": ece([p["conf"] for p in P[s]], ok, 15), "ece10": ece([p["conf"] for p in P[s]], ok, 10)})
        out["systems"][s] = m
    hv = max(JEV, key=lambda v: out["systems"][v]["auroc"])
    out["jev_headline"] = {"variant": hv, "rule": "AUROC of P(lost)", "values": {v: out["systems"][v]["auroc"] for v in JEV}}
    out["paired"] = {}
    for s in systems:
        if s == hv:
            continue
        a, b = out["systems"][hv], out["systems"][s]
        out["paired"][f"{hv}_minus_{s}"] = {**{f"{k}_diff": a[k] - b[k] for k in ("auroc", "flagged_pct_at_0.2", "false_alarm_pct_at_0.2", "acc_at_0.5")},
                                            "ci95": boot_lost([p["p_yes"] for p in P[hv]], [p["p_yes"] for p in P[s]], G)}
    out["jev_cost"] = {v: jev_cost(v, keys) for v in JEV}
    rp[name] = out
    print(name, hv, {s: (round(m["auroc"], 4), m["flagged_at_0.2"], m["false_alarms_at_0.2"]) for s, m in out["systems"].items()}, flush=True)

# ---------------------------------------------------------------------------- hosted scorecard suites
for suite in ("git3_known", "git3_held", "guard_held", "worlds", "intent"):
    keys = sets[f"scorecard:{suite}"]
    systems = [s for s in (*JEV, *NAMES_PUB) if has(s, keys)]
    P = {s: preds(s, keys) for s in systems}
    G = [items[k]["gold"] for k in keys]
    ok = {s: [int(p["pred"] == g) for p, g in zip(P[s], G)] for s in systems}
    out = {"n": len(keys), "systems": {s: scorecard_score(P[s], keys) for s in systems}}
    hv = max(JEV, key=lambda v: out["systems"][v]["accuracy"])
    out["jev_headline"] = {"variant": hv, "rule": "accuracy", "values": {v: out["systems"][v]["accuracy"] for v in JEV}}
    out["paired"] = {f"{hv}_minus_{s}": {"acc_diff": out["systems"][hv]["accuracy"] - out["systems"][s]["accuracy"], "acc_diff_ci95": boot_acc(ok[hv], ok[s])}
                     for s in systems if s != hv}
    out["jev_cost"] = {v: jev_cost(v, keys) for v in JEV}
    res["scorecard"][suite] = out
    print(suite, hv, {s: round(m["accuracy"], 2) for s, m in out["systems"].items()}, flush=True)
json.dump(res, open(D / "results_full.json", "w"), indent=1)
