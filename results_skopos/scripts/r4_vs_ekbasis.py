"""Skopos (R4) against Ekbasis-27B, trainer readout, on the sets of PREREG_R4.md: the same per-item predictions and the
same paired bootstrap as scripts/analyze_r4.py (2,000, seed 20261015), for the contrast R4 - Ekbasis-27B, which that
analysis did not print (it reported R4 - first Skopos and first Skopos - Ekbasis-27B). Descriptive, not a criterion.
Predictions read from the research backup (private HF caiovicentino1/ekbasis-v50-research, rtx/v50p/).
    python3 r4_vs_ekbasis.py OUT.json"""
import json, random, sys
from huggingface_hub import hf_hub_download
REPO, PRE = "caiovicentino1/ekbasis-v50-research", "rtx/v50p"
SRC = {"fac_val": "base_facval", "git_long_val": "diag_base", "sess_val": "base_sessval"}  # as analyze_r4.py
SETS = ["fac_val", "git_long", "git_long_val", "fhorizon", "latent_test", "sess_val", "git3_test_known", "git3_test_held",
        "guard_known", "ftest_family", "m3val", "fval_git3"]
L = lambda d, s: [json.loads(l) for l in open(hf_hub_download(REPO, f"{PRE}/{d}/preds_{s}_floor.jsonl"))]


def boot(a, b):
    rng = random.Random(20261015); n = len(a); d = [x - y for x, y in zip(a, b)]
    v = sorted(sum(d[rng.randrange(n)] for _ in range(n)) / n for _ in range(2000))
    return round(sum(d) / n, 4), [round(v[50], 4), round(v[1949], 4)]


out = {"method": __doc__.split("\n")[0], "sets": {}}
for s in SETS:
    try:
        r4, b = L("run_r4", s), L(SRC.get(s, "base_probs"), s)
    except Exception as e:
        out["sets"][s] = {"missing": type(e).__name__}; continue
    assert len(r4) == len(b), s
    ok = lambda X: [int(x["ok"]) for x in X]
    out["sets"][s] = {"n": len(r4), "r4": round(sum(ok(r4)) / len(r4), 4), "ekbasis27b": round(sum(ok(b)) / len(b), 4),
                      "r4_minus_ekbasis27b": boot(ok(r4), ok(b))}
    print(s, out["sets"][s], flush=True)
json.dump(out, open(sys.argv[1], "w"), indent=1)
