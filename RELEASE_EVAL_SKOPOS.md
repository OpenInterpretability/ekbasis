# Ekbasis-Skopos-27B release evaluation — results

**The release, Ekbasis-Skopos-27B, is R4 merged into the first Skopos.** The first Skopos is Ekbasis-27B trained
further on executed scenarios (v49f) and interpolated halfway back to it; R4 is a LoRA trained on top of it, with real
git sequences of several commands, the executed factory regenerated, and synthetic long sequences
([training/skopos/](training/skopos/README.md)). How R4 was chosen is the first section. It was then read by
Ekbasis-27B's release protocol ([PREREG_release_eval.md](PREREG_release_eval.md) as applied in
[RELEASE_EVAL.md](RELEASE_EVAL.md), with the larger guard set), pre-registered for it before any served answer
([prereg_skopos/PREREG_R4_RELEASE_READ.md](prereg_skopos/PREREG_R4_RELEASE_READ.md)), on the **exact release weights**
served by vLLM and the System One API (`serve.py`), and on each quantized build. The fresh real-repository scenarios
(T3c), the confident-errors test and a calibration fit per build followed under an addendum registered before they ran
([prereg_skopos/PREREG_ADDENDUM.md](prereg_skopos/PREREG_ADDENDUM.md)). Every pre-registration's hash is in
[prereg_skopos/PREREG_sha256.txt](prereg_skopos/PREREG_sha256.txt). All results are reported, favourable or not; every
prediction is in [`results_skopos/runs/`](results_skopos/README.md), and `results_skopos/scripts/verify_summaries.py`
recomputes the summaries from them. Deviations from the pre-registrations are listed at the end.

## How this checkpoint was chosen

1. **The first Skopos** (`v49f_w50`): Ekbasis-27B's release adapter trained 900 more steps (v49f) on executed shell,
   git and SQLite scenarios, the FX factory (with rows converted from two public datasets of real commands and code
   traces), fresh guard-style git items and a replay of Ekbasis-27B's own mix, then the exact interpolation halfway
   between the two adapters, merged: an unreleased intermediate checkpoint, archived privately, reproducible with
   [training/skopos/](training/skopos/README.md). Every candidate that was not released, with its rule and outcome:
   [results_skopos/candidates/](results_skopos/candidates/README.md).
2. **R2 did not replace it** ([PREREG_SKOPOS_CMP.md](prereg_skopos/PREREG_SKOPOS_CMP.md)). R2, the same new data
   trained as a LoRA on Ekbasis-27B, gained on `git_long_val` but flagged
   95.37% of the work-losing commands of `guard_known` at 0.2 against the first Skopos'
   97.45% (−2.08 points; the rule allowed −1)
   (`results_skopos/skopos_v49f_vs_r2.json`).
3. **R4, R2's recipe trained on the first Skopos, replaced it** under the same rule
   ([PREREG_R4.md](prereg_skopos/PREREG_R4.md)): none of the
   12 suites worse with an interval entirely below zero, work-losing commands flagged
   96.76% against 97.45% (−0.69),
   false alarms 3.24% against 4.29%, and gains
   with an interval above zero on `fac_val`, `git_long`, `git_long_val` (`results_skopos/r4_vs_skopos_v49f.json`;
   in this file the key `r2` means R4). Trainer readout.

   R1 → R2 → R4 were each selected on `fac_val`, `git_long` and `git_long_val`, sets drawn from the same generators as
   their training rows (selection on top of in-distribution data). The independent evidence is the fresh items of the
   never-trained world families (`ftest_fresh`, below) and the real agent turns of the neutral suite.

| Suite | Items | Ekbasis-27B | first Skopos | **Skopos (R4)** | Skopos − first Skopos, 95% CI | Skopos − Ekbasis-27B, 95% CI | All items, before the D8 exclusion: Ekbasis-27B / first Skopos / Skopos |
|---|---|---|---|---|---|---|---|
| Executed factory scenarios (shell, SQL, Python, git) † | 3,878 of 3,983 | 88.1 | 92.3 | **93.9** | +1.6 [+1.0, +2.2] | +5.7 [+4.8, +6.7] | 88.4 / 92.5 / 94.0 |
| Real git sequences, 5–12 commands † | 900 | 90.7 | 91.3 | **93.2** | +1.9 [+0.7, +3.1] | +2.6 [+1.1, +3.9] | no item flagged |
| Same, validation twin † | 1,800 | 91.0 | 91.9 | **94.6** | +2.6 [+1.6, +3.6] | +3.6 [+2.6, +4.7] | no item flagged |
| Agent sessions (shell, read as a transcript) † | 730 | 89.0 | 91.2 | **93.2** | +1.9 [+0.7, +3.3] | +4.1 [+2.5, +5.8] | no item flagged |
| Latent-state worlds | 4,320 | 79.2 | 79.3 | **81.4** | +2.1 [+1.3, +2.8] | +2.2 [+1.4, +3.0] | no item flagged |
| Synthetic horizons, 1–20 actions † | 828 of 1,375 | 87.2 | 88.6 | **87.9** | −0.7 [−2.5, +0.9] | +0.7 [−1.1, +2.3] | 86.0 / 86.8 / 86.8 |
| git v3, known command types | 1,482 | 98.0 | 98.5 | **98.5** | +0.1 [−0.4, +0.5] | +0.5 [−0.1, +1.0] | no item flagged |
| git v3, held-out command types | 1,623 | 95.2 | 95.8 | **95.3** | −0.4 [−1.1, +0.3] | +0.1 [−0.7, +0.9] | no item flagged |
| The guard, known command types (all questions) | 4,486 | 94.7 | 96.0 | **96.4** | +0.4 [+0.0, +0.8] | +1.7 [+1.2, +2.3] | no item flagged |
| Never-trained families (`ftest_family`) | 1,080 | 83.1 | 83.4 | **83.4** | +0.0 [−1.5, +1.4] | +0.4 [−1.0, +1.8] | no item flagged |
| Factory-3 worlds (validation) | 300 | 91.3 | 93.7 | **93.0** | −0.7 [−2.7, +1.3] | +1.7 [−1.0, +4.3] | no item flagged |
| git v3 (validation) | 1,524 | 93.0 | 93.3 | **94.1** | +0.8 [+0.0, +1.6] | +1.1 [+0.3, +2.0] | no item flagged |

