# Round 4, confirmation in the loop: r4a too (addendum)

Written on 2026-10-04 after r4a's exploratory loop result and before any chain of the confirmation ran.

r4a's exploratory loop test (PLAN_v43_round4_loop_explore.md) also passed: at the default rule, steps wrong along the
way 0.07 against V42's 0.42 per 100 actions, looks 18.7 against 18.9, every chain exact; fewer looks or equal in each
world except cards (40.7 against 37.2). r4a goes through the same confirmation as r4b (PLAN_v43_round4_confirm.md): the
same fresh chains, the same V42 chains, the same three criteria, judged on its own. With both confirmed, neither is
preferred by this test: the choice of a V43 candidate would weigh the loop (fewer steps wrong: r4a; fewer looks: r4b)
with the single-question results (r4a: confident errors lower in every group, AUROC 0.928; r4b: the sharpest, 79.2% of
right answers at 0.99 or more, confident errors in group U slightly higher than V42's) and the full release evaluation.
