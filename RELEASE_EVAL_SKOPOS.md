# Ekbasis-Skopos-27B release evaluation — results

> **Draft.** Results still to come are marked *pending*; the final version is written with `--final`, which refuses to build while any of them is missing.

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

| Suite | Ekbasis-27B | first Skopos | **Skopos (R4)** | Skopos − first Skopos, 95% CI | Skopos − Ekbasis-27B, 95% CI |
|---|---|---|---|---|---|
| Executed factory scenarios (shell, SQL, Python, git) † | 88.4 | 92.5 | **94.0** | +1.6 [+1.0, +2.2] | +5.6 [+4.8, +6.6] |
| Real git sequences, 5–12 commands † | 90.7 | 91.3 | **93.2** | +1.9 [+0.7, +3.1] | +2.6 [+1.1, +3.9] |
| Same, validation twin † | 91.0 | 91.9 | **94.6** | +2.6 [+1.6, +3.6] | +3.6 [+2.6, +4.7] |
| Agent sessions (shell, read as a transcript) † | 89.0 | 91.2 | **93.2** | +1.9 [+0.7, +3.3] | +4.1 [+2.5, +5.8] |
| Latent-state worlds | 79.2 | 79.3 | **81.4** | +2.1 [+1.3, +2.8] | +2.2 [+1.4, +3.0] |
| Synthetic horizons, 1–20 actions † | 86.0 | 86.8 | **86.8** | +0.0 [−1.3, +1.3] | +0.7 [−0.6, +2.1] |
| git v3, known command types | 98.0 | 98.5 | **98.5** | +0.1 [−0.4, +0.5] | +0.5 [−0.1, +1.0] |
| git v3, held-out command types | 95.2 | 95.8 | **95.3** | −0.4 [−1.1, +0.3] | +0.1 [−0.7, +0.9] |
| The guard, known command types (all questions) | 94.7 | 96.0 | **96.4** | +0.4 [+0.0, +0.8] | +1.7 [+1.2, +2.3] |
| Never-trained families (`ftest_family`) | 83.1 | 83.4 | **83.4** | +0.0 [−1.5, +1.4] | +0.4 [−1.0, +1.8] |
| Factory-3 worlds (validation) | 91.3 | 93.7 | **93.0** | −0.7 [−2.7, +1.3] | +1.7 [−1.0, +4.3] |
| git v3 (validation) | 93.0 | 93.3 | **94.1** | +0.8 [+0.0, +1.6] | +1.1 [+0.3, +2.0] |

Paired bootstrap by item (2,000 resamples, seed 20261015); the last column, descriptive, from `results_skopos/r4_vs_ekbasis27b_trainer.json` (the same predictions and bootstrap). † In-distribution: the same generators as training rows, with fresh seeds and firewalls.
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

## git v3 held-out tests

Repositories built and commands executed in a sandbox; "held" = command types never seen in training (`rebase`, `restore --source`). 95% bootstrap intervals (`results_skopos/release_read_bf16_report.json`).

| | Known command types | Never-seen command types |
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

