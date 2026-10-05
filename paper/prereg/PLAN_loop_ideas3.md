# Two views fused into one read (no training)

Written on 2026-10-04 before any chain of this test ran (criteria fixed in advance).

The two-views test (PLAN_loop_ideas.md) showed that a second view of the state catches errors (steps wrong along the way
0.40 → 0.17 per 100 actions) but, used only to trigger looks, it costs looks (+46%). Here the second view is not a trigger:
at every step the primary questions and the second view are asked together and combined into the state most probable
under both, and that state's probability (normalized over every state) is the step's confidence:

- containers: each container's amount with "Is it full?" and "Is it empty?";
- lamps and machines: every pair of neighbours' "same state?" answers, a chain of neighbours solved exactly (the best
  state by Viterbi, the probability by the forward pass);
- cards: the inverse questions ("At which position is the X?") inside the assignment, as the existing dual mode.

The implementation was checked before any run: identical to brute force on 600 random worlds, and identical to the
plain read when the second view carries no information.

The release model (V42) on the same 40 chains as the earlier loop-idea tests, modes fuse0.9E and fuse0.5E (looks as the
default: the threshold, the checks, the last-action look), against V42's default on the same chains, with the same
criterion: fewer steps wrong along the way without more than 10% more looks, or fewer looks without more steps wrong,
pooled over the four worlds. Reported per world, and next to the views modes.
