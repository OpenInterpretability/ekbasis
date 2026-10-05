# r4c in the loop (asked by Caio)

Written on 2026-10-04 before any chain of this test ran (criteria fixed in advance).

r4c (round 4: from V42, 300 steps, the chain items alone at 20%, the other kinds scaled by 0.8) was never loop-tested:
it failed round 4's single-question criteria (git3 pooled 95.7 against 96.3). It is the only fine-tuned run whose guard
did not lose work-losing commands in total (trainer readout: git3_test_known 49/51, git3_test_held 42/42, 91/93 as
V42's 50/51 + 41/42; false alarms 4/93 against 2/93), and the chain items are what the round-4 analysis credits with
the loop's gain.

The loop test: r4c merged and served like the release (fidelity 97% or more), against V42, on the 160 chains planned for
round 5 and never run (no round-5 run qualified: cards seeds 32-47, the other worlds 16-23, both lengths; rules check0.9
and conf0.5), with round 4's confirmation criteria: at the default rule, pooled over the four worlds, fewer steps wrong
along the way per 100 actions than V42, looks per 100 actions not higher by more than 10%, chains exact at the end not
fewer.

If it passes, it goes through the release evaluation (PLAN_v43_release_eval.md), whose guard checks are per split (as
written: on git3_test_known it would need 50/51). Whether a pooled guard criterion is acceptable is Caio's decision;
the results are reported both ways.
