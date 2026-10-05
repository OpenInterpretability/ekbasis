# Pre-registration: are Ekbasis' errors confident in the worlds it knows?

Written on 2026-10-03, before any item of this test was generated or answered. Its SHA-256 is recorded in
`PREREG_sha256.txt` before the run.

## Why

Per-step traces of long chains (`results/release_eval/long_chain3*_trace.jsonl`, never looking) suggested a pattern:

- in worlds the model was trained on, errors are rare but confident: containers 5 wrong steps of 1,200 at a
  probability of 0.917–0.988, lamps 4 of 1,200 at 0.991–0.994;
- in worlds it never saw, errors are frequent but flagged: card orderings 82 of 2,400, all below 0.7 (machines, 3 of
  1,200 at 0.846–0.929, in between).

Only 12 errors on the familiar side, and card orderings differ from the other worlds in kind, so the pattern may come
from the type of world rather than from familiarity. This test checks it on many more errors and world families.

## Hypothesis

H1. On short consequence questions, the release model's wrong answers carry higher confidence in world families and
question types it was trained on than in world families it never saw.

## Design

- **Model**: the release weights (Ekbasis-27B, bf16, `merged_v42`), served by vLLM 0.30 behind the System One API, one
  prompt per question; several replicas of the same build, requests in turn.
- **Items**: generated for this test with `worldgen.fbalanced(..., change_balance=True)`, every item a new world, for
  every world family and question type, with 1, 2 and 3 actions, 120 items per (family, question type, actions) cell;
  the random seed of each cell is the string `ce-<family>-<question type>-<actions>-20261003`, never used before. A
  cell that cannot reach 120 items keeps what it reached (reported).
- **Groups** (from `worldgen.TRAIN`, `VAL`, `TEST` and each family's `HELD_Q`):
  - **T**, familiar: the 7 training families (grid, gravity, counters, toggles, seq, jugs, craft) with their trained
    question types;
  - **H**: the same 7 families with the question type each keeps out of training (reported apart);
  - **U**, never seen: the 2 validation and 3 test families (track, tally, cards, timers, machines), every question
    type; none of them is in the training data.
- **Recorded per item**: the chosen option and its probability (the confidence), whether it is right, and whether the
  actions changed the answer (the same question about the initial state has a different answer).

## Primary analysis

Among wrong answers, the share with a confidence of 0.9 or more ("confident errors"), T against U, pooled over items.

- **Confirmed** if the share in T exceeds the share in U by at least 15 points, the 95% bootstrap interval of the
  difference excludes 0 (2,000 resamples of items within each family, families fixed), and the family medians agree
  (median over T families of the per-family share above the median over U families, counting families with at least
  10 wrong answers).
- **Refuted** if the interval includes 0 or the difference is negative.
- **Inconclusive** otherwise.

## Secondary analyses (reported whatever the primary result)

- The primary analysis on the answers the actions change.
- Error rate per group and per family; median confidence of wrong answers; share of wrong answers below 0.7.
- How well confidence separates right from wrong answers: AUROC per family and group; the share of a family's errors
  caught by looking at its least-confident 10% of answers.
- Group H next to T and U.
- Difficulty as an explanation: per family, the error rate against the share of confident errors.

## Reporting

Every prediction is saved (`results/confident_errors/`). Any deviation from this plan is listed in the report.
