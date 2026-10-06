# Addendum 2 (2026-10-06 ~15:38 UTC, mode (a) had written 16 rows)

Bug fix only: the first `score_a.py` run stopped after 16 rows because AgentWorld's tokenizer was loaded lazily from 8
threads at once and the concurrent `transformers` import failed (`ImportError: cannot import name 'AutoTokenizer'`), the
same failure WS-U recorded in its confirmation. `aw_common.tok()` now loads under a lock and both runners load it before
starting threads. The 16 rows already written are kept (the runner resumes by id); no change to items, prompts, readout,
metrics, samples or the decision rule.
