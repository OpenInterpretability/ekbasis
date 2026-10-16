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
