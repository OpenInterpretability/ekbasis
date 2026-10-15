"""V50R3 analysis (PREREG_R3.md). Neutral: pooled AUROC R3 − R2 with a trajectory-clustered paired bootstrap
(2,000, seed 20261015). Other suites: item-paired bootstrap (2,000, seed 20261014).
    python3 analyze_r3.py /root/v50p"""
import json, random, sys, collections
D = sys.argv[1]
L = lambda p: [json.loads(l) for l in open(p)]


def auroc(ix, P, gold):
    pos = [P[i]["probs"][0] for i in ix if gold[i]]; neg = [P[i]["probs"][0] for i in ix if not gold[i]]
    if not pos or not neg:
        return None
    return sum((a > b) + 0.5 * (a == b) for a in pos for b in neg) / (len(pos) * len(neg))


def bal(ix, P, gold):
    pos = [i for i in ix if gold[i]]; neg = [i for i in ix if not gold[i]]
    return (sum(P[i]["pred"] == "yes" for i in pos) / len(pos) + sum(P[i]["pred"] != "yes" for i in neg) / len(neg)) / 2


out = {}
data = L(f"{D}/data/awb_neutral.jsonl"); gold = [bool(r["gold"]) for r in data]
P = {m: L(f"{D}/{d}/preds_awb_neutral_floor.jsonl") for m, d in (("base", "neutral_base"), ("r2", "neutral_r2"), ("r3", "neutral_r3"))}
traj = collections.defaultdict(list)
for i, r in enumerate(data):
    traj[r["traj"]].append(i)
T = sorted(traj); allix = list(range(len(data)))
rng = random.Random(20261015); dif = []
for _ in range(2000):
    ix = [i for t in (rng.choice(T) for _ in T) for i in traj[t]]
    a, b = auroc(ix, P["r3"], gold), auroc(ix, P["r2"], gold)
    if a is not None and b is not None:
        dif.append(a - b)
dif.sort()
out["neutral"] = {m: {"auroc": round(auroc(allix, P[m], gold), 4), "bal": round(bal(allix, P[m], gold), 4)} for m in P}
d0 = auroc(allix, P["r3"], gold) - auroc(allix, P["r2"], gold)
out["neutral"]["r3_minus_r2_auroc"] = (round(d0, 4), [round(dif[50], 4), round(dif[1949], 4)])
for w in ("awb_swe_fail", "awb_term_fail"):
    ix = [i for i in allix if data[i]["world"] == w]
    out["neutral"][w] = {m: round(auroc(ix, P[m], gold), 4) for m in P}


def boot(a, b):
    rng = random.Random(20261014); n = len(a); d = [x - y for x, y in zip(a, b)]
    v = sorted(sum(d[rng.randrange(n)] for _ in range(n)) / n for _ in range(2000))
    return round(sum(d) / n, 4), [round(v[50], 4), round(v[1949], 4)]


src = {"sess_val": ("base_sessval", "r2_sessval"), "fac_val": ("base_facval", "run_r2")}
for s in ["sess_val", "fac_val", "git_long", "fhorizon", "latent_test", "git3_test_known", "git3_test_held", "guard_known", "ftest_family", "m3val", "fval_git3"]:
    bdir, r2dir = src.get(s, ("base_probs", "run_r2"))
    r3, r2, b = L(f"{D}/run_r3/preds_{s}_floor.jsonl"), L(f"{D}/{r2dir}/preds_{s}_floor.jsonl"), L(f"{D}/{bdir}/preds_{s}_floor.jsonl")
    ok = lambda X: [int(x["ok"]) for x in X]
    out[s] = {"r3": round(sum(ok(r3)) / len(r3), 4), "r2": round(sum(ok(r2)) / len(r2), 4), "base": round(sum(ok(b)) / len(b), 4),
              "r3_minus_r2": boot(ok(r3), ok(r2)), "r3_minus_base": boot(ok(r3), ok(b))}
    if s == "sess_val":
        out[s]["by_qtype"] = {q: {m: round(sum(X[i]["ok"] for i in range(len(X)) if X[i]["qtype"] == q) / max(1, sum(1 for x in X if x["qtype"] == q)), 3)
                                  for m, X in (("r3", r3), ("r2", r2), ("base", b))} for q in sorted({x["qtype"] for x in r3})}
nd = out["neutral"]["r3_minus_r2_auroc"]; sv = out["sess_val"]["r3_minus_r2"]
grd = {s: not (out[s]["r3_minus_r2"][0] < -0.01 and out[s]["r3_minus_r2"][1][1] < 0) for s in ("fac_val", "git_long")}
grd.update({s: not (out[s]["r3_minus_base"][0] < -0.01 and out[s]["r3_minus_base"][1][1] < 0)
            for s in ("git3_test_known", "git3_test_held", "guard_known", "ftest_family", "m3val", "fval_git3")})
out["verdict"] = {"transfer_neutral": bool(nd[0] >= 0.03 and nd[1][0] > 0), "mechanism_sess_val": bool(sv[0] >= 0.03 and sv[1][0] > 0),
                  "guards": grd, "all_guards": all(grd.values())}
json.dump(out, open(f"{D}/run_r3/R3_RESULTS.json", "w"), indent=1)
print(json.dumps(out, indent=1))
