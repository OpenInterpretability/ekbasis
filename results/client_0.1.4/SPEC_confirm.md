# WS-U confirmatory test: "check when sure" on fresh items (SPEC, frozen before any fresh item exists)

Written 06/10 BRT. The policy, its parameters, the threshold rule, the criteria and the analysis code are frozen in
`FROZEN_confirm.sha256` before the first fresh item is generated and before the first model call on a fresh item.
Released model w4a5 (Ekbasis-27B). Model calls only on the rig's `:8544` replica (GPU 3), never more than 16 requests in
flight, never `:8542`. Zero Claude spend. Nothing published.

## The question

The best policy from parts 1–4 combines three signals: the observable question family's error rate learned online, the
flip/rewrite perturbation and the self-check. Does it hold on **new items**? The bar is to catch ≥ 80% of confident
errors (answers with confidence ≥ 0.9 that are wrong) while verifying ≤ 30% of confident answers, with a threshold fixed
in advance.

## The frozen policy (`confirm/policy.py` + `confirm/policy_params.json`, made by `confirm/dev_calibrate.py` from dev data only)

For each confident answer:
- **famobs**: the error rate of its observable family, (errors + 1) / (answers + 2).
  - It counts the dev history (WS-P's 29,029 answered questions) and every earlier fresh answer, so it is a warm start
    plus online updates.
  - Outcomes become known after execution (full delayed feedback).
  - Stream order: sha256("wsu-confirm-20261006|row id").
  - Family key: Addendum 2's `observable()`, unchanged. It drops accumulation's distance to the limit and planning's
    move kind; rules_stress, sql_wild, shell_wild and git_wild keep their family as is.
- **minpert**: 1 − min(P_reordered(answer), P_prefixed(answer)), using WS-P's two perturbations in one request: options
  in reverse order, and the fixed prefix "Answer from the rules and the state above. ".
- **verify**: P(no) on the self-check question 'Consider this question: "<q>" Is "<answer>" the correct answer?', asked
  as one request with the same evidence.
- **Score:** the mean of the signals, each mapped through its dev mid-ECDF. The ECDF is weighted to the dev population of
  confident answers in the primary suites.
- **Self-check dropped on git_wild and shell_wild** (variant B). A pre-written rule chose it: the lower dev verify share
  at 80% recall wins, and B needs 20.4% against A's 23.6%. On dev, AUROC on git is 0.910 for B vs 0.866 for A, and on
  shell 0.894 vs 0.825.
- **Check the answer by real execution when score ≥ τ = 0.641350** (stored exactly in policy_params.json).
- **Threshold rule, fixed before seeing any fresh data:** τ maximises min(recall − 0.80, 0.30 − share) on dev
  ("equal margins").
- **Dev at τ:** recall 84.3%, share 25.8%, AUROC 0.894 against confidence's 0.756.

Extra cost per confident answer: one request (two prompts) on git and shell; two requests (three prompts) elsewhere. The
family rate costs no call.

## Items

**Primary population:** rules_stress, sql_wild, shell_wild, git_wild, accumulation. Their dev confident answers number
10,198, of which 676 are errors. The truth comes from each generator's simulation or from real execution (sqlite, bash
sandboxes, git repositories), as in the capability map.

Each generator is a copy patched only with a seed switch (`confirm/make_fresh.py`). With the default (dev) settings the
copies were checked to reproduce the dev items byte for byte (`confirm/repro_check.py`: all identical). Fresh settings:

| Suite | Fresh settings | Dev |
|---|---|---|
| rules_stress | FRESH_SEED 9100601 (addendum 9100602), main + addendum, N_BASE 75, N_MANUAL 25 | seed 20261005, same plan |
| sql_wild | seeds 1000·t + 501…900 per template, 10 pairs per template, full-schema variant only | seeds 1000·t + 1…200, 5 pairs |
| shell_wild | FRESH_SEED 9100605, instances 100… (2× the dev count) | seed 2026105, instances 0… |
| git_wild | salt "git_wild_fresh_9100606", reps 100… (2× the dev count) | salt "git_wild", reps 0… |
| accumulation | FRESH_SEED 9100603, 4 instances per cell; conditions A (direct) and B (released `simulate`) | seed 20261005, 3 per cell |

