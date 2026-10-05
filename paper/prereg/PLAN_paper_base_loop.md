# Paper experiment A: the model before consequence training, in the loop

Pre-registered 2026-10-04 13:02 BRT, before any chain below was run. For the paper "Look when unsure, check when sure".

## Question

On single questions, consequence training made the remaining errors confident (`PREREG_confident_errors_eikos.md`,
confirmed). Eikos-27B, the model before that training, errs more (14.4% of answers in the trained families T, 21.3% in
the unseen families U) but rarely with confidence: 1.9% and 0.5% of its errors are at >= 0.9. Ekbasis-27B's remaining
errors are often confident: 58.1% and 27.8%.

Does the same hold inside long chains, where each model reads states it predicted itself? If it does, the loop needs
scheduled checks because of the training. Confidence alone would catch the parent model's errors, at the price of many
more looks.

## Model and service

Eikos-27B (bf16, the released weights), served exactly as in the follow-up (`run_confident_errors_eikos.sh`):

- three research replicas on GPUs 1-3, with the same vLLM flags as every Ekbasis run;
- the same System One API code;
- temperature 1 (both models' `calib.json` are mode T1).

The replicas start after phase B of `run_guard_wise2.sh` and are stopped at the end by their pid files.

## Chains (paired)

The chains are those of the release evaluation's "Rules compared" (`results/release_eval/long_chain3.jsonl`):

- cards i 0-7; containers, lamps and machines i 0-3;
- 100 and 200 actions;
- 40 chains per mode, with the same worlds, seeds and actions as Ekbasis-27B's rows.

Modes: text (never look), conf0.5, conf0.9, check0.5 and check0.9, for 200 chains in all. With TRACE=1, each step records
the probability of the state read and whether the step itself was right from the model's own previous state.

## Ekbasis-27B on the same chains (already known, stated here)

Never-look traces (`long_chain3_controls_trace.jsonl`, `long_chain3_trace.jsonl`), wrong steps made at step
probability >= 0.9:

- containers 5/5 and lamps 4/4, the worlds it was trained on (9/9);
- machines 1/3 and cards 0/82, the worlds it was not trained on (1/85).

The loop (`long_chain3.jsonl`):

| Mode | Silent wrong steps per 100 actions | Looks per 100 actions | Exact chains (of 40) |
|---|---|---|---|
| never | 32.45 | 0 | 24 |
| conf0.5 | 2.82 | 8.7 | 39 |
| conf0.9 | 0.73 | 16.7 | 40 |
| check0.5 | 1.30 | 11.1 | 40 |
| check0.9 | 0.40 | 18.1 | 40 |

## Predictions and tests

- **P1 (primary).** Take the never-look traces of the two worlds Ekbasis-27B was trained on (containers, lamps). There,
  Eikos-27B makes a lower share of its wrong steps at step probability >= 0.9 than Ekbasis-27B does (9/9).
  - Test: one-sided Fisher exact, p < 0.05.
  - If Eikos-27B has fewer than 10 wrong steps in those traces, P1 is inconclusive.
- **P2.** The same share in the two worlds neither model was trained on (machines, cards), reported for both.
  Prediction: low for both (Ekbasis-27B 1/85).
- **Descriptive, the loop**, for both models: silent wrong steps, looks per 100 actions and exact chains in each mode, and
  the checks' gain (conf0.9 minus check0.9, in silent wrong steps per 100 actions).
  - Expectation: Eikos-27B looks far more and gains little from the checks.
- **Descriptive, the scale.** Also reported:
  - the share of right steps at >= 0.9;
  - the AUROC of the step probability, for right against wrong steps;
  - each value per model and per world group, and per world.

## Reading

- **P1 confirmed:** in chains too, the training made the remaining errors confident in the worlds it trained on. That is
  the reason the default rule adds scheduled checks.
- **P1 not confirmed:** the single-question result does not carry into chains, and the paper says so.

## Files

- Runner: `conseq/run_paper_base_loop.sh` (rig), writing `/dev/shm/conseq/long_chain3_eikos_base.jsonl`.
- Analysis: `conseq/paper_base_loop_compare.py`, writing `eval_handoff/paper/base_loop.json`.
