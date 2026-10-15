# V50R4 result (PREREG_R4.md, same rule as PREREG_SKOPOS_CMP) — 2026-10-15 16:48 UTC

**Verdict: R4 REPLACES SKOPOS as the release candidate.** R4 = R2's data (real long-git plan items, regenerated F
factory, synthetic plan items) as a new LoRA on top of Ekbasis-Skopos-27B (v49f_w50).

| suite | R4 | Skopos | base | R4 − Skopos [95% CI] |
|---|---|---|---|---|
| fac_val | **0.940** | 0.925 | 0.884 | **+0.016 [+0.010, +0.022]** |
| git_long | **0.932** | 0.913 | 0.907 | **+0.019 [+0.007, +0.031]** |
| git_long_val | **0.946** | 0.919 | 0.910 | **+0.026 [+0.016, +0.036]** |
| latent_test | **0.814** | 0.793 | 0.792 | **+0.021 [+0.013, +0.028]** |
| sess_val | **0.931** | 0.912 | 0.890 | **+0.019 [+0.007, +0.033]** |
| fval_git3 | 0.941 | 0.933 | 0.930 | +0.008 [0.000, +0.016] |
| guard_known | 0.964 | 0.960 | 0.947 | +0.004 [−0.000, +0.008] |
| fhorizon | 0.868 | 0.868 | 0.860 | 0.000 [−0.013, +0.013] |
| git3_test_known | 0.985 | 0.985 | 0.980 | +0.001 |
| git3_test_held | 0.953 | 0.958 | 0.952 | −0.004 [−0.011, +0.003] |
| ftest_family | 0.834 | 0.834 | 0.831 | 0.000 [−0.015, +0.014] |
| m3val | 0.930 | 0.937 | 0.913 | −0.007 [−0.027, +0.013] |

Guard at 0.2 (guard_known "lost"): flagged R4 96.76% / Skopos 97.45% / base 95.71% (−0.69, tolerance −1);
false alarms **3.24%** / 4.29% / 4.40% (−1.05: fewer).

## Reading
The two lines added: Skopos' guard sensitivity is (almost) kept, false alarms drop a quarter, and R2's gains in git,
the factory and sessions land on top — plus latent +2.1, which neither had. No suite is worse.
## Before release (in order)
1. The full release read (the 18-suite protocol of RELEASE_EVAL, incl. `multi`, where Skopos missed by −0.71).
2. Confirmation on fresh firewalled items. 3. Merge the LoRA into Skopos; INT4 (GPTQ W4A16) / FP8 / MLX builds and
re-measure on the INT4 serving stack. 4. A/B on the production stack. 5. Caio's OK to publish.
