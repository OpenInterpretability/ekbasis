"""Neutral ground (PREREG_NEUTRAL.md): balanced accuracy per world and pooled, AUROC and recall at 10% false alarms
for Ekbasis (probabilities), AgentWorld (letters; A = yes = fails). Bootstrap clustered by trajectory, 2,000, seed 20261015.
    python3 analyze_neutral.py DATA.jsonl name=ekbasis_preds.jsonl ... aw=aw_awb_neutral.jsonl"""
import json, random, sys, collections

data = [json.loads(l) for l in open(sys.argv[1])]
models = {}
for arg in sys.argv[2:]:
    name, path = arg.split("=", 1)
    rows = [json.loads(l) for l in open(path)]
    if "probs" in rows[0]:  # trainer preds, in data order; option 0 is 'yes' (fails)
        models[name] = {i: {"p": r["probs"][0], "y": r["pred"] == "yes"} for i, r in enumerate(rows)}
    else:  # frontier_eval: i = data index, pred letter
        # unparsed counts as wrong (PREREG_NEUTRAL): its 'y' is the opposite of the gold answer
        models[name] = {r["i"]: {"p": None, "y": (r["pred"] == "A") if r["pred"] is not None else (not bool(data[r["i"]]["gold"])),
                                 "tok": r.get("tokens"), "s": r.get("s"), "unparsed": r["pred"] is None} for r in rows}
gold = [bool(r["gold"]) for r in data]
traj = collections.defaultdict(list)
for i, r in enumerate(data):
    traj[r["traj"]].append(i)
T = sorted(traj)


def bal(idx, m):
    pos = [i for i in idx if gold[i]]; neg = [i for i in idx if not gold[i]]
    if not pos or not neg:
        return None
    return (sum(m[i]["y"] for i in pos) / len(pos) + sum(not m[i]["y"] for i in neg) / len(neg)) / 2


def auroc(idx, m):
    pos = [m[i]["p"] for i in idx if gold[i]]; neg = [m[i]["p"] for i in idx if not gold[i]]
    if not pos or not neg or pos[0] is None:
        return None
    return sum((a > b) + 0.5 * (a == b) for a in pos for b in neg) / (len(pos) * len(neg))


def rec_at(idx, m, fpr=0.10):
    neg = sorted((m[i]["p"] for i in idx if not gold[i]), reverse=True)
    if not neg or neg[0] is None:
        return None
    thr = neg[int(len(neg) * fpr)] if int(len(neg) * fpr) < len(neg) else 1.0
    pos = [m[i]["p"] for i in idx if gold[i]]
    return sum(p > thr for p in pos) / len(pos)


def boot(fn, sel, B=2000):
    rng = random.Random(20261015); vals = []
    for _ in range(B):
        idx = [i for t in (rng.choice(T) for _ in T) for i in traj[t] if sel(i)]
        v = fn(idx)
        if v is not None:
            vals.append(v)
    vals.sort()
    return round(vals[int(.025 * len(vals))], 3), round(vals[int(.975 * len(vals)) - 1], 3)


out = {}
worlds = {"pooled": lambda i: True, **{w: (lambda i, w=w: data[i]["world"] == w) for w in sorted({r["world"] for r in data})}}
for name, m in models.items():
    out[name] = {}
    for w, sel in worlds.items():
        idx = [i for i in range(len(data)) if sel(i) and i in m]
        res = {"n": len(idx), "fails": sum(gold[i] for i in idx), "bal_acc": round(bal(idx, m), 3),
               "bal_ci": boot(lambda ix: bal([i for i in ix if i in m], m), sel)}
        if m[idx[0]]["p"] is not None:
            res["auroc"] = round(auroc(idx, m), 3); res["auroc_ci"] = boot(lambda ix: auroc([i for i in ix if i in m], m), sel)
            res["recall_at_10fpr"] = round(rec_at(idx, m), 3)
        else:
            res["unparsed"] = sum(m[i]["unparsed"] for i in idx)
            tk = sorted(m[i]["tok"] or 0 for i in idx); ss = sorted(m[i]["s"] or 0 for i in idx)
            res["median_tokens"], res["median_s"] = tk[len(tk) // 2], ss[len(ss) // 2]
        out[name][w] = res
names = list(models)
if "aw" in models:
    out["diff_vs_aw"] = {}
    for n in names:
        if n == "aw":
            continue
        both = lambda i: i in models[n] and i in models["aw"]
        f = lambda ix: (lambda a, b: None if a is None or b is None else a - b)(bal(ix, models[n]), bal(ix, models["aw"]))
        idx = [i for i in range(len(data)) if both(i)]
        out["diff_vs_aw"][n] = {"bal_diff": round(f(idx), 3), "ci": boot(f, both)}
print(json.dumps(out, indent=1))
