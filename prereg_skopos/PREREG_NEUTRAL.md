# Neutral ground: AgentWorldBench "will the next action fail?" (pre-registration, 2026-10-15 02:58 UTC, no model scored)

## Why
Every Ekbasis suite so far is built from our own worlds and renderers. Qwen/AgentWorldBench (Apache-2.0) holds real
agent turns (Terminal-Bench, SWE tool calls) with the real environment observation. It is the product question on
ground neither model was built around: before an agent's action runs, does it fail?
Eval only: these trajectories come from frontier commercial agents, so per the data rule they never enter training
(and they are firewalled from every training file by construction: nothing in `data/` is derived from them).

## Suite (`neutral/awb_neutral.jsonl`, built by `scripts/build_awb_neutral.py`, 455 items, 136 trajectories)
- `awb_swe_fail` (140; 14 fail): SWE shell tool calls; gold = exit status ≠ 0 (`Exit Code: N` / `Exit code N`). Exact.
- `awb_term_fail` (315; 40 fail): Terminal-Bench keystroke actions (one or more command lines); gold = an error
  signature in the output after the first command's echo (command not found, No such file or directory, Permission
  denied, Python traceback, a line starting `error:`/`fatal:`/`E:`, or `XxxError: <text>`). Heuristic; spot-check of
  14 positives found 13 genuine (one metric line 'Error: 0.000835', fixed by requiring a non-digit after the colon).
- Context: earlier actions and observations, newest first kept, each observation cut to 1,500 chars, total ≤ 14,000.
- A third question type (does an `ls` listing contain X) was dropped at design time: only 10 pairs and weak negatives.

## Models (same items)
Ekbasis base, R1, R2 (probabilities saved; read out as the trainer does) and Qwen-AgentWorld-35B-A3B (vLLM, may
reason, 4,096 tokens, 'Answer: X' parsed; same prompt builder as the frontier test).

## Measures (bootstrap clustered by trajectory, 2,000, seed 20261015)
- Primary: **balanced accuracy** (mean of recall on fail and on no-fail; 'always no' = 0.50), per world and pooled.
- Ekbasis also: AUROC of P(fail); recall at 10% false alarms.
- AgentWorld: balanced accuracy, unparsed answers counted wrong, median tokens and seconds per item.
- Read: a model "has the neutral skill" if pooled balanced accuracy CI is above 0.60. Ekbasis vs AgentWorld:
  difference of balanced accuracy with its CI. Descriptive; no release decision rides on it (n of failures is 54).

## Prediction (written before scoring)
Ekbasis base: AUROC 0.65–0.80 (never saw this format; failures here are mostly missing tools/modules, which the
context often hints at). AgentWorld: trained on real terminal/SWE trajectories, likely better at this format; possible
contamination (its training corpus may include the source benchmarks' tasks), noted when reading.

## Operational note (2026-10-15 04:28 UTC, nothing scored)
AgentWorld's vLLM launch gets the same flags the frontier test needed (`--language-model-only --max-num-seqs 64`;
text-only checkpoint; Mamba cache blocks) and a 40-min wait. Nothing else changes.
AgentWorld on the neutral suite uses Addendum B's setting of the frontier test (thinking off, 8,192 tokens, 64 concurrent).

## Operational note (2026-10-15 08:30 UTC, before any Ekbasis neutral score exists)
The Ekbasis evaluations crashed with CUDA OOM (eval batch 48 × ~4k-token contexts) and would also have failed on the
missing 'ceiling' field in base mode. Rerun (`scripts/run_neutral_ek.sh`) after the git diagnosis: EVAL_BS=6, data
copy with ceiling = floor (only the floor predictions are read). AgentWorld's neutral answers were complete.
Analysis fix (08:35 UTC, before any Ekbasis neutral score): `analyze_neutral.py` treated AgentWorld's unparsed answers
as "no" (correct on every no-fail item); per this pre-registration they now count as wrong.
