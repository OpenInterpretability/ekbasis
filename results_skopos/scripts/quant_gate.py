"""PREREG_quantized.md gate for a Skopos build against Skopos bf16 (both served, same items):
1 accuracy within 1 point (git3 pooled, multi_test_testfam changed one prompt [+ read-once for GPU builds], ftest changed);
2 ECE (git3) within 0.01; 3 guard flagged not >1 pt lower, false alarms not >1 pt higher (known, held);
4 agreement >= 97% (git3 + multi_testfam answers + ftest) and >= 99% on answers bf16 gives at >= 0.9 (git3, ftest).
    python3 quant_gate.py BF16_DIR BUILD_DIR [--no-read-once]"""
import json, sys, collections
B, Q = sys.argv[1], sys.argv[2]; ro = "--no-read-once" not in sys.argv
FAC = "/dev/shm/conseq/fac"
L = lambda p: [json.loads(l) for l in open(p)]
n = lambda g: {True: "yes", False: "no"}[g] if isinstance(g, bool) else str(g)
out, chk = {}, {}
# git3
gb, gq = [], []
for s in ("git3_test_known", "git3_test_held"):
    gb += L(f"{B}/preds_{s}.jsonl"); gq += L(f"{Q}/preds_{s}.jsonl")
acc = lambda P: 100 * sum(p["pred"] == p["gold"] for p in P) / len(P)
def ece(P):
    b = collections.defaultdict(list)
    for p in P: b[min(9, int(p["conf"] * 10))].append(p)
    return sum(len(v) / len(P) * abs(sum(x["pred"] == x["gold"] for x in v) / len(v) - sum(x["conf"] for x in v) / len(v)) for v in b.values())
out["git3"] = (acc(gb), acc(gq)); chk["1 git3"] = acc(gq) >= acc(gb) - 1
out["ece_git3"] = (ece(gb), ece(gq)); chk["2 ECE"] = ece(gq) <= ece(gb) + 0.01
# multi testfam changed
rows = L(f"{FAC}/multi_test_testfam.jsonl")
def multi(d, mode):
    P = L(f"{d}/preds_multi_test_testfam_{mode}.jsonl"); ok, ans = [], []
    for r, p in zip(rows, P):
        for k, q in enumerate(r["questions"]):
            ans.append(p["preds"][k])
            g0 = r["gold0s"][k]
            if r["known0s"][k] and g0 is not None and n(g0) != n(r["golds"][k]):
                ok.append(p["preds"][k] == n(r["golds"][k]))
    return 100 * sum(ok) / len(ok), ans
for mode in (("single", "read_once") if ro else ("single",)):
    (ab, ansb), (aq, ansq) = multi(B, mode), multi(Q, mode)
    out[f"multi_{mode}"] = (ab, aq); chk[f"1 multi {mode}"] = aq >= ab - 1
# ftest changed
fr = L(f"{FAC}/ftest_family.jsonl"); g0 = L(f"{FAC}/gold0_ftest_family.jsonl")
fb, fq = L(f"{B}/preds_ftest_family.jsonl"), L(f"{Q}/preds_ftest_family.jsonl")
ch = [i for i, (r, g) in enumerate(zip(fr, g0)) if g["known"] and n(g["gold0"]) != n(r["gold"])]
fa = lambda P: 100 * sum(P[i]["ok"] for i in ch) / len(ch)
out["ftest_changed"] = (fa(fb), fa(fq)); chk["1 ftest"] = fa(fq) >= fa(fb) - 1
# guard
for s in ("guard_known", "guard_held"):
    gr = L(f"{FAC}/{s}.jsonl"); pb, pq = L(f"{B}/preds_{s}.jsonl"), L(f"{Q}/preds_{s}.jsonl")
    def g(P):
        lost = [(r, p) for r, p in zip(gr, P) if r["qtype"] == "lost"]
        pos = [p for r, p in lost if r["gold"]]; neg = [p for r, p in lost if not r["gold"]]
        return 100 * sum(p["p_yes"] >= 0.2 for p in pos) / len(pos), 100 * sum(p["p_yes"] >= 0.2 for p in neg) / len(neg)
    (fb_, ab_), (fq_, aq_) = g(pb), g(pq)
    out[s] = {"flagged": (fb_, fq_), "false_alarms": (ab_, aq_)}
    chk[f"3 {s} flagged"] = fq_ >= fb_ - 1; chk[f"3 {s} false alarms"] = aq_ <= ab_ + 1
# agreement
_, ansb = multi(B, "single"); _, ansq = multi(Q, "single")
same = [p["pred"] == q["pred"] for p, q in zip(gb, gq)] + [a == b for a, b in zip(ansb, ansq)] + [p["pred"] == q["pred"] for p, q in zip(fb, fq)]
conf = [p["pred"] == q["pred"] for p, q in zip(gb + fb, gq + fq) if p["conf"] >= 0.9]
out["agreement"] = 100 * sum(same) / len(same); out["agreement_conf09"] = 100 * sum(conf) / len(conf)
chk["4 agreement >= 97"] = out["agreement"] >= 97; chk["4 agreement conf>=0.9 >= 99"] = out["agreement_conf09"] >= 99
res = {"values_bf16_build": out, "checks": chk, "pass": all(chk.values())}
print(json.dumps(res, indent=1))
