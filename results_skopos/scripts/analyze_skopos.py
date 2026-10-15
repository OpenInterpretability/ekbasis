"""PREREG_SKOPOS_CMP.md: R2 vs Skopos (and base) on the same items. Paired bootstrap 2,000, seed 20261015.
    python3 analyze_skopos.py /root/v50p"""
import json, random, sys
D = sys.argv[1]
L = lambda p: [json.loads(l) for l in open(f"{D}/{p}")]
SRC = {  # split -> (R2 preds, base preds)
    "fac_val": ("run_r2", "base_facval"), "git_long_val": ("diag_r2", "diag_base"), "sess_val": ("r2_sessval", "base_sessval")}


def boot(a, b):
    rng = random.Random(20261015); n = len(a); d = [x - y for x, y in zip(a, b)]
    v = sorted(sum(d[rng.randrange(n)] for _ in range(n)) / n for _ in range(2000))
    return round(sum(d) / n, 4), [round(v[50], 4), round(v[1949], 4)]


out = {}
for s in ["fac_val", "git_long", "git_long_val", "fhorizon", "latent_test", "git3_test_known", "git3_test_held",
          "guard_known", "ftest_family", "m3val", "fval_git3", "sess_val"]:
    r2d, bd = SRC.get(s, ("run_r2", "base_probs"))
    sk, r2, b = L(f"skopos_eval/preds_{s}_floor.jsonl"), L(f"{r2d}/preds_{s}_floor.jsonl"), L(f"{bd}/preds_{s}_floor.jsonl")
    assert len(sk) == len(r2) == len(b), s
    ok = lambda X: [int(x["ok"]) for x in X]
    out[s] = {"skopos": round(sum(ok(sk)) / len(sk), 4), "r2": round(sum(ok(r2)) / len(r2), 4), "base": round(sum(ok(b)) / len(b), 4),
              "r2_minus_skopos": boot(ok(r2), ok(sk)), "skopos_minus_base": boot(ok(sk), ok(b))}
data = L("data/guard_known.jsonl")
g = {}
for name, d in (("skopos", "skopos_eval"), ("r2", "run_r2"), ("base", "base_probs")):
    P = L(f"{d}/preds_guard_known_floor.jsonl")
    lost = [(x, p) for x, p in zip(data, P) if x["qtype"] == "lost"]
    pos = [p for x, p in lost if p["gold"] == "yes"]; neg = [p for x, p in lost if p["gold"] == "no"]
    g[name] = {"flagged_at_0.2": round(100 * sum(p["probs"][0] >= 0.2 for p in pos) / len(pos), 2),
               "false_alarms_at_0.2": round(100 * sum(p["probs"][0] >= 0.2 for p in neg) / len(neg), 2)}
out["guard_0.2"] = g
try:
    nd = L("data/awb_neutral.jsonl")
    def auroc(P):
        pos = [p["probs"][0] for x, p in zip(nd, P) if x["gold"]]; neg = [p["probs"][0] for x, p in zip(nd, P) if not x["gold"]]
        return round(sum((a > c) + 0.5 * (a == c) for a in pos for c in neg) / (len(pos) * len(neg)), 4)
    out["neutral_auroc"] = {"skopos": auroc(L("neutral_skopos/preds_awb_neutral_floor.jsonl")),
                            "r2": auroc(L("neutral_r2/preds_awb_neutral_floor.jsonl")), "base": auroc(L("neutral_base/preds_awb_neutral_floor.jsonl"))}
except FileNotFoundError:
    out["neutral_auroc"] = None
worse = [s for s in out if isinstance(out[s], dict) and "r2_minus_skopos" in out[s]
         and out[s]["r2_minus_skopos"][0] < -0.01 and out[s]["r2_minus_skopos"][1][1] < 0]
gain = [s for s in ("fac_val", "git_long", "git_long_val") if out[s]["r2_minus_skopos"][0] >= 0.01 and out[s]["r2_minus_skopos"][1][0] > 0]
gd = g["r2"]["flagged_at_0.2"] - g["skopos"]["flagged_at_0.2"]; fa = g["r2"]["false_alarms_at_0.2"] - g["skopos"]["false_alarms_at_0.2"]
out["verdict"] = {"suites_worse": worse, "gain_suites": gain, "guard_flagged_diff": round(gd, 2), "guard_fa_diff": round(fa, 2),
                  "r2_replaces_skopos": bool(not worse and gd >= -1 and fa <= 1 and gain)}
json.dump(out, open(f"{D}/skopos_eval/SKOPOS_CMP.json", "w"), indent=1)
for s, v in out.items():
    if isinstance(v, dict) and "r2_minus_skopos" in v:
        print(f"{s:16s} skopos {v['skopos']:.3f} r2 {v['r2']:.3f} base {v['base']:.3f} | r2-skopos {v['r2_minus_skopos']} | skopos-base {v['skopos_minus_base']}")
print("guard_0.2", g); print("neutral_auroc", out["neutral_auroc"]); print("VERDICT", out["verdict"])