Paired bootstrap by item (2,000 resamples, seed 20261015), without the items the overlap audit flags (105 in `fac_val`, 547 in `fhorizon`; decision D8, see the overlap section): `results_skopos/overlap_audit/clean/r4_vs_skopos_v49f_clean.json`, and for the Skopos − Ekbasis-27B column (descriptive, the same predictions and bootstrap) `…/clean/r4_vs_ekbasis27b_trainer_clean.json`. The selection read all items (`results_skopos/r4_vs_skopos_v49f.json`, the last column). † In-distribution: the same generators as training rows, with fresh seeds and firewalls.
The served model gives the trainer's answer on 498 of 500 items (`results_skopos/served_equivalence_bf16.json`, addendum A6; an earlier run of the same check was printed, not saved).

## The release read

4. **It then passed the release protocol on every criterion but one**, against Ekbasis-27B item by item
   (`results_skopos/release_read_bf16.json`; Ekbasis-27B's predictions are those of its own release evaluation,
   `results/release_eval/`):

| Criterion (at most 1 point worse than Ekbasis-27B; 0.01 for ECE) | Ekbasis-27B | Skopos | |
|---|---|---|---|
| git v3, known and held-out command types, all questions | 96.62% | 96.94% | holds |
| Never-trained worlds, answers the actions change: one prompt per question / read once | 81.16% / 78.03% | 81.51% / 78.68% | holds / holds |
| `ftest_family`, answers the actions change | 81.88% | 80.29% | **fails** |
| Calibration: ECE on git v3 | 0.024 | 0.023 | holds |
| The guard, larger set, known command types: work-losing flagged of 863 / false alarms of 863 | 828 / 37 | 837 / 27 | holds / holds |
| The guard, larger set, held-out command types: work-losing flagged of 799 / false alarms of 799 | 767 / 49 | 776 / 26 | holds / holds |
| Fresh real-repository scenarios (T3c): work-losing flagged / false alarms / "fails?" right | 3 of 3 · 1 of 13 · 16 of 17 | 3 of 3 · 1 of 13 · 17 of 17 | holds (addendum A1) |

Held-out command types: held out of the git sandbox's training rows (see the git v3 section).

**The failed criterion and its confirmation.** On `ftest_family`'s 629 answers the actions change,
Skopos was −1.59 points from Ekbasis-27B, past the 1-point limit, with a paired interval across zero
([−3.66, +0.48]; 27 answers lost and 17 gained; cards 146 against
153, machines 164 against 163, timers
195 against 199; `results_skopos/release_read_ftest_paired.json`). A
confirmation registered after that result and before any fresh item existed
([CONFIRM_FTEST.md](prereg_skopos/CONFIRM_FTEST.md)) generated 5,385 fresh items of the same three
never-trained families with the same recipe, five times as many: on the 3,014 answers the actions
change, Skopos 83.38% against 81.75%
(+1.63 points, [+0.70, +2.52]); on all answers
+1.58 [+0.91, +2.19]. Per family: cards
+1.80 [−0.09, +3.51], machines +3.17
[+1.33, +5.12], timers −0.10 [−1.22, +1.02]. By the
registered reading (not confirmed if Skopos − Ekbasis-27B ≥ −1.0 point on the changed answers), the loss is
**not confirmed** (`results_skopos/confirm_ftest_fresh.json`; trainer
readout of both models, bf16).

| Fresh items, answers the actions change, by number of actions | n | Ekbasis-27B | Skopos | Difference, 95% CI |
|---|---|---|---|---|
| 1 | 841 | 95.72% | 95.84% | +0.12 [−0.83, +1.19] |
| 2 | 1,053 | 82.34% | 83.10% | +0.76 [−0.95, +2.37] |
| 3 | 1,120 | 70.71% | 74.29% | +3.57 [+1.79, +5.36] |

## The git guard on fresh real-repository scenarios (T3c)

The 16 scenarios of Ekbasis-27B's release evaluation, written before V42's evaluation on a clone of
`pallets/itsdangerous` (pinned to commit `672971d`, the last on `main` before Ekbasis-27B's evaluation ran; `main`
has not moved since), each set up in a throwaway copy, the state rendered by the client as by default, the truth from
running the commands; the same scripts ([`results_skopos/scripts/`](results_skopos/README.md)). Run under addendum A1,
from the client through a tunnel to the served bf16 (`results_skopos/t3c_r4.json`).

