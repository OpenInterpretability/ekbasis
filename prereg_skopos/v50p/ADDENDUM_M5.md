# Addendum M5 — does the long-horizon gain transfer to REAL git? (written 2026-10-15 ~00:05 UTC, before any M5 score)

Data: `data/git_long.jsonl` (`scripts/gen_git_long.py`): 900 questions on real git sequences of 5, 8 and 12 commands,
each executed by gitbox3 on a scratch repository for the exact answer (lost work, failing commands, state questions);
no held command types; seeds 7000+. The lineage (and the pilot/dose) trained git on 1–3 commands only, and the
plan-level items were synthetic worlds, never git. Models: base, pilot adapter, dose adapter, scored by the same
trainer code (eval_base / eval_adapter, floor prompts). Reported: accuracy by length, and by question type for
"lost" and "fails"; paired bootstrap (2,000, seed 20261014) dose − base and pilot − base.
Reading fixed now (exploratory, no release claim): transfer if dose − base on 8+12 commands ≥ +0.03 with CI above 0;
no transfer if the CI includes 0; harm if the CI is entirely below 0.
