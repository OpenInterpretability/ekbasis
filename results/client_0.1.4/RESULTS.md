# Client 0.1.4: the tests behind `ekbasis.verify` ("check when sure")

`ekbasis.verify` says which of the model's confident answers (confidence ≥ 0.9) to check by real execution before
acting ([docs/VERIFY.md](../../docs/VERIFY.md)). Its signals, reference distributions and thresholds were fitted on
development data only, then tested on fresh items in two pre-registered tests on the released model (Ekbasis-27B,
w4a5). This folder holds what those tests were run from and what they produced. The sections below are the tests'
write-up, as written when they ran.

**What the client ships.** `ekbasis/verify_policy.json` holds the confirmed policy
(`confirm/policy_params.json`, sha256 bdc66886…) and the confirm-2 thresholds (`confirm2/params_confirm2.json`, sha256
0430cdf3…). Both hashes are written inside it.

**Overlap with training.** The items of the development set (29,029 rows), of the first test (19,825) and of confirm-2
(19,790) were checked against every training file of w4a5's lineage (2.2M rows): 0 identical and 0 near-duplicate
items. The same code finds a known overlap in a positive control
([firewall/RESULTS_firewall.md](firewall/RESULTS_firewall.md)).

**The freeze.** Files keep their paths from the test folder, so `shasum -a 256 -c FROZEN_confirm2.sha256` (or
`FROZEN_confirm.sha256`) run here checks every published file the freeze lists. Three exceptions are expected:
- The items, the per-item outputs and the files of other folders of the lab machine (`/root/...`) are not published,
  so their lines report that the file is missing.
- `confirm/extra_calls.py` is the version after deviation 1, and its hash is in `FROZEN_confirm_dev1.sha256`.
- `DEVIATIONS_confirm.md` gained deviation 2 after that freeze. Its first 1,027 bytes are the text frozen there.

**Files.** The analysis code is as it ran on the lab machine; its paths point there.
- `SPEC_confirm.md`, `SPEC_confirm2.md`: the pre-registrations.
- `FROZEN_*.sha256`: the hash lists frozen before each test's fresh items existed, and after deviation 1.
- `DEVIATIONS_*.md`: the deviations.
- `confirm/`, `confirm2/`, `common.py`, `part2_run.py`: the code and the dev-fitted parameters.
- `results/confirm/confirm.json`, `results/confirm2/confirm2.json`, `results/confirm2/heldout_confirm1.json`: the
  results.
- `firewall/`: the overlap check.

## Confirmatory test on fresh items (SPEC_confirm.md, 06/10) — the policy PASSES

The policy, its parameters, the threshold rule, the criteria and the analysis code were frozen in
`FROZEN_confirm.sha256` before any fresh item existed. All parameters came from dev data only (`confirm/dev_calibrate.py`).
Model calls ran on the `:8544` replica only.

Deviations are in `DEVIATIONS_confirm.md`:
1. A one-line thread-safety fix in `extra_calls.py` (the tokenizer is loaded before the worker threads). No value or
   decision changed.
2. The planning secondary suite was not run (infra cut): the replica was stopped for training after the primary
   result was complete.

**Policy.** For a confident answer, average three signals, each mapped through its dev ECDF:
- the error rate of its observable question family (dev history plus online updates);
- the flip/rewrite perturbation;
- the self-check, which is not used on git and shell (a pre-written rule chose this on dev).

Verify by real execution when the score ≥ τ = 0.6414. τ came from the "equal margins" rule on dev, where it gave
84.3% caught with 25.8% verified.

**Fresh items.**
- Source: new seeds from the capability generators. The patched copies reproduce the dev items byte for byte with the
  dev seeds.
- Overlap check: an item is excluded if the sha256 of its prompt or of its evidence equals that of any of the 106,405
  dev questions. 61 accumulation rows were excluded this way, 17 repeated rows were dropped, and no other suite lost a
  row.
- Primary population: 5 suites, 18,642 confident answers, 1,224 of them errors. Each suite is weighted to its share of
  the dev confident population.

| Criterion | Result on fresh | 95% CI | Dev (expected) | Verdict |
|---|---|---|---|---|
| **C1** confident errors caught at τ | **84.9%** | 82.7–87.0% | 84.3% | ✅ ≥ 80% |
| **C1** confident answers verified at τ | **23.4%** | 22.8–24.0% | 25.8% | ✅ ≤ 30% |
| **C2** AUROC, policy vs confidence | **0.909** vs 0.771 | difference +0.125 to +0.151 | 0.894 vs 0.756 | ✅ |
| **C3** accumulation arm (simulate vs direct): caught / verified | **87.9% / 22.8%** | 82.7–92.5% / 20.6–25.1% | 86.2% / 23.4% | ✅ |
| C3 AUROC, ab_gap vs confidence | 0.948 vs 0.710 | difference +0.190 to +0.286 | 0.921 vs 0.653 | — |

