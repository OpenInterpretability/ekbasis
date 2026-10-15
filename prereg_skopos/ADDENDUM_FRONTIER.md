# Addendum FRONTIER — Qwen-AgentWorld-35B-A3B on Ekbasis' typed questions (written 2026-10-15 ~01:30 UTC, before running)

Descriptive (no pass/fail). The general language world model answers the same items as Ekbasis (floor prompt + question
+ lettered options; may reason, max 4,096 tokens, temperature 0.6, top-p 0.95, one sample; last "Answer: X" parsed;
unparsed = wrong). vLLM on the same RTX PRO 6000. Items: git_long (all 900), guard_known (800 sampled), fhorizon (700),
latent_test (800), seed 20261015. Compared with Ekbasis base and R1 on the same items: accuracy (paired), and the cost
side — completion tokens and seconds per answer vs Ekbasis' one forward pass. Script `scripts/frontier_eval.py`.

## Operational note (2026-10-15 04:25 UTC, before any AgentWorld answer)
The first launch failed: the released checkpoint is text-only (no `visual.*` weights) while its config declares the
vision tower, so vLLM refused to load it. Relaunched with `--language-model-only` and `--max-num-seqs 64` (the default 1,024 exceeded the 876 Mamba cache blocks; the test uses 32 concurrent requests) (the config itself carries
`language_model_only`), server wait raised to 40 min, and a failure now writes FRONTIER_FAILED + FRONTIER_DONE so the
queue (R2) is not blocked. Items, prompt, decoding and scoring are unchanged.

## Addendum B (2026-10-15 04:36 UTC) — budget, written after seeing only that answers were truncated
The sealed setting (thinking on, 4,096 tokens) truncated before any answer: of the first 66 git_long items, 55 hit the
4,096 cap with no 'Answer:' line (median 4,096 tokens, 99 s per item; 11 parsed, 0.167 accuracy). That measures the
cap, not the model. A probe with thinking off produced a full worked state and a final 'Answer:' in 4,001 tokens.
New setting, for every AgentWorld run (frontier and neutral): `enable_thinking: false`, max 8,192 tokens, 64
concurrent requests, temperature 0.6 / top-p 0.95 as before; finish reason and the answer's tail are now saved.
Samples cut to fit about an hour: git_long 300, guard_known 200, fhorizon 300, latent_test 200 (seed 20261015;
Ekbasis compared on the same indices). The 66 truncated answers are kept as `aw_git_long.v1_truncado.jsonl` and
reported as the thinking-on/4k result. A thinking-on run with a larger budget is not run (cost: >8k tokens/item).

## Addendum C (2026-10-15 05:20 UTC) — exploratory: GLM-5.3 as the cascade's fallback on real commands
After the frontier result (AgentWorld weaker than Ekbasis on real commands), the cascade's open question is whether a
different reasoning model helps there. Items: the 64 frontier items on git_long (41) and guard_known (23) where
Ekbasis base's refit confidence (T = 1.55) is < 0.9 (`neutral/escalated_real.json`); on them Ekbasis is right 41/64,
AgentWorld 23/64. Model: our production GLM-5.3 (served `glm-5.3-flash`, default reasoning effort), same prompt as the
frontier test, temperature 0.6 / top-p 0.95, max 16,384 tokens, one sample, 2 concurrent requests (light load on
production; nothing in the server changes). Read: the cascade helps on real commands only if GLM is right on more of
the 64 than Ekbasis (41), reported with the paired counts. Exploratory; n is small.

### Addendum C result (06:00 UTC) and C2 (pre-registered now)
C: GLM-5.3 at its default effort (`max`) finished 30/64 within 16,384 tokens (34 truncated) and was right on 27 of
those 30 (Ekbasis right on 18 of them). Cascade "GLM if it finished, else Ekbasis": 41 → 50/64; whole frontier
sample git_long 0.913 → 0.927, guard 0.940 → 0.965; median 119 s per escalated item.
C2: the same 64 items with `chat_template_kwargs: {reasoning_effort: "high"}` (and, as a second arm, "low"), same
prompt, sampling, 16,384 cap and 2 concurrent. Read: the cheaper effort is preferred for the cascade if its
cascade score on the 64 is within 2 items of `max` (≥ 48) at a lower median time.
