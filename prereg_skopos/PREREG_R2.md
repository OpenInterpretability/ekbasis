# V50R2 — R1 + regenerated real-domain factory data (pre-registration, written 2026-10-15 ~03:10 UTC, BEFORE R1's result)

## Why
The full V50 needs F's executed real-domain data (shell, SQL, Python, git), lost with the rig. Tested 15/10: all four
factories run on the RTX (git via the current ekbasis client 0.1.40 renderer). Regenerated with fresh seeds 100000+
(`gen_factory.sh`: sql 2,600 / python 5,800 / shell 2,300 / git 2,200 seeds), packed by F's `pack.py`, firewalled
against every test and validation floor → `data/fac_rx.jsonl` (kind floorRX).

## Arm R2 (frozen; identical to R1 except the mix)
Base Ekbasis-27B; trainer and recipe as R1 (LoRA r64, JEPA 3 ev 16/32/48/64, LR 1.5e-5, BS 8/micro 4, seed 2, turns,
1,200 steps); train file = ftrain_r1 + fac_rx. **Mix: V42 shares × 0.55 + floorPL 0.15 + floorPLG 0.15 + floorRX 0.15.**

## Measures (same as R1, plus breadth)
All R1 suites with SAVE_PROBS and the same temperature refit; **plus `fac_val`**: factory items from seeds 200000+
(200 seeds per family; firewalled), scored by family (shell/sql/python/git) for base, R1 and R2.

## Rule (paired bootstrap, 2,000, seed 20261014)
- **R2 is preferred over R1** if, on fac_val pooled, R2 − R1 ≥ +0.02 with CI above 0, and on git_long R2 is not below
  R1 (CI not entirely below 0), and no M3 suite drops vs base by > 1 point with CI entirely below 0.
- Reported regardless: R2 vs base on everything; confident errors and ECE after refit.
- Runs when the GPU is free (after R1's analysis and the frontier test), whatever R1's verdict.

## Addendum A (2026-10-15 02:58 UTC, before R1's result and before any R2 data exists)
fac_val rows come straight from `run_family.py`, whose choice options are not shuffled (pack.py shuffles them only for
training). To avoid a gold-position artefact, fac_val applies pack.py's deterministic md5-seeded option shuffle.
Nothing else changes.
