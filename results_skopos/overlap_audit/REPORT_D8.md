# D8 overlap audit — Ekbasis-Skopos-27B (workstream B), final report, 2026-10-16

Saved by the main thread from WS-B's message (its harness blocks report files), with two facts added at the end.
Scripts: `audit/audit_overlap_skopos.py`, `audit/recompute_without_overlap.py`. Outputs: `out/overlap.json`,
`out/recomputed.json`, `out/clean/*_clean.json` (13 twins, copied into `results/` by the main thread), 
`inputs/calib_scores_ekbasis_int4.jsonl` (byte-identical to `github/ekbasis/results_skopos/runs/calibration/`; reproduces
`calib_fit_ekbasis_int4.json` exactly). Run order: audit (~2 min) → recompute (~10 min; adds a "recomputed" pointer to
overlap.json) → `certified_carryover/overlap_step.py exclude`.

## Findings
1. **The git sandbox's held-out command types were trained by Skopos.** git3_test_held and guard_held test
   `git rebase <branch>` and `git restore --source=HEAD~1 <file>`. Ekbasis-27B's ftrain_mixG3 contains neither (the
   held-out claim stands for Ekbasis-27B). Skopos' later stages contain them through the shell/git factory:
   `git rebase <branch>` in 945 rows (v45rx_git 424, v49_fx 77, fac_rx 444); `git restore --source=<branch> <file>` in
   815 rows (459, 27, 329); different repositories, and the factory uses a branch as `--source`, not HEAD~1. Item-level
   overlap is 0, but "command types never seen in training" is false for Skopos.
2. **No published conclusion changes.** Every number from a set with flagged items was recomputed with the original
   metric code and bootstrap, after first reproducing the published value on all items (21 of 21). The release read
   (bf16, INT4, FP8, MLX), PREREG_R4 "R4 replaces the first Skopos", CONFIRM_FTEST, PREREG_IMAGE "preserved", the
   quantization gates and the confident-errors confirmatory question hold under the primary and the stricter
   sensitivity rule. The A2 prediction (±1 point) stays "not met", as published.
3. **Zero overlap (primary rule):** every release-protocol criterion set (git3 known/held, multi_test_testfam,
   ftest_family, guard_known/held), ftest_fresh, git_long, git_long_val, sess_val, latent_test, awb_neutral, fval_git3,
   m3val, certified_carryover (0 of 2,781; best J < 0.2).
4. **Overlap sits in in-distribution sets:** fhorizon 547/1,375 (whole small worlds: grid 227/280, seq 172/193);
   multi_test_trainfam 291/600 (reported only); ce_items 5,381/15,008 (T 4,153, H 1,228, U 0); fac_val 105/3,983
   (100 of its 140 Python items, 6 of them identical to v49_fx rows of the first Skopos; the other 5 are git items);
   image 5/400. Flagged items are not answered better, except fac_val's near-trivial Python slice (R4 100%, first
   Skopos 98.6%, Ekbasis-27B 97.9%).
5. **Wording and data hygiene:** the calibration test (2,500) is not held-out — git_long, guard_known and fac_val come
   from generators that made training rows. fac_val's build-time firewall (run_r2.sh) checked only fac_rx, not the v49f
   files. The old overlap_audit_r4.json did not include the v49f files and missed the 6 identical prompts.

