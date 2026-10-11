# When Does a Consequence Model Make AI Agents Safer?

Pre-registered studies on demo apps, real self-hosted apps and a real terminal.

DOI: [10.5281/zenodo.23197341](https://doi.org/10.5281/zenodo.23197341)

Paper, data and scripts. The paper is `agents.pdf` (source `agents.tex`); every number it cites is in `numbers.json`,
recomputed from the tables in `data/` by `reproduce.py`.

```
python3 reproduce.py        # data/ -> numbers.json   (Python 3.9+, numpy; about 20 s)
python3 check_numbers.py    # fails if agents.tex cites a number that numbers.json does not contain
python3 figures.py          # numbers.json -> figures/  (matplotlib)
python3 verify_refs.py      # resolves every reference against arXiv, Crossref, DataCite or its URL -> refs_check.json
python3 prereg/verify_prereg.py   # checks the published pre-registration documents against every frozen SHA-256
python3 benchmark/verify_benchmark.py   # checks the benchmark against the files that ran
```

`prereg/` holds each study's plan, addenda and freeze files, as written before the runs they govern. Only machine paths
were replaced by placeholders (each substitution is listed in `prereg/README.md`); `verify_prereg.py` undoes them and
checks every hash recorded at a freeze, including earlier versions that are byte prefixes of the published documents.

`benchmark/` holds what is needed to rerun the studies, not only recompute them: the tasks and their generators, the
demo apps, the real apps' Docker Compose file (official images pinned by digest) with seeding and fresh test
credentials, the adapters, the judges, the stages, the agent's tools, the forecast bridges, the runners and the task
verifiers. Its README runs one task end to end with any agent and any Ekbasis server; `verify_benchmark.py` checks each
file against the file that ran (machine paths, a server's address and a user name were replaced by environment
variables; `MANIFEST.json` lists every edit).

## What is in `data/`

In `data/`, no transcript, no evaluation prompt or state text, no command line, no path and no credential is released.
Every row is an outcome, a count, a cost, a time or a category.

| File | One row per | Fields |
|---|---|---|
| `x_runs.jsonl` | agent run on the demo apps (Claude Sonnet 5.5; Claude Haiku 4.5 with default thinking and with thinking off) | study (original, fresh), agent, cond, task, app, kind (harm, control), rep, harm, success, blocked, cost_usd, oracle_cost_usd, turns, seconds, foresee_calls, foresee_ms, panel_on_harmful; token counts from the run's usage record (fresh set, first repetition) |
| `open_runs.jsonl` | agent run of GLM-5.3-Flash and Qwen 3.5 4B and 9B on the fresh demo set | as above, plus agent_exit_error, panels, panels_conf_below_0.5 |
| `skill_loads.jsonl` | GLM and Qwen run (fresh demo set, and the Qwen 9B arm on the real apps), added in v2 | set, agent, task, cond, rep, run (real apps), skill_loaded: whether opencode loaded an unrelated `computer-use` skill in that run, read from its session log (null where the log is missing); see the erratum in the paper |
| `glm_foresee_calls.jsonl` | Ekbasis call during the GLM runs | ms, answers, min_confidence |
| `ra_runs.jsonl` | agent run on the real self-hosted apps | run, task, app, family, kind, agent, cond, rep, excluded (reason or null), harm, success, blocked, cost_usd, oracle_cost_usd, seconds, turns, foresee_calls, panel_shown, panel_flagged_harm, flags, flags_on_asked_effects, adapter_defect, conflict_task |
| `ra_verified_paths.jsonl` | Ekbasis answer before a click of a scripted harmful or safe path (one row per answer; a path without questions has one row marked no_questions) | task, task_kind, path, click (the click's number within the task; no label text), last_click, key (the adapter's question key), action_type, right, flag, truth_corrected, confidence, path_last_flagged |
| `ra_conflict_rule.json` | | the rule and the list of conflict tasks (exploratory analysis) |
| `ra2_runs.jsonl` | agent run of the follow-up on fresh real-app tasks (turning warnings into safe actions) | run, task, app, family, kind, new_family, conflict, agent, model, cond, rep, excluded (reason or null), harm, success, blocked, cost_usd, seconds, turns, tool_calls, n_actions, n_checks, n_pauses, n_user_q, n_user_needless, n_suggest, foresee_errors; checks: one entry per guard check (action_type, silent, kind, flagged_intent, flagged_other, safer_way category, user_asked, user_concern, ms), with no question, answer, label or suggestion text |
| `ra2_tasks.json` | | the frozen task list of the follow-up with its harm, control, conflict and new-family sets, the conflict rule, its Claude spend (in all and when the spending cap stopped it), and the one verdict the normalised mail judge of addendum C changes |
| `terminal_sessions.jsonl` | Claude Code session (clients 0.1.2 and 0.1.3) | study, model, sid, task, round, arm (H hook, C control), done, preserved_total, preserved_share, usd |
| `terminal_calls.jsonl` | Bash call in those sessions | study, model, sid, task, arm, cls (truth class a to d), executed, live and replayed decisions and their wall times |
| `terminal_e1.jsonl` | classic destructive shortcut or safe alternative run on the tasks' real states | task, kind, decision_012, cls |
| `aw_items_a.jsonl.gz` | question in the AgentWorld comparison, both models in one pass | suite, item (sha256 of the prompt), cluster (hashed), ek_correct, aw_correct, ek_conf, aw_conf, ek_brier, aw_brier, aw_ms_per_item |
| `aw_items_b.jsonl` | question in the 100-item samples where AgentWorld reasons first | suite, item, cluster, ek_correct, aw_a_correct, aw_b_correct, think_done, tagged, gen_tokens, sim_ms |
| `panel_truth.json` | aggregated | panel answers on the demo apps scored against the apps' own truth, and panel latency |
| `visible.json` | aggregated | look-ahead, state tracker and τ-bench retail results (τ-bench: pass@1, harmful-write runs, violations, unrequested writes, cost and seconds per run, and the paired contrasts) |
| `overlap.json` | aggregated | rows scanned and rows flagged per question suite of the AgentWorld comparison |
| `spend.json` | aggregated | Claude API spend per study |
| `first_reported_claims.json` | | the numbers first reported for the GLM and Qwen runs, checked in `numbers.json` (`claims_check`) |

Three quantities are released aggregated, as the studies' own analyses computed them: panel accuracy against the demo
apps' truth (computed from the session logs, which are not released), the visible-consequence studies, and the overlap
scans. Everything else
is recomputed from per-run or per-item rows.

## Estimators

- Demo apps: task bootstrap, 10,000 resamples, seed 11; cross-agent contrasts and cost ratios pair per-task values
  (seed 13); the app-level resampling uses seed 17.
- Real apps and the follow-up: per-task means resampled over tasks, 10,000 resamples, seed 20261006; the family-level
  check resamples the 9 task families with the same seed.
- Terminal: Wilson score intervals; sessions resampled as a check (10,000 resamples, seed 11); Fisher's exact test for
  the planted-work comparisons and the exact McNemar test for 0.1.3 against 0.1.2 on the same commands.
- AgentWorld calibration: expected calibration error over 15 equal-width bins of the top probability, confident errors
  (wrong at a top probability of at least 0.9) and the AUROC of the top probability for correctness.
- AgentWorld comparison: item clusters resampled with numpy `default_rng(0)`, 10,000 resamples.

## Licenses

The paper is CC-BY-4.0. The scripts and `benchmark/` follow the repository's license (Apache-2.0). The data are
CC-BY-4.0.
