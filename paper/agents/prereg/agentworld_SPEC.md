# WS-AW: Qwen-AgentWorld-35B-A3B vs Ekbasis — pre-registration

Written and frozen (FROZEN.sha256) on 2026-10-06 before any AgentWorld forward pass and before any new Ekbasis call.
Changes after the freeze go to addenda with their own hashes.

## Question

Qwen released Qwen-AgentWorld-35B-A3B (2026-06-22, Apache-2.0, arXiv 2606.24597; `Qwen/Qwen-AgentWorld-35B-A3B`,
revision `60d2b0434a53d2e62a7c00a489586815d94ebffb`; qwen3_5_moe, 35B total / 3B active, base Qwen3.5-35B-A3B-Base;
CPT → SFT → RL on >10M real agent trajectories in 7 domains). Does it predict consequences better than Ekbasis-27B (the
released w4a5) on our graded batteries? If yes, it is a candidate base for V48 (Caio decides); if not, our niche holds.

## Models and serving

- **Ekbasis**: the released w4a5 through serve.py 1.3 (vLLM, letter readout, the release calibration). Its answers on
  sets A–C are the stored ones (no new calls); set R and the fidelity sample are asked on rig :8544 (GPU 2 eval server)
  before GPU 2 is handed to AgentWorld.
- **AgentWorld**: downloaded to `<SERVER_SHM>/agentworld` (35/35 files, sizes = the HF API). Served on GPU 2 only after
  the coordinator hands it over, with `aw_server.sh`: our vLLM 0.30.0 (`<SERVER_VENV>`, which registers
  `Qwen3_5MoeForConditionalGeneration`), `--language-model-only` (model card), max length 65,536,
  `--logprobs-mode processed_logprobs --max-logprobs 600` (the same letter readout as Ekbasis' server), prefix caching.
  No calibration is applied to AgentWorld (it has none); Ekbasis is read as released.

## Items (built by `build_items.py`, checked by `check_items.py`; counts and sha256 in `items/MANIFEST.json`)

Every item = the chat messages Ekbasis read (system + user, rendered by the server's own `decision_core`, sha
e07bd7b2…), the option labels in order, the truth (from code or execution), and Ekbasis' answer.

| Set | Suite | Items | Clusters | Source |
|---|---|---|---|---|
| A | accumulation | 1,736 | 1,736 | U's fresh confirm rows (exact served prompts; U's exclusions kept) |
| A | git_wild | 3,250 | 1,014 | " |
| A | planning_probe | 8,898 | 1,554 | " |
| A | rules_stress | 9,075 | 9,075 | " |
| A | shell_wild | 3,708 | 816 | " |
| A | sql_wild | 2,056 | 900 | " |
| B | apps | 1,776 | 1,208 | capability map, scored items, rebuilt with the runner's own builders |
| B | git_wild_capmap | 1,625 | 507 | capability map git_wild: the guard's stored prompt; lost / fails_k / in_progress (disputed truths and branch dropped) |
| B | habit_vs_rule | 2,880 | 1,440 | main items with a right answer ("blind" items have none) |
| B | languages_formats | 3,503 | 2,375 | kept items |
| C | guard_held | 6,394 | 6,394 | release eval data (`ekbasis-data/raw`), "floor" state; Ekbasis = F's w4a5 readout (aligned row by row, gold and top label asserted) |
| C | guard_known | 4,486 | 4,486 | " |
| R | terminal | 148 | 65 | AgentWorldBench (Apache-2.0) terminal test: which option is the environment's response to the current action |
| R | mcp | 150 | 27 | AgentWorldBench mcp test, same construction |

