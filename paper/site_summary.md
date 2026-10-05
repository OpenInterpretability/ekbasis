# Look When Unsure, Check When Sure
### Consequence training makes a world model's remaining errors confident, most of all where it knows the world best

**Caio Vicentino · OpenInterpretability · Published 2026-10-04.**
**Zenodo · CC-BY-4.0 · [DOI 10.5281/zenodo.23146971](https://doi.org/10.5281/zenodo.23146971).**

> The on-site summary. The full paper — every table, the pre-registrations and the reproduction script — is the
> **[PDF](/papers/look-when-unsure.pdf)**, also on **[Zenodo](https://doi.org/10.5281/zenodo.23146971)**.

---

## Abstract

An agent that predicts the consequences of its actions can chain those predictions and plan without acting, but errors
compound, and checking the real state costs time. With V42, the first release candidate of Ekbasis-27B, an open 27B
consequence model that reads the probability of every candidate next state from a single forward pass, we ask when the
agent should look.

- **The rule.** Look when the chain's confidence since the last look falls below 0.9, plus scheduled checks with a
  Trickle-style backoff.
- **The result.** The rule keeps **197 of 200** fresh 100- and 200-action chains exact in four worlds, two of them never
  seen in training, at **17.9 looks per 100 actions**. Never looking keeps 25 of 40.

The checks are needed because of a pre-registered finding. On 15,008 new questions, **58.1%** of the model's errors in
the families it was trained on carry confidence ≥ 0.9, against **27.8%** in families it never saw (+30.3 points, 95% CI
[24.0, 36.5]). The model before consequence training shows almost none (1.9% and 0.5%). The training cut its errors in
the trained families by two-thirds, but multiplied confident errors per answer tenfold.

Recalibration and smoother losses do not fix it. Training on the model's own errors made inside its own chains does,
cutting silent wrong steps by 71–97% with no more looks. Every such fine-tune, though, failed a release criterion, most
of them by forgetting rare work-losing git commands. An exact weight interpolation halfway back to V42 passes every
single-question and guard criterion, keeps the loop's gain on fresh chains (91% fewer silent wrong steps) and passes
the release evaluation: it is the released Ekbasis-27B, with the checks kept in its default rule.

## Why it matters

Confidence is the natural trigger for an agent to stop and look. This paper shows the place where that trigger fails.
In the worlds a model knows best, its few remaining errors look like its right answers, and the training that makes it
accurate is what makes them so. An agent should look when the model is unsure, and still check when it is sure. The
fix belongs in training, on the states the model visits itself, and every such fix must be gated against forgetting.

## Key results

- **The loop.** `check 0.9` keeps 40 of 40 development chains exact at 0.40 silent wrong steps per 100 actions. Never
  looking keeps 24 of 40.
  - The model looks 3.8 and 4.4 times per 100 actions in the two trained worlds, and 12.2 and 35.1 in the two unseen
    ones.
  - Reading the cards from two views halves their looks (33.4 to 17.0).
- **Confident where trained (pre-registered).** 58.1% of errors at ≥ 0.9 in trained families against 27.8% in unseen
  ones.
  - The ranking of confidences is similar (AUROC 0.922 and 0.908), but the scale is not.
  - A 0.9 trigger can flag at most 41.9% of the errors in the trained families, against 72.2% in the unseen ones.
- **Training made it (pre-registered).** The parent model shows 1.9% and 0.5%. The difference in gaps is +28.9 points
  [22.8, 34.9].
  - Confident errors per 100 answers went from 0.28 to 2.79 in the trained families.
  - 200 more training steps raised the confident share again, from 57.7% to 67.3%.
  - In long chains, the parent's step probabilities never reach 0.9. To run the same loop it looks at 99 of every
    100 actions, where V42 looks at about 17.
- **What does not fix it (pre-registered).**
  - Temperature, Platt and isotonic recalibration make the 0.9–0.99 band honest (84.0% to about 97% right), but keep
    the gap and fail the guard.
  - Label smoothing and focal loss blur the ranking (AUROC 0.919 to 0.871 and 0.891).
  - Training on errors made from true states makes single answers honest, but the loop then looks 81% more.
- **What fixes the loop (pre-registered, fresh chains).** Errors mined inside the model's own chains:
  - silent wrong steps 0.93 to 0.03 (−97%) at 18.2 looks against 18.6;
  - 0.93 to 0.09 (−90%) at 15.0 looks;
  - with chain items only, 0.45 to 0.13 (−71%) at 12.9 looks against 16.4.
- **Its cost.** Every such fine-tune failed a release criterion.
  - Five distinct work-losing command sequences stopped being flagged, three of them with `git reset --merge`.
  - On a 17× larger guard set, five of the six runs fail the gate (four miss work-losing commands, one raises false
    alarms).
  - On 72 real-repository scenarios, V42 and the chain-only run were identical: 28 of 28 caught and
    0 false alarms.
- **Halfway back in weight space.** The exact interpolation between V42 and the first chain-mined run
  passes the guard on both splits and every single-question criterion, with 2.05 confident errors per 100 answers in
  the trained families against 2.76. On 160 fresh chains it cut silent wrong steps by 91% (0.57 to 0.05 per 100
  actions) with 6% fewer looks. It then passed the release evaluation and is the released Ekbasis-27B.

## Reproducibility

Every analysis is re-run on the saved predictions by `reproduce.py`, and each one reproduces its stored result. Every
number in the paper comes from its `numbers.json`, which `check_numbers.py` verifies. Each test's plan was sealed by
SHA-256 before it ran.

The model, client and data are open: `caiovicentino1/Ekbasis-27B`, `ekbasis` and `caiovicentino1/ekbasis-data`.
