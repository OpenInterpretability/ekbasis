# Ekbasis-Skopos-27B — pre-launch evaluation (plan, 2026-10-15, Caio: "eval completo pre lançamento")

Three parts. Part A is a measurement battery and is pre-registered (sealed in DM/mission/V50R/SEAL.txt) before its
first request; Parts B and C are acceptance checks with pass/fail per item. The launch ("abre") is Caio's decision on
the review package; nothing here publishes anything.

## Part A — the model (everything Ekbasis-27B's release evaluation measured that Skopos has not yet run)
Model: Ekbasis-Skopos-27B bf16, served exactly as in the release read (vLLM `serve_vllm.sh` + `serve.py`, RTX PRO 6000);
client-level suites also on the INT4 build (what the hosted API would serve). Reference: Ekbasis-27B's published
results on the **identical items and scripts** (`ekbasis/RELEASE_EVAL.md`, `results/release_eval/`, the cookbook); where
the published reference was measured on other hardware or without per-item outputs, Ekbasis-27B is re-run here with
the same script.

| # | Measurement (Ekbasis-27B section) | Items | Reported |
|---|---|---|---|
| P1 | The 240-question git comparison | 240 (120 seen / 120 never-seen types) | accuracy per half and per question type |
| P2 | Git v3 held-out tests per question type | git3 known 1,482 / held 1,623 (release-read predictions) | accuracy per type, AUROC of P(lost), work-losing caught at a 10% false-alarm rate |
| P3 | Long chains (text / image / image + look again) | the same seeds, 6 chains per cell | final answer, whole final state, first error |
| P4 | Predict, observe, correct (`long_chain3`): the rules compared, and the 200 more chains | the same seeds | exact chains, looks per 100 actions |
| P5 | Speed (`speed_bench`): 80 forecasts of 10–30 actions | 80 | accuracy, latency, throughput (one prompt per question / read once) |
| P6 | Portuguese | the same 90 questions × 2 languages | accuracy per language |
| P7 | Chains that start from an image | 60 | final answer from text / image / image + first action; start state read exactly |
| P8 | Short checks, two wordings | 120 × 2 | accuracy per wording |
| P9 | Planning by search, no LLM | the same problems | solved, steps |
| P10 | Real use on real repositories | the same 72 scenarios | as published |
| P11 | GPU memory of each build (capped as in Ekbasis-27B's test) | 60 items per cap | same answers as uncapped |
| P12 | Client suites on the INT4 build: preflight (141 plans), intent_check replay (2,092), and the certified-mode carry-over check (its own pre-registration) | as published | as published |

**Rule.** Every result is reported next to Ekbasis-27B's on the same items. On any set of ≥ 100 items with per-item
outputs for both models, a drop whose paired 95% bootstrap CI (2,000, seed 20261015) lies entirely below 0 is a
**release blocker** that goes to Caio with the numbers; smaller sets (6-chain cells, the 72 real-use scenarios) are
reported as counts, and a cell where Skopos is worse by 2 or more is flagged in the report. Anything that cannot be
run exactly as published is reported as not run, with the reason (no substitute measurement is presented as the same).

## Part B — the artifacts (acceptance; each pass/fail)
B1 From-scratch install (clean venv) following each card's Quick start against the served build: `ekbasis git-check`
answers. B2 `verify_skopos_hf.py private`: every repo file listed, nothing extra, sha256 matching, visibility as
expected (archive `-dev` private). B3 The dataset: every config loads with `datasets.load_dataset` from the private
repo; counts = counts.json; MANIFEST sha256 match; raw/ files byte-identical to what the code read. B4 The code
repository branch: its test suite passes; `training/skopos` smoke run (the trainer's CPU/tiny-model check) and
`stage_files_skopos.py` reproduce each stage's row count; the generators' smoke run in a disposable container for one
seed per family; secrets scan clean. B5 Card generators in DRAFT=0 build with no pending input; every number in the
cards, report and site equals card_values.json / results (script-checked). B6 The site branch: `tsc` and `next build`
pass; local preview of /ekbasis and /ekbasis/skopos at phone and desktop width; every link resolves (private targets
listed). B7 The production swap runbook dry-run on the RTX (download, smoke, rollback) — not on the 5090.

## Part C — independent review (adversarial)
A reviewer with no part in the work reads the cards, the evaluation report, the dataset card, the site pages and the
announcement draft against the results files and the audit, and lists every claim that is unsupported, overstated,
missing a caveat, or inconsistent between documents; plus licensing/attribution and privacy. Every finding is fixed or
answered before the review package goes to Caio.
