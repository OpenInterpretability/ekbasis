# WS-U confirm-3: the corrected certified acceptance rule (SPEC, frozen before any confirm-3 item exists)

Written 06/10. Hashes are in `FROZEN_confirm3.sha256`.
- **Not run yet:** the coordinator runs it when a w4a5 replica is free (GPU 2 is busy).
- **No Claude spend. Nothing published.**

## Why

Confirm-2's P3 failed. Its Learn-then-Test (LTT) rule aimed at ≤ 2% errors among the confident answers acted on
without checking:
- **Overall** it held: 1.16%.
- **But** rare rules families, which fell back to their suite's λ, reached 3.4% (81 of 2,367). That was significant
  after Bonferroni.

This is the HG-CRC warning (arXiv 2607.24562): a family that falls back to its suite inherits only the suite's average.

## The two fixes (`confirm3/ltt3.py`; parameters in `confirm3/params_confirm3.json`)

The score is the frozen one, unchanged (confirm-1's policy, variant B: dev warm start, online within the set).

| Rule | Decision |
|---|---|
| **L1 strict** (primary) | A family with ≥ 3/α calibration units and a certified λ accepts when S < λ_family. **Every other family, rare, uncertified or never seen, is always verified.** No fallback. |
| **L2 difficulty** (secondary) | A family with its own certified λ uses it. Any other family seen in calibration falls back to a **(suite, difficulty)** node instead of the suite, so a hard family never inherits an easy average. Difficulty is the family's calibration error rate among its confident units, Beta(1, 1), in bins [0, 1%), [1, 3%), [3, 10%), [10, 100%]; in deployment, the family tracker's rate. Each node is calibrated on the units of the families that use it. Unseen families, and nodes with nothing certified, are always verified. |

**Calibration** (`confirm3/fit_ltt3.py`) uses **confirm-1 + confirm-2 only**: both fully enumerated fresh sets,
already spent, 25,470 units, 1,318 of them errors.
- **Unit:** one confident question per scenario (seeds 61 and 62).
- **λ:** fixed-sequence LTT over acceptance fractions 0.300…0.995, binomial p-values, δ = 0.05, from confirm-2's
  `metrics2.ltt_lambda`. The sequence starts at the first count that could be certified at all.
- **Levels:** α = 0.02 (primary) and 0.01 (secondary).

**Expected price** (in sample on the calibration units; confirm-3 is the test):

| α = 2% | Verified | Errors among accepted | Errors caught | rules / sql / shell / git / accumulation verified |
|---|---|---|---|---|
| **L1 strict** | 44.4% | 0.27% | 97.1% | 22% / 100% / 100% / 100% / 72% |
| **L2 difficulty** | 26.4% | 0.25% | 96.5% | 14% / 51% / 36% / 41% / 72% |
| α = 1%: L1 / L2 | 57.1% / 33.8% | 0.01% / 0.05% | 99.9% / 99.3% | |

Under L1 every sql, shell and git answer is verified: none of their families has the 150 units a certification needs
(the data cost the research scan named, ≈ 3/α). L2's difficulty nodes are what let those suites accept anything.

## Confirm-3: items, calls, analysis

**Items.** Same generators and settings, new seeds:

| Suite | Setting |
|---|---|
| rules | 9300601 (addendum 9300602) |
| accumulation | 9300603, 4 per cell, condition A only |
| sql | seeds 1000·t + 100001…100400 (disjoint from dev, confirm-1 and confirm-2) |
| shell | 9300605, instances 300… |
| git | salt `git_wild_fresh_9300606`, reps 300… |

- **Overlap check** (`fresh_rows3.py`): a row is excluded if its prompt's or its evidence's sha256 equals that of any
  dev, confirm-1 or confirm-2 question.
- **Extra calls** (`extra_calls3.py`): the perturbation request and the self-check, as in confirm-1. No abstain
  baseline: confirm-2 showed it unused, at 0.11%. The server must be w4a5.
- **Chain:** `confirm3/run_confirm3.sh` (`EKBASIS_URL=<replica>`, ≤ 16 in flight, resumable). Analysis:
  `confirm3_analyze.py` → `results/confirm3/confirm3.json`. Units are one confident question per scenario (seed 63).

**Criteria** (point estimates; one-sided binomial per node, Bonferroni over the nodes with accepted units):

| Id | Claim | Pass |
|---|---|---|
| **C1** | L1 strict, α = 2% | errors among accepted ≤ 2% **and** no node significantly above 2% |
| C2 | L2 difficulty, α = 2% | the same |
| S1 | the per-domain rule (the client's default), third fresh test | ≥ 80% caught, ≤ 30% verified, every suite ≥ 75% |

**Reported, not claimed:** α = 1% for both rules, the price of each (verified share, errors caught, per suite), every
node, the conformal and global rules.

## Cost

- **GPU:** about 1 h 40 min on one shared w4a5 server, maybe 2 h with RA/BR traffic.
  - Requests: about 13,600 direct (rules 9,075, sql ~900, shell ~816, git ~1,014, accumulation ~1,820), plus 2 per
    confident answer (about 37,200): about 51,000 requests, 76,000 prompts.
  - Reference times: confirm-1's two-request extra phase took 68 min; direct answers without accumulation's step
    condition take about 30 min.
- **CPU:** about 5 min of generation and real execution (sqlite, bash, git sandboxes).
- **Disk:** under 1 GB.
- **No Claude spend.**

## Caveats

- **Guarantees.**
  - The guarantees hold per node, at δ each, for items exchangeable with the calibration (same generators, new seeds).
  - They hold for this model version only (w4a5; arXiv 2609.04445). Re-fit per release.
- **Deployment.**
  - The family rates and difficulty buckets would come from the client's tracker. In deployment they must be learned
    with observed outcomes only: audits or sandbox replay for blocked actions.
  - The thresholds stay fixed. An online version (ACI, rolling risk control or MVP per family) is the step after this.

## Procedure

**Frozen before any confirm-3 item exists:**
- this SPEC;
- `confirm3/ltt3.py`, `fit_ltt3.py`, `params_confirm3.json`, `ltt3_calibration.json`;
- `fresh_rows3.py`, `extra_calls3.py`, `confirm3_analyze.py`, `run_confirm3.sh`, `test_confirm3_analyze.py`;
- the confirm-1/2 files they read.

The analysis ran end to end on confirm-2 data before the freeze; the per-domain numbers reproduced confirm-2 exactly.
Deviations go to `DEVIATIONS_confirm3.md`.