## Method
Rules of Ekbasis-27B's 2026-10-06 audit (ekbasis `results/overlap_audit/scripts/pi_overlap.py`, origin/main 941968e),
same tokenizer, word 8-grams, layout, thresholds, PYTHONHASHSEED=0. identical = normalized floor equals a training floor
or ceiling; near = ≥ 10 non-layout 8-grams and Jaccard ≥ 0.5 against ONE training text, J = |s∩t| / (|s| + |t| − |s∩t|),
s = the evaluation floor's 8-grams minus the set's layout, t = all the training text's 8-grams, layout = 8-grams in ≥ 20%
of a sample of the set's floors plus its question texts; same prompt + question (+ answer) as pi_sameitem.py.
Changes from the 06/10 code (each can only flag more): exact best match against every training text sharing any 8-gram
(not the top 20; sparse incidence over 49,306 unique evaluation prompts × 23.5 M kept training 8-gram hits over 437,253
unique training texts; 9.05e9 exact posting operations; no MinHash); near-duplicates also searched among ceilings;
sensitivity rule "near_symmetric" (layout also removed from the training text); `--check` re-derives J from raw text for
every flagged item (passed). Exclusion sets: primary = identical OR near ("flagged"); sensitivity = primary OR
near_symmetric. Validation: with the 06/10 settings the code reproduces Ekbasis-27B's published audit exactly
(ce_items 5,378 flagged, 174 identical, 104 same prompt+question; multi_test_trainfam 291, 5 identical; clean
multi_trainfam 93.6 [91.3, 95.8]); exact best match adds 1 ce item, ceilings 2.

Training corpus: 13 files, 345,957 distinct rows, 437,253 distinct texts, each verified by sha256 or git blob against HF;
every row counts as trained (conservative: R4 sampled ~9.6k rows). ftrain_mixG3 (machine file, 198,276 rows incl. 7,423
withheld replay rows; ekbasis-fac-data@ee92bd6e60); mined_wide 7,458; mined_chain 555; v49f extras v45_v44git 2,612,
v45rx_shell 19,032, v45rx_git 17,189, v45rx_sql 14,630, v46_anchor 2,212, v49_anchor2 1,398, v49_fx 17,625; R4
ftrain_v50p 195,188 (exactly 4,335 rows not in the full mixG3: its floorPL), git_plan_train 6,048, fac_rx 55,469
(ftrain_v50p + git_plan_train + fac_rx has exactly ftrain_r2's sha256 f1500d57, R4's TRAIN). R1/R3 are siblings, not
ancestors (excluded); Eikos' own data out of scope. Replay rows (incl. withheld) share at most 2 8-grams with any
evaluation prompt. Evaluation corpus: 20 sets with sha256; the image set regenerated with image_served.py's code matches
the served run's 400 (family, changed, gold) triples; the calibration test and frontier subsets covered via parents;
T3c is not dataset items.

## Per set (items | identical | same prompt+question+answer | flagged | sensitivity | stage holding the match)
| Set | Items | Identical | Same item | Flagged | Sensitivity | Stage |
|---|---|---|---|---|---|---|
| git3_test_known | 1,482 | 0 | 0 | 0 | 25 | — |
| git3_test_held | 1,623 | 0 | 0 | 0 | 6 | — |
| guard_known | 4,486 | 0 | 0 | 0 | 77 | — |
| guard_held | 6,394 | 0 | 0 | 0 | 27 | — |
| multi_test_trainfam | 600 | 5 | 5 | 291 | 313 | Ekbasis-27B |
| multi_test_testfam | 600 | 0 | 0 | 0 | 0 | — |
| ftest_family | 1,080 | 0 | 0 | 0 | 0 | — |
| ftest_fresh | 5,385 | 0 | 0 | 0 | 0 | — |
| fac_val | 3,983 | 6 | 3 | 105 | 170 | first Skopos 42 (6 identical), R4 new rows 63 |
| git_long | 900 | 0 | 0 | 0 | 0 | — |
| git_long_val | 1,800 | 0 | 0 | 0 | 0 | — |
| sess_val | 730 | 0 | 0 | 0 | 0 | — |
| fhorizon | 1,375 | 0 | 0 | 547 | 584 | Ekbasis-27B |
| latent_test | 4,320 | 0 | 0 | 0 | 0 | — |
| awb_neutral | 455 | 0 | 0 | 0 | 0 | — |
| fval_git3 | 1,524 | 0 | 0 | 0 | 47 | — |
| m3val | 300 | 0 | 0 | 0 | 0 | — |
| ce_items | 15,008 | 174 | 104 | 5,381 | 5,697 | Ekbasis-27B 5,380, R4 1 |
| image | 400 | 0 | 0 | 5 | 21 | Ekbasis-27B |
| certified_carryover | 2,781 | 0 | 0 | 0 | 0 | — |

