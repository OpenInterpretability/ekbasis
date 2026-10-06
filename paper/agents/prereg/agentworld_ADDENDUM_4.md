# Addendum 4 (2026-10-06 ~16:15 UTC, before any mode (b) forward pass)

Logistics only, at the coordinator's request: mode (b) runs on GPU 0 between ~17:40 and ~19:40 UTC, launched by the
coordinator's `<SERVER_WORKDIR>/mission/aw_b_on_gpu0.sh` (it calls `run_b.sh 0`).
- `aw_server.sh` accepts a GPU whose only compute process is systemone_v4.py (PID 1101009, 1.3 GB, must keep running);
  any other process still makes it refuse. `run_b.sh` checks the same thing after stopping AgentWorld.
- `run_b.sh` stops `simulate_b.py` at a hard deadline (19:30 UTC by default; `timeout`, TERM then KILL after 30 s), so the
  GPU goes back by ~19:40. The done flag says DONE, PARTIAL (deadline) or FAILED, with the number of rows written.
- `simulate_b.py` answers and appends each simulation as soon as it finishes (it used to write each suite at the end), so
  a stop loses only the simulations in flight and the next run resumes the rest. A failed request leaves its items undone.
  Same items, prompts, sampling parameters and per-request seeds.
No change to items, metrics, the mode (b) sample or the decision rule. If the deadline cuts mode (b), the suites without
(b) results count as "not won by AgentWorld" in S1, and the report says so.
