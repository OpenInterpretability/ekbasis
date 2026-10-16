# V50R1 result (rule in PREREG_R1.md, sealed before training) — 2026-10-15 04:15 UTC

**Verdict: FAIL (narrowly).** Guards pass; neither primary criterion is met.

| suite | R1 | base | diff [95% CI] | conf. errors/100 after refit (R1/base) |
|---|---|---|---|---|
| git_long (5/8/12 real git cmds) | 0.921 | 0.907 | +0.014 [+0.000, +0.029] | 3.22 / 4.11 (−22%; rule −30%) |
| fhorizon (synthetic 1–20) | 0.873 | 0.860 | +0.013 [−0.000, +0.025] | 1.02 / 0.80 |
| fhorizon long (8/12/20) | | | **+0.030 [+0.005, +0.054]** | |
| latent_test | 0.805 | 0.792 | **+0.013 [+0.004, +0.021]** | 0.90 / 0.88 |
| git3_test_held | 0.961 | 0.952 | **+0.009 [+0.002, +0.016]** | 1.73 / 2.40 |
| guard_known | 0.952 | 0.947 | +0.005 [+0.000, +0.010] | 2.05 / 2.67 |
| git3_test_known | 0.981 | 0.980 | +0.001 [−0.004, +0.006] | 0.81 / 1.01 |
| ftest_family | 0.825 | 0.831 | −0.006 [−0.018, +0.007] | 1.20 / 1.11 |
| m3val | 0.920 | 0.913 | +0.007 [−0.017, +0.030] | 2.33 / 1.33 |
| fval_git3 | 0.929 | 0.930 | −0.001 [−0.009, +0.008] | 1.44 / 1.51 |

git_long by length: 5 .940→.957, 8 .887→.907, 12 .893→.900.
Temperatures fitted on validation (fval_git3 + m3val): R1 1.60, base 1.55.

## Reading
- Real-domain plan items help in the right direction but below the bar; nothing regresses (all M3 guards hold).
- **The refit alone is the large, cheap win:** for the *base* model, T = 1.55 cuts confident errors on git_long from
  6.67 to 4.11 per 100 (−38%) and ECE 0.074 → 0.046, with no training. Every suite's ECE improves similarly.
  This is a serving-side change (scale logits by 1/T before the softmax), to be refit on the INT4 production model
  and proposed to Caio (clients' thresholds see different probabilities).
- Where errors remain on git_long (test, diagnosis only): rm --cached, commit --allow-empty, stash --keep-index,
  mixed reset, clean (12–18% error vs 7.9%). Any targeted recipe will be designed on git_long_val (seeds 40000+).

## Process note
analyze_r1.py crashed at R1_DONE (gold index read as a letter; gold is a label). Fixed by recovering the gold index
from the saved probabilities (checked: 0 mismatches in 900) and a JSON bool cast; method unchanged. Old file kept as
analyze_r1.py.bug on the RTX.

## Deployment of the refit (2026-10-15 11:58 UTC, approved by Caio)
Refit on the production INT4 model through /v1/evaluate (fit fval_git3 + m3val, 1,824): T = 1.55. Test (2,500 items:
git_long 900, guard 800, fac_val 800): accuracy 0.911 both; ECE 0.068 → 0.036; confident errors 6.24 → 3.88 per 100;
Brier 0.155 → 0.142. Deployed as an ADDITIVE "calibrated" field (raw fields unchanged) because the pre-registered
test of 3 October rejected a global switch (fixed client thresholds shift). Client 0.1.41 / TS 0.2.5 read it.
