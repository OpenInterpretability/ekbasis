# Certified mode on Ekbasis-Skopos-27B: does Ekbasis-27B's certificate carry over? (pre-registration)

**Status: written by workstream D on 15/10/2026; sealed by the main thread at 2026-10-16T00:56:03Z, nothing run.** The main thread seals it (sha256 of this file and
of `certified_carryover/MANIFEST.sha256`, with the time) before step 1 and before any request to a Skopos server; any
later change is a deviation. Modeled on the MLX check of `docs/VERIFY.md` ("On the MLX 4-bit build", 2026-10-07), whose
pre-registration, code and data are WS-MAC T2 (`mission/MAC/SPEC_T2.md`, `t2/`).

## Question

`ekbasis.verify`'s certified mode (`rule="certified"`, confirm-3's L2, α = 2%, δ = 0.05) acts on a confident answer
without checking it only where a Learn-then-Test certificate holds. The certificate was calibrated on Ekbasis-27B (w4a5,
bf16) and "holds for w4a5 and for items exchangeable with the calibration items" (`ekbasis/verify.py`, docs/VERIFY.md);
on the MLX build it was checked empirically and held (1 error among 666 accepted, 95% upper bound 0.71%). Does the
guarantee — error among the accepted answers ≤ 2%, no node above — hold when the same client, with the same thresholds,
reads Ekbasis-Skopos-27B's answers?

This is a check that the certificate carries over, on fresh items. It is not a new certificate.

## What is fixed

