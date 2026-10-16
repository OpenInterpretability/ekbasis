# Jev vs Ekbasis-27B and Ekbasis-Skopos-27B — numbers

**Measured on 2026-10-16. Not pre-registered.** Method, items, seeds and caveats: [METHOD.md](METHOD.md). Every number here is computed by `scripts/analyze_full.py` from `items.jsonl`, `sets.json` and `preds/`; `python3 -I scripts/recompute.py` checks that it reproduces `results.json` exactly.

Jev was run with two wordings of each question (A: Ekbasis' question as it is; B: rewritten in the style of TypeSafe's docs). The headline Jev row of each set is the better of the two by a rule fixed before scoring: accuracy (git v3 sets, scorecard suites; a tie goes to A), AUROC of P(lost) (guard sets). Choosing the better of two after seeing both favours Jev slightly.

## 1. Release protocol

All rows of `git3_test_known` (1,482) and `git3_test_held` (1,623); the `lost` rows of the larger guard set, `guard_known` (863 work-losing + 863 safe) and `guard_held` (799 + 799). Same items and readout as Ekbasis-27B's `results/release_eval/` and `results/release_read_*.json`. Published systems: their per-item predictions in the ekbasis repository at 4d4e268 (no Ekbasis-27B INT4 file exists for the guard sets).

### Git v3, all question types

| system | accuracy known | accuracy held | accuracy all (3,105) | ECE all, 15 bins | ECE all, 10 bins | AUROC P(lost), all (93 + 93) |
|---|---|---|---|---|---|---|
| Jev, Ekbasis' question | 89.68% | 88.05% | 88.82% | 0.0392 | 0.0377 | 0.8970 |
| Jev, Jev-style question (headline) | 90.42% | 89.53% | 89.95% | 0.0611 | 0.0611 | 0.8692 |
| Ekbasis-27B (bf16) | 98.11% | 95.26% | 96.62% | 0.0239 | 0.0241 | 0.9949 |
| Ekbasis-27B INT4 | 97.98% | 95.01% | 96.43% | 0.0254 | 0.0254 | 0.9956 |
| Ekbasis-Skopos-27B (bf16) | 98.58% | 95.44% | 96.94% | 0.0239 | 0.0230 | 0.9974 |
| Ekbasis-Skopos-27B INT4 | 98.38% | 95.32% | 96.78% | 0.0248 | 0.0253 | 0.9972 |

Headline Jev variant: `git3_test_known` Jev, Jev-style question, `git3_test_held` Jev, Jev-style question, `git_v3_all` Jev, Jev-style question.

The release evaluation's categories, known and held together (n: lost 186, fails 366, in_progress 633, changed state 137):

| system | lost | fails | in_progress | changed state |
|---|---|---|---|---|
| Jev, Ekbasis' question | 79.0% | 74.3% | 92.9% | 57.7% |
| Jev, Jev-style question | 74.7% | 77.0% | 95.6% | 63.5% |
| Ekbasis-27B (bf16) | 97.8% | 88.8% | 98.4% | 78.8% |
| Ekbasis-27B INT4 | 97.3% | 88.3% | 98.1% | 78.8% |
| Ekbasis-Skopos-27B (bf16) | 98.4% | 90.2% | 97.2% | 84.7% |
| Ekbasis-Skopos-27B INT4 | 98.4% | 89.6% | 96.8% | 84.7% |

Accuracy by question type, known and held together:

| type | n | Jev, Ekbasis' question | Jev, Jev-style question | Ekbasis-27B (bf16) | Ekbasis-27B INT4 | Ekbasis-Skopos-27B (bf16) | Ekbasis-Skopos-27B INT4 |
|---|---|---|---|---|---|---|---|
| branch | 155 | 83.2% | 87.7% | 94.8% | 94.2% | 96.1% | 96.8% |
| clean | 293 | 76.5% | 77.1% | 94.2% | 93.9% | 95.6% | 94.9% |
| content | 303 | 92.7% | 92.1% | 97.0% | 97.0% | 98.0% | 97.7% |
| exists | 299 | 96.0% | 96.3% | 99.3% | 99.3% | 99.7% | 99.7% |
| fails | 366 | 74.3% | 77.0% | 88.8% | 88.3% | 90.2% | 89.6% |
| in_progress | 633 | 92.9% | 95.6% | 98.4% | 98.1% | 97.2% | 96.8% |
| lost | 186 | 79.0% | 74.7% | 97.8% | 97.3% | 98.4% | 98.4% |
| remote | 278 | 91.4% | 93.2% | 97.8% | 97.8% | 98.2% | 98.2% |
| staged | 268 | 95.9% | 97.4% | 98.1% | 98.1% | 98.5% | 98.9% |
| stash | 324 | 98.5% | 98.1% | 99.1% | 99.4% | 99.1% | 99.1% |

