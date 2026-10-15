# V50R3 result (PREREG_R3.md) — 2026-10-15 12:40 UTC

**Verdict: FAIL on both pre-registered tests; guards hold.** R2 stays the candidate of this line.

- Primary (transfer): neutral AUROC R3 − R2 = +0.005 [−0.004, +0.015] (rule +0.03, CI > 0). AUROC base 0.833 /
  R2 0.835 / R3 0.840. Balanced accuracy at 0.5: base 0.720 / R2 0.696 / **R3 0.771** (a threshold shift; ranking
  nearly unchanged). SWE exact AUROC 0.841 / 0.852 / 0.846; terminal 0.825 / 0.824 / 0.835.
- Mechanism: sess_val R3 − R2 = +0.026 [+0.012, +0.040] (rule +0.03). R2, which never saw the session format, already
  scored 0.914 vs base 0.890 → presentation was not the gap; prediction held (the neutral failures are mostly missing
  tools/modules/paths, which shell file operations do not cover).
- Guards: all pass. vs R2: fac_val −0.3, git_long −0.8, git3_held −0.7 (CI just below 0; vs base −0.55, CI across 0),
  latent +0.9, ftest_family +1.2.
- Next for the neutral axis: failure-type coverage (executed scenarios where a tool, module, path or permission is
  missing, visible only from earlier output), not presentation.
