# V50R2 result (rule in PREREG_R2.md + addendum A, sealed before R1's result) — 2026-10-15 08:10 UTC

**Verdict: R2 PREFERRED over R1** (all three conditions hold). Best candidate so far.

| suite | R2 | R1 | base | R2 − R1 [95% CI] | R2 − base [95% CI] | conf. err./100 refit (R2/R1/base) | ECE refit (R2/base) |
|---|---|---|---|---|---|---|---|
| **fac_val** (factory shell/SQL/python/git, seeds 200000+) | **0.925** | 0.889 | 0.884 | **+0.035 [+0.028, +0.043]** | **+0.041 [+0.033, +0.049]** | 2.71 / 5.80 / 6.35 | 0.019 / 0.064 |
| git_long (real git 5/8/12) | 0.927 | 0.921 | 0.907 | +0.006 [−0.008, +0.019] | **+0.020 [+0.007, +0.036]** | 2.89 / 3.22 / 4.11 | 0.028 / 0.046 |
| fhorizon | 0.879 | 0.874 | 0.860 | +0.006 [−0.008, +0.020] | **+0.019 [+0.004, +0.034]** | 1.31 / 1.02 / 0.80 | 0.024 / 0.027 |
| latent_test | 0.796 | 0.805 | 0.792 | −0.009 [−0.017, 0.000] | +0.004 [−0.004, +0.013] | 1.00 / 0.90 / 0.88 | 0.031 / 0.037 |
| git3_test_known | 0.983 | 0.981 | 0.980 | +0.001 | +0.002 [−0.003, +0.007] | 0.88 / 0.81 / 1.01 | |
| git3_test_held | 0.954 | 0.961 | 0.952 | −0.007 [−0.015, +0.001] | +0.002 [−0.007, +0.011] | 2.16 / 1.73 / 2.40 | |
| guard_known | 0.953 | 0.952 | 0.947 | +0.001 | **+0.006 [+0.002, +0.011]** | 1.56 / 2.05 / 2.67 | 0.030 / 0.015 |
| ftest_family | 0.822 | 0.825 | 0.831 | −0.003 | −0.008 [−0.022, +0.005] | 1.02 / 1.20 / 1.11 | 0.067 / 0.047 |
| m3val | 0.927 | 0.920 | 0.913 | +0.007 | +0.013 [−0.013, +0.040] | | |
| fval_git3 | 0.935 | 0.929 | 0.930 | +0.006 | +0.005 [−0.004, +0.015] | | |

fac_val by family (R2 / R1 / base): **SQL 0.901 / 0.818 / 0.809** (n 902), shell 0.938 / 0.907 / 0.906 (1,509),
git 0.919 / 0.907 / 0.899 (1,432), python 1.000 / 0.986 / 0.979 (140). Temperatures: R2 1.60, R1 1.60, base 1.55.

## Reading
- The regenerated real-domain factory data (55,469 executed rows, 15% of the mix) is the strongest lever measured this
  week: +4.1 pts on held-out factory items (+9.2 on SQL) and −57% confident errors after refit, with git_long
  +2.0 over base (CI > 0) and confident errors there −30%, and no guard regression.
- Caveat: fac_val comes from the same generators as the training rows (fresh seeds, firewalled floors), so it is
  in-distribution. The out-of-distribution check is the neutral suite (real agent actions, AgentWorldBench), next.
- Watch: fresh families −0.8 (CI across 0) and their ECE 0.067 vs 0.047; latent −0.9 vs R1.
