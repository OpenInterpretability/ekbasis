# Recalibrating Ekbasis' confidence: a pre-registered test

> This test was run on V42, the first release candidate of Ekbasis-27B and the model the paper *Look When Unsure*
> studies; "the release" below means V42. The released Ekbasis-27B is the interpolation of V42 and r4a
> (`RELEASE_EVAL.md` at the root).

Pre-registration: [`PREREG_recalibration.md`](../../PREREG_recalibration.md), written before any item was answered. Every
method was fit on the fit set only (4,998 new world items and the 774 git validation items) and measured on the
15,008 items of the confident-errors test and on the git test splits. All answers, with every option's probability, are
in `answers.jsonl`.

## Result: not adopted

No method met all three conditions. Every one made the [0.9, 0.99) band honest in both groups, and Platt scaling and
isotonic regression halved the calibration error, but each raised the git guard's false alarms at the 0.2 threshold by
more than the 1 point the plan allowed. Per the plan, the release keeps temperature 1 with its confidence bands
documented, and the fix moves to training (V43).

| | ECE | [0.9, 0.99): said / right, trained families | Same, never seen | Wrong answers at ≥ 0.9, trained | Same, never seen | AUROC | Guard at 0.2 (git3 held): work-losing flagged / false alarms |
|---|---|---|---|---|---|---|---|
| Temperature 1 (the release) | 0.049 | 97.1% / 84.7% | 96.5% / 85.5% | 59.1% | 27.7% | 0.918 | 97.6% / 2.4% |
| M1 one temperature | 0.027 | 96.7% / 97.1% | 96.2% / 96.9% | 31.9% | 10.4% | 0.921 | 97.6% / 4.8% |
| M2 temperature from features | 0.027 | 96.4% / 97.3% | 96.1% / 97.0% | 29.8% | 9.9% | 0.920 | 97.6% / 4.8% |
| M3 Platt scaling | 0.019 | 96.4% / 97.1% | 96.1% / 97.4% | 27.5% | 7.6% | 0.918 | 100.0% / 4.8% |
| M4 isotonic | 0.010 | 97.1% / 97.0% | 96.5% / 97.3% | 24.3% | 6.4% | 0.917 | 100.0% / 11.9% |

- **The band**: at temperature 1 the answers in [0.9, 0.99) say about 97% and are right about 85%; after any of the
  four maps, said and right agree within a point in both groups.
- **Confident errors** drop (trained families 59.1% → 27.5% with Platt
  scaling, never seen 27.7% → 7.6%), but the gap between the
  two groups stays: a map of confidence cannot tell familiar from unfamiliar worlds.
- **What failed**: the guard's false alarms on the 42 safe "will it lose work?" questions of git3 held went
  from 2.4% to 4.8% (one more command) with temperature or Platt
  scaling and to 11.9% with isotonic regression; Platt and isotonic also flagged the one
  work-losing command that temperature 1 misses (97.6% → 100%). One item is 2.4 points here: the
  condition was strict for this sample, and it is kept as written.
- **Transfer**: fit on the trained families only, the never-seen families' band stays within 3 points with one
  temperature (96.3% said, 96.1% right) and Platt scaling
  (96.1% / 97.1%); the feature temperature drifts
  (96.2% / 93.4%).

## Exploratory (not pre-registered)

Re-tuning the guard threshold on the git validation split to keep its false-alarm rate does not restore it on the test
split: the validation split has only 48 "will it lose work?" items, too few to set a
threshold. A future test with a larger git guard set could adopt Platt scaling together with a re-tuned guard threshold.
For reference, the fitted maps: one temperature 1.488; Platt scaling
a = 0.757, d = -0.673 on the log-odds of the chosen answer's confidence.

## Files

`answers.jsonl` (23,885 answers with every option's probability), `report.json` (the pre-registered analysis),
`guard_retune.json` (the exploratory check); code: `recalib_collect.py`, `recalib_fit.py`.
