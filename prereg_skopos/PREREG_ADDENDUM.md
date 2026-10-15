# Ekbasis-Skopos-27B — release evaluation addendum (pre-registration, 2026-10-15, before any request below)

Model: Ekbasis-Skopos-27B = R4 merged (bf16 folder `/root/Skopos-R4-27B` on the RTX PRO 6000 research machine),
served exactly as in the release read (`serve_vllm.sh` + the folder's `serve.py`); builds FP8 (`/root/Skopos-R4-27B-FP8`,
vLLM) and MLX 4-bit (`/root/Skopos-R4-27B-MLX-4bit`, `mlx_serve.py`, MLX CUDA backend). INT4 was measured before
(`results/calib_fit_skopos_int4.json`). Nothing here gates the decision already taken (R4 replaces Skopos; release read
8/9 + confirmation); A1 completes the release protocol, A2–A4 complete the documentation of the builds.

## A1 — T3c, the git guard on real-repository scenarios (criterion 7 of PREREG_R4_RELEASE_READ.md)
- Protocol of `PREREG_release_eval.md` primary 1 and its injection secondary, run by `conseq/release_eval_t3c.py`
  unchanged, with the client copy that ran Ekbasis-27B's release evaluation (`release_clean/code_eikos/ekbasis`), on the
  same 16 scenarios (`git_battery3.py`, `GIT_V3=1`), against the served bf16 through an SSH tunnel.
- The clone of `pallets/itsdangerous` is pinned to the last commit of `main` before 2026-10-04 21:00 UTC (the day of
  Ekbasis-27B's release evaluation; that run cloned the then-current `main`); the commit id is recorded.
- Reference: Ekbasis-27B's recorded result (`results/release_eval/release_eval_t3c.json`): work-losing flagged 3/3,
  false alarms 1/13, `fails` right 16/17.
- Criterion (the release read's "at most 1 point worse", on counts of 3, 13 and 17 that means no worse): **all 3
  work-losing scenarios flagged, false alarms ≤ 1 of 13, `fails` right ≥ 16 of 17.** Reported regardless, with the
  injection secondary. A miss is reported on the card; it does not by itself reverse the release decision, which is
  Caio's.

## A2 — Confident errors (PREREG_confident_errors.md, reported, no gate)
- The published 15,008 items (`ekbasis-data` `confident_errors/test` = `raw/ce_items.jsonl`), one prompt per question,
  through the served bf16 (`conseq/confident_errors.py eval`, items file replaced by the published one), analysis by
  the same code as the published report (`conseq/confident_errors_report.py`), compared with Ekbasis-27B's published
  predictions.
- Reported per group (trained families, trained families with held-out question types, never-trained families):
  accuracy, wrong answers given with confidence ≥ 0.9 per 100, ECE; with and without the items the overlap audit
  (workstream B) finds in the Skopos lineage's training rows.
- Prediction: within ±1 point of Ekbasis-27B in every group (Skopos' added training is executed shell/git/SQL/Python and
  plan-level items, not these world families).

## A3 — Calibration per build (reported; it sets each build's `calibrated_temperature`)
- `calib_items.json` (fit 1,824 = fval_git3 1,524 + m3val 300; test 2,500 = git_long 900 + guard_known 800 + fac_val
  800), scored through each build's own server (bf16, FP8, MLX) with the INT4 scorer adapted only in its URL; one global
  temperature fitted by `scripts_main/fit_T.py` (NLL of the gold option on the fit set, grid 0.50–3.00 by 0.01);
  reported on the test splits raw and calibrated (accuracy, ECE, confident errors per 100, Brier).
- Sanity rule: a build whose temperature differs from INT4's 1.67 by more than 0.30 is investigated before its value is
  used.

## A4 — MLX on Apple hardware (release condition for the MLX build only)
- On an Apple-silicon Mac with ≥ 32 GB: `mlx_serve.py` from the private repo answers 200 fixed items (100 of
  `git3_test_held`, 100 of `guard_known`, ids drawn with seed 20261015) and a client `git-check` smoke test.
- Pass: the same answer as the Linux (CUDA backend) MLX run on ≥ 99% of the 200 items and the smoke test answers.
  Until it passes, the MLX build stays private.

## Deviations
Any change to the above after the first request is reported as a deviation, with its reason.

## A5 — Latency and cost for the hosted-model scorecard (appended 2026-10-15 23:23 UTC, before any A5 request)
The API policy requires latency and cost on fixed suites before the served model changes. Both INT4 builds
(Ekbasis-27B-INT4 as published, Ekbasis-Skopos-27B-INT4) served the same way on the same RTX PRO 6000 (vLLM
`serve_vllm.sh` + `serve.py`, nothing else on the GPU), on the 200 fixed items of A4 (100 git3_test_held + 100
guard_known, seed 20261015): 20 warm-up requests, then every item one at a time (median and p90 latency), then all
200 with 16 in parallel (requests per second); input tokens per request from `usage` (cost = tokens × the published
price). Reported, no criterion. The hosted API runs on a different GPU (RTX 5090): the scorecard says so.

## A6 — Served = trainer equivalence of the bf16, saved per item (appended, same time)
`equiv_r4.py` (the 500 items: git_long 300, guard_known 200) re-run against the served bf16 with its per-item output
saved (`results/served_equivalence_bf16.json`); the earlier run (499/500) was printed, not saved. Reported, no criterion.