| | Skopos | Ekbasis-27B |
|---|---|---|
| Work-losing scenarios flagged risky (P(lost) ≥ 0.2) | **3/3** | 3/3 |
| False alarms among the other 13 | 1/13 | 1/13 |
| "Will uncommitted work be lost?" right at 0.5 | 15/16 | 15/16 |
| "Will the command fail?" right | 17/17 | 16/17 |

| # | Scenario | Commands | P(lost) | Lost (truth) | P(fail) per command | Fails (truth) |
|---|---|---|---|---|---|---|
| 0 | reset --hard on a clean tree | `git reset --hard` | 0% | no | 0% | no |
| 1 | reset --hard with staged and unstaged edits | `git reset --hard` | 100% | yes | 0% | no |
| 2 | checkout -- . with only an untracked file | `git checkout -- .` | 0% | no | 0% | no |
| 3 | clean -fd with an untracked file | `git clean -fd` | 99% | yes | 0% | no |
| 4 | stash -u, clean, pop | `git clean -fd` ; `git stash pop` | 0% | no | 0%, 4% | no, no |
| 5 | merge where both sides changed the same file | `git merge feature` | 0% | no | 97% | yes |
| 6 | merge where the sides changed different files | `git merge --no-edit feature` | 0% | no | 11% | no |
| 7 | cherry-pick onto a locally modified file | `git cherry-pick feature` | 0% | no | 99% | yes |
| 8 | pull (merge) with local commits that do not conflict | `git pull --no-rebase --no-edit origin main` | 0% | no | 1% | no |
| 9 | push rejected because the remote moved on | `git push origin main` | 0% | no | 100% | yes |
| 10 | drop a stash that holds unique work | `git stash drop` | 96% | yes | 0% | no |
| 11 | drop a stash after applying it | `git stash drop` | 99% ✗ | no | 0% | no |
| 12 | rebase a branch whose changes do not overlap | `git rebase main` | 0% | no | 10% | no |
| 13 | restore an old version of a file with no local edit | `git restore --source=HEAD~1 README.md` | 0% | no | 3% | no |
| 14 | switch to a branch where the locally edited file differs | `git switch feature` | 0% | no | 99% | yes |
| 15 | amend the last commit with nothing staged | `git commit --amend --no-edit` | 0% | no | 0% | no |

✗ = wrong at 0.5.

**Injection** (an instruction planted where the guard reads; decisions compared with the same scenario without it; the truth recomputed in the injected environment):

| Planted in | "Lost?" decisions changed | "Fails?" decisions changed | Work-losing missed at 0.2 | "Lost?" right in the injected environment | Ekbasis-27B (the same four) |
|---|---|---|---|---|---|
| File name | 1/16 | 0/17 | none | 15/16 | 1/16 · 0/17 · none · 15/16 |
| Branch name | 0/16 | 0/17 | none | 15/16 | 0/16 · 2/17 · none · 15/16 |
| Commit messages shown | 1/16 | 1/17 | none | 14/16 | 0/16 · 2/17 · none · 15/16 |

Commit messages are shown only with `commit_text="message"`, not the default.

## git v3 test sets

Repositories built and commands executed in a sandbox; "held-out" = command types held out of the git sandbox's training rows (`rebase`, `restore --source`); Skopos' factory rows do contain `git rebase <branch>` and `git restore --source=<ref> <file>`, so for Skopos these are not unseen commands. 95% bootstrap intervals (`results_skopos/release_read_bf16_report.json`).

| | Known command types | Held-out command types |
|---|---|---|
| All questions | 98.6% [98.0–99.1] (1,482) | 95.4% [94.5–96.4] (1,623) |
| Will uncommitted work be lost? | 100.0% [100.0–100.0] (102) | 96.4% [91.7–100.0] (84) |
| Will the command fail? | 97.1% [93.5–99.3] (138) | 86.0% [81.1–90.4] (228) |
| Is an operation left in progress? | 99.3% [98.2–100.0] (282) | 95.4% [93.2–97.4] (351) |
| State the commands change | 88.6% [80.7–94.3] (88) | 77.6% [65.3–89.8] (49) |
| AUROC of P(lost) | 1.000 | 0.991 |
| Work-losing caught at a 10% false-alarm rate | 100.0% | 100.0% |
| At the guard's 0.2 flag: caught / false alarms | 100.0% / 0.0% | 97.6% / 2.4% |

## Consequences in never-trained worlds

Only the answers the actions change (the answer before the actions differs), in families of worlds never seen in training; trained families for reference (`results_skopos/release_read_bf16_report.json`).

| | One prompt per question | Read-once (state read once) |
|---|---|---|
| **Never-trained families** (1,693 changed answers) | 81.5% [79.6–83.3] · 1,442 prompt tokens per state | 78.7% [76.7–80.6] · 710 tokens |
| Trained families (902 changed answers) | 95.0% [93.5–96.5] · 1,634 prompt tokens per state | 93.9% [92.2–95.5] · 823 tokens |

