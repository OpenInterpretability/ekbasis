# Client 0.1.5: the certified mode of `ekbasis.verify` — WS-U confirm-3 (2026-10-06)

## Why

Confirm-2's Learn-then-Test acceptance rule failed (results/client_0.1.4): rare rules families that inherited their
suite's threshold reached 3.4% errors among accepted answers.

## Confirm-3

**What was tested.** Two fixes, pre-registered in [`SPEC_confirm3.md`](SPEC_confirm3.md) and calibrated on the first
test + confirm-2 only:
- **L1:** rare families are always verified;
- **L2:** a rare family uses a (domain, difficulty) node.

**Run.** New seeds; 18:08–19:38 UTC; no deviation ([`DEVIATIONS_confirm3.md`](DEVIATIONS_confirm3.md)). The frozen
hashes are in [`FROZEN_confirm3.sha256`](FROZEN_confirm3.sha256). Their paths are relative to the analysis folder: the
`confirm3/` files are here, the `confirm/` and `confirm2/` ones are in `../client_0.1.4`.

**Size.** 18,544 confident answers; 12,667 scenarios (one question each), 686 of them wrong.

| Rule (α = 2%, δ = 0.05) | Errors among accepted | Verified | Errors caught | Node above 2% | Criterion |
|---|---|---|---|---|---|
| **L2** = `rule="certified"` | 0.39% (36 / 9,259) | 26.9% | 94.8% | none | passed |
| L1 (rare families always verified) | 0.44% (31 / 7,013) | 44.6% | 95.5% | none | passed |
| `rule="domain"` (the default), third test | — | 22.8% | 85.1% (every domain ≥ 80%) | — | passed |

**Training overlap.** Confirm-3's 19,738 rows share nothing with the lineage's training files:
[firewall](firewall/RESULTS_firewall.md).

**Scope of the certificate.**
- It holds per node (δ = 0.05 each), for this model version (w4a5) and for items exchangeable with the calibration
  (these generators, new seeds).
- It does not cover real traffic, blocked actions, or families outside the calibration (those are always verified).

## Files

- `confirm3/`: the rules, the calibration and its parameters, the chain, the analysis, and the client test fixture's
  builder (`make_fixture.py`, not frozen: written after the run).
- `results/confirm3/confirm3.json`: every number above.
