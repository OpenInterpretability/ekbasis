# Confirmation of the loop ideas that pass (no training)

Written on 2026-10-04 before the results of the exploratory loop-idea tests 2-4 (PLAN_loop_ideas2.md, 3, 4) were known.

Each exploratory test compares a mode with the release model's default on the same 40 chains (24 for the partial looks),
and was judged on those chains; a mode chosen on them may have won by chance. Every mode that passes its exploratory test
is run again on the 40 chains it has not seen (the chains added in round 3: cards seeds 8-15, the other worlds 4-7, both
lengths; the partial looks on the 24 of containers, lamps and machines among them), against the release model's default
on the same chains (`long_chain3_v42more.jsonl`, run before any of these ideas), with the same criterion as its own test.
It is confirmed if it passes again. If the confirmation fails, the idea is reported as not confirmed, whatever its
first result. Reported in any case: the 80 chains pooled.
