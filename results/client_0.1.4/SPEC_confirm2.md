# WS-U confirm-2: per-domain, conformal and certified "check when sure" rules (SPEC, frozen before Part A and before any confirm-2 item exists)

Written 06/10. Hashes are in `FROZEN_confirm2.sha256`.
- **No model call to write this.** Model calls in Part B go only to the w4a5 replica the coordinator assigns
  (`/health` must show `merged_w4a5`), with ≤ 16 in flight.
- **No Claude spend. Nothing published.**

## The score stays the same; only the decision changes

Every rule here uses the score S of the policy confirmed on 06/10, unchanged (`confirm/policy.py`, variant B):
- the observable family's error rate (dev history, then online);
- the flip/rewrite perturbation;
- the self-check, except on git and shell;
- each signal mapped through its dev mid-ECDF, then averaged.

The global rule verifies a confident answer when S ≥ τ = 0.6414. Three new rules, with every parameter fixed before
this SPEC (`confirm2/params_confirm2.json`):

| Rule | Decision | Fitted on | Values |
|---|---|---|---|
| **P-domain** (per-suite thresholds) | verify when S ≥ τ_suite | dev only (`fit_dev.py`) | Equal recall r in every suite, the largest r whose dev share verified is ≤ 25%: r* = 0.83. τ: rules 0.6056, sql 0.4836, shell 0.6571, git 0.7675, accumulation 0.7361. Dev, in sample: 83.1% caught, 24.8% verified. |
| **P-conformal** (Mondrian split conformal on the miss rate) | verify when S ≥ τ_group | dev only (`fit_dev.py`) | α = 0.15. A family with ≥ 10 dev confident errors is its own group (12 groups); the rest of each suite pools (5 groups). τ_g = k-th smallest error score, k = ⌊α(n_g+1)⌋. Guarantee per group: P(caught \| confident error) ≥ 0.85. Dev, in sample: 88.6% caught, 29.3% verified. |
| **P-ltt** (acceptance rule certified by Learn-then-Test) | accept (act without verifying) when S < λ_node; everything else is verified | confirm-1 (`fit_ltt.py`), see below | Errors among accepted ≤ α with probability ≥ 1 − δ, at α = 0.02 (primary) and 0.01 (secondary), δ = 0.05. Hierarchical nodes, family → suite. α = 0.02: suite λ rules 0.7973, git 0.7097, shell 0.6221, accumulation 0.6756; **sql: nothing certified, always verify**; 28 of 42 family nodes certified. α = 0.01: rules 0.6921, git 0.5696, shell 0.5177; sql and accumulation always verify. Pooled single λ: 0.7431 (α = 0.02), 0.6133 (α = 0.01). |

**Learn-then-Test details** (LTT/SGR; after HG-CRC, arXiv 2607.24562):
- **Unit:** one confident question per scenario (a fixed seed), because questions of the same scenario share the
  state.
- **Test:** fixed-sequence testing over acceptance fractions 0.300 … 0.995 in order, with a binomial p-value for
  H0 "error rate among accepted > α".
- **Where the sequence starts:** the first fraction whose accepted count could be certified at all, n ≥ ln δ / ln(1−α)
  (149 at 2%, 299 at 1%). This depends only on group size, never on labels.
- **Family nodes:** a family gets its own node when it has ≥ 3/α calibration units. With zero observed errors,
  certifying a family costs about 3/α accepted units: 150 at 2%, 300 at 1%.
- **Fallback:** a family without its own certification uses its suite's λ (rare families pool). A family never seen
  in calibration is always verified (unseen → verify), and so is a suite with nothing certified.

**Why LTT is calibrated on confirm-1, not on dev:**
- The guarantee needs an exchangeable, fully counted sample with every signal.
- Dev is a case-control sample: every confident error, but about 20% of the right answers. The error rate among
  accepted answers cannot be counted there.
- Confirm-1 was fully enumerated and its confirmatory test is complete, so it is spent. Confirm-2 uses new seeds.
- The coordinator's "dev only" applies to P-domain and P-conformal, which are fitted on dev only.

**Required baseline, abstain instruction** (arXiv 2510.16492):
- **Request.** Ask the same question again with the prefix `If the rules and the state above do not settle the answer,
  choose "unsure". ` and one more option, `unsure` (described "not sure"). A yes/no question becomes yes / no / unsure.
  One request.
- **Decision.** Verify when the model picks "unsure"; P(unsure) is its score for curves.
- **The bar.** Any external claim of ours must beat this free instruction.

## Part A — held-out check on confirm-1 data (CPU, run right after this freeze; NOT confirmatory)

P-domain and P-conformal were fitted on dev only, so the confirm-1 fresh set is held out for them. Script:
`confirm2/heldout_confirm1.py` → `results/confirm2/heldout_confirm1.json`.
- **Not confirmatory.** Confirm-1's aggregates (e.g. SQL caught 68.9% under the global τ) were known when P-domain was
  designed.
- **Reproduction check.** The global rule must reproduce confirm-1 exactly (84.86% / 23.44%); it was checked before
  this freeze.
- **LTT excluded.** LTT is calibrated on confirm-1, so it is not evaluated there.

## Part B — confirm-2 on fresh items (when a w4a5 replica is assigned)