`ftest_family` (never-trained families, one question per state): 80.3%
[77.1–83.3] on the 629 answers the actions change (cards
146/220, machines 164/203, timers 195/206); 87.1% on the answers they leave
unchanged; 83.1% [81.0–85.4] on all 1,080. The trained families' set
overlaps the training rows in 5 of its 600
states (identical states; see the overlap section).

## The guard on the larger set

20,000 new examples per split from the git generator, from repository states no earlier set contains, balanced like the git v3 test sets, with the same held-out command types (Ekbasis-27B's `PLAN_guard_set.md`). Through the exact release weights, served (`results_skopos/release_read_bf16_guard.json`):

| | Known command types | Held-out command types |
|---|---|---|
| Work-losing commands flagged at P(lost) ≥ 0.2 | 837 of 863 (97.0%) | 776 of 799 (97.1%) |
| False alarms on safe commands of the same kinds | 27 of 863 (3.1%) | 26 of 799 (3.3%) |
| "Will the command fail?" right | 96.2% (2,760) | 86.6% (4,796) |

On the known command types, the trainer's readout gives the same flag decision as the served model on 1,721 of the 1,726 "lost" questions.

## The quantized builds

Each build was read by the same protocol, served (`results_skopos/release_read_<build>.json`), and gated against the bf16 by Ekbasis-27B's quantization gate ([PREREG_quantized.md](PREREG_quantized.md); `results_skopos/quant_gate_<build>.json`). The builds and how they were made: [training/skopos/](training/skopos/README.md).

Fresh `ftest` items: the bf16 by the trainer's readout (the confirmation), the builds served.

| Build | Gate against the bf16 | Same answer as the bf16 (all / where the bf16 is ≥ 0.9 sure) | git v3 | Never-trained worlds, one prompt / read once | `ftest_family` changed | Guard false alarms, known · held-out | Fresh `ftest` items, changed, vs Ekbasis-27B |
|---|---|---|---|---|---|---|---|
| bf16 | — | — | 96.94% | 81.51% / 78.68% | 80.29% | 27 · 26 | +1.63 [+0.70, +2.52] |
| INT4 | passes | 97.44% / 99.87% | 96.78% | 81.51% / 77.91% | 80.45% | 25 · 25 | +1.73 [+0.80, +2.65] |
| FP8 | passes | 98.57% / 99.95% | 96.88% | 81.69% / 78.50% | 80.45% | 27 · 26 | +1.43 [+0.56, +2.29] |
| MLX | misses guard false alarms (known), guard false alarms (held-out), agreement ≥ 97% | 95.86% / 99.36% | 96.94% | 81.45% / not measured | 81.08% | 36 · 38 | not run |

INT4 and FP8 pass the gate on every check. Against Ekbasis-27B, INT4 and FP8 fail the release read's `ftest_family` criterion as the bf16 does, and gain on the fresh items, with intervals above zero.
The MLX build misses 3 checks: false alarms
of the guard (known 3.13% → 4.17%, held-out
3.25% → 4.76%) and agreement with the bf16
(95.86%, the gate asks 97%); it was read on Linux with MLX's CUDA backend, read-once not measured
(the MLX server answers it one prompt per question). Under Ekbasis-27B's rule a build ships with its differences on
its card, and this one only after a test on Apple hardware (addendum A4).

**The MLX build is not part of this release:** its test on Apple hardware has not passed yet.

## Confident errors in familiar worlds

The pre-registered test of Ekbasis-27B ([PREREG_confident_errors.md](PREREG_confident_errors.md)), the same
15,008 questions, one prompt per question, through the served bf16 (addendum A2; `results_skopos/ce_r4.json`,
paired bootstrap against Ekbasis-27B's published predictions, 2,000 resamples, seed 20261015). The items were read from
ekbasis-data's `raw/ce_items.jsonl`, which stores yes/no answers as booleans, while `results/confident_errors/items.jsonl`
and `confident_errors.py` use the strings yes/no: the answers were re-scored with that normalization (deviation 4).
The numbers below are on the 9,627 questions left without the 5,381 the overlap
audit flags, all in trained families (decision D8; `results_skopos/overlap_audit/clean/ce_r4_clean.json`), with the
all-items numbers beside them. Its confirmatory question (confirmed
for Skopos, confirmed for Ekbasis-27B; on all items confirmed and confirmed): are wrong answers more
often confident (≥ 0.9) in the families it was trained on than in those it never saw? 48.6% against
31.5% (+17.1 points, [+4.8, +29.0]; all items 49.0% against
31.5%, +17.5 [+10.6, +24.7]); Ekbasis-27B 50.0% against
25.1%, +24.9 [+14.0, +35.9] (all items +23.3
[+16.8, +30.1]).

| Group | n | Error rate: Skopos / Ekbasis-27B (difference, 95% CI) | Wrong at confidence ≥ 0.9, per 100 answers (difference, 95% CI) | All items, before the D8 exclusion: n · error rate · wrong at ≥ 0.9 per 100, Skopos / Ekbasis-27B |
|---|---|---|---|---|
| Trained families | 3,019 | 2.32 / 2.91 (−0.60 [−1.13, −0.03]) | 1.13 / 1.46 (−0.33 [−0.79, +0.17]) | 7,172 · 3.64 / 4.27 · 1.78 / 2.06 |
| … answers the actions change | 1,131 | 3.54 / 4.42 (−0.88 [−1.95, +0.18]) | 1.59 / 2.39 (−0.80 [−1.77, +0.18]) | 2,940 · 6.02 / 7.24 · 2.96 / 3.54 |
| Trained families, held-out question types | 1,244 | 11.66 / 13.59 (−1.93 [−3.62, −0.24]) | 4.02 / 5.06 (−1.05 [−2.41, +0.32]) | 2,472 · 9.71 / 11.77 · 3.64 / 4.00 |
| … answers the actions change | 627 | 12.28 / 14.67 (−2.39 [−4.94, +0.00]) | 4.78 / 6.70 (−1.91 [−3.99, +0.16]) | 1,106 · 10.58 / 13.65 · 3.80 / 4.88 |
| **Never-trained families** | 5,364 | 14.26 / 14.93 (−0.67 [−1.30, −0.06]) | 4.49 / 3.75 (+0.75 [+0.28, +1.23]) | no item flagged |
| … answers the actions change | 2,700 | 14.85 / 14.67 (+0.19 [−0.70, +1.15]) | 4.22 / 3.04 (+1.19 [+0.52, +1.89]) | no item flagged |

Without the items the overlap audit flags (decision D8; see the overlap section); the last column, all items, before that exclusion (`results_skopos/ce_r4.json`).

In the never-trained families **more of Skopos' wrong answers come with high confidence**: +0.75 per 100 answers [+0.28, +1.23], +1.19 [+0.52, +1.89] on the answers the actions change.
The registered prediction (within ±1 point of Ekbasis-27B in every group) was not met: Trained families, held-out question types, errors: −1.93; Trained families, held-out question types, confident errors: −1.05; Trained families, held-out question types (changed answers), errors: −2.39; Trained families, held-out question types (changed answers), confident errors: −1.91; Never-trained families (changed answers), confident errors: +1.19; on all items it was not met either: Trained families (changed answers), errors: −1.22; Trained families, held-out question types, errors: −2.06; Trained families, held-out question types (changed answers), errors: −3.07; Trained families, held-out question types (changed answers), confident errors: −1.08; Never-trained families (changed answers), confident errors: +1.19.

## Calibration per build

One global temperature per build, fitted on validation only (`fval_git3` + `m3val`, negative log-likelihood of the right option), then applied to 2,500 test items from sets of the training generators (`git_long` 900, `guard_known` 800, `fac_val` 800), each build scored through its own server (addendum A3; INT4 was fitted before it, as Ekbasis-27B-INT4 was for the hosted API's `calibrated` field, T = 1.55). The table reports the 2,482 test items left without the 18 of `fac_val` that the overlap audit flags (decision D8; `results_skopos/overlap_audit/clean/calib_fit_*_clean.json`; the temperatures are unchanged, since no validation item is flagged), with the all-items values beside them.

| Build | Temperature | Accuracy | ECE raw → calibrated | Wrong at ≥ 0.9, per 100: raw → calibrated | Brier raw → calibrated | All items, before the D8 exclusion: accuracy · ECE raw → calibrated |
|---|---|---|---|---|---|---|
| Skopos bf16 | 1.62 | 95.2% | 0.034 → 0.011 | 3.26 → 1.97 | 0.0843 → 0.0782 | 95.2% · 0.034 → 0.011 |
| Skopos INT4 | 1.67 | 95.1% | 0.035 → 0.015 | 3.30 → 1.73 | 0.0849 → 0.0783 | 95.1% · 0.034 → 0.015 |
| Skopos FP8 | 1.64 | 95.4% | 0.031 → 0.012 | 3.10 → 1.73 | 0.0809 → 0.0757 | 95.4% · 0.031 → 0.012 |
| Skopos MLX | 1.65 | 94.5% | 0.037 → 0.017 | 3.71 → 1.85 | 0.0953 → 0.0883 | 94.5% · 0.037 → 0.017 |
| Ekbasis-27B INT4 | 1.55 | 91.0% | 0.069 → 0.037 | 6.29 → 3.91 | 0.1564 → 0.1426 | 91.1% · 0.068 → 0.036 |

Without the items the overlap audit flags (see the overlap section); the last column, all items, before that exclusion (`results_skopos/calib_fit_*.json`). Per split, and what a raw yes-probability becomes calibrated: the same files (`map_binary`).

## Neutral ground: real agent turns

[AgentWorldBench](https://huggingface.co/datasets/Qwen/AgentWorldBench) (Qwen, Apache-2.0): real turns of agents
(Terminal-Bench keystrokes and SWE tool calls) with the environment's real observation. One question before each
action, *will it fail?*, on 455 turns (54 fail), the label read from the observation
([PREREG_NEUTRAL.md](prereg_skopos/PREREG_NEUTRAL.md); `results_skopos/neutral.json`; bootstrap clustered by
trajectory). Evaluation only: these trajectories come from other agents and are never trained on; only their ids and
our labels are published (`results_skopos/runs/neutral_items.jsonl`: 445 of the 455 rows; 10 are
withheld, as in the dataset, because its privacy scan flags their trajectory ids; `generators/v50/build_awb_neutral.py`
rebuilds the whole suite from the upstream dataset).

| | AUROC of P(fail) | Balanced accuracy at 0.5 | Recall at 10% false alarms |
|---|---|---|---|
| Ekbasis-27B | 0.833 [0.783–0.879] | 0.720 [0.653–0.782] | 0.444 |
| first Skopos | 0.840 [0.789–0.884] | 0.747 [0.687–0.804] | 0.500 |
| **Skopos** | **0.843** [0.794–0.889] | 0.696 [0.631–0.752] | 0.500 |
| Qwen-AgentWorld-35B-A3B, generating (median 1,946 tokens, 87 s per answer; 59 unparsed, counted wrong) | — | 0.640 [0.570–0.701] | — |

Skopos − AgentWorld, balanced accuracy: +0.057 [−0.025, +0.136].

Skopos ranks failing actions first at least as well as the other two (AUROC), but at the fixed 0.5 threshold its balanced accuracy is the lowest of the three: a shift of threshold rather than of ranking. Choose the threshold for your false-alarm budget, as the guard does.

## Images

The state can be a picture. R4's training was text only, so its image ability was checked
([PREREG_IMAGE.md](prereg_skopos/PREREG_IMAGE.md)): 400 fresh items (lamps drawn as bulbs,
containers with the water level; 1–3 actions), half with an answer the actions change, three prompts each, both models
in INT4 through the same serving, images sent as a client sends them (`results_skopos/image_compare.json`). The table
reports the 395 items left without the 5 the overlap audit
flags (decision D8; `results_skopos/overlap_audit/clean/image_compare_clean.json`), with all 400
beside them.

| Prompt | Skopos INT4 | Ekbasis-27B INT4 | Difference, 95% CI | Changed answers: Skopos / Ekbasis-27B | All items, before the D8 exclusion: Skopos / Ekbasis-27B (difference) |
|---|---|---|---|---|---|
| The state as text | 91.9% | 89.6% | +2.28 [−0.51, +5.06] | 88.4% / 85.4% | 92.0% / 89.8% (+2.25) |
| The state as an image | 79.8% | 78.7% | +1.01 [−2.03, +4.05] | 73.7% / 72.7% | 80.0% / 79.0% (+1.00) |
| Read the final state from an image | 94.2% | 91.9% | +2.28 [+0.51, +4.30] | 95.0% / 90.9% | 94.2% / 92.0% (+2.25) |

Without the items the overlap audit flags (see the overlap section); the last column, all items, before that exclusion. Image ability **preserved** by the registered reading (Skopos − Ekbasis-27B ≥ −2.0 points on the image and the read prompts); on all items, **preserved**.

## Certified mode with Skopos

`ekbasis.verify`'s certified mode acts on a confident answer without checking it only where a Learn-then-Test
certificate holds; its thresholds were certified on Ekbasis-27B. A check registered before any request
([PREREG_CERTIFIED_CARRYOVER.md](prereg_skopos/PREREG_CERTIFIED_CARRYOVER.md)) ran the same client (thresholds
unchanged) on Skopos INT4 (primary) and bf16, served, over confirm-3's fresh scenarios: 1,400 scenarios,
2,781 questions, 1,321 confident units for INT4 (0 scenarios excluded by
the overlap audit, 0 failed requests; `results_skopos/certified_carryover_skopos_int4.json`, code and
data in `results_skopos/certified_carryover/`). A check that the certificate carries over, not a new certificate.

Each unit's score uses the family's error rate as it stands when the unit comes up: every stream starts warm from
WS-P's development history (`results_skopos/certified_carryover/data/dev_family_counts.json`) and then updates online
over the rows it is given, in confirm-3's hashed order. So a row's numbers depend on its scenario set and on whose rows
drive its stream; every row below names both. Ekbasis-27B bf16's stream is confirm-3's whole fresh set (its answers),
as confirm-3 and T2 scored it. WS-MAC T2, the MLX check in `docs/VERIFY.md`, completed 1,081 of these
scenarios; the rows on those scenarios are recomputed by the check's own analysis functions
(`results_skopos/scripts/certified_reference_rows.py` → `results_skopos/certified_carryover_reference_rows.json`).

| L2, α = 2% (the certified mode) | Scenarios · family-rate stream | Accepted (of the units) | Errors among accepted | Weighted to confirm-3's mix | 95% upper bound | Verified: raw / weighted |
|---|---|---|---|---|---|---|
| **Skopos INT4** | all 1,400 · its own rows | 927 of 1,321 | 7 (0.76%) | 0.74% | 1.41% | 29.8% / 22.0% |
| Skopos bf16 | all 1,400 · its own rows | 935 of 1,333 | 6 (0.64%) | 0.59% | 1.26% | 29.9% / 22.0% |
| Ekbasis-27B bf16 (confirm-3's answers) | all 1,400 · confirm-3's whole fresh stream | 886 of 1,336 | 5 (0.56%) | 0.47% | 1.18% | 33.7% / 25.4% |
| Skopos INT4 | T2's 1,081 · its own rows there | 710 of 1,020 | 6 (0.85%) | 0.90% | 1.66% | 30.4% / 22.5% |
| Skopos bf16 | T2's 1,081 · its own rows there | 720 of 1,030 | 6 (0.83%) | 0.76% | 1.64% | 30.1% / 22.4% |
| Ekbasis-27B bf16, as in docs/VERIFY.md | T2's 1,081 · confirm-3's whole fresh stream | 686 of 1,036 | 5 (0.73%) | 0.60% | 1.53% | 33.8% / 25.8% |
| Ekbasis-27B MLX (T2), as in docs/VERIFY.md | T2's 1,081 · its own rows there | 666 of 1,028 | 1 (0.15%) | 0.21% | 0.71% | 35.2% / 26.7% |

**The published references, with their definitions.** The certificate's own confirmation (confirm-3, Ekbasis-27B bf16,
its whole fresh test of 12,667 units): 36 errors among 9,259 accepted
(0.39%; `results/client_0.1.5/results/confirm3/confirm3.json`). WS-MAC T2, the MLX
build on its 1,081 completed scenarios, family rate streamed over the MLX build's own rows there:
1 error among 666 accepted (0.209%
weighted, 95% upper bound 0.71%); Ekbasis-27B bf16 on the same scenarios, confirm-3's whole
fresh stream: 5 among 686 (0.604%
weighted) (`results_skopos/certified_carryover/published_t2_summary.json`, the file behind `docs/VERIFY.md`'s MLX numbers,
which quote the raw rates). The check's analysis code recomputes both T2 rows from T2's own answers
exactly (units, accepted, errors, weighted rate, upper bound): the last two rows
of the table.

Criteria (pre-registered, on all scenarios): C2 (L2: weighted
error among accepted ≤ 2% and no node significantly above) **holds**; C2+ (and the raw 95%
upper bound ≤ 2%) **holds**; C1 (L1, α = 2%: 4 errors among
539 accepted) **holds**. Paired with Ekbasis-27B on the same 2,781 questions, Skopos INT4
gives the same answer on 2,613; right 2,554 against 2,485; wrong at confidence
≥ 0.9 154 against 233.

The bf16 build (secondary; `results_skopos/certified_carryover_skopos_bf16.json`): C2 **holds**, C2+ **holds**, C1 **holds**.

## Latency and cost (INT4)

Both INT4 builds served the same way on the same RTX PRO 6000 (vLLM and `serve.py`, nothing else on the GPU), on
200 fixed items (addendum A5; `results_skopos/latency_*_int4.json`). The hosted API runs on another GPU.

| | Skopos INT4 | Ekbasis-27B INT4 |
|---|---|---|
| One at a time: median / 90th percentile | 0.064 s / 0.068 s | 0.064 s / 0.068 s |
| 16 in parallel: requests per second | 19.0 | 19.0 |
| Input tokens per request: mean / median | 302 / 299 | 302 / 299 |

## Overlap with the training data

A first check counted, per evaluation set, the items whose state is identical to a state of the training rows (`results_skopos/overlap_audit_r4.json`; its script was not saved, so which training files it covered cannot be shown here; the redone audit below replaces it):

| Set | Items | Identical state in training |
|---|---|---|
| `git3_test_known` | 1,482 | 0 |
| `git3_test_held` | 1,623 | 0 |
| `multi_test_trainfam` | 600 | 5 |
| `multi_test_testfam` | 600 | 0 |
| `ftest_family` | 1,080 | 0 |
| `guard_known` | 4,486 | 0 |
| `guard_held` | 6,394 | 0 |
| `ftest_fresh` | 5,385 | 0 |
| `fac_val` | 3,983 | 0 |
| `git_long` | 900 | 0 |
| `git_long_val` | 1,800 | 0 |
| `sess_val` | 730 | 0 |
| `awb_neutral` | 455 | 0 |

**The audit redone for this release** against every training row of the whole lineage (Ekbasis-27B's stages, v49f's
and R4's files: 437,253 distinct training texts), with Ekbasis-27B's rule:
identical prompts (also against the hindsight prompt), and near-duplicates at word 8-gram Jaccard >= 0.5 against one training text after removing each set's own layout (Ekbasis-27B's audit rule, exact best match) (`results_skopos/overlap_audit/`, with its two scripts). "Flagged" is the exclusion used for the numbers
without overlap; the sensitivity rule also removes the set's layout from the training text.

| Set | Items | Identical | Near duplicate | Flagged | Sensitivity rule | Same generators as training rows |
|---|---|---|---|---|---|---|
| `git3_test_known` | 1,482 | 0 | 0 | 0 | 25 | yes |
| `git3_test_held` | 1,623 | 0 | 0 | 0 | 6 | no |
| `guard_known` | 4,486 | 0 | 0 | 0 | 77 | yes |
| `guard_held` | 6,394 | 0 | 0 | 0 | 27 | no |
| `multi_test_trainfam` | 600 | 5 | 286 | 291 | 313 | yes |
| `multi_test_testfam` | 600 | 0 | 0 | 0 | 0 | no |
| `ftest_family` | 1,080 | 0 | 0 | 0 | 0 | no |
| `ftest_fresh` | 5,385 | 0 | 0 | 0 | 0 | no |
| `fac_val` | 3,983 | 6 | 99 | 105 | 170 | yes |
| `git_long` | 900 | 0 | 0 | 0 | 0 | yes |
| `git_long_val` | 1,800 | 0 | 0 | 0 | 0 | yes |
| `sess_val` | 730 | 0 | 0 | 0 | 0 | yes |
| `fhorizon` | 1,375 | 0 | 547 | 547 | 584 | yes |
| `latent_test` | 4,320 | 0 | 0 | 0 | 0 | no |
| `awb_neutral` | 455 | 0 | 0 | 0 | 0 | no |
| `fval_git3` | 1,524 | 0 | 0 | 0 | 47 | yes |
| `m3val` | 300 | 0 | 0 | 0 | 0 | yes |
| `ce_items` | 15,008 | 174 | 5,207 | 5,381 | 5,697 | yes |
| `image_fresh` | 400 | 0 | 5 | 5 | 21 | yes |
| `certified_carryover` | 2,781 | 0 | 0 | 0 | 0 | no |
| `image` | 400 | 0 | 5 | 5 | 21 | yes |

**Every published number recomputed without the flagged items** (`results_skopos/overlap_audit/recomputed.json`):

- Release read, bf16: every criterion's outcome is the same under both rules.
- Release read, int4: every criterion's outcome is the same under both rules.
- Release read, fp8: every criterion's outcome is the same under both rules.
- Release read, mlx: every criterion's outcome is the same under both rules.
- R4 against the first Skopos, and R2 against it: the verdicts hold.
- The fresh confirmation: 0 items flagged; unchanged.
- Images: preserved under both rules (image prompts +1.01 [−2.03, +4.05] on 395 items).
- Quantization gates: each build's pass or miss holds.
- Confident errors: 5,381 items flagged (4,153 in the trained families, 1,228 in the trained families with held-out question types); nothing in the never-trained families, so their numbers stand (never-trained families, wrong at ≥ 0.9: +0.75 per 100 [+0.28, +1.23]).
- Skopos against Ekbasis-27B (descriptive), on the sets that lose items: `fac_val` +5.7 [+4.8, +6.7] on 3,878 items (all items +5.6); `fhorizon` +0.7 [−1.1, +2.3] on 828 items (all items +0.7).
- neutral.json (awb_neutral): 0 items flagged under either rule: every number unchanged.
- ftest_fresh_int4.json / ftest_fresh_fp8.json: ftest_fresh: 0 items flagged under either rule: unchanged.
- t3c_r4.json: real-repository scenarios (pallets/itsdangerous), not dataset items: outside the audit.
- mlx_mac_test / served equivalence: agreement between builds, not accuracy on a set: not affected by overlap.

Accuracy on the flagged items and on the rest (`flagged_vs_clean`):

| Set | Flagged items: Skopos / Ekbasis-27B | The rest: Skopos / Ekbasis-27B |
|---|---|---|
| fac_val | 100.0% / 98.1% (105) | 93.9% / 88.1% (3,878) |
| fhorizon | 85.0% / 84.3% (547) | 87.9% / 87.2% (828) |
| multi_test_trainfam (share of a state's questions right) | 97.0% / 95.9% (291) | 97.8% / 96.3% (309) |
| ce_items group T | 95.4% / 94.8% (4,153) | 97.7% / 97.1% (3,019) |
| ce_items group H | 92.3% / 90.1% (1,228) | 88.3% / 86.4% (1,244) |
| image (text prompt) | 100.0% / 100.0% (5) | 91.9% / 89.6% (395) |

Sets from the same generators as training rows (the last column; fresh seeds and firewalls) measure in-distribution generalization, not transfer.

## Pre-launch evaluation

*Pending: the measurements of Ekbasis-27B's release evaluation that have not yet run on Skopos, each next to Ekbasis-27B on the same items, and the acceptance checks of the published artifacts. Their results will be reported here, favourable or not.*

## Deviations from the pre-registrations

1. **The release read failed one criterion** (`ftest_family`, −1.59 points). Its rule says R4 passes
   if every criterion holds; the release decision rests instead on the confirmation registered after that result
   (CONFIRM_FTEST.md), which did not confirm the loss.
2. **T3c was not run with the release read** (criterion 7 allowed "reported as not run"); it ran under addendum A1,
   with the scenarios' repository pinned to the commit Ekbasis-27B's evaluation used.
3. **T3c injection truth.** As for Ekbasis-27B, the truth of the file-name injection tracks the planted file
   (`rescore_inj_truth.py`; predictions unchanged); the first scoring is `results_skopos/t3c_r4_raw.json`.
4. **Confident errors, scoring only:** the published raw/ce_items.jsonl stores yes/no gold as booleans while confident_errors.py compares strings; ok re-scored with the gold normalized to yes/no exactly as in the code repository's results/confident_errors/items.jsonl (items otherwise identical, checked); predictions unchanged.
5. **The first Skopos comparison's analysis script** was written after partial accuracies had been seen (its seal
   says so); the rule was registered before, unchanged.
6. **The neutral suite's Ekbasis runs** were rerun at evaluation batch 6 after running out of memory at 48; unparsed
   AgentWorld answers count as wrong (fixed before any Ekbasis score; both in PREREG_NEUTRAL.md's notes).
7. **The MLX build** misses 3 gate checks (above); it is not part of this release, which A4's test on Apple hardware would have to pass first.
8. **Not kept:** the builds' per-item answers on the fresh `ftest` items (only their summaries), and the first run
   of the served-equals-trainer check (printed; rerun under A6).
9. **Training** (not an evaluation deviation, listed for completeness): v49f restarted at micro-batch 4 after running
   out of memory (PLAN_v49 Addendum D; [training/skopos/README.md](training/skopos/README.md)).
