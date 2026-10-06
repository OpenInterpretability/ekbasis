# Overlap with the training data: the audit of every published number (2026-10-06)

While new training data was being checked against every evaluation set, we found that the world generator's small
worlds repeat across seeds: some evaluation questions generated "with seeds never used before" repeat, or nearly
repeat, rows of the training data. This folder checks every evaluation set behind a published number against V42's
training rows (`ftrain_mixG3`) and against the released model's whole lineage (V42's rows and r4a's two mined sets,
`mined_wide` and `mined_chain`; `caiovicentino1/ekbasis-data`, config `lineage`), and recomputes every published
number without the overlapping items, with the original analysis scripts unchanged.

## Rules

- **Identical:** the evaluation prompt (rules, state and actions), with whitespace normalized and in lower case, equals
  a training row's prompt or hindsight prompt.
- **Near duplicate:** the prompt's word 8-grams, minus the set's own layout (8-grams in at least 20% of a sample of its
  prompts, and its question texts), are at least half present among the training 8-grams, and their Jaccard similarity
  with one training row (the best of the 20 rows sharing the most 8-grams) is at least 0.5.

## What overlaps

| Evaluation set | Overlap (V42's rows) | Overlap (the release's lineage) |
|---|---|---|
| The 15,008 questions of the confident-errors test | 5,318: 173 identical, 5,145 near (T 4,101 of 7,172; H 1,217 of 2,472; U 0) | 5,378: 174 identical, 5,204 near |
| Trained families, several questions per state (`multi_trainfam`) | 290 of 600 states | 291 of 600 (5 identical prompts, same questions) |
| `ftest_in` (the V41/V42 selection rule) | 1,026 of 1,774 | — |
| Short checks (240) | — | 20 (19 container items and 1 lamp item, original wording) |
| Portuguese test (90 changed questions) | — | 2 English versions (lamps), 0 Portuguese |
| Chains (step prompts, rebuilt from their seeds) | — | containers 3,601 of 9,600 distinct prompts (1 identical); lamps 218 of 9,600; machines and cards 0 |
| Planning puzzles (first search step) | — | 6 of 180 and 10 of 180 |
| Image chains (60) | — | 1 |
| git v3 and v2 tests (and the 240-question comparison), the larger guard set, never-trained families (`multi_testfam`, `ftest_family`), speed items, validation sets | 0 | 0 |

104 of the 15,008 questions share the prompt **and** the question with a training row (all in the sequences family,
group T, all answered right by V42 and by the release); the first note counted 88. Most other matches share the
family's template rather than the item: of the 5,378, 2,869 near duplicates differ from the row they match in both the
state and the actions, 1,838 share only the actions, 439 only the start state, 58 both with other wording. Whole small
families are flagged (grids 1,440 of 1,440, sequences 1,080 of 1,080 in T). `examples.md` shows ten side by side.

## The published numbers without the overlap

| Claim | All items (published) | Without the overlap | Conclusion |
|---|---|---|---|
| Confident-errors test, V42 (pre-registered) | 58.1% vs 27.8%, +30.3 [24.0, 36.5] | 50.5% vs 27.8%, +22.7 [12.6, 32.5]; family medians 62.5% vs 25.8% | holds (confirmed) |
| Changed answers (secondary) | +40.4 [32.8, 48.1] | +32.2 [18.5, 46.6] | holds |
| The parent (Eikos-27B) | 1.9% and 0.5% | 1.8% and 0.5% (gap +1.3 [−0.1, 2.9]) | holds |
| Training made it: D (pre-registered) | +28.9 [22.8, 34.9] | +21.4 [10.6, 31.4] | holds |
| Confident errors per 100 answers in T, parent → V42 | 0.28 → 2.79 (tenfold) | 0.20 → 1.69 (8.7-fold) | holds |
| Errors in T, parent → V42 | 14.4% → 4.8% (two-thirds fewer) | 10.9% → 3.4% (69% fewer) | holds |
| A 0.9 trigger can flag at most, in T | 41.9% | 49.5% | holds |
| Logistic regression: odds ratio of familiarity (exploratory) | 2.44 | 1.10 (log-odds [−0.82, 1.21]) | **changes** |
| Own scale: gap V42 vs parent (exploratory) | +28.3 vs +8.8 | +20.1 vs +13.2 | holds, smaller |
| Recalibration (pre-registered): band right after a map; T–U gap | 96.8–97.1%; 18–22 points | 97.1–97.5%; 12.1–18.7 points | holds (no map passes) |
| Label smoothing / focal loss AUROC | 0.871 / 0.891 vs 0.919 | 0.881 / 0.895 vs 0.925 | holds |
| r2err, confident errors per 100 in T | 0.22 vs 2.76 | 0.13 vs 1.67 | holds |
| r3w20 "beat V42" (accuracy) | 90.5% vs 90.2% | 88.6% vs 88.9% | **changes** |
| w4a5 (the release), trainer readout: accuracy; per 100 in T | 90.7% vs 90.2%; 2.05 vs 2.76 | 89.0% vs 88.9%; 1.42 vs 1.69 | holds |
| The release, served: T vs U; per 100 in T vs V42 | 48.4% vs 25.1%, +23.3 [16.8, 30.1]; 2.06 vs 2.79 | 50.0% vs 25.1%, +24.9 [13.3, 35.8]; 1.46 vs 1.69 | holds (fewer, not gone) |
| Trained families, changed answers (release) | 92.4% [90.6, 94.0] / 91.5% read once | 93.6% [91.3, 95.8] / 92.8% | holds |
| V41/V42 selection checks (`ftest_in`, trained families) | +0.2, −0.4 / +0.2 | −0.3, −1.3 / −0.8 (limit −2) | holds (V42) |
| Short checks: original / paraphrased; routing at 0.90 | 95.8% / 97.5%; 6.7% → 98.8% | 95.0% / 97.5%; 6.8% → 98.6% | holds |
| Planning: plans that work | 100.0% / 98.9% | 100.0% (174) / 98.8% (170) | holds |
| Chains: trained-world errors at ≥ 0.9 (never-look traces) | 9 of 9 (parent 0 of 281) | 6 of 6 (parent 0 of 170; Fisher p = 2.6e-11) | holds |
| Chains: errors in containers and lamps vs V42 (fresh chains) | — | r4a 0 vs 27, r4b 2 vs 27, r4c 6 vs 28, w4a5 2 vs 14 | holds |

Errors are not rarer at the chain steps that overlap (V42's 200 fresh chains, containers: 55 errors in 4,898 such
steps, 42 in 8,302 others). Silent wrong steps per 100 actions cannot be split by step, since a wrong state persists.
The Portuguese numbers cannot be recomputed (answers per question were not kept; at most two questions).

## Files

- `numbers.json`: every number above and more (Table ce without the overlap, every trainer readout, the chains).
- `flags.json`: the flagged items of the confident-errors test and of the trained families' set (indices into the
  files of `results_v42/confident_errors/` and the dataset's raw splits), for V42's rows and for the lineage, and the 104
  items with the same prompt and question. `flags_chains.json`: for every chain (`family/length/seed`), the steps whose
  prompt overlaps.
- `examples.md`: ten matches side by side.
- `scripts/`: the audit's code, run on the training machine (its paths are that machine's). `pi_overlap.py` and
  `pi_overlap_byfile.py` apply the rules; `pi_ce_recompute.py`, `pi_more.py`, `pi_extra.py`, `pi_r5.py` re-run the
  paper's analysis scripts without the overlap; `pi_select.py`, `pi_short_pt.py`, `pi_chains.py` the other sets;
  `pi_numbers.py` collects `numbers.json`.
