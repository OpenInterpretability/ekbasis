# Pre-registration: does consequence training make the errors confident?

Written on 2026-10-03, after the test of `PREREG_confident_errors.md` (confirmed) and before Eikos-27B answered any of
its items. Its SHA-256 is recorded in `PREREG_sha256.txt` before the run.

## Why

On 15,008 new questions, Ekbasis gave 58.1% of its wrong answers with a confidence of 0.9 or more in the world families
it was trained on (T) and 27.8% in the families it never saw (U), 30.3 points apart (`results/confident_errors/`). Two
explanations remain: consequence training made Ekbasis confidently wrong where it is familiar, or the T families are
simply ones where any model errs with confidence. Eikos-27B is the same model before consequence training: it never
saw any of the 12 families, so for it T and U are both new. If the gap is a property of the families, Eikos-27B shows it
too; if training made it, Eikos-27B does not.

## Design

- **Model**: Eikos-27B (`/root/decis/release_final/models/Eikos-27B`, the published release, bf16), served exactly as
  Ekbasis was: vLLM 0.30 with the same flags, the same System One API code, one prompt per question. Both models read the
  answer letters the same way and use the same calibration (temperature 1).
- **Items**: the same 15,008 items (`results/confident_errors/items.jsonl`), the same groups (T, H, U by the families'
  roles in Ekbasis' training).

## Primary analysis

The gap in the share of wrong answers given with a confidence of 0.9 or more (T minus U) for each model, and the
difference between the two gaps, D = gap(Ekbasis) − gap(Eikos-27B), with a paired bootstrap: 2,000 resamples of items
within each family, the same resampled items scored for both models.

- **Training made it** if D is at least 15 points (half of Ekbasis' gap) and its 95% interval excludes 0.
- **The families explain it** if the interval of D includes 0.
- **Both contribute** otherwise (D above 0 with an interval excluding 0, but under 15 points).

## Secondary analyses (reported whatever the primary result)

- Eikos-27B's own result under the rule of `PREREG_confident_errors.md` (the share in T against U, its interval, the
  family medians).
- Error rates, the share of confident errors and AUROC per group and family, for both models side by side.
- Within each group, how consequence training changed the share of confident errors (Ekbasis against Eikos-27B, paired
  bootstrap).

## Reporting

Every prediction is saved (`results/confident_errors/eikos27b/`). Deviations are listed in the report.
