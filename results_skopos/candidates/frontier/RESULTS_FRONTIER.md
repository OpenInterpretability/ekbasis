# Frontier test — Qwen-AgentWorld-35B-A3B vs Ekbasis on Ekbasis' typed items (2026-10-15 05:12 UTC)

Setting (ADDENDUM_FRONTIER + Addendum B): AgentWorld via vLLM on the same RTX PRO 6000, thinking off (it still writes
a full worked state), max 8,192 tokens, temperature 0.6, one sample, last 'Answer: X' parsed, unparsed = wrong.
Ekbasis base and R1 on the same indices (one forward pass, no generation). Paired bootstrap by item.

| suite | n | AgentWorld | AW among parsed (parsed) | Ekbasis base | R1 | base − AW [95% CI] | AW tokens / s (median) |
|---|---|---|---|---|---|---|---|
| git_long (real git 5/8/12) | 300 | 0.660 | 0.934 (212; 89 truncated) | **0.913** | 0.907 | **+0.253 [+0.200, +0.307]** | 6,435 / 219 s |
| guard_known (real commands) | 200 | 0.780 | 0.918 (170; 31 truncated) | **0.940** | 0.945 | **+0.160 [+0.105, +0.220]** | 4,203 / 139 s |
| fhorizon (synthetic 1–20) | 300 | **0.977** | 0.987 (297) | 0.843 | 0.873 | **−0.133 [−0.177, −0.090]** | 943 / 34 s |
| latent_test (synthetic) | 200 | **0.885** | 0.989 (179) | 0.810 | 0.815 | **−0.075 [−0.135, −0.020]** | 920 / 34 s |

Among only the items AgentWorld finished: git_long base +0.024 [−0.009, +0.057]; guard +0.053 [+0.006, +0.100];
fhorizon −0.141; latent −0.134.
By length — git_long AW .757/.684/.521 at 5/8/12 (truncations 22/27/40) vs base .937/.947/.851; fhorizon at 20
actions AW .930 vs base .651 / R1 .744; at 12, .923 vs .692 / .744.
Thinking on with 4,096 tokens (sealed setting, stopped): 132 git_long answers, 26 parsed, 0.197.

## Reading
1. **Real commands (git, guard): Ekbasis wins clearly**, in one forward pass against 4–6k generated tokens and
   2–4 minutes per answer; even counting only finished answers it is ahead on guard and level on git.
2. **Synthetic worlds with explicit rules: step-by-step simulation wins**, and the gap grows with horizon (20 actions:
   0.93 vs 0.65). This is the ceiling of answering in one pass, not missing knowledge — the dose/R1 training moves it
   (+3–9 pts at 12–20 actions) but nowhere near closing it.
3. Exploratory cascade (post hoc, `scripts/cascade.py`, base refit T = 1.55): escalate to the reasoning model when
   Ekbasis' refit confidence < 0.9 → fhorizon 0.843 → 0.967 escalating 34% (26 s/item mean); latent 0.810 → 0.930
   escalating 44%; git_long and guard: no gain (AgentWorld is the weaker model there). So the cascade pays only where
   the fallback is stronger: on real commands it would need a different fallback (e.g. GLM-5.3 reasoning) — untested.

## Cascade with GLM-5.3 as the fallback on real commands (Addendum C, exploratory)
On the 64 low-confidence real-command items (Ekbasis right 41, AgentWorld 23): GLM-5.3 at default effort finished
30 within 16,384 tokens and was right on 27 (Ekbasis right on 18 of those). Cascade "GLM if it finished, else keep
Ekbasis": **41 → 50/64**; on the full frontier sample **git_long 0.913 → 0.927, guard 0.940 → 0.965**, escalating
11–14% of items, at a median 119 s per escalated item (34/64 hit the token cap). C2 (cheaper efforts) running.

### C2 — GLM effort for the fallback (64 escalated real-command items; Ekbasis alone 41)
| effort | finished | right (of finished) | cascade | git / guard | median tokens / s |
|---|---|---|---|---|---|
| max (default) | 30 | 27 | **50** | 30/41 · 20/23 | 16,384 / 119 s |
| **high** | 59 | 46 | **48** | 30/41 · 18/23 | 1,682 / **19 s** |
| low | 59 | 39 | 40 (below Ekbasis) | 27/41 · 13/23 | 461 / 5 s |

Pre-registered read (≥ 48 at lower time): **`high` is the fallback setting** — 2 items behind `max` at 1/6 of the time.
Full sample with `high`: git_long 0.913 → 0.927, guard 0.940 → 0.955, escalating 11–14% of actions at ~19 s each
(about 2–3 s added per action on average). `low` hurts: do not use it as a fallback.