**Secondary suite: planning_probe.** It is reported separately and is not in the primary criterion. The dev probe
enumerated every (state, action) pair of the small worlds, so only the sampled worlds can give new pairs. The fresh set
uses their dev recipe with base seed 9100604: Hanoi 6, Lights Out 4×4, 12 random jug worlds and 16 Sokoban levels
(`confirm/fresh_planning.py`; its `check` reproduces the dev pairs and worlds with the dev seeds).

**Not included.** These generators cannot make new items:
- apps and habit_vs_rule are hand-written scenarios, and a new seed only rewords analysed items;
- languages_formats would need Claude translations;
- web's questions come from the model's own navigation games.

Together they held 156 of the 947 dev confident errors.

**Overlap check by hash (`confirm/fresh_rows.py`).** A fresh question is excluded if the sha256 of its exact prompt, or
of its evidence (the state text), equals that of any dev question. The dev side is every question the capability suites
ran (uncapped, 106,405 distinct prompts and 31,169 distinct evidences) plus WS-P's dataset. Repeated fresh prompts keep
one copy. Exclusions are reported per suite.

Rows are built with WS-P's own `build_dataset.py` functions (the same prompts and family labels as dev). Runner rows with
an error, a skip or missing fields are set aside and counted.

## Criteria

All are computed on fresh confident answers. "Reweighted" means each primary suite is weighted to its share of the dev
confident population (rules 4,739; sql 986; shell 1,797; git 1,523; accumulation 1,153); within a suite every fresh
confident answer counts once.

- **C1 (primary).** PASS iff recall(τ) ≥ 0.80 **and** share(τ) ≤ 0.30, using the point estimates on the reweighted
  primary population. 95% CIs come from a cluster bootstrap within suites (cluster = scenario, 2,000 replicates).
- **C2 (confirmatory, secondary).** The weighted AUROC of the policy score exceeds that of confidence (1 − conf), with the
  95% cluster-bootstrap CI of the difference above 0.
- **C3 (separate arm, accumulation).** The signal is ab_gap = |P_A(answer_A) − P_B(answer_A)|. A asks all actions at once;
  B is the released `simulate` one action at a time, and its last step is used.
  - The threshold τ_acc = 0.033441 comes from the same equal-margins rule on dev, where it gives recall 86.2% and
    share 23.4%.
  - PASS iff recall ≥ 0.80 and share ≤ 0.30 on the fresh accumulation confident A answers (natural population).
  - The arm also reports AUROC against confidence and its cost: one request per action.
- **Exploratory, reported but not claimed:**
  - the post-hoc verify share needed for 50/80/90/95% recall, for the policy and each signal;
  - unweighted numbers;
  - cold start (no dev history);
  - the self-check kept on git and shell;
  - every suite separately, including git and shell;
  - planning (secondary suite).

## Procedure (`confirm/run_confirm.sh`, detached on the rig, one step at a time)

1. Generate the fresh items.
2. Ask the direct questions with each suite's own runner (client 0.1.0, as dev).
3. Build the rows and run the overlap check.
4. Make the extra calls on every kept primary confident answer.
5. Run the analysis (`confirm/confirm_analyze.py`) → `results/confirm/confirm.json`.
6. Run the planning suite, then re-run the analysis. The primary numbers do not change, because the stream order is per
   row and the weights use primary rows only.

Any deviation after freezing is logged in STATUS.md with its reason. A fix that is mechanical and made before the first
fresh model call is allowed and logged. Nothing is tuned on the fresh set.
