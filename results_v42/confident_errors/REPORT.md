# Confident errors in familiar worlds: a pre-registered test

Pre-registration: [`PREREG_confident_errors.md`](../../PREREG_confident_errors.md), written on 2026-10-03 before any
item was generated or answered (its SHA-256 is in `PREREG_sha256.txt`). V42, then the release weights of Ekbasis-27B (bf16; the first release candidate, the model the paper *Look When Unsure* studies), answered
15,008 new questions, one prompt per question, about the state after 1 to 3 actions, in
12 world families: 7 it was trained on and 5 it never saw.

## Result: confirmed

Among wrong answers, the share given with a confidence of 0.9 or more is **58.1%** in the families it was
trained on and **27.8%** in the families it never saw: 30.3 points apart (95% interval
24.0 to 36.5, items resampled within each family). The family medians agree (60.9%
against 25.8%, families with at least 10 wrong answers). On the answers the actions change:
62.0% against 21.6% (40.4 points, interval 32.8 to 48.1).

| | Answers | Wrong | Error rate | Wrong answers at confidence ≥ 0.9 | Wrong answers below 0.7 | Median confidence of wrong answers | AUROC (right vs wrong) |
|---|---|---|---|---|---|---|---|
| Trained families, trained question types | 7,172 | 344 | 4.8% | 58.1% | 21.2% | 0.94 | 0.92 |
| Trained families, the question type held out of training | 2,472 | 334 | 13.5% | 37.1% | 38.9% | 0.79 | 0.89 |
| Families never seen in training | 5,364 | 798 | 14.9% | 27.8% | 44.9% | 0.75 | 0.91 |

## What it means

- In the worlds it knows, Ekbasis errs rarely, but more than half of its errors come with high confidence; in worlds it
  never saw it errs more often, and most errors come flagged. Its confidence still ranks right answers above wrong ones
  about equally well in both (AUROC 0.92 and 0.91): what moves with
  familiarity is the scale, not the ranking.
- So a fixed threshold misses more errors in the worlds it knows. This is why "look when unsure" also checks the
  forecast now and then (the checks find the errors a fixed threshold misses), and why a threshold tuned on one world does not
  transfer to another.
- A known family asked a question type it was never trained on falls in between (37.1%):
  the familiarity of the question counts too.

## Per family

| | Answers | Wrong | Error rate | Wrong answers at confidence ≥ 0.9 | Wrong answers below 0.7 | Median confidence of wrong answers | AUROC (right vs wrong) |
|---|---|---|---|---|---|---|---|
| T · crafting | 720 | 12 | 1.7% | 75.0% | 16.7% | 0.98 | 0.89 |
| T · grid | 1,440 | 170 | 11.8% | 66.5% | 18.8% | 0.96 | 0.83 |
| T · containers (jugs) | 1,080 | 49 | 4.5% | 65.3% | 14.3% | 0.94 | 0.95 |
| T · sequences | 1,080 | 23 | 2.1% | 56.5% | 17.4% | 0.94 | 0.89 |
| T · lamps (toggles) | 720 | 52 | 7.2% | 40.4% | 26.9% | 0.86 | 0.94 |
| T · counters | 1,080 | 37 | 3.4% | 32.4% | 35.1% | 0.79 | 0.96 |
| T · gravity (fewer than 10 wrong) | 1,052 | 1 | 0.1% | 0.0% | 100.0% | 0.56 | 1.00 |
| U · timers | 1,044 | 34 | 3.3% | 61.8% | 8.8% | 0.94 | 0.95 |
| U · track | 1,080 | 277 | 25.6% | 32.5% | 36.8% | 0.80 | 0.77 |
| U · tally | 1,080 | 31 | 2.9% | 25.8% | 45.2% | 0.75 | 0.97 |
| U · machines | 1,080 | 193 | 17.9% | 25.4% | 51.3% | 0.69 | 0.91 |
| U · card orderings | 1,080 | 263 | 24.4% | 20.5% | 53.2% | 0.67 | 0.90 |
| H · gravity (fewer than 10 wrong) | 360 | 5 | 1.4% | 80.0% | 0.0% | 0.98 | 0.93 |
| H · sequences (fewer than 10 wrong) | 360 | 7 | 1.9% | 71.4% | 0.0% | 0.97 | 0.97 |
| H · containers (jugs) | 360 | 27 | 7.5% | 66.7% | 29.6% | 0.97 | 0.94 |
| H · crafting | 360 | 21 | 5.8% | 57.1% | 19.0% | 0.92 | 0.93 |
| H · grid | 312 | 77 | 24.7% | 48.1% | 18.2% | 0.90 | 0.86 |
| H · lamps (toggles) | 360 | 122 | 33.9% | 29.5% | 44.3% | 0.76 | 0.79 |
| H · counters | 360 | 75 | 20.8% | 16.0% | 66.7% | 0.56 | 0.78 |

## Robustness (exploratory, not pre-registered)

- **Answer format.** Yes/no questions: 61.3% against 41.2%; questions
  with options: 55.6% against 19.9%.
- **Difficulty.** Grouping the (family, question type, actions) cells by error rate, the familiar side has more confident
  errors in every band: under 5% errors 47.9% against 35.7%
  (14 wrong answers on the unfamiliar side), 5–15% 63.9% against
  43.0%, 15% or more 54.3% against 24.7%.
