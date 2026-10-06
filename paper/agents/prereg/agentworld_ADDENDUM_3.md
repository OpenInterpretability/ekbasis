# Addendum 3 (2026-10-06 ~16:00 UTC, after mode (a), before any mode (b) forward pass)

Logistics only, at the coordinator's request: mode (b) runs on a training GPU freed for about 2 hours (probably GPU 0),
not on GPU 2, which stays the Ekbasis eval server.
- `aw_server.sh` takes the GPU index as its argument, refuses GPU 2, and refuses any GPU that has a compute process.
  Same port (30196), same flags.
- `run_b.sh` (new): start AgentWorld on the given GPU, run `simulate_b.py`, stop AgentWorld by its PID, confirm the GPU is
  empty, run `analyze.py`, and write the done flag `<SERVER_SHM>/mission/aw_b_done`.
- `simulate_b.py`: WORKERS 32 → 64, to fill the server's 64 sequences inside the slot. Concurrency only: same items,
  prompts, sampling parameters and per-request seeds.
No change to items, metrics, the mode (b) sample or the decision rule.