- **Client:** `ekbasis` 0.1.41 from PyPI (the current release); `verify.py` sha256 `f85aec3e…15f5` and
  `verify_policy.json` `58e9ea93…b88b`, both unchanged since 0.1.5, the version the certificate was made for (its
  sources: `policy_params.json` `bdc66886…`, `params_confirm2.json` `0430cdf3…`, `params_confirm3.json` `fd83e0e2…`, copied
  in `certified_carryover/confirm_code/`, byte-identical to the code repository's `results/client_0.1.5/`). The client's
  verify reads the raw probabilities; the `calibrated` field plays no part (served with or without it, the same).
- **Models (served as released):** primary **Ekbasis-Skopos-27B-INT4** (the hosted API's next model), vLLM with the
  build's `serve_vllm.sh` and `serve.py` on the RTX PRO 6000; secondary **Ekbasis-Skopos-27B** (bf16), the same way. The
  run refuses a server whose `/health` model name does not contain "Skopos".
- **Items:** confirm-3's frozen fresh rows (`fresh_rows_bf16.jsonl`, sha256 `0130df16…579f`) and Ekbasis-27B's extra calls
  on them (`extra_bf16.jsonl`, `e319ea74…064a`), and T2's stratified subset (`subset_requests.jsonl`, `6cd779a9…`):
  1,400 scenarios, 2,781 questions — rules_stress 600, sql_wild 200, shell_wild 200, git_wild 200, accumulation 200
  scenarios — **all of them** (T2 ran the first 1,081 for lack of time on a Mac; here there is no time cap).
- **Code:** `certified_carryover/` as listed in its `MANIFEST.sha256` (run_carryover.py, analyze_carryover.py,
  overlap_step.py, run_carryover.sh, confirm_code/, data/). analyze_carryover.py is T2's analyze_t2.py with paths, the
  overlap exclusion, the MLX reference and the C2+ reading added; given T2's own raw file it reproduces T2's published
  numbers exactly (MLX: L2 666 accepted, 1 error, weighted 0.209%, upper bound 0.71%, 26.67% verified; Ekbasis-27B bf16
  on the same scenarios: 686, 5, 0.604%) — checked 15/10 — and a dry run with Ekbasis-27B's answers in place of a
  model's runs end to end.

## Step 1 — overlap, before any request

confirm-3's items were firewalled against Ekbasis-27B's lineage (`results/client_0.1.5/firewall`), not against the rows
Skopos added (the first Skopos' factory and FX rows, the last stage's factory, git and plan rows).
- `overlap_step.py export` writes the 2,781 questions as the client sends them (state, question, options).
- The D8 audit (`audit/audit_overlap_skopos.py`, rules unchanged: identical, or word 8-gram Jaccard ≥ 0.5 against one
  training text after removing the set's own layout) runs with them as an evaluation set (`certified_carryover`).
- `overlap_step.py exclude <overlap.json>`: every scenario with a flagged question is excluded from the run and from every
  analysis (the references included). Reported: flagged questions per suite and the audit's attribution.
- If the audit's notes show that a suite shares its generator with a Skopos training kind, that suite is reported as
  in-distribution for Skopos (as fac_val is); this is reported, not a reason to drop it.

## Step 2 — the calls (`run_carryover.py`, as T2's run_t2.py)

Per scenario: one direct request with all its questions. The unit = one question the model answers with raw confidence ≥
0.9, chosen with `random.Random("63|<suite>|<req>")` over the scenario's confident rids in order. For the unit, the
certified mode's own extra requests built by the client: `verify.perturbed` (reversed options and the prefixed question,
one request) and, except for git_wild and shell_wild, the self-check (`verify.SELF_CHECK`). Scenarios run in parallel
(8 workers; the analysis orders the family-rate stream by hash, so dispatch order enters no number); a failed request is
retried 3 times with health checks; scenarios still failing are reported and left out. If more than 2% of scenarios
fail, the run is repeated for them and the event is a deviation.

## Step 3 — the analysis (`analyze_carryover.py`)

Scored exactly as confirm-3 (`confirm/policy.py` `Policy.score`, the frozen transforms): family rate warm-started from
WS-P's dev history (`dev_family_counts.json`, as counts; the dev dataset's sha256 `426a2ed9…`), then updated online over
the run's rows in confirm-3's hashed stream order; stability = 1 − min(P_reordered, P_prefixed) of the model's answer;
self-check P(no) (not used for git and shell). **Thresholds unchanged:** `params_confirm3.json`, as the client ships them.
L1 and L2 at α = 2% (primary) and 1%.

Per rule: accepted share, error among accepted (raw, and weighted to confirm-3's suite mix: rules 8,611, sql 892,
shell 816, git 1,009, accumulation 1,339 units), the one-sided 95% Clopper-Pearson upper bound, errors caught, verified
share (raw and weighted), per suite, per node with confirm-3's one-sided binomial test and Bonferroni.
Paired references, on the same (non-excluded) scenarios: Ekbasis-27B bf16 (confirm-3's answers and extra calls, its
full-stream family rate); the MLX build (T2's run) on the scenarios both completed. Paired answers against Ekbasis-27B:
agreement, accuracy, confident errors, per suite. Secondary: the per-domain rule (the client's default) on the units.

## Criteria

| Id | Claim | Pass |
|---|---|---|
| **C2-Skopos** (primary; the client's certified mode), INT4 | L2, α = 2%, Ekbasis-27B's thresholds, on Skopos INT4's answers | weighted error among accepted ≤ 2% **and** no node significantly above 2% (one-sided binomial, Bonferroni) — T2's criterion |
| C2+ | the same, stronger | C2 **and** the 95% upper bound of the raw error among accepted ≤ 2% |
| C1-Skopos | L1, α = 2% | as C2 |
| C2-Skopos-bf16 (secondary) | L2 on the bf16 build's answers | as C2 |

Reported, not claimed: α = 1%; raw rates; bounds per suite (with a few dozen accepted units per suite outside rules, a
suite's bound stays wide: the total and the paired comparisons carry the result); per node; caught and verified shares;
the references; the per-domain rule.

**Prediction (written before any request).** C2 holds (Ekbasis-27B 0.39% on confirm-3, 0.60% weighted on these
scenarios; MLX 0.21%). The risk is rules_stress, the weighted mix's largest suite: in the confident-errors addendum
(`PREREG_ADDENDUM.md` A2) Skopos gave more confidently wrong answers than Ekbasis-27B in never-trained world families
(+0.75 per 100, CI above 0); those are not confirm-3's families, but they are written-rule worlds. In sql, shell and git,
where Skopos trained further, the verified share may drop (fewer unstable answers).

## What follows from each outcome

- **C2 and C2+ pass:** the docs (docs/VERIFY.md, the card's limit, the client README) say, as for MLX: on confirm-3's
  fresh scenarios with Skopos INT4, X errors among N accepted answers (weighted Y%; 95% upper bound Z%), V% verified: the
  certificate carries over; a check, not a new certificate.
- **C2 passes, C2+ does not:** the same, plus "the 95% upper bound exceeds 2%: this sample does not rule out an error rate
  above the target"; certified mode stays usable, with that caveat.
- **C2 fails:** certified mode is uncertified with Skopos. The docs say so; the hosted API's notice says so; the client
  gate below becomes necessary before the hosted switch; a new calibration on Skopos (WS-U's dev pipeline, then a fresh
  test) is a separate study.

## Deviations from T2, fixed now

All 1,400 scenarios with no time cap; parallel dispatch; the overlap step; client 0.1.41 instead of 0.1.6 (verify code
and policy identical); vLLM on a GPU instead of MLX on a Mac; the C2+ reading added.

## Until it passes: what the card and docs must say

- **Model card (Limits)** — in the draft already, driven by `results/certified_carryover_skopos_int4.json`: "its
  thresholds were certified on Ekbasis-27B and checked on its MLX build; they have not been checked with this model yet.
  Until they are, treat `rule="certified"` as uncertified with Skopos (the other rules' measured rates are Ekbasis-27B's
  too)."
- **docs/VERIFY.md** ("Model version" and "The certificate's scope"): add "Ekbasis-Skopos-27B (October 2026): not checked
  yet; the rates on this page are Ekbasis-27B's."
- **Client README note and the hosted API's notice** for the switch: the same sentence; the announcement draft has it.
- **The scorecard and the console**: nothing to change (they do not use certified mode).

## Should the client gate certified mode by the server's model? (proposal, not implemented)

Yes, fail-safe and opt-out:
- `verify_policy.json` gains `"certified_models": ["Ekbasis-27B", "Ekbasis-27B-MLX-4bit", ...]` (the builds where the
  certificate was calibrated or checked; Skopos added only after C2 passes) and the matching hosted ids
  (`ekbasis-27b-int4-v1.3`).
- With `rule="certified"`, `verify.check` reads the model name of the answer it judges — the response's `model` field
  (the served folder's name; the hosted gateway keeps the basename) or the `X-Ekbasis-Model` header. The TypeScript SDK
  already keeps it (`lastUsage.model`); the Python client keeps only the token counts (`last_usage`) and would need a
  `last_model` attribute.
- If the name is not in the list, the answer is treated as an uncertified node: verify it (`verify=True`, reason
  "certified mode is not certified for model <name>"), with one warning per process. `EKBASIS_CERTIFIED_ANY_MODEL=1`
  turns the gate off for users who accept the risk.
- Why fail-safe: an uncertified node already means "always verify" in the client, so this adds no new behavior, only a
  new reason; the cost is extra verification requests until the list is updated.
- Weakness: a folder name is not an identity (a user can rename a folder). A sturdier identity is a `model_id` in each
  build's `decision_config.json`, returned by `/health` and in every response; that is a server change (serve.py) for a
  later release, and the gate should then prefer it.
