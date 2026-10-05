# V43, round 3: the dose of the model's own errors

Written on 2026-10-03 before any round-3 run started (research plan, criteria fixed in advance).

## Question

Round 2 showed that training on the model's own mined errors makes its errors honest on single questions (confident
errors −86 to −92%, better AUROC, even in families and question types never mined), but at 30% of every batch it also
lowered the confidence of right answers, so the look-when-unsure loop looked more (27.6 against 18.1 per 100 actions at
the default, with one chain not exact). Is there a dose that keeps the errors honest without that cost?

## Runs (GPUs 1-3; each continues `sw_v42/ckpt_400` for 300 steps with the V42 recipe, plain cross-entropy)

- **r3h10**: `mined_hard` (the 2,486 mined errors and 1,298 right answers given below 0.9) at 10% of every batch;
- **r3h20**: the same at 20%;
- **r3w20**: `mined_wide` (the mined errors and right answers given below 0.99, at most twice as many as the errors) at
  20%.

The other kinds of the V42 mix are scaled to fill the rest of every batch.

## Single-question evaluation (as round 2, against V42 under the trainer's readout)

A run qualifies if, against V42: confident errors per 100 answers drop by at least 40% in group T and do not rise in U
and H; git3 (known and held pooled) and `multi_test_testfam` changed answers within 0.5 points or better; the share of
wrong answers at 0.9 or more does not rise; AUROC not lower by more than 0.005. Among the qualifying runs, the one with
the largest share of right answers at a confidence of 0.99 or more (the sharpest, the one the loop should check least)
goes to the loop test; with none qualifying, the closest one is reported and nothing goes to the loop.

## Loop test (more chains)

The chosen run, merged and served like the release, against V42 on the same chains: `long_chain3.py`, 16 card chains and
8 chains of each other world per length (100 and 200 actions; the first 8 and 4 are the earlier ones, the rest new
seeds), never looking (with traces), chain confidence below 0.5, and the default (below 0.9 with checks). V42's new
chains run on its test API meanwhile.

The loop is better if, pooled over the four worlds:

- at the default, the steps wrong along the way per 100 actions are not higher than V42's and the looks per 100 actions
  are not higher by more than 10%; or
- at matched cost, the run's best rule (below 0.5, or the default) has both fewer steps wrong along the way and fewer
  looks than V42's default.

Reported in any case: chains exact at the end (and whether a miss is only the last action, which no rule can check), and
the share of confidently wrong steps in the never-looking traces of the trained worlds.
