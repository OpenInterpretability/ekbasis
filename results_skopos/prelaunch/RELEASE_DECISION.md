# Release decision — Ekbasis-Skopos-27B

**2026-10-16, ~11:55 UTC (08:55 BRT). Decided by Caio Vicentino (owner): release, with the pre-launch release blocker
below declared.** Recorded by the main thread from the conversation; the numbers are read from
`prelaunch_out/compare/P8.json`, `P8_same_machine.json` and `P8_context.json`.

## The blocker (PRELAUNCH_EVAL.md, Part A rule, sealed 2026-10-15 23:36:26Z)
P8, short checks, paraphrased wording (120 items): Ekbasis-Skopos-27B 113/120 (94.2%) against Ekbasis-27B's published
117/120 (97.5%); difference −3.3 points, paired bootstrap 95% CI [−6.7, −0.8] (2,000 resamples, seed 20261015),
entirely below 0. Under the rule, a release blocker that goes to Caio with the numbers.

What was shown to Caio before the decision:
- The interval rests on 4 discordant items, all against Skopos (4 that only Skopos gets wrong, 0 the other way); the
  exact McNemar test on the same pairs gives p = 0.125. One of the 4 is at confidence ≥ 0.99 (machines); 2 are in a
  never-trained family (machines), 1 lamps, 1 containers.
- Original wording: 116/120 vs 115/120 (+0.8, CI [−1.7, +4.2]); both wordings: 229/240 vs 232/240 (−1.25, CI [−3.3, +0.8]).
- Same-machine control, run on Caio's request: Ekbasis-27B bf16 served on the same RTX PRO 6000 reproduced its
  published answers item for item (240/240 right/wrong identical; 117/120 and 115/120); the comparison against that run
  is identical. Not a serving or hardware artifact.
- The weighing: the gains (git guard false alarms on held-out command types 49 → 26 of 799, p < 0.001; executed
  scenarios +5.7; real git sequences +2.6; fresh never-trained worlds +1.6; real repositories P10 95/96 vs 92/96, 28/28
  work-losing caught, 0 false alarms) against the regressions (confident errors in never-trained world families +0.75
  per 100 and ECE +0.009, both significant; P8 paraphrase −3.3, not significant by the exact test), with the caveat that
  the largest gains are in-distribution.

## Conditions of the decision
- The blocker is declared wherever the results are summarized: the model card, the evaluation report's pre-launch
  section, the release page, the announcement; worded as above (the pre-registered rule fired; the exact test does not
  reject; the same-machine control reproduces the reference; consistent with the declared confident-error limitation).
- The remaining pre-launch items that can block (P4 long chains, P9 planning by search, P12 intent replay) are completed
  and checked before any public step; another blocker goes back to Caio before anything is published.
- Release date 2026-10-16; hosted API switch 2026-10-30 (the 14-day model-change policy); MLX build not released.

## Second decision — the hosted switch on release day
**2026-10-16, ~14:05 UTC (11:05 BRT). Decided by Caio: the hosted API switches to Ekbasis-Skopos-27B-INT4 today, not
on 2026-10-30.** The hosted Ekbasis-27B-INT4 is retired from the API (the 5090 holds one model); its weights stay public.
This is shorter notice than the 14 days the published model-change policy promises; the policies page, the changelog,
the cards and the announcement say so plainly, with the time of the switch. The switch follows repos/PRODUCTION_SWAP.md:
a staging rehearsal on the RTX PRO 6000 with production's stack (smoke, 500-item equivalence, release-protocol subset)
first; /root/Ekbasis-27B-INT4 kept on the 5090 as the rollback. After the launch is checked and everything is backed up
on Hugging Face and GitHub, the RTX PRO 6000 is shut down; pre-launch items that had not run by then (phases E and F:
the Ekbasis-27B INT4 same-machine controls, the preflight substitute, P11 memory caps; A7 unless it runs before) are
reported as not run.
