# V43, round 2: train on the model's own errors

Written on 2026-10-03 before any round-2 item was answered (research plan, criteria fixed in advance). Runs only if no
round-1 run meets `PLAN_v43_calibration.md`.

## Question

The release model is confidently wrong on 2–3% of the items of the families it was trained on. Does training on its own
errors, mined from new items of those families, cut the confident errors without losing accuracy, and does the gain
reach the families it never saw?

## Mining

New items (`mine_collect.py`): the 7 training families, their trained question types only, 1 to 3 actions, 800 per
cell, seed string `mine-<family>-<question type>-<actions>-20261003`. The never-seen families and the held-out question
types are never mined, and no test item is used, so they stay clean tests. Every item is answered by the release model;
the simulator gives the truth.

## Runs (one GPU each; identical except the mined items they add)

Each continues the released adapter (`sw_v42/ckpt_400`) for 300 steps with the V42 recipe (batch 8, learning rate 1e-5,
JEPA 3, the V42 mix), plain cross-entropy, with the mined items as their own kind at 30% of every batch (the other kinds
scaled by 0.7):

- **r2conf**: the items it got wrong with a confidence of 0.9 or more;
- **r2err**: every item it got wrong;
- **r2hard**: every item it got wrong, plus as many items it got right with a confidence below 0.9.

## Evaluation

As in round 1 (the trainer's readout; `git3_test_known`, `git3_test_held`, `multi_test_testfam`, `ftest_family`, the
15,008 items of the confident-errors test), against round 1's V42 baseline.

## A run succeeds if, against V42

- confident errors (wrong answers at 0.9 or more, per 100 answers) drop by at least 40% in group T and do not rise in
  groups U and H;
- accuracy holds: git3 (known and held pooled) and `multi_test_testfam` changed answers within 0.5 points or better;
- the share of wrong answers at 0.9 or more does not rise, and AUROC is not lower by more than 0.005.
