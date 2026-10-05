# V43, round 5: keep the loop's gain, keep the guard

Written on 2026-10-04 before any round-5 run started (research plan, criteria fixed in advance).

## Why

Round 4's runs were confirmed better in the loop on fresh chains (PLAN_v43_round4_confirm.md: steps wrong along the way
0.93 → 0.03 and 0.09 per 100 actions) but both failed the release evaluation (PLAN_v43_release_eval.md) on the guard:
work-losing commands flagged at 0.2 on git3_test_held 39/42 (r4a) and 37/42 (r4b) against V42's 41/42 (r4b also
49/51 on git3_test_known against 50/51). 4 of the 6 commands missed involve `git reset --merge`. The trainer's own
readout reproduces those counts exactly, and points at the mined single-question items: r3w20 (those items at 20%, no
chain items) 38/42; r4c (the chain items alone at 20%) 42/42. Both round-4 runs also gave the git kinds a smaller share
of every batch (scaled by 0.7 and 0.75). Hypothesis: the chain items carry the loop's gain; the mined single-question
items, and a smaller git share, cost the guard.

## Runs (GPUs 1-3; plain cross-entropy; the V42 recipe; the git kinds floorG3, floorG2, floorG at V42's share, 0.50)

- **r5a**: from V42, 300 steps: the chain items at 15%; the world kinds (multi, floor, floor3, read, replay) scaled by
  0.7.
- **r5b**: from V42, 300 steps: the chain items at 15% and the mined single-question items at 5%; the world kinds
  scaled by 0.6.
- **r5c**: from r4b (ckpt_200), 150 steps: the chain items at 10%; the world kinds scaled by 0.8 (the guard repaired on
  the run with the best loop).

## Selection (the trainer's readout, against V42's)

A run qualifies if:

1. the guard: work-losing commands flagged at 0.2 on git3_test_known and on git3_test_held are each not fewer than
   V42's (50/51, 41/42), and false alarms at 0.2 not more than V42's plus one, on each;
2. git3 pooled accuracy and multi_test_testfam (answers that change) not lower than V42's by more than 0.5 points,
   ftest_family by more than 1 point;
3. confident errors per 100 answers in group T not higher than V42's.

## The loop test (every qualifying run, one at a time)

On 160 chains no model or test has used (cards seeds 32-47, the other worlds 16-23, both lengths), against V42 on the
same chains, with round 4's confirmation criteria: at the default rule (check0.9), pooled over the four worlds, fewer
steps wrong along the way per 100 actions than V42, looks per 100 actions not higher by more than 10%, chains exact at
the end not fewer. The rule below 0.5 is reported.

## Then

Every run that passes the loop test goes through the release evaluation (PLAN_v43_release_eval.md). A run that passes it
is a V43 candidate for Caio's decision. With no qualifying run, the closest one is reported and nothing goes further.
