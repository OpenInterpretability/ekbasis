# Two views, only on confident disagreement (no training)

Written on 2026-10-04 before any chain of this test ran (criteria fixed in advance).

The first test of two views (PLAN_loop_ideas.md) cut the steps wrong along the way by 58% (0.40 → 0.17 per 100 actions)
but added 46% looks: the second view disagreed at 1,107 steps, nearly all false alarms. Here a disagreement triggers a
look only when it is confident: the second view gives the answer implied by the first read less than 10%.

The release model (V42) on the same 120 chains, modes viewsc0.9E and viewsc0.5E (the default threshold 0.9 or 0.5,
checks, the last-action look, and the confident-disagreement trigger), against its default on the same chains, with the
same criterion: fewer steps wrong along the way without more than 10% more looks, or fewer looks without more steps
wrong, pooled over the four worlds.
