# WS-U confirmatory test: deviations from the frozen files (FROZEN_confirm.sha256)

## 1. extra_calls.py: the tokenizer is loaded before the worker threads (06/10, 12:53 UTC)

- **What happened.** The step `extra_primary` crashed after 6 rows with `ImportError: cannot import name 'AutoTokenizer'
  from 'transformers'`. The first `build_dataset.tok()` call (lazy `from transformers import AutoTokenizer`) ran in 16
  threads at once, and that import is not thread-safe.
- **Fix.** One line in `main()`, before the thread pool: `IB.B.tok()`, which loads the tokenizer once in the main thread.
- **Impact.** No prompt, signal, threshold, criterion or analysis line changed. The 6 rows already written are kept, and
  the run resumes from them.
- **When.** After the direct answers and before any extra call result or analysis was read. Nothing about the policy's
  performance on the fresh set had been seen.
- **Hashes.** extra_calls.py was de215465aaf836e6… (frozen); its new hash is recorded in FROZEN_confirm_dev1.sha256.

## 2. Secondary suite (planning) not run: infrastructure cut (06/10, ~14:30 UTC)

- **What happened.** The `:8544` replica was stopped for training (the coordinator's decision) during step
  `extra_planning`. At that point the planning direct answers were complete: 1,619 pairs, 8,349 kept confident rows,
  225 of them errors. The extra calls covered only 5,613 of those rows, in row-id order (mostly Hanoi, jugs and part of
  Lights Out), with 5 connection errors.
- **What was done.** The chain and its two child processes were stopped by exact PID at 14:32 UTC. `analyze_all` was
  not run.
- **Result.** The planning secondary is reported as **not run (infra cut)**. A partial, ordered subset is not
  representative, so it is not analysed.
- **Primary result untouched.** The primary analysis (C1–C3) had finished at 14:03 UTC, with every primary confident
  row's extra calls done (none missing), before the replica stopped. `results/confirm/confirm.json` sha256 is
  5d483ce9c31b9d2e….
