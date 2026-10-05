# V43, round 4: errors mined inside the model's own chains (DAgger-style)

Written on 2026-10-04 before any round-4 item was mined (research plan, criteria fixed in advance).

Round 3 made single answers better (r3w20) but not the loop: inside chains, where the model reads states it predicted
itself, its errors stay confident (16 of 23 wrong steps at 0.9 or more in the trained worlds). Round 4 mines errors where
they happen: the release model runs new chains (seeds i 1000-1049, never used by any test) in the two trained worlds
with chains, containers and lamps, never looking; at every step, every variable it got wrong or answered below 0.99 is
kept with the true result of the action from the state it was reading (the simulator), as a training item (kind
floorC). Machines and cards are never mined.

Runs (GPUs 1-3; plain cross-entropy; the V42 recipe):

- **r4a**: from V42, 300 steps, mined_wide at 20% and the chain items at 10% (the other kinds scaled by 0.7);
- **r4b**: from r3w20, 200 steps, mined_wide at 10% and the chain items at 15% (the other kinds scaled by 0.75);
- **r4c**: from V42, 300 steps, the chain items alone at 20% (the other kinds scaled by 0.8).

If fewer than 30 wrong items are mined, the runs do not start (too little to learn from) and that is reported.

Evaluation, selection and the loop test: exactly as in round 3 (`PLAN_v43_round3.md`): the single-question criteria,
the sharpest qualifying run to the loop test, the loop criteria against V42 on the same 240 chains.