Paired differences, headline Jev minus each system (items resampled 2,000 times, seed 20261015):

| difference | known (pp) | held (pp) | all (pp) |
|---|---|---|---|
| headline Jev − Jev, Ekbasis' question | 0.74 [-0.34, 1.82] | 1.48 [0.37, 2.71] | 1.13 [0.35, 1.93] |
| headline Jev − Ekbasis-27B (bf16) | -7.69 [-9.18, -6.21] | -5.73 [-7.27, -4.13] | -6.67 [-7.70, -5.57] |
| headline Jev − Ekbasis-27B INT4 | -7.56 [-9.04, -6.14] | -5.48 [-6.96, -4.00] | -6.47 [-7.47, -5.38] |
| headline Jev − Ekbasis-Skopos-27B (bf16) | -8.16 [-9.58, -6.68] | -5.91 [-7.52, -4.31] | -6.99 [-8.08, -5.83] |
| headline Jev − Ekbasis-Skopos-27B INT4 | -7.96 [-9.45, -6.48] | -5.79 [-7.39, -4.13] | -6.83 [-7.89, -5.70] |

### Guard: "Do these commands permanently lose any uncommitted work?" (`lost` rows)

**`guard_known`** (863 work-losing, 863 safe). Headline Jev: Jev, Ekbasis' question.

