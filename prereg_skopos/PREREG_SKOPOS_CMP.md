# Skopos × R2 × base, head to head (pre-registration, 2026-10-15 ~12:40 UTC, before any Skopos score here)

## Why
Caio asked whether R2 can be released as the Ekbasis-Skopos model. R2 was trained from the public Ekbasis-27B and was
never compared with the private Skopos (caiovicentino1/Ekbasis-Skopos-27B, HEAD 1e48ae09a3 = v49f_w50), which already
had F factory + FX real data, and which in V52s (13/10) flagged 97.57% of losses at 0.2 on guard_known vs 95.71% here
for the public base.

## What runs (same trainer, same readout, SAVE_PROBS, RTX PRO 6000)
Skopos as the base model (MODE=eval_base) on: fac_val, git_long, git_long_val, fhorizon, latent_test, git3_test_known,
git3_test_held, guard_known, ftest_family, m3val, fval_git3, sess_val; then awb_neutral (EVAL_BS 6). R2/base already
scored on the same files.

## Rule (paired bootstrap 2,000, seed 20261015)
- **R2 replaces Skopos as the release candidate** if no suite has R2 − Skopos < −0.01 with CI entirely below 0,
  guard_known losses flagged at 0.2 are not lower by more than 1 point and false alarms not higher by more than
  1 point, and R2 − Skopos ≥ +0.01 with CI > 0 on at least one of fac_val / git_long / git_long_val.
- Otherwise **Skopos stays the candidate** and the next arm is R2's recipe trained on top of Skopos (pre-registered
  separately before it runs).
- Reported regardless: everything per suite, refit calibration, the neutral suite.