**Verification curve** (post hoc, weighted): share of confident answers to verify to catch 50 / 80 / 90 / 95% of
confident errors.

| Signal | Extra calls per confident answer | 50% | 80% | 90% | 95% |
|---|---|---|---|---|---|
| Confidence alone | 0 | 13.4% | 50.9% | 70.4% | 79.1% |
| Perturbation alone | 1 request (2 prompts) | 12.4% | 39.1% | 69.2% | 77.8% |
| Self-check alone | 1 request | 28.4% | 41.2% | 61.5% | 74.1% |
| Family error rate alone (warm + online) | 0 | 8.9% | 18.8% | 30.6% | 43.7% |
| **Policy** (family + perturbation + self-check, no self-check on git/shell) | 1–2 requests | **7.7%** | **18.6%** | **28.5%** | **36.7%** |
| Policy, cold start (no dev history, learns only online) | 1–2 requests | 8.9% | 21.7% | 32.6% | 42.9% |
| Policy with the self-check kept on git/shell | 2 requests | 8.6% | 21.5% | 35.2% | 45.5% |
| Accumulation arm: ab_gap (accumulation only) | 1 request per action (5.1 on average) | 6.0% | 14.7% | 26.9% | 38.1% |

The table needs to be read with these points in mind.
- **Cold start.** It also clears the bar at τ: 85.0% caught with 27.3% verified, AUROC 0.889.
- **Where the gain comes from.** Most of it is the family error rate (AUROC 0.893 alone, no call). This holds on new
  instances of question families the history already contains. It is not evidence for new families or new domains.
- **The feedback assumption.** The online family rate assumes every earlier outcome becomes known, i.e. the action was
  executed and observed. A guard that blocks commands never sees the outcome of the blocked ones.

**Per suite at τ** (unweighted within each suite):

| Suite | Confident (errors) | Caught | Verified | AUROC policy / confidence | Self-check AUROC |
|---|---|---|---|---|---|
| rules_stress | 8,620 (227) | 81.9% | 10.3% | 0.947 / 0.939 | 0.943 |
| sql_wild | 1,966 (273) | **68.9%** | 27.7% | 0.819 / 0.695 | 0.652 |
| shell_wild | 3,623 (307) | 82.4% | 24.2% | 0.920 / 0.795 | **0.570** |
| git_wild | 3,022 (260) | 94.2% | 33.5% | 0.928 / 0.832 | **0.328** |
| accumulation | 1,411 (157) | 98.1% | **59.5%** | 0.834 / 0.710 | 0.819 |

- **The single global τ spreads the effort unevenly.** It verifies 59.5% of accumulation and 33.5% of git, but only
  10.3% of rules, and sql stays below 80% caught. A threshold per domain would rebalance this; that is untested.
- **Accumulation:** the simulate-vs-direct arm is the better tool there (87.9% caught with 22.8% verified, versus 59.5%
  verified by the policy).
- **Dropping the self-check on git/shell is confirmed.** Kept, it gives AUROC 0.895 vs 0.928 on git (97.7% caught with
  44.6% verified) and 0.848 vs 0.920 on shell (77.9% caught with 27.5% verified). On fresh git the self-check is
  anti-informative again (0.33).
- **Not run (infra cut):** the planning secondary suite (sampled Hanoi-6, Lights Out 4×4, jugs, Sokoban). Its direct
  answers are complete: 8,349 confident answers, 225 errors (2.7%, dev 2.4%). Its extra calls stopped at 5,613 of
  8,349 when the replica was stopped, and it is not analysed.
- **Excluded by design:**
  - apps and habit_vs_rule are hand-written scenarios, and a new seed only rewords analysed items;
  - languages_formats would need Claude translations;
  - web's questions come from the model's own games.

  Together they held 156 of the 947 dev confident errors.

## Confirm-2 (06/10): per-domain, conformal and certified rules (SPEC_confirm2.md) — P1, P2, S1–S3 pass; P3 fails

The score is unchanged; only the decision rule changes.
- **P-domain** (dev only): per-suite thresholds, equal recall under a 25% budget.
- **P-conformal** (dev only): Mondrian, α = 0.15, family groups with ≥ 10 errors, else the suite.
- **P-ltt**: a Learn-then-Test acceptance rule certifying "errors among accepted ≤ α with probability ≥ 95%",
  hierarchical family → suite, unseen → verify. It is calibrated on confirm-1, because dev is case-control.
- **Required baseline:** the abstain instruction.

**Part A: held-out check on confirm-1 data** (CPU, after the freeze). Not confirmatory: confirm-1's aggregates were
known when P-domain was designed. 18,642 confident answers, 1,224 errors; 95% cluster-bootstrap CIs.

| Rule | Caught | Verified | Every suite ≥ 80% caught? |
|---|---|---|---|
| Global τ (confirmed rule; reproduces confirm-1) | 84.9% | 23.4% | no: SQL 68.9% |
| **P-domain** | 84.8% (82.6–87.0) | **22.3%** (21.7–22.9) | **yes** |
| **P-conformal** | **87.8%** (85.7–89.6) | 26.1% (25.5–26.9) | **yes**; 5 of 17 groups below the 85% target |
| Confidence alone, at the global rule's 23.4% | 64.2% | 23.4% | — |

