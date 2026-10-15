# Confirmation: is R4's ftest_family loss real? (pre-registration, 2026-10-15 ~17:45 UTC, before any fresh item exists)

## Why
R4's release read failed one criterion: ftest_family, answers the actions change, 80.29% vs the release's 81.88%
(−1.59, paired CI [−3.66, +0.48], n 629). Caio chose "confirm and prepare" (15/10).

## Items
`scripts/gen_ftest_fresh.py`: the exact ftest_family recipe (worldgen TEST families Cards/Timers/Machines, every
question type, 1/2/3 actions, fbalanced, no change balance) at 200 per cell (5× the original 40), seed string
'ftest-fresh-20261015', firewalled against every data file on the RTX.

## Models (trainer readout; served = trainer on 499/500 items)
Current public release (caiovicentino1/Ekbasis-27B, bf16) and R4 merged (/root/Skopos-R4-27B), both MODE=eval_base.

## Reading (paired bootstrap 2,000, seed 20261015)
On the answers the actions change (known0 and gold0 ≠ gold): **the loss is not confirmed if R4 − release ≥ −1.0
point** (the release criterion itself, on a 5× fresh sample); confirmed if below. Reported: all answers, per family,
per number of actions. If confirmed, R4 does not go to release as is (a fix is designed on validation first).
