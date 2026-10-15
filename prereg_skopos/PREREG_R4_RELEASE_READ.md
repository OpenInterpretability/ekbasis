# R4 release read (pre-registration, 2026-10-15 17:00 UTC, before any served R4 answer on these items)

## What
The release protocol of the public repo (PREREG_release_eval.md as applied in RELEASE_EVAL.md, the larger guard set of
PLAN_guard_set.md), on **R4 merged into Ekbasis-Skopos-27B** (bf16, /root/Skopos-R4-27B: 496 LoRA pairs, scale 2.0),
served exactly as in production (vLLM `serve_vllm.sh` flags + the model folder's `serve.py`), through `/v1/systemone`.
Items: `caiovicentino1/ekbasis-data` raw/ (git3_test_known/held, multi_test_trainfam/testfam, ftest_family + gold0,
guard_known/held). Scripts: release_eval.py (as is), release_eval_extra_rtx.py (ftest part only; the rig-only LLM
comparison removed), guard_big_served_rtx.py (trainer readout optional). Reference = the current public release's own
served predictions in results/release_eval/, recomputed by the same comparison code (compare_release.py).

## Criteria (each: at most 1 point worse than the current release; ECE at most +0.01)
1. git v3 known + held, all questions (release 96.62%).
2. Never-trained worlds, answers the actions change: one prompt per question (81.16%) and read-once (78.03%).
3. ftest_family, answers the actions change (81.88%).
4. ECE on git v3 (both computed here with the same code from the predictions' confidences).
5. Guard, larger set, known command types: work-losing flagged at 0.2 (828/863) and false alarms (37/863), each within
   1 point of 863.
6. Guard, larger set, held-out command types: flagged (767/799) and false alarms (49/799), each within 1 point of 799.
7. T3c (fresh real-repository scenarios) only if its script runs here without the rig; otherwise reported as not run.
**R4 passes the release read if every criterion that runs holds.** Reported regardless: multi_test_trainfam,
per-question-type git, every number with its CI. A pass does not publish anything: release needs Caio's OK.

## Before the read
Served-vs-trainer equivalence on 500 items (git_long 300, guard_known 200): same answer ≥ 98% expected; if lower, the
serving is investigated before the read.
