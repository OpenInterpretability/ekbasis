# V50 pilot (V50P) — do plan-level items teach Ekbasis long horizons? (pre-registration)

Written 2026-10-14 before any training. Sealed by SHA-256 in `SEAL.txt`. One arm, a pilot for PLAN_v50_draft §1 (the
H-JEPA "higher level predicts further ahead" idea); not a release candidate by itself.

## Why
Ekbasis' training forecasting items have **1–3 actions only** (ftrain_mixG3). Measured 14/10 (LATENT): forecasting
from text falls from 0.93 at 1 action to 0.64 at 10 while reading the true state stays at 0.98. Plan-level items
(long action sequences, label from the true final state, the JEPA term pulling the floor latent to the teacher's latent
on the final state) target exactly that gap.

## Base, data, recipe (frozen)
- **Base:** `caiovicentino1/Ekbasis-27B` (bf16; the served INT4 is quantized from it), its `decision_core.py`.
- **Train file:** `data/ftrain_v50p.jsonl` = the public lineage mix `ftrain_mixG3` (caiovicentino1/ekbasis-data) +
  **4,335 `floorPL` items**: 4/5/6/8/10/12/16 actions in the 7 training families (worldgen TRAIN) and factory 3
  (m3balanced, held pairs excluded), seed 4501, change-balanced, firewalled against the test (0 overlaps).
- **Mix (V42's shares × 0.85 + floorPL 0.15):** floorG3 0.2975, floorG2 0.085, floorG 0.0425, multi 0.1275, floor
  0.085, floor3 0.0595, read 0.034, replay 0.119, floorPL 0.15.
- **Recipe:** the lineage's (recipes.json "common"): new LoRA rank 64 (alpha 128) on every linear layer; cross-entropy on
  the letter readout + JEPA weight 3, layers 16/32/48/64, end of the evidence (teacher = the base with the adapter off,
  reading the ceiling prompt). LR 1.5e-5, batch 8 (micro 4), **600 steps**, seed 2; the trainer is
  `mission/F/v50/train_conseq_v50.py` unchanged except paths. The final step is the candidate (no selection on test).
- **Not available off the rig** (stated as a limit): F's factory data, the V46/V49 anchors, FX. A full V50 would use them.

## Measures (base vs candidate, both bf16, same vLLM + serve.py, same prompts)
- **M1, primary — horizon test** `data/fhorizon.jsonl` (built exactly as conseq/gen_horizon.py: seed 81, training
  families, new worlds; 1/2/3/5/8/12/20 actions, ~200 each). Accuracy by length.
- **M2 — LATENT text forecast** (mission/LATENT/data.jsonl test split; worlds Ekbasis never trained on): accuracy at
  k = 1, 3, 5, 10, predictor-worlds and held-out-worlds groups.
- **M3 — no regression** on the public suites: git3_test_known, git3_test_held, guard_known, ftest_family, m3val,
  fval_git3, multi_test_testfam (accuracy; paired by item).
- **M4 (reported) — latent readout** (LATENT D1 recipe, L32 and L48 last token) on the candidate vs 0.689 (base).

## Decision rule (paired bootstrap by item, 2,000 resamples, seed 20261014)
- **Promising** if (a) M1 long accuracy (8, 12 and 20 actions pooled) improves by **≥ +3 points with the 95% CI
  above 0**, and (b) no M3 suite drops by more than 1.0 point with its CI entirely below 0.
- If (a) holds and (b) fails: report; the full V50 would need its anchors/replay (and WiSE λ on validation).
- Else: not promising; the plan-level idea needs the full data and arms, or is dropped.
- Predictions: (a) likely holds at 8–12 actions (in-distribution families, trained lengths), weaker at 20 (never
  trained); M2 uncertain (other worlds); M3 small drops possible (no anchors).

Nothing public without Caio's approval.