Under P-domain:
- SQL goes from 68.9% to 86.8% caught, but verifies 50.1% of its confident answers.
- Git drops from 33.5% to 20.3% verified (84.2% caught).
- Running totals drop from 59.5% to 42.0% verified (86.6% caught).

**Learn-then-Test, in sample on confirm-1** (its calibration set, so not a test). At α = 2%:
- 78.5% of units are accepted;
- errors among accepted run 0.9–1.6% per certified suite;
- SQL cannot be certified (13.9% confident errors), so all of it is verified.

At α = 1%, 70.8% of units are accepted, and SQL and running totals are always verified.

**Part B: confirm-2 on fresh items** (06/10, 15:53–17:55 UTC, on the restarted shared :8544 w4a5 server; ≤ 16 in
flight).
- **Items:** new seeds from the same generators. 98 accumulation rows were excluded for matching dev (64) or confirm-1
  (34) by hash, and 14 repeated rows were dropped; no other suite lost a row.
- **Population:** 18,615 confident answers, 1,202 of them wrong, every extra call done (0 errors), reweighted to the
  dev mix. 95% cluster-bootstrap CIs.

| Rule | Caught | Verified | Criterion | Verdict |
|---|---|---|---|---|
| Global τ (S1: replication of 06/10) | 83.5% (81.1–85.6) | 23.4% (22.8–24.1) | ≥ 80% / ≤ 30% | ✅ |
| **P1 P-domain** | 84.5% (82.2–86.6) | **22.6%** (22.0–23.3) | ≥ 80% / ≤ 30%, every suite ≥ 75% (lowest: shell 79.9%) | ✅ |
| **P2 P-conformal** (α = 0.15) | **86.3%** (84.2–88.4) | 26.2% (25.5–26.8) | ≥ 85%, every suite ≥ 80% (lowest: shell 83.4%) | ✅ (4 of 17 groups under 85%) |
| **P3 P-ltt** (≤ 2% errors among accepted) | 82.3% of errors caught; 1.16% errors among accepted (116 / 10,001 units) | 21.4% | ≤ 2% **and** no node significantly above | ❌ The rules suite node (rare rules families) had 3.4% (81 / 2,367), significant |
| P-ltt at 1% (secondary) | 90.2% caught; 0.71% among accepted | 29.3% | ≤ 1%, no node above | met (not claimed) |
| P-ltt pooled λ, 2% / 1% (reported) | 70.9% / 87.2% caught; 1.71% / 0.85% among accepted | 12.1% / 22.4% | — | under α |
| Confidence alone, at the global rule's 23.4% | 65.7% | 23.4% | — | — |
| **Abstain instruction** (required baseline) | 1.0% | 0.11% | S3: S beats it | the model almost never says "unsure" |
| Accumulation arm (simulate vs direct), replication | 86.3% | 22.2% | ≥ 80% / ≤ 30% | ✅ (AUROC 0.942) |

AUROC of the score is 0.907, against 0.773 for confidence (difference CI +0.121 to +0.146, S2 ✅) and 0.685 for
P(unsure) (difference CI +0.203 to +0.240, S3 ✅).

Per suite, caught / verified (unweighted within each suite):

| Suite | Global τ | P-domain | P-conformal |
|---|---|---|---|
| rules | 81.8 / 10.4 | 85.5 / 12.8 | 91.4 / 18.5 |
| sql | **67.2** / 27.3 | 87.6 / **50.3** | 87.2 / 37.7 |
| shell | 80.8 / 23.2 | 79.9 / 21.6 | 83.4 / 25.8 |
| git | 93.4 / 34.4 | 83.7 / 20.1 | 86.8 / 21.6 |
| accumulation | 95.9 / 59.4 | 87.0 / 44.4 | 83.6 / 54.4 |

**What this means**
- **The confirmed policy replicated** on a second fresh set: 83.5% caught with 23.4% verified.
- **Per-domain thresholds fix SQL.** SQL goes from 67% to 88% caught, and every suite is ≥ 80% except shell (79.9%),
  at slightly less overall verification (22.6%). SQL then verifies half of its confident answers.
- **The conformal version** buys about 2 points more caught for about 3.6 points more verified.
- **The certified acceptance rule did not pass as pre-registered.**
  - The overall error rate among accepted was 1.16%, under the 2% target, but rare rules families pooled into the
    suite node exceeded it (3.4%). This is the HG-CRC warning: a family that falls back to its suite inherits only the
    suite's average.
  - The pooled and the 1% versions held (reported only).
  - Next: no fallback for rare families (verify them), or a difficulty level in the hierarchy.
- **The abstain instruction is not a usable baseline for this model.** w4a5 picked "unsure" on 0.11% of confident
  answers.
