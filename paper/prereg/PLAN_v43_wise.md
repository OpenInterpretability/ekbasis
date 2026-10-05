# Weight-space interpolation of V42 with the round-4 runs (WiSE-FT)

Written on 2026-10-04 before any of these interpolations was evaluated (criteria fixed in advance).

Five of the six runs fine-tuned from V42 lost 2-4 of the same rare work-losing git commands (git3_test_held 37-39/42
against 41/42), while round 4's runs were confirmed far better in the loop. Interpolating the weights of the starting
and the fine-tuned model (WiSE-FT, Wortsman et al., 2022) is known to keep the original model's robustness while keeping
much of the fine-tuning's gain. Here the interpolation is exact: W0 + (1-λ)·Δ(V42) + λ·Δ(run), written as one LoRA
adapter of rank 128 (`wise_lora.py`, checked against the direct interpolation).

Three interpolations, each evaluated by the trainer's readout (the adapter loaded, one step at learning rate 0, the
round-5 splits): **w4a5** (r4a, λ = 0.5), **w4a7** (r4a, λ = 0.7), **w4b5** (r4b, λ = 0.5).

Selection: the round-5 criteria (PLAN_v43_round5.md): the guard per split not fewer flagged than V42 and false alarms at
most V42's plus one; git3 pooled and multi changed within 0.5 points, ftest within 1; confident errors in T not higher
than V42's.

Every qualifying interpolation, one at a time (largest λ first), goes to the loop test on 160 chains no model or test has
used (cards seeds 48-63, the other worlds 24-31, both lengths), against V42 on the same chains, with round 4's
confirmation criteria; every one that passes goes through the release evaluation (PLAN_v43_release_eval.md).