Checks already run (CPU): set A prompts re-render byte-identically from their messages (0 failures) and the set-A
requests rebuild exactly (0 failures); option labels are single tokens with the same ids in both tokenizers;
**AgentWorld's chat template renders the same messages byte-identically to Ekbasis' (700/700 sampled)**; the letter-readout
code reproduces Ekbasis' stored answers through Ekbasis' own vLLM (48/48 top labels, median |Δp| ≈ 0); the longest R
prompt is 14,872 tokens (fits Ekbasis' 16,384). Ekbasis' stored accuracies per set are in `items/ek_stored_accuracy.json`.

**R construction (fixed):** truth = the recorded observation of the current turn; distractors = the next 3 distinct
observations of the same trajectory (taken from the trajectory's longest record), none of which is visible in the item's
history; records without 3 such observations, or whose truth already appears in the history, or whose options become
identical after cutting, are skipped (counts in MANIFEST). History = the most recent turns that fit 9,000 tokens;
every option cut to 2,000 characters; option order fixed by sha256(id|index).

**Excluded, with reason:** X's agent panels (truth per panel is not stored in a reusable form); git branch questions
(only the top label was stored); habit_vs_rule "blind" items (no right answer); other AgentWorldBench domains (time).

## Scoring

**Mode (a), all items:** AgentWorld reads the byte-identical prompt with thinking off; one /v1/completions call,
max_tokens 1, temperature 0, allowed tokens = the option labels, probabilities normalized over them (`aw_common.letters`,
the same mechanics as Ekbasis' `letter_adapter`). Metrics per suite and model: accuracy (top label = truth), Brier
(multiclass), ECE (15 equal-width bins of the top probability), confident errors (top probability ≥ 0.9 and wrong; count
and rate among confident answers), AUROC of the top probability for correctness; AgentWorld's latency per item.

**Mode (b), seeded sample:** 100 items per suite (the 100 smallest sha256("aw-2026-10-06"|id)); one simulation per
distinct evidence. Step 1 (native): AgentWorld with thinking on and the model card's sampling (temperature 0.6, top_p
0.95, top_k 20, max 8,192 tokens, seed from the evidence hash) predicts the outcome. System prompt for sets A–C (fixed
text in `aw_common.NATIVE_SYSTEM`): a language world model that predicts the resulting state inside
`<predicted_observation>` tags; user = the item's evidence without the question. For R: the benchmark's own system
prompt and multi-turn messages (most recent turns within 48,000 tokens). Extraction by code: the last
`<predicted_observation>` block after `</think>`, else the text after `</think>`, else "(no prediction)". Step 2:
AgentWorld itself answers the typed question with the letter readout, the evidence followed by "Predicted outcome of the
actions (simulated by a world model):" and the prediction (first 4,000 characters). Never Claude. Accuracy only (plus how
often the thinking finished and the tags were present, generated tokens, time).

**Statistics:** paired differences over the same items, 95% percentile intervals from 10,000 bootstrap resamples of
clusters (seed 0). Clusters: the request / state (several questions about one state move together), the trajectory for R.

## Decision rule (stated now)

- A suite is **won by AgentWorld** if its accuracy minus Ekbasis' has a 95% CI above 0; **won by Ekbasis** if the CI is
  below 0; otherwise a tie. Primary = mode (a) over all items of the 12 own suites (A, B, C).
- Sets B and C count only if their rebuilt requests pass the fidelity check: a seeded sample (25 items per B/C suite, 10
  per A suite as a control) asked again on :8544 must match the stored answer with median |Δp| ≤ 0.01 and the same top
  label on ≥ 98%. A suite that fails is reported but not counted; the majority below is then over the counted suites.
- **P1:** AgentWorld (a) wins a majority of the counted suites. **P2:** AgentWorld (a) wins or ties a majority AND has a
  lower Brier score (CI of the difference below 0) in a majority. **S1 (secondary):** AgentWorld (b) beats Ekbasis on the
  same sample items (CI above 0) in at least 7 of the 12 own suites.
- Recommendation: P1 or P2 → propose AgentWorld as V48's base (Caio decides), with a plan to put our recipe (typed
  calibrated answers, guard, look-when-unsure) on top. Only S1 → AgentWorld-with-reasoning is stronger: propose it as a
  teacher / data source, base only after a cost study (generation tokens and latency). Neither → keep Ekbasis' base.
- R (AgentWorld's home domains) is reported separately, not counted.

## Procedure after GPU 2 is handed over

1. `aw_server.sh` (GPU 2 must be empty; it never stops other processes). 2. `score_a.py` (all suites). 3. `simulate_b.py`
(all suites). 4. `analyze.py`. Before the handover, while :8544 is up: `ek_reverse.py reverse` and
`ek_reverse.py fidelity` (≤ 8 requests in flight, shared server).

## Rules

No Claude spend. Nothing published. Process hygiene: PID files, only our PIDs are stopped, never by pattern. Never touch
GPUs 0, 1, 3 or other processes. HF token already configured on the rig, never printed.