| system | flagged at 0.2 | false alarms at 0.2 | AUROC | ECE, 15 bins | accuracy at 0.5 | caught at 10% false alarms | flagged at false alarms ≤ 4.3% (Ekbasis-27B's at 0.2) |
|---|---|---|---|---|---|---|---|
| Jev, Ekbasis' question (headline) | 860/863 (99.7%) | 733/863 (84.9%) | 0.8791 | 0.0863 | 79.1% | 64.9% | 45.3% (threshold 0.760, false alarms 4.3%) |
| Jev, Jev-style question | 863/863 (100.0%) | 796/863 (92.2%) | 0.8535 | 0.0857 | 76.0% | 51.4% | 33.6% (threshold 0.780, false alarms 4.3%) |
| Ekbasis-27B (bf16) | 828/863 (95.9%) | 37/863 (4.3%) | 0.9816 | 0.0282 | 95.4% | 97.6% | 95.9% (threshold 0.212, false alarms 4.3%) |
| Ekbasis-Skopos-27B (bf16) | 837/863 (97.0%) | 27/863 (3.1%) | 0.9922 | 0.0184 | 96.9% | 99.1% | 97.3% (threshold 0.060, false alarms 4.1%) |
| Ekbasis-Skopos-27B INT4 | 836/863 (96.9%) | 25/863 (2.9%) | 0.9922 | 0.0194 | 96.9% | 99.3% | 97.3% (threshold 0.064, false alarms 4.3%) |

| difference (headline Jev − system) | AUROC | flagged at 0.2 (pp) | false alarms at 0.2 (pp) |
|---|---|---|---|
| Jev, Ekbasis' question − Jev, Jev-style question | 0.0256 [0.0159, 0.0350] | -0.3 [-0.8, 0.0] | -7.3 [-9.2, -5.4] |
| Jev, Ekbasis' question − Ekbasis-27B (bf16) | -0.1025 [-0.1172, -0.0878] | 3.7 [2.4, 5.1] | 80.6 [78.0, 83.3] |
| Jev, Ekbasis' question − Ekbasis-Skopos-27B (bf16) | -0.1131 [-0.1288, -0.0981] | 2.7 [1.5, 3.9] | 81.8 [79.0, 84.4] |
| Jev, Ekbasis' question − Ekbasis-Skopos-27B INT4 | -0.1131 [-0.1290, -0.0984] | 2.8 [1.6, 4.1] | 82.0 [79.3, 84.6] |

**`guard_held`** (799 work-losing, 799 safe). Headline Jev: Jev, Ekbasis' question.

| system | flagged at 0.2 | false alarms at 0.2 | AUROC | ECE, 15 bins | accuracy at 0.5 | caught at 10% false alarms | flagged at false alarms ≤ 6.1% (Ekbasis-27B's at 0.2) |
|---|---|---|---|---|---|---|---|
| Jev, Ekbasis' question (headline) | 799/799 (100.0%) | 748/799 (93.6%) | 0.8707 | 0.0911 | 75.1% | 55.3% | 43.7% (threshold 0.720, false alarms 5.6%) |
| Jev, Jev-style question | 799/799 (100.0%) | 784/799 (98.1%) | 0.8213 | 0.0825 | 71.1% | 44.8% | 32.4% (threshold 0.730, false alarms 5.6%) |
| Ekbasis-27B (bf16) | 767/799 (96.0%) | 49/799 (6.1%) | 0.9853 | 0.0330 | 94.7% | 97.1% | 96.2% (threshold 0.173, false alarms 6.1%) |
| Ekbasis-Skopos-27B (bf16) | 776/799 (97.1%) | 26/799 (3.3%) | 0.9926 | 0.0174 | 96.9% | 99.5% | 98.7% (threshold 0.042, false alarms 6.0%) |
| Ekbasis-Skopos-27B INT4 | 778/799 (97.4%) | 25/799 (3.1%) | 0.9929 | 0.0166 | 96.6% | 99.6% | 98.9% (threshold 0.045, false alarms 6.0%) |

| difference (headline Jev − system) | AUROC | flagged at 0.2 (pp) | false alarms at 0.2 (pp) |
|---|---|---|---|
| Jev, Ekbasis' question − Jev, Jev-style question | 0.0494 [0.0368, 0.0620] | 0.0 [0.0, 0.0] | -4.5 [-6.0, -3.1] |
| Jev, Ekbasis' question − Ekbasis-27B (bf16) | -0.1146 [-0.1318, -0.0983] | 4.0 [2.8, 5.4] | 87.5 [85.1, 89.6] |
| Jev, Ekbasis' question − Ekbasis-Skopos-27B (bf16) | -0.1219 [-0.1392, -0.1049] | 2.9 [1.8, 4.1] | 90.4 [88.2, 92.2] |
| Jev, Ekbasis' question − Ekbasis-Skopos-27B INT4 | -0.1222 [-0.1394, -0.1053] | 2.6 [1.5, 3.9] | 90.5 [88.4, 92.4] |

## 2. Hosted scorecard suites

The five suites exactly as `scorecard/scorecard.py fetch` builds them at ekbasis 4d4e268 (400 + 400 + 400 + 400 + 300 items), scored with scorecard.py's `score()`: accuracy, wrong answers at confidence ≥ 0.9 per 100, Brier over the full distribution, ECE over 10 bins. The non-Jev columns are the published per-item predictions on the same rows (the release evaluations' served models, not a hosted scorecard run); their Brier is shown only where those files carry the full distribution (yes/no questions). Hosted staging runs of Ekbasis-Skopos-27B-INT4 and Ekbasis-27B-INT4 are to be added.

| suite | Jev, Ekbasis' question | Jev, Jev-style question | Ekbasis-27B INT4 | Ekbasis-Skopos-27B INT4 | Ekbasis-27B (bf16) | Ekbasis-Skopos-27B (bf16) | Ekbasis, hosted API (intent_check replay, 2026-10-11) |
|---|---|---|---|---|---|---|---|
| git3_known (accuracy) | 90.00% | 91.50% ★ | 97.75% | 98.25% | 97.75% | 98.25% | — |
| git3_held (accuracy) | 89.75% | 92.00% ★ | 95.50% | 95.25% | 95.75% | 95.00% | — |
| guard_held (accuracy) | 74.50% ★ | 73.75% | — | 86.75% | 83.25% | 87.25% | — |
| worlds (accuracy) | 74.75% ★ | 73.50% | 83.50% | 83.75% | 84.00% | 83.50% | — |
| intent (accuracy) | 100.00% ★ | 100.00% | — | — | — | — | 100.00% |

★ headline Jev variant of the suite.

**`git3_known`** (400 items)

| system | accuracy | confident errors per 100 | Brier | ECE (10 bins) | input tokens per check | p50 / p90 latency | US$ per 1,000 checks |
|---|---|---|---|---|---|---|---|
| Jev, Ekbasis' question | 90.00% | 0.75 | 0.1431 | 0.0410 | 484.0 | 303 / 416 ms | 0.0203 |
| Jev, Jev-style question (headline) | 91.50% | 0.50 | 0.1399 | 0.0621 | 523.4 | 303 / 393 ms | 0.0220 |
| Ekbasis-27B (bf16) | 97.75% | 2.00 | — | 0.0192 | — | — | — |
| Ekbasis-27B INT4 | 97.75% | 2.25 | — | 0.0205 | — | — | — |
| Ekbasis-Skopos-27B (bf16) | 98.25% | 1.50 | — | 0.0134 | — | — | — |
| Ekbasis-Skopos-27B INT4 | 98.25% | 1.25 | — | 0.0142 | — | — | — |

| difference (headline Jev − system) | accuracy (pp) | 95% CI |
|---|---|---|
| Jev, Jev-style question − Jev, Ekbasis' question | 1.50 | [-0.50, 3.50] |
| Jev, Jev-style question − Ekbasis-27B (bf16) | -6.25 | [-9.25, -3.50] |
| Jev, Jev-style question − Ekbasis-27B INT4 | -6.25 | [-9.25, -3.50] |
| Jev, Jev-style question − Ekbasis-Skopos-27B (bf16) | -6.75 | [-9.75, -4.00] |
| Jev, Jev-style question − Ekbasis-Skopos-27B INT4 | -6.75 | [-9.75, -4.00] |

**`git3_held`** (400 items)

| system | accuracy | confident errors per 100 | Brier | ECE (10 bins) | input tokens per check | p50 / p90 latency | US$ per 1,000 checks |
|---|---|---|---|---|---|---|---|
| Jev, Ekbasis' question | 89.75% | 0.25 | 0.1529 | 0.0618 | 487.4 | 298 / 385 ms | 0.0205 |
| Jev, Jev-style question (headline) | 92.00% | 0.25 | 0.1428 | 0.0909 | 526.7 | 303 / 394 ms | 0.0221 |
| Ekbasis-27B (bf16) | 95.75% | 4.00 | — | 0.0363 | — | — | — |
| Ekbasis-27B INT4 | 95.50% | 3.75 | — | 0.0392 | — | — | — |
| Ekbasis-Skopos-27B (bf16) | 95.00% | 4.25 | — | 0.0432 | — | — | — |
| Ekbasis-Skopos-27B INT4 | 95.25% | 3.75 | — | 0.0441 | — | — | — |

| difference (headline Jev − system) | accuracy (pp) | 95% CI |
|---|---|---|
| Jev, Jev-style question − Jev, Ekbasis' question | 2.25 | [0.00, 4.50] |
| Jev, Jev-style question − Ekbasis-27B (bf16) | -3.75 | [-6.75, -0.75] |
| Jev, Jev-style question − Ekbasis-27B INT4 | -3.50 | [-6.50, -0.50] |
| Jev, Jev-style question − Ekbasis-Skopos-27B (bf16) | -3.00 | [-6.00, 0.00] |
| Jev, Jev-style question − Ekbasis-Skopos-27B INT4 | -3.25 | [-6.25, -0.25] |

**`guard_held`** (400 items)

| system | accuracy | confident errors per 100 | Brier | ECE (10 bins) | input tokens per check | p50 / p90 latency | US$ per 1,000 checks |
|---|---|---|---|---|---|---|---|
| Jev, Ekbasis' question (headline) | 74.50% | 0.00 | 0.3657 | 0.0858 | 475.9 | 294 / 371 ms | 0.0200 |
| Jev, Jev-style question | 73.75% | 0.00 | 0.3614 | 0.0786 | 521.0 | 297 / 380 ms | 0.0219 |
| Ekbasis-27B (bf16) | 83.25% | 14.50 | 0.3061 | 0.1429 | — | — | — |
| Ekbasis-Skopos-27B (bf16) | 87.25% | 9.75 | 0.2291 | 0.1057 | — | — | — |
| Ekbasis-Skopos-27B INT4 | 86.75% | 10.75 | 0.2396 | 0.1115 | — | — | — |

| difference (headline Jev − system) | accuracy (pp) | 95% CI |
|---|---|---|
| Jev, Ekbasis' question − Jev, Jev-style question | 0.75 | [-3.00, 4.75] |
| Jev, Ekbasis' question − Ekbasis-27B (bf16) | -8.75 | [-13.00, -4.75] |
| Jev, Ekbasis' question − Ekbasis-Skopos-27B (bf16) | -12.75 | [-17.00, -8.50] |
| Jev, Ekbasis' question − Ekbasis-Skopos-27B INT4 | -12.25 | [-16.50, -7.75] |

**`worlds`** (400 items)

| system | accuracy | confident errors per 100 | Brier | ECE (10 bins) | input tokens per check | p50 / p90 latency | US$ per 1,000 checks |
|---|---|---|---|---|---|---|---|
| Jev, Ekbasis' question (headline) | 74.75% | 0.75 | 0.3174 | 0.0328 | 443.4 | 302 / 382 ms | 0.0186 |
| Jev, Jev-style question | 73.50% | 0.00 | 0.3154 | 0.0490 | 448.4 | 297 / 360 ms | 0.0188 |
| Ekbasis-27B (bf16) | 84.00% | 4.00 | — | 0.0794 | — | — | — |
| Ekbasis-27B INT4 | 83.50% | 4.75 | — | 0.0821 | — | — | — |
| Ekbasis-Skopos-27B (bf16) | 83.50% | 8.00 | — | 0.1051 | — | — | — |
| Ekbasis-Skopos-27B INT4 | 83.75% | 7.50 | — | 0.0959 | — | — | — |

| difference (headline Jev − system) | accuracy (pp) | 95% CI |
|---|---|---|
| Jev, Ekbasis' question − Jev, Jev-style question | 1.25 | [-1.25, 3.75] |
| Jev, Ekbasis' question − Ekbasis-27B (bf16) | -9.25 | [-14.00, -5.00] |
| Jev, Ekbasis' question − Ekbasis-27B INT4 | -8.75 | [-13.50, -4.25] |
| Jev, Ekbasis' question − Ekbasis-Skopos-27B (bf16) | -8.75 | [-13.25, -4.50] |
| Jev, Ekbasis' question − Ekbasis-Skopos-27B INT4 | -9.00 | [-13.50, -5.00] |

**`intent`** (300 items)

| system | accuracy | confident errors per 100 | Brier | ECE (10 bins) | input tokens per check | p50 / p90 latency | US$ per 1,000 checks |
|---|---|---|---|---|---|---|---|
| Jev, Ekbasis' question (headline) | 100.00% | 0.00 | 0.0110 | 0.0538 | 1256.4 | 322 / 434 ms | 0.0528 |
| Jev, Jev-style question | 100.00% | 0.00 | 0.0108 | 0.0529 | 1265.4 | 329 / 439 ms | 0.0531 |
| Ekbasis, hosted API (intent_check replay, 2026-10-11) | 100.00% | 0.00 | 0.0012 | 0.0195 | — | — | — |

| difference (headline Jev − system) | accuracy (pp) | 95% CI |
|---|---|---|
| Jev, Ekbasis' question − Jev, Jev-style question | 0.00 | [0.00, 0.00] |
| Jev, Ekbasis' question − Ekbasis, hosted API (intent_check replay, 2026-10-11) | 0.00 | [0.00, 0.00] |

## 3. Cost per million checks

| set | Jev input tokens per check (measured, headline variant) | Jev US$ per 1M checks | Ekbasis input tokens per check (estimated) | Ekbasis hosted US$ per 1M checks |
|---|---|---|---|---|
| release `git3_test_known` | 522.1 | 21.93 | 298.9 | 89.66 |
| release `git3_test_held` | 526.2 | 22.10 | 302.4 | 90.73 |
| release `guard_known` | 494.1 | 20.75 | 317.2 | 95.16 |
| release `guard_held` | 499.2 | 20.97 | 321.7 | 96.52 |
| scorecard `git3_known` | 523.4 | 21.98 | 299.8 | 89.94 |
| scorecard `git3_held` | 526.7 | 22.12 | 302.6 | 90.78 |
| scorecard `guard_held` | 475.9 | 19.99 | 299.1 | 89.73 |
| scorecard `worlds` | 443.4 | 18.62 | 248.7 | 74.60 |
| scorecard `intent` | 1256.4 | 52.77 | 1084.7 | 325.40 |

Jev: US$0.042 per million input tokens, output free (Vercel AI Gateway, 2026-10-16). Ekbasis hosted: US$0.30 per million input tokens, no output charge (openinterp.org/ekbasis/pricing, 2026-10-16). Ekbasis' tokens per check are an estimate (METHOD.md); the hosted scorecard runs will give the measured value.
