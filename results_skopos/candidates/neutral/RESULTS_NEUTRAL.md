# Neutral ground — AgentWorldBench "will the next action fail?" (PREREG_NEUTRAL.md) — 2026-10-15 09:18 UTC

455 real agent turns (136 trajectories; 54 failures): SWE shell tools with exact exit status (140) and Terminal-Bench
keystrokes with error-signature labels (315). Bootstrap clustered by trajectory.

| model | balanced acc. [95% CI] | AUROC [95% CI] | recall @10% FA | SWE exact: bal. / AUROC | terminal: bal. / AUROC |
|---|---|---|---|---|---|
| **Ekbasis base** | **0.720 [0.653, 0.782]** | **0.833 [0.783, 0.879]** | 0.44 | 0.825 / 0.841 | 0.683 / 0.825 |
| R1 | 0.708 [0.642, 0.772] | 0.832 [0.783, 0.878] | 0.50 | 0.829 / 0.852 | 0.667 / 0.819 |
| R2 | 0.696 [0.633, 0.755] | 0.835 [0.785, 0.881] | 0.46 | 0.758 / 0.852 | 0.676 / 0.824 |
| AgentWorld-35B-A3B (thinking off, 8k) | 0.640 [0.570, 0.701] | — | — | 0.643 / — | 0.639 / — (59 unparsed) |

Ekbasis base − AgentWorld (balanced): **+0.080 [+0.002, +0.161]**; R1 +0.068 [−0.011, +0.146]; R2 +0.057 [−0.016, +0.127].

## Reading
- **Ekbasis has the neutral skill** (CI above 0.60) on real agent sessions it was never built around, above my
  pre-registered prediction (AUROC 0.65–0.80), and beats a 35B world model trained on real trajectories that spends
  ~2k tokens and ~90 s per answer. AgentWorld's CI includes 0.60.
- **R1/R2 do not move it:** AUROC 0.832–0.835 vs 0.833 (identical ranking; R2's lower balanced accuracy is a
  threshold shift at 0.5). The week's training gains are in the domains we generate (factory, git, synthetic
  horizons), not yet in raw agent sessions.
- Next lever (proposed): render our executed factory scenarios as raw session transcripts (listing/reading commands
  with their exact outputs, then the next command) so training sees what agents actually see; neutral stays an
  untouched one-shot test.

Operational: first Ekbasis run OOMed (eval batch 48 × ~4k tokens); rerun with batch 6. Analysis fix before any
Ekbasis score: AgentWorld's unparsed answers now count as wrong (they were read as "no").
