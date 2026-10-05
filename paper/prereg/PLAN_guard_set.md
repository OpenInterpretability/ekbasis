# A larger guard set (agreed with Caio: measure better instead of loosening the criterion)

Written on 2026-10-04 before the set was generated and before any model was evaluated on it (criteria fixed in advance).

## Why

The release gate judges the guard on git3_test_known and git3_test_held: 51 and 42 work-losing commands, so one item is
about 2 points and the 1-point margin forbids a single swap. A run that misses one more known command and catches one
more held-out command (r4c) cannot be told from noise, nor a real regression (r4a, r4b: the same held-out kinds missed
again and again) from a bad draw.

## The set

The git3 generator (`gitbox3.py`: every answer computed by running real git in a throwaway repository), the same two
kinds of examples as the existing sets: **guard_known** (no held command type) and **guard_held** (every example uses a
held command type: `rebase`, `restore_old`), 1-3 commands, 20,000 examples each, from seeds no git generator has used
(known 2910000-2910239, held 2960000-2960239). Dropped before balancing: every example whose state and commands (the
floor text) appear in any training or validation file or any existing git test file, and exact duplicates. Balanced like
the existing sets (every "yes" kept and as many "no" drawn) and kept: the questions the guard asks, "lost" (does it
permanently lose uncommitted work?) and "fails". About ten times the work-losing commands of the current sets.

## Measured

By the trainer's readout (`MODE=eval_adapter`, which reproduced the served counts exactly on git3), for V42 and every
candidate so far, all reported: r4a, r4b, r4c, r5a, r5b, r5c, w4a5, w4a7, w4b5.

## The gate (replaces the guard checks on git3_test_known/held; the rest of the release gate unchanged)

On guard_known and on guard_held separately: work-losing commands flagged at 0.2 not lower than V42's by more than 1
point, and false alarms at 0.2 not higher than V42's by more than 1 point. Reported too: the paired counts (commands V42
flags and the run misses, and the reverse) and the "fails" accuracy.

A V43 candidate passes this gate, is confirmed better in the loop on fresh chains, and passes the rest of the release
evaluation; then it is Caio's decision.
