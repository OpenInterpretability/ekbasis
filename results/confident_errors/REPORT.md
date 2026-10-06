# Confident errors in familiar worlds: the release

The pre-registered test ([`PREREG_confident_errors.md`](../../PREREG_confident_errors.md)) was run on V42, the first
release candidate: its report, confirmed, is [`results_v42/confident_errors/REPORT.md`](../../results_v42/confident_errors/REPORT.md).
Here the same 15,008 questions (one prompt per question, the state after 1 to 3 actions, 12 world families: 7 trained
and 5 never seen) were answered by the release weights, served the same way, and the same analysis was applied
unchanged (`confident_errors_analyze.py`, `confident_errors_compare.py`). For the release this is a measurement, not a
pre-registered test.

## Result

Among wrong answers, the share given with a confidence of 0.9 or more: **48.4%** in the families it was
trained on and **25.1%** in the families it never saw, 23.3 points apart (95% interval
16.8 to 30.1, items resampled within each family). V42: 58.1% and 27.8%,
30.3 points apart.

| | Answers | Wrong | Error rate | Wrong answers at confidence ≥ 0.9 | Wrong answers below 0.7 | Median confidence of wrong answers | AUROC (right vs wrong) |
|---|---|---|---|---|---|---|---|
| Release · Trained families, trained question types | 7,172 | 306 | 4.3% | 48.4% | 23.5% | 0.89 | 0.94 |
| Release · Trained families, the question type held out of training | 2,472 | 291 | 11.8% | 34.0% | 37.8% | 0.79 | 0.89 |
| Release · Families never seen in training | 5,364 | 801 | 14.9% | 25.1% | 49.6% | 0.71 | 0.91 |
| V42 · Trained families, trained question types | 7,172 | 344 | 4.8% | 58.1% | 21.2% | 0.94 | 0.92 |
| V42 · Trained families, the question type held out of training | 2,472 | 334 | 13.5% | 37.1% | 38.9% | 0.79 | 0.89 |
| V42 · Families never seen in training | 5,364 | 798 | 14.9% | 27.8% | 44.9% | 0.75 | 0.91 |

Confident errors per 100 answers (wrong at ≥ 0.9): trained families 2.06 (V42 2.79),
held-out question types 4.00 (5.02), never-seen families 3.75
(4.14).

## Against Eikos-27B, the same model before consequence training

| | Error rate, trained families | Error rate, never seen | Wrong answers at confidence ≥ 0.9, trained families | Same, never seen | Gap |
|---|---|---|---|---|---|
| Eikos-27B (before) | 14.4% (1,035) | 21.3% (1,141) | 1.9% | 0.5% | 1.4 points |
| V42 | 4.8% (344) | 14.9% (798) | 58.1% | 27.8% | 30.3 points |
| Release | 4.3% (306) | 14.9% (801) | 48.4% | 25.1% | 23.3 points |

The difference between the release's gap and Eikos-27B's: 21.9 points (95% interval 15.5 to
28.1, paired bootstrap; V42: 28.9).

## What it means

- In the families it was trained on, the release errs less (4.27% against 4.80%), and fewer of its errors come with a
  confidence of 0.9 or more (48.4% against 58.1%): confident errors per 100 answers fall from 2.79 to 2.06 (−26%).
- The gap between trained and never-seen families is 23.3 points (95% interval 16.8 to 30.1), against V42's 30.3:
  training on the model's own errors and interpolating reduced the effect without removing it.
- Its confidence still ranks right answers above wrong ones about equally well in both kinds of families (AUROC 0.94
  and 0.91).
- So the advice stands: look when unsure, and keep the checks (the client's default), because in the worlds it knows
  its remaining errors can still come with confidence.

## Correction (2026-10-06): overlap with the training data

An audit after publication found that 5,378 of the 15,008 questions (4,151 of 7,172 in the trained families, 1,227
of 2,472 with held-out question types, none in the never-seen families) repeat or nearly repeat a row of the
release's training lineage (V42's file and r4a's two mined sets): 174 identical prompts and 5,204 near duplicates,
mostly the same family template rather than the same item. Without them, with the same analysis: 50.0% against
25.1%, 24.9 points apart (95% interval 13.3 to 35.8); accuracy in the trained families 97.1% (V42 96.8% on the same
questions); confident errors per 100 answers 1.46 against V42's 1.69 (−14%, against −26% on all questions). The
conclusion stands: fewer, not gone. Details: [`results/overlap_audit/`](../../results/overlap_audit/README.md).
