# Partial looks: see only the variables that are unsure (no training)

Written on 2026-10-04 before any chain of this test ran (criteria fixed in advance).

A look at the whole state is what `git status` gives; elsewhere a look can cost per thing seen (a sensor, a request per
resource). Mode part0.9: the same trigger as the default (the chain confidence, here the product of each variable's own
confidence since it was last seen, below 0.9), but the look covers only the least sure variables, as many as needed to
bring the rest back to 0.95; the scheduled checks and the looks after a surprise stay whole (a confident error is never
among the least sure). Mode parta0.9: the same, and every partial look also sees the variable unseen the longest (a
rotating audit). Not for cards (a partial look would break the ordering).

A simulation with a noisy reader (no model) showed the risk before any run: variables seen −55% but steps wrong along
the way up (part), less so with the audit (parta).

The release model (V42) on the same 24 chains of containers, lamps and machines as the earlier loop-idea tests, against
its default on the same chains. Partial looks pass if, pooled over the three worlds, they see fewer variables per 100
actions than the default (a whole look sees every variable) with steps wrong along the way not higher. Reported: look
events, whole looks, chains exact at the end.
