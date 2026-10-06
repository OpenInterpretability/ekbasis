# WS-U confirm-2: deviations from the frozen files (FROZEN_confirm2.sha256)

**None.** Every frozen file matched on the rig after the run (`sha256sum -c`).

Orchestration (not a frozen file): `confirm2/watch_confirm2.sh` started `run_confirm2.sh` after the shared :8544 server
restarted.
- **A first watcher would have started on the old server.** It was armed at 15:06 UTC and would have run on the server
  that was about to go down. It was stopped by PID at 15:07, before any step ran.
- **The second watcher** waited for the API's new pid (3341211, replacing 2585394) and 3 healthy polls, then started
  the chain at 15:53. The chain finished at 17:55.
- **Steps and errors:** every step ran once, with 0 runner errors and 0 extra-call errors (18,615 rows).
