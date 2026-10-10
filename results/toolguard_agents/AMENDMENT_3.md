# Amendment 3 / deviations log (before the main run)

Written 10 October 2026 ~18:58 UTC, before any main run.

1. **Parallelism 2** (also in AMENDMENT_2): asked by the team lead at ~18:45 UTC to protect the production GLM service
   that shares the B200 GPUs with Ekbasis.
2. **Gateway limiter.** Since ~18:32 UTC the hosted API passes every Ekbasis request through a global limiter: one
   request at a time plus a pause proportional to its tokens; internal accounts (this study's key is one) go through a
   lane of their own at ~600 input tokens/s, wait up to 120 s, then get HTTP 429. The guard's latency per check therefore
   includes queueing. **Instrumentation added (no change to any decision):** the client keeps the Server-Timing header
   of each answer (`queue;dur=`, `model;dur=`) and the HTTP status; the guard's log stores them per check
   (`server_timing`, `http_status`, `error`). **Model latency** (`model`) is the latency outcome; total seconds per
   check and the gateway queue are reported as context. Every failed check (429 or other) is counted, with what the
   guard did (under fail closed it blocks the click), and reported apart, since it affects harm and success.
3. **Start condition.** The main run starts at 19:50 UTC or later, and only once no external-benchmark process
   (`run.py --full`, same internal lane) is alive (`main_run.sh`). The pause at 03:30 UTC stands.
4. The first latency numbers of pilot 3 (p50 26.5 s, p90 110 s per check, before this instrumentation) came from
   gateway queueing while the external benchmark ran.

5. **Two windows** (team lead, ~19:00 UTC): the B200 changes profile at 04:00 UTC (Ekbasis restarts), so the main run
   stops taking new runs at 03:30 UTC and is resumed only on the team lead's signal after the switch, from the same
   fixed queue (`resume_run.sh`; runs already in `runs.jsonl` are skipped). The real start, pause and resume times are
   added below as they happen.

Real times (UTC):
- 20:52:58 — main run starts (window 1), parallelism 2, after the external benchmark ended.
- 22:21:40 — `STOP` to drain the first runner, for two reasons: (a) the team lead asked for parallelism 3 from now on
  (gateway lane raised to 1,200 tokens/s and 2 in parallel; Ekbasis idle; GLM healthy at 27–86 tokens/s per request);
  (b) a bookkeeping bug: the runner crashed after the agent had run when a control task's `paths.harm` is null, so 9
  finished runs (8 controls, 1 harm) were not recorded. Fixed in `run_study_tg.py`; those 9 rows were rebuilt from the
  saved sessions by `rescore_unrecorded.py` (`"rescored": true`), judged exactly as the runner judges; no agent was run
  again. Runs in flight finished normally.
- 22:32:35 — window 1 continues with parallelism 3 (`window1b.sh`), same fixed queue, 61 runs left of 140 (79 recorded).
  The pause at 03:30 UTC stands (the pause guard started by `main_run.sh`).
