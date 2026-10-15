# Addendum DOSE — more plan-level data and steps (written 2026-10-14 ~21:30 UTC, after the pilot's results)

Pilot result: long (8/12/20) +0.025 [+0.002, +0.047], below +0.03; no regression; 20 actions +0.061; M4 unchanged.
Question: does the gain grow with the dose? **Arm D:** identical to the pilot (base, data files, recipe, seed 2,
MULTI_STYLE turns, trainer) except **MIX = V42 shares × 0.70 + floorPL 0.30** and **STEPS = 1200** (floorPL draws
≈ 2,880 vs 720 in the pilot). The final step is the candidate. Base predictions are the pilot's (same base, same
splits, same code). Same analysis script (`analyze.py`) and same rule: promising if long +0.03 with CI above 0 and no
clear drop > 1 point. Also reported: the trend pilot → D per length, and M4 (`m4.py`, adapter of D).
Mix D: floorG3 0.245, floorG2 0.07, floorG 0.035, multi 0.105, floor 0.07, floor3 0.049, read 0.028, replay 0.098,
floorPL 0.30.
