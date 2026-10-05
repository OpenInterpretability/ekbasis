# V43, first round: keep the errors uncertain while accuracy holds

Written on 2026-10-03 before any of these runs started (research plan, criteria fixed in advance).

## Question

Consequence training cut Ekbasis' errors and made the remaining ones confident (`PREREG_confident_errors_eikos.md`:
the share of wrong answers at 0.9 or more went from 1.9% to 58.1% on the trained families, 0.5% to 27.8% on the
others). Can a change of the training objective keep the errors uncertain without losing accuracy?

## Runs (identical except the loss on the answer letter)

Each continues the released adapter (`sw_v42/ckpt_400`) for 200 steps with the V42 recipe: Eikos-27B base, LoRA rank 64,
batch 8, learning rate 1e-5, JEPA 3 at the end of the evidence on layers 16, 32, 48, 64, the V42 data mix
(`ftrain_mixG3`, `MIX=floorG3:0.35,...`), one GPU each.

- **v43ce** (control): cross-entropy, as in V42; it separates the effect of 200 more steps from the effect of the loss.
- **v43ls**: label smoothing 0.1 on the one-hot targets (the replay items keep their soft targets).
- **v43fl**: focal loss with gamma 2.

## Evaluation (the trainer's own readout, the same for every run and for V42 itself)

`git3_test_known`, `git3_test_held`, `multi_test_testfam` (answers the actions change), `ftest_family`, and the 15,008
items of the confident-errors test (groups T, H, U), with every option's probability saved.

## A run succeeds if, against V42 under the same readout

- accuracy holds: git3 (known and held pooled) and `multi_test_testfam` changed answers within 0.5 points;
- the errors become uncertain: on the 15,008 items, the share of wrong answers at 0.9 or more drops by at least
  20 points in group T and drops in group U;
- confidence still separates right from wrong: AUROC not lower by more than 0.005; ECE lower.

If a loss only rescales confidence (AUROC unchanged, the same as recalibration does after training), recalibration is
the cheaper fix and the next round tries what can improve the separation itself (for example distilling an ensemble of
adapters into one model, which keeps one pass).
