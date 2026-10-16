# V50R1 — plan-level items in the real domain (git) + temperature refit (pre-registration)

Written 2026-10-15 ~01:10 UTC, before any R1 training or score. Sealed in `SEAL.txt`.

## Why (measured, mission/V50P)
- Dose (synthetic plan-level 30%, 1,200 steps) passed its rule on synthetic horizons (+0.040) but did **not** transfer to
  real git sequences of 5–12 commands (+0.007, CI across 0).
- Scarce-axis audit of the current model: reading the true state is 0.99–1.00 everywhere; predicting is the gap. The
  riskiest cell is **real long git: 6.7 confident errors (wrong at ≥ 0.9) per 100**, twice the other suites;
  "fails" and "lost" are the weak question types. The dose model was also more confident (ECE up).

## Arm R1 (frozen)
- Base `caiovicentino1/Ekbasis-27B`; trainer, LoRA r64, JEPA 3 (16/32/48/64, ev), LR 1.5e-5, BS 8 (micro 4), seed 2,
  MULTI_STYLE turns, **1,200 steps** — as the dose.
- Train file: `ftrain_v50p` (lineage mix + synthetic floorPL) + **`git_plan_train` (kind floorPLG)**: real git
  sequences of 4/5/6/8/10/12/16 commands, executed by gitbox3 for exact answers, seeds 9000+, firewalled against the
  git_long test (seeds 7000+) and every git3/guard test floor.
- **Mix: V42 shares × 0.70 + floorPL 0.15 + floorPLG 0.15.**
- Evaluation with every option's probability saved (SAVE_PROBS=1) on: git_long, fhorizon, latent_test, git3 known/held,
  guard_known, ftest_family, m3val, fval_git3, multi_test_testfam. Base predictions: re-scored the same way.

## Temperature refit (part of the arm)
One global temperature T for the candidate (and, separately, for the base), fitted only on validation (fval_git3 +
m3val) by NLL of the gold option; applied to every test suite. Reported before and after: ECE and confident errors
(wrong at ≥ 0.9) per 100.

## Decision rule (paired bootstrap by item, 2,000, seed 20261014)
- **Primary (real domain):** git_long accuracy (all lengths) R1 − base **≥ +0.03 with CI above 0**, **or** confident
  errors on git_long cut by **≥ 30%** after both are refit (the lower one counts only if accuracy is not below base).
- **Guards:** no M3 suite drops by more than 1 point with CI entirely below 0; synthetic long (fhorizon 8/12/20)
  not below base (CI not entirely below 0).
- Pass → R1's recipe is the V50 core; then F factory data, consistency/SIGReg arms and the release gates.
- Prediction: git_long gain at 8–16 commands likely (in-domain now); confident errors down after refit; small or no
  effect on synthetic horizons vs the dose.