**Items.** Same generators and settings as confirm-1, new seeds:

| Suite | Setting |
|---|---|
| rules | 9200601 (addendum 9200602) |
| sql | seeds 1000·t + 201…500 (dev 1…200, confirm-1 501…900), 10 pairs, full schema only |
| shell | 9200605, instances 200… |
| git | salt `git_wild_fresh_9200606`, reps 200… |
| accumulation | 9200603, 4 per cell, conditions A and B |

- **Overlap check** (`fresh_rows2.py`): a row is excluded if its prompt's or its evidence's sha256 equals that of any
  dev question (106,405 prompts) or any confirm-1 row.
- **Extra calls per confident answer** (`extra_calls2.py`): perturbation, self-check and abstain baseline, three
  requests.
- **Chain:** `confirm2/run_confirm2.sh` (`EKBASIS_URL=<replica>`; resumable). Analysis: `confirm2/confirm2_analyze.py`
  → `results/confirm2/confirm2.json`.

**Criteria.** The point estimates decide. The population is reweighted to the dev confident mix of the 5 suites, as
in confirm-1. 95% CIs come from a cluster bootstrap (scenario), 1,000 replicates.

| Id | Claim | Pass |
|---|---|---|
| **P1** | P-domain | overall caught ≥ 80% **and** verified ≤ 30% **and every suite** caught ≥ 75% |
| **P2** | P-conformal | overall caught ≥ 85% **and every suite** caught ≥ 80%. The verified share is reported: it is the price of the guarantee. |
| **P3** | P-ltt, α = 0.02, hierarchical. Units are one confident question per scenario (seed 62, natural mix). | error rate among accepted ≤ 2% **and** no certified node with a significant excess (one-sided binomial, p < 0.05 / number of nodes with accepted units) |
| S1 | the global rule replicates | ≥ 80% caught, ≤ 30% verified |
| S2 | S beats confidence | AUROC difference, CI above 0 |
| S3 | S beats the abstain baseline | AUROC(S) − AUROC(P(unsure)) with CI above 0, **and**, at the baseline's own verified share, S catches more confident errors than the baseline |

**Reported, not claimed:**
- P-ltt at α = 0.01 and the pooled λ's;
- the accumulation arm's replication (simulate vs direct at τ_acc);
- the realized recall of every conformal group, against 0.85;
- every suite under every rule.

## Caveats stated in advance (from the research scans: decision_model/mission/RS/RESEARCH.md and the second scan)

- **One model version** (arXiv 2609.04445: when the scoring changes, coverage fell from 90% to 74%).
  - Transforms, thresholds and λ's belong to w4a5. Re-fit per release and monitor online.
  - `extra_calls2.py` refuses to run on another model.
- **Exchangeability.** The guarantees (conformal, LTT) hold for items exchangeable with the calibration items: same
  generators, new seeds. Real traffic is not.
- **Conformal.**
  - The guarantee is per group of a partition, not simultaneous over groups. HG-CRC's Bonferroni over a hierarchy is
    stricter: 22–37 points more abstention than global control.
  - The score's transforms were fitted on the same dev rows, a mild dependence.
- **LTT.**
  - The guarantee holds per node at δ each, not simultaneously over nodes.
  - A family that falls back to its suite inherits only the suite's average.
  - Certifying costs data: about 3/α accepted units per family with zero errors.
  - SQL cannot be certified at 2%. Its confident error rate (13.9% on confirm-1) leaves no large low-risk subset under
    this score, so every confident SQL answer is verified.
- **Online, not tested here.**
  - The family rates are learned online, but the thresholds are fixed.
  - The online next step: ACI or a rolling risk control per family; multivalid (MVP) control for overlapping groups
    (suite × question type × family); anytime-valid acting with e-processes (CSA, arXiv 2605.20270).
- **Blocked actions.**
  - In deployment a blocked action has no outcome. Label blocked actions by sandbox replay or random audits, or the
    online family rate is biased low.
  - Blocking also changes the agent's next proposals, so offline calibration may not hold live. That needs a live
    agent study.
- **Precedents.**
  - KnowNo asks for help when the conformal set has more than one option. For one-label questions with confident
    answers this reduces to a confidence threshold, which the confidence baseline covers.
  - CORA is a conformal execute/abstain guard for mobile agents, the closest product design.
  - Trust-or-Escalate is a cascade Ekbasis → bigger model → human with a guarantee. Our "verify" could route to a bigger
    model when execution is impossible; not tested (no Claude spend).

## Procedure and deviations

**Frozen before Part A:**
- this SPEC;
- `confirm2/fit_dev.py`, `fit_ltt.py`, `metrics2.py`, `heldout_confirm1.py`;
- `fresh_rows2.py`, `extra_calls2.py`, `confirm2_analyze.py`, `run_confirm2.sh`, `test_confirm2_analyze.py`;
- `params_confirm2.json` (+ the dev-only copy), `dev_reference_confirm2.json`, `ltt_calibration.json`;
- and the confirm-1 files they read.

Before freezing, the analysis ran end to end on dev data posing as fresh. That test found the arm's τ hard-coded
rounded; it is now read exactly from the frozen confirm-1 parameters.

Any later change is logged in `DEVIATIONS_confirm2.md` with its reason. Nothing is tuned on confirm-2.