- **One family at a time.** Leaving any one family out, the difference stays between 22.2 and 33.5 points.
- **Families as the unit.** A logistic regression of "confident" among the 1,142 wrong answers on familiarity,
  the cell's error rate and the answer format gives odds 2.4 times higher in familiar worlds; resampling
  whole families (12 of them), the 95% interval of that coefficient is -0.35 to
  1.63 and includes zero. Two families go against the pattern (timers, never
  seen, 61.8%; counters, trained, 32.4%).
  It is a strong tendency of this model over these families, not yet a law across world families.

## Follow-up: Eikos-27B, the same model before consequence training

Pre-registration: [`PREREG_confident_errors_eikos.md`](../../PREREG_confident_errors_eikos.md), written before Eikos-27B
answered any item. Eikos-27B never saw any of the 12 families, so if the gap belonged to the families it would show it
too. Same 15,008 items, same serving and readout, same calibration (temperature 1); predictions in `eikos27b/`.

### Result: training made it

| | Error rate, trained families | Error rate, never seen | Wrong answers at confidence ≥ 0.9, trained families | Same, never seen | Gap |
|---|---|---|---|---|---|
| Eikos-27B (before) | 14.4% (1,035) | 21.3% (1,141) | 1.9% | 0.5% | 1.4 points |
| Ekbasis (after) | 4.8% (344) | 14.9% (798) | 58.1% | 27.8% | 30.3 points |

The difference between the gaps is 28.9 points (95% interval 22.8 to 34.9, paired bootstrap):
above the pre-registered 15 points. Before consequence training the model almost never erred with confidence, in either
kind of family. Consequence training cut its errors on the families it learned (14.4% → 4.8%) and
on the ones it never saw (21.3% → 14.9%), and it made the remaining errors confident: by
56.2 points in the families it trained on (interval 50.8 to
61.5) and by 27.3 points in the others
(24.3 to 30.4). Both models rank right answers above
wrong ones about equally well (AUROC: Eikos-27B 0.90 and 0.90; Ekbasis
0.92 and 0.91).

### On each model's own scale (exploratory, not pre-registered)

Eikos-27B rarely reaches 0.9 at all (the median confidence of its wrong answers is 0.57),
so a fixed threshold also measures its overall scale. Setting the threshold at each model's own right answers: the
share of wrong answers as confident as 90% of the model's right answers is 42.4% against
33.6% for Eikos-27B (gap 8.8) and 48.0% against
19.7% for Ekbasis (gap 28.3); as confident as 75% of them,
6.4 against 11.0 points. The families it was later trained on were already
somewhat more prone to errors that look like right answers; consequence training widened that gap and, above all,
moved the whole scale up.

### What it means

The training that makes a world model more accurate also makes its remaining errors confident, most of all where it
trained. The base model errs about three times as often on the trained families (14.4% against 4.8%)
but almost never with confidence, so a threshold flags nearly all of its errors along with many right answers; the
trained model errs far less, and a fixed threshold misses more of its errors. This is why "look when unsure" also
checks now and then, and a target for the next training round: keep the errors uncertain while accuracy rises.

## Deviations from the plan

- Nine cells could not reach 120 items (96 to 112): grid "moved", gravity "full" and timers "n_done" (allowed by the plan).
- A pipeline test of 251 items (2 per cell, same generator) ran before the main run; its answers are not used.

## A note added after the run (2026-10-04)

When the training data was packaged for release (`caiovicentino1/ekbasis-data`), every test item was compared with the
training rows. 88 of the 15,008 items (all of the sequences family, 73 of them one action long, all in group T) have the
same prompt and question as a training row, with the same answer: small worlds repeat by chance across seeds. The model
answered all 88 right. Without them nothing reported above moves except group T's error rate (4.8% → 4.9%): 344 wrong
answers, 58.1% of them at a confidence of 0.9 or more; groups H and U have none of them. The pre-registered analysis is
left as it ran.

**Correction (2026-10-06).** Counting the training data's multi-question and reading rows too, 104 items (all of the
sequences family, group T, all answered right) share the prompt and the question with a training row. An audit with
near-duplicate rules then found that 5,318 items overlap V42's training rows: 173 identical prompts and 5,145 near
duplicates (4,101 of 7,172 in T, 1,217 of 2,472 in H, none in U), mostly the same family template rather than the
same item. Without them, with the same scripts: 50.5% against 27.8%, 22.7 points apart (95% interval 12.6 to 32.5),
family medians 62.5% and 25.8%: confirmed. Eikos-27B: 1.8% and 0.5%; the difference between the gaps, 21.4 points
(10.6 to 31.4): training made it. Without only the 104 items nothing above moves (30.3 points, 23.9 to 36.5; the
difference 28.9, 23.2 to 34.9). Details: [`results/overlap_audit/`](../../results/overlap_audit/README.md).

## Files

`items.jsonl` (the questions), `preds.jsonl` (every answer, its confidence, right or wrong, changed or not),
`report.json` (the pre-registered analysis), `exploratory.json` (the checks above); `eikos27b/` (the follow-up: predictions, `compare.json`, `report.json`, `relative_scale.json`).
