# V50R4 — R2's recipe trained on top of Skopos (pre-registration, 2026-10-15 13:55 UTC)

## Why (PREREG_SKOPOS_CMP verdict, 13:50 UTC)
R2 does not replace Skopos: guard_known losses flagged at 0.2 Skopos 97.45% vs R2 95.37% (−2.08, tolerance −1);
false alarms 4.29 vs 4.87. R2 gains only on git: git_long_val +2.4 [+1.4, +3.5], git_long +1.3 [−0.1, +2.8].
Everything else level (fac_val 0.925 both). The natural combination: Skopos' weights (its guard sensitivity) plus
R2's data (real long-git plan items, regenerated factory, synthetic plan items).

## Arm R4 (frozen)
Base `caiovicentino1/Ekbasis-Skopos-27B` @ 1e48ae09a3 (v49f_w50), new LoRA; everything else identical to R2: train
file ftrain_r2, mix V42 shares × 0.55 + floorPL 0.15 + floorPLG 0.15 + floorRX 0.15, LoRA r64, JEPA 3 (16/32/48/64
ev), LR 1.5e-5, BS 8 (micro 4), seed 2, turns, 1,200 steps.

## Rule (same as PREREG_SKOPOS_CMP, with Skopos as the reference; paired bootstrap 2,000, seed 20261015)
**R4 replaces Skopos as the release candidate** if no suite has R4 − Skopos < −0.01 with CI entirely below 0,
guard_known losses flagged at 0.2 are not lower than Skopos' by more than 1 point and false alarms not higher by more
than 1 point, and R4 − Skopos ≥ +0.01 with CI > 0 on at least one of fac_val / git_long / git_long_val.
Reported: all suites, neutral AUROC, refit calibration. Prediction: git gains of R2 mostly kept (+1 to +2.5 on git
val), guard flagged within 1 point of Skopos.