20,000 new examples per split from the git generator, from repository states no earlier set contains, balanced like the git v3 test sets (Ekbasis-27B's `PLAN_guard_set.md`). Through the exact release weights, served (`results_skopos/release_read_bf16_guard.json`):

| | Known command types | Never-seen command types |
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
and `confident_errors.py` use the strings yes/no: the answers were re-scored with that normalization (deviation 4). Its confirmatory
question (confirmed for Skopos, confirmed for
Ekbasis-27B): are wrong answers more often confident (≥ 0.9) in the families it was trained on than in those it never
saw? 49.0% against 31.5% (+17.5
points, [+10.6, +24.7]; Ekbasis-27B 48.4% against 25.1%, +23.3
[+16.8, +30.1]).

| Group | n | Error rate: Skopos / Ekbasis-27B (difference, 95% CI) | Wrong at confidence ≥ 0.9, per 100 answers (difference, 95% CI) |
|---|---|---|---|
| Trained families | 7,172 | 3.64 / 4.27 (−0.63 [−1.03, −0.22]) | 1.78 / 2.06 (−0.28 [−0.59, +0.03]) |
| … answers the actions change | 2,940 | 6.02 / 7.24 (−1.22 [−2.01, −0.48]) | 2.96 / 3.54 (−0.58 [−1.16, +0.03]) |
| Trained families, held-out question types | 2,472 | 9.71 / 11.77 (−2.06 [−3.11, −0.97]) | 3.64 / 4.00 (−0.36 [−1.21, +0.44]) |
| … answers the actions change | 1,106 | 10.58 / 13.65 (−3.07 [−4.88, −1.36]) | 3.80 / 4.88 (−1.08 [−2.44, +0.18]) |
| **Never-trained families** | 5,364 | 14.26 / 14.93 (−0.67 [−1.30, −0.06]) | 4.49 / 3.75 (+0.75 [+0.28, +1.23]) |
| … answers the actions change | 2,700 | 14.85 / 14.67 (+0.19 [−0.70, +1.15]) | 4.22 / 3.04 (+1.19 [+0.52, +1.89]) |

In the never-trained families **more of Skopos' wrong answers come with high confidence**: +0.75 per 100 answers [+0.28, +1.23], +1.19 [+0.52, +1.89] on the answers the actions change.
The registered prediction (within ±1 point of Ekbasis-27B in every group) was not met: Trained families (changed answers), errors: −1.22; Trained families, held-out question types, errors: −2.06; Trained families, held-out question types (changed answers), errors: −3.07; Trained families, held-out question types (changed answers), confident errors: −1.08; Never-trained families (changed answers), confident errors: +1.19. Numbers without the items that overlap the training rows: see the overlap section.

## Calibration per build

One global temperature per build, fitted on validation only (`fval_git3` + `m3val`, negative log-likelihood of the right option), then applied to 2,500 held-out items (`git_long` 900, `guard_known` 800, `fac_val` 800), each build scored through its own server (addendum A3; INT4 was fitted before it, as Ekbasis-27B-INT4 was for the hosted API's `calibrated` field, T = 1.55).

| Build | Temperature | Accuracy | ECE raw → calibrated | Wrong at ≥ 0.9, per 100: raw → calibrated | Brier raw → calibrated |
|---|---|---|---|---|---|
| Skopos bf16 | 1.62 | 95.2% | 0.034 → 0.011 | 3.24 → 1.96 | 0.0837 → 0.0776 |
| Skopos INT4 | 1.67 | 95.1% | 0.034 → 0.015 | 3.28 → 1.72 | 0.0843 → 0.0778 |
| Skopos FP8 | 1.64 | 95.4% | 0.031 → 0.012 | 3.08 → 1.72 | 0.0803 → 0.0752 |
| Skopos MLX | 1.65 | 94.5% | 0.037 → 0.017 | 3.68 → 1.84 | 0.0946 → 0.0878 |
| Ekbasis-27B INT4 | 1.55 | 91.1% | 0.068 → 0.036 | 6.24 → 3.88 | 0.1553 → 0.1416 |

Per split, and what a raw yes-probability becomes calibrated: the same files (`map_binary`).

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
in INT4 through the same serving, images sent as a client sends them (`results_skopos/image_compare.json`).

| Prompt | Skopos INT4 | Ekbasis-27B INT4 | Difference, 95% CI | Changed answers: Skopos / Ekbasis-27B |
|---|---|---|---|---|
| The state as text | 92.0% | 89.8% | +2.25 [−0.50, +5.00] | 88.5% / 85.5% |
| The state as an image | 80.0% | 79.0% | +1.00 [−2.00, +4.25] | 74.0% / 73.0% |
| Read the final state from an image | 94.2% | 92.0% | +2.25 [+0.50, +4.25] | 95.0% / 91.0% |

Image ability **preserved** by the registered reading (Skopos − Ekbasis-27B ≥ −2.0 points on the image and the read prompts).

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
- neutral.json (awb_neutral): 0 items flagged under either rule: every number unchanged.
- ftest_fresh_int4.json / ftest_fresh_fp8.json: ftest_fresh: 0 items flagged under either rule: unchanged.
- t3c_r4.json: real-repository scenarios (pallets/itsdangerous), not dataset items: outside the audit.
- mlx_mac_test / served equivalence: agreement between builds, not accuracy on a set: not affected by overlap.

Sets from the same generators as training rows (the last column; fresh seeds and firewalls) measure in-distribution generalization, not transfer.

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
