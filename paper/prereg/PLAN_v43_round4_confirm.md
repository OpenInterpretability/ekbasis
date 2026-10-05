# Round 4, confirmation in the loop: r4b against V42 on fresh chains

Written on 2026-10-04 after the exploratory loop test of r4b (PLAN_v43_round4_loop_explore.md) and before any chain of
this test ran (criteria fixed in advance).

The exploratory test, on the 240 chains of the earlier loop tests, found r4b better than V42 at the default rule (below
0.9 with checks): steps wrong along the way 0.13 against 0.42 per 100 actions, looks 15.1 against 18.9 per 100 actions,
every chain exact, better in each of the four worlds. r4b was not chosen by the round-4 plan (it failed the
single-question criteria), so that result is confirmed here on chains no model or test has used: cards seeds 16-31, the
other worlds seeds 8-15, both lengths (80 chains per rule: 32 of cards, 16 of each other world). Both models run the same
chains at the same time: r4b merged and served like the release (`sw_r4b/ckpt_200`, its merge's fidelity checked as
before, 97% or more), V42 the release weights.

r4b is confirmed if, at the default rule (check0.9), pooled over the four worlds:

- its steps wrong along the way per 100 actions are lower than V42's;
- its looks per 100 actions are not higher than V42's by more than 10%;
- its chains exact at the end are not fewer than V42's.

Reported in any case: each world, and the rule below 0.5 without checks (secondary). A confirmed r4b is a V43 candidate,
not a release: replacing V42 would still need the full release evaluation and Caio's decision.