Matches are mostly template-level (the same small world, not the same item): fhorizon 452/547 share the rules
paragraph, 80 the start state, 119 the actions; ce_items 3,972/5,207 the rules paragraph, 502 the state; the
sensitivity-only hits in the git sets share the rules and often the short command list, never the state.

## In-distribution vs held-out (overlap.json sets[*].distribution)
In-distribution (same generator made training rows; unseen seeds): git3_test_known, guard_known (gitbox3 known types:
floorG3, floorGA, floorPLG); multi_test_trainfam; fac_val (the factory of fac_rx/v45rx/v49_fx); git_long, git_long_val
(gitbox3, the generator of floorPLG; for Ekbasis-27B git_long is length extrapolation); sess_val (fac_val's
single-command shell rows; the session layout was trained only by the R3 sibling); fhorizon (worldgen training
families; 20 actions never trained); m3val; the calibration test (all 2,500). Held-out: multi_test_testfam,
ftest_family, ftest_fresh (worlds in no training file); latent_test (LATENT worlds); awb_neutral; certified_carryover
(capability suites; the F factory was firewalled against them). Mixed: fval_git3 (gitbox3 774 + factory-3 300 +
never-trained Track/Tally 450; also R4's checkpoint-selection and the calibration-fit set); ce_items (T in-distribution,
H held-out question type, U never-trained); image (trained families, untrained modality). git3_test_held and
guard_held: held out of the generator, not of training (finding 1).
fac_val's Python slice: run_r2.sh dropped val rows whose floor is in fac_rx (436 of the 576 raw Python rows, none of
the other families); the 140 left come from 10 of 35 templates; 111 are identical to a training prompt once digits are
masked, 100 flagged. fac_val without the Python slice: R4 93.81 / first Skopos 92.25 / Ekbasis-27B 88.06; R4 − first
Skopos +1.56 [+0.96, +2.16].

## Recomputed (published → primary → sensitivity)
- Release read: criterion sets have 0 primary flags (identical numbers). Sensitivity: bf16 git v3 96.94 vs 96.62
  (3,074 items); guard known false alarms 26/843 vs 37/843; held 26/795 vs 49/795; checks equal the published ones for
  all 4 builds (8/9, criterion 3 ftest fails as before; MLX as published).
- multi_trainfam changed (reported only): Skopos 95.01 → 96.60 [94.90, 98.09] (471) → 96.77; Ekbasis-27B 92.35 → 93.63 → 93.55.
- r4_vs_skopos_v49f fac_val: 94.02 / 92.47 / 88.40 → 93.86 / 92.32 / 88.14; R4 − first Skopos +1.56 [+0.95, +2.18] →
  +1.55 [+0.98, +2.17] → +1.57 [+0.94, +2.20]. fhorizon 86.76 / 86.76 / 86.04 → 87.92 / 88.65 / 87.20 (828); R4 − first
  Skopos 0.00 [−1.31, +1.31] → −0.72 [−2.54, +0.85] → −0.76 [−2.40, +1.01] — not "worse" under the rule; "R4 replaces"
  holds (guard −0.69 / −1.05; sensitivity −0.70 / −1.19).
- r4_vs_ekbasis27b_trainer: fac_val +5.62 [4.75, 6.55] → +5.72 [4.82, 6.68]; fhorizon +0.73 [−0.58, +2.11] → +0.72
  [−1.09, +2.29]; rest unchanged. ftest_fresh, awb_neutral, ftest_fresh_int4/fp8: 0 flagged.
- Image: image prompt +1.0 [−2.0, +4.25] → +1.01 [−2.03, +4.05] (395) → +1.06 [−2.11, +4.22]; read +2.25 [+0.5, +4.25]
  → +2.28 [+0.51, +4.30]; "preserved" holds.
