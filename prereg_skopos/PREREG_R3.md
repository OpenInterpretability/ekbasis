# V50R3 — R2 + the same executed shell scenarios rendered as agent sessions (pre-registration, 2026-10-15 09:20 UTC)

## Why (measured tonight)
R2 is the best candidate on everything we generate (fac_val +4.1, git_long +2.0 over base) but the neutral suite
(real agent sessions, AgentWorldBench) did not move: AUROC base 0.833 / R1 0.832 / R2 0.835. Hypothesis: our training
items always state the world as a structured "State before" block; agents see raw sessions (commands and their
printed output). R3 teaches reading the state from a session.

## Data (`scripts/gen_session.py`)
Every 1-command shell-factory training row (8,954, from fac_rx; exact labels unchanged) rendered as a session:
`ls -laR` (exact sizes, types, link targets), and — only when the original item showed contents — `grep -r '' .` and
the archives' contents (`tar -xzOf`), then the next command; question reworded to "the next command". Two
presentation styles (a $-transcript and a turn/observation list), half each. kind floorSX. `sess_val`: the same
rendering of the 1-command shell rows of fac_val (seeds 200000+, firewalled).
Nothing from AgentWorldBench is used; the neutral suite stays a one-shot test.

## Arm R3 (frozen; R2's recipe except the mix)
Train file = ftrain_r2 + fac_sess. Mix: **V42 shares × 0.45 + floorPL 0.15 + floorPLG 0.15 + floorRX 0.15 + floorSX 0.10.**
LoRA r64, JEPA 3 (16/32/48/64 ev), LR 1.5e-5, BS 8 (micro 4), seed 2, turns, 1,200 steps.

## Measures and rule (paired bootstrap; neutral clustered by trajectory, 2,000, seed 20261015)
- **Primary (transfer): neutral pooled AUROC R3 − R2 ≥ +0.03 with CI lower bound > 0.**
- Mechanism check: sess_val accuracy R3 − R2 ≥ +0.03 with CI > 0.
- Guards: fac_val and git_long R3 − R2 not < −0.01 with CI entirely below 0; M3 suites vs base as in R1/R2.
- Reported: neutral balanced accuracy, SWE-exact and terminal subsets, refit calibration.
## Prediction
sess_val up clearly (the format is new to R2); neutral AUROC unchanged to +0.02 — the neutral failures are mostly
missing tools/modules/paths, which shell file operations only partly cover. A null here says the gap is failure-type
coverage, not presentation.
