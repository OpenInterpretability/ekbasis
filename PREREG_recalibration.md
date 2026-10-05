# Pre-registration: recalibrating Ekbasis' confidence

Written on 2026-10-03, before any item of this test was answered. Its SHA-256 is recorded in `PREREG_sha256.txt` before
the run.

## Why

On the 15,008 questions of the confident-errors test, the release model is well calibrated at the top and overconfident
in the middle: answers at 0.99 or more say 99.8% and are right 99.2%; at 0.9 to 0.99 they say 96.7% and are right 84.3%;
at 0.7 to 0.9, 81.6% against 61.3%. Its wrong answers are more confident in the world families it was trained on.
Recalibration rescales the confidence without changing which answer is chosen; this test checks whether it makes the
numbers honest, everywhere.

## Data

- **Fit set** (used to fit every method, and for nothing else):
  - new world items made with `worldgen.fbalanced(..., change_balance=True)`, every family and question type, 1 to 3
    actions, 40 items per cell, seed string `calib-<family>-<question type>-<actions>-20261003` (never used before);
  - `git3_val` (774 items), the git validation split.
- **Test sets**: the 15,008 items of `PREREG_confident_errors.md` (groups T, H, U), `git3_test_known` and
  `git3_test_held`.
- **Model**: the release weights (`merged_v42`) through the System One API at temperature 1, one prompt per question;
  the full probability of every option is recorded.

## Methods

- **M1** one temperature for every question;
- **M2** a temperature from the question's features, `T(x) = exp(b + w·f)` (prompt length, number of options, yes/no),
  as the serving code already supports;
- **M3** Platt scaling of the chosen answer's confidence (two parameters on its log-odds);
- **M4** isotonic regression of the chosen answer's confidence.

M1 and M2 are fit by the negative log-likelihood of the right option, M3 by the log loss of "the chosen answer is
right", M4 by pool-adjacent-violators; all on the fit set only. A second fit of each method on the trained families
only (T and H, plus git) is evaluated on the never-seen families, as a transfer check.

## Measures (on each test set; on the 15,008 items also per group)

ECE (15 equal-width bins of the chosen answer's confidence); Brier score; accuracy against mean confidence in the bands
[0.7, 0.9), [0.9, 0.99) and [0.99, 1]; the share of wrong answers at 0.9 or more; AUROC; on `git3_test_held` "will it
lose work?", the work-losing commands flagged at a probability of 0.2 and the false alarms.

## Decision

A method **fixes it** if, on the 15,008 items, its ECE is at most half of the ECE at temperature 1, the answers it puts
in [0.9, 0.99) are right within 3 points of their mean confidence in both groups T and U, and on `git3_test_held` it
neither lowers the work-losing commands flagged at 0.2 by more than 1 point nor raises the false alarms by more than
1 point. The simplest method that fixes it is adopted for the release (M1 and M2 through `calib.json`; M3 and M4 need a
small change in the serving code), and the release evaluation is run again with it before anything is published. If
none fixes it, the release keeps temperature 1 with the confidence bands documented, and training (V43) is the way.

## Reporting

Every answer with its full distribution is saved (`results/recalibration/`). Deviations are listed in the report.
