# Pre-launch battery (Part A): how it was run, deviations

- 16/10 01:31–01:52 UTC: the first local driver's SSH helper returned grep's exit status, so its waits never ended;
  fixed (`return ${PIPESTATUS[0]}`) and relaunched; 21 min lost, nothing measured in that window.
- 16/10 03:40 UTC: `run_all.sh` prints the Mac-side P10 steps but does not wait for them, so the served model could
  change under a running P10 (phase A → B; and phase D → E, where the Mac step is the phase's last line). Found before
  any phase change. Fix without editing the running script: the runner's main bash (pid 2577535) was paused with
  SIGSTOP at 03:40:36 UTC while P10 skopos_bf16 runs (its children, the phase A items, kept running), and is resumed
  with SIGCONT when that P10 ends; in phase D it is paused as soon as the INT4 build is served (during the intent
  replay) for P10 skopos_int4, then resumed. Times are in the driver's log.
- P10 for Ekbasis-27B bf16 (the runner's optional same-tunnel timing control) is not run: the comparison P10
  pre-registers is against Ekbasis-27B's published run of the same 72 scenarios.
- P10 skopos_bf16 ran while the phase A items shared the GPU (as printed by the runner); P10 records outcomes
  (guard and git.check answers), so the load affects its time, not its answers.
- A7 (PREREG_ADDENDUM): a bf16 run started during phase A was too slow while sharing the GPU (124 items in 12 min),
  was stopped, and its partial file kept as `ce_a7_skopos_bf16.partial_during_phaseA.jsonl`; A7 runs after the battery,
  each build served alone.
- 16/10 11:32–~11:50 UTC, asked by Caio after the P8 blocker: the P8 identity re-run of Ekbasis-27B bf16 was run during
  phase A instead of in phase B. The P4 clients (pids 2582504, 2582506) were paused with SIGSTOP, the server queue
  drained to 0, Skopos bf16 was replaced by Ekbasis-27B bf16 (same serve_vllm.sh + serve.py, same flags), P8 ran exactly
  as phase B runs it (output kept as P8/ekbasis_bf16_early; phase B runs it again), then Skopos bf16 was served again
  (logs/vllm_skopos_bf16_resumed.log) and the clients resumed. The P4 chains keep their client-side state; the server is
  the same model with the same flags.
- Found while doing it: the battery's serve_down stopped nothing. serve_up stores the launching subshell's pid in
  logs/vllm.pid and logs/front.pid, so serve_down's command-line check never matches; the GPU never frees and the runner
  would have exited at its first phase change (A → B). The first swap attempt (11:32–11:36) failed this way with no
  effect on the running server. Fixed without editing the running runner: /root/v50p/pidfix.sh rewrites a pid file whose
  pid is not the process it names with the real pid every 5 s (logs/pidfix.log); servers in the swap were stopped by
  their real pids.
- 16/10 11:56 UTC: run order changed after Caio's release decision (RELEASE_DECISION.md), so the items that can still
  block finish first. The first runner (run_prelaunch.sh / run_all.sh, pids 2577534/2577535) was stopped while phase A's
  P4 clients kept running (parent first, so no false PHASES_DONE line); runner v2 (/root/run_prelaunch2.sh) waits for P4,
  then runs phase C with EK_P9=0 (Skopos' P9; Ekbasis-27B's P9 moved to the end), then phase D's steps exactly as
  run_all.sh runs them with the INT4 server kept up until the Mac step P10 skopos_int4 writes a marker file (the first
  runner only printed the Mac step), then phases B, E, F (with the compares), then Ekbasis-27B's P9.
  common/serve.sh was fixed for runner v2 (real pids in the pid files; an engine process left after its API server
  stopped is stopped by its pid); the version that ran until then is kept as common/serve.sh.as_run_until_20261016.
  No measurement changes: the same scripts, models, flags and items.