- Calibration test, T as published, 2,500 → 2,482 (18 fac_val items out); acc / confident errors per 100 at T1 → fitted
  T: INT4 95.12 / 3.28 → 1.72 becomes 95.08 / 3.30 → 1.73; Ekbasis INT4 91.08 / 6.24 → 3.88 becomes 91.02 / 6.29 → 3.91;
  bf16 (1.62) 3.26 → 1.97; FP8 (1.64) 3.10 → 1.73; MLX (1.65) 3.71 → 1.85; ECE moves ≤ 0.0006. A sensitivity refit
  would give T 1.68 (Skopos INT4) and 1.56 (Ekbasis).
- Confident errors: T error −0.63 [−1.03, −0.22] → −0.60 [−1.13, −0.03] (3,019); confident wrong −0.28 → −0.33
  [−0.79, +0.17]. H −2.06 [−3.11, −0.97] → −1.93 [−3.62, −0.24]; sensitivity −1.71 [−3.51, +0.09] (CI touches 0). U
  unchanged (0 flagged): confident wrong +0.75 [+0.28, +1.23], changed +1.19 [+0.52, +1.89] — the card's limit stands.
  Confirmatory T vs U: +17.5 [+10.6, +24.7] → +17.1 [+4.8, +29.0], still "confirmed"; after cleaning the family-median
  condition rests on only 2 trained families with ≥ 10 errors.
- Quantization gates identical; sensitivity INT4 97.43 (pass), FP8 98.56 (pass), MLX 95.85 (missed, as published).
- Frontier (not in the card): fhorizon subset 300 → 173; AgentWorld − Ekbasis-27B +0.127 [0.069, 0.185]; holds.
- Flagged vs clean accuracy, Skopos: fhorizon 85.0 vs 87.9; ce T 95.4 vs 97.7; ce H 92.3 vs 88.3; multi_trainfam
  97.0 vs 97.8 — the overlap did not inflate the published numbers (clean fhorizon rises because grid and seq drop out).
Clean twins keep the original schema plus "clean" = {audit, rule, excluded_n, excluded_ids}; calibration twins keep the
published T and carry a "note".

## Card: may / must change (as sent to workstream D)
May claim (overlap paragraph): every evaluation set checked against every training row of the lineage (345,957 rows
of 13 files incl. withheld replay rows); no item of the release-protocol criteria, the fresh confirmation, the real git
sequences, agent sessions, latent-state worlds, neutral agent turns or the certified-mode check overlaps a training
row; overlap found in fac_val, fhorizon, image, ce_items (none in never-trained families) and multi_test_trainfam;
numbers on those sets given without them; every pre-registered conclusion holds. Fine to keep: "never-trained
families" (testfam, ftest_family, ftest_fresh), "never trained on" (neutral), "worlds no stage trained on" (latent_test).
Must change: (a) model-index name → "command types held out of the git sandbox's training rows"; (b) the guard bullet
naming the two command forms and that Skopos' factory rows contain both in other repositories; (c) calibration on 2,482
items from generators that also made training rows, numbers from the clean twins; (d) marks from overlap.json; (e)
never "every evaluation item is firewalled", never "held-out" for fac_val, git_long, git_long_val, sess_val, fhorizon or
the calibration test; (f) long-chain limit 87.9% on 828 clean items, in-distribution; (g) the Python-slice sentence.

## Other caveats
- R1 → R2 → R4 were chosen by pre-registered rules on fac_val, git_long and git_long_val, the same sets the "what this
  version adds" table reports; the independent evidence is ftest_fresh and the neutral turns.
- Not covered: Eikos-27B's own decision data; T3c (not dataset items).
- Generator facts verified by WS-B: the command forms in the factory rows, world labels, fhorizon/floorPL
  (build_data.py), the git generators and seeds, the fac_val firewall, sess_val ⊂ fac_val; other seed/line references
  are from the code as read by a subagent.

## Added by the main thread
- certified_carryover: 0 of 2,781 questions flagged; `certified_carryover/data/overlap_excluded.json` records the audit
  at sha256 c1019f3a26f3 (the post-recompute overlap.json). The exclude step was run by the main thread after
  PREREG_CERTIFIED_CARRYOVER.md was sealed (00:56 UTC, 0 flagged); an identical earlier run by WS-B (~00:20 UTC, before
  the seal; same file, same 0) is noted here for completeness — no request had been made to any server.
