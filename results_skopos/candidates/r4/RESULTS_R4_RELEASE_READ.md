# R4 release read (PREREG_R4_RELEASE_READ.md) — 2026-10-15 17:25 UTC

R4 merged into Ekbasis-Skopos-27B (bf16), served exactly as production (vLLM + serve.py). Served = trainer on 499/500
items (equivalence check). Reference: the current public release's own served predictions, same comparison code
(self-test reproduces RELEASE_EVAL.md exactly).

**Verdict: 8 of 9 criteria pass; fails ftest_family (answers the actions change) by 0.59 beyond the 1-point limit.**

| Criterion | R4 | current release | |
|---|---|---|---|
| git v3 known + held | 96.94% | 96.62% | pass |
| never-trained worlds, changed answers, one prompt per question | 81.51% | 81.16% | pass |
| same, read-once | 78.68% | 78.03% | pass |
| ECE git v3 (10 / 15 bins) | 0.023 / 0.024 | 0.024 / 0.024 | pass |
| guard larger set, known: flagged / false alarms (of 863) | 837 / 27 | 828 / 37 | pass |
| guard larger set, held-out: flagged / false alarms (of 799) | 776 / 26 | 767 / 49 | pass |
| ftest_family, changed answers | 80.29% | 81.88% | **FAIL** (−1.59, paired CI [−3.66, +0.48]; 27 lost / 17 gained of 629; cards 146 vs 153, timers 195 vs 199, machines 164 vs 163) |

Reported: multi trainfam changed 95.01 / 93.90 (release 92.35 / 91.46); ftest all answers 83.15 vs 83.33; guard
fails questions right: known 2654 vs 2602 of 2760, held 4152 vs 3989 of 4796. T3c not run (needs the rig).

Same shape as Skopos on 7 Oct (multi −0.71, CI across 0, kept private by Caio). Decision is Caio's.

## Confirmation of the ftest_family criterion (CONFIRM_FTEST.md, 18:00 UTC)
On 5,385 fresh never-trained-family items (5× the original; 3,014 changed answers), R4 vs the current release:
changed answers 83.38 vs 81.75 (**+1.63 [+0.70, +2.52]**), all answers 85.81 vs 84.23 (+1.58 [+0.91, +2.19]); cards
+1.8 [−0.1, +3.5], machines +3.2 [+1.3, +5.1], timers −0.1 [−1.2, +1.0]. **The loss is not confirmed** (rule: below
−1.0): the −1.59 of the 629-item set was sampling noise. With it, every release criterion holds.
