# Look When Unsure, Check When Sure

The paper and everything needed to check it: `look_when_unsure.tex` (PDF: `look_when_unsure.pdf`), its figures, and the
code that recomputes every number in it from the saved model outputs.

## Reproduce

```bash
python3 reproduce.py        # re-runs every analysis on the saved predictions and chains; writes numbers.json
python3 check_numbers.py    # every number in the paper must come from numbers.json
python3 make_figs.py        # figures/*.pdf and figures/*.png from numbers.json
pdflatex look_when_unsure.tex && pdflatex look_when_unsure.tex
```

`reproduce.py` reads two folders:

- `EKB_RESULTS` (default `../results`): the package's release evaluation, the confident-errors tests and the
  recalibration test;
- `EKB_RUNS` (default `runs/`): the research runs, which are the training rounds, the loop tests, the guard sets, the
  real-use test and the paper's experiment on the parent model.

Each pre-registered analysis is re-run with its original script (`analysis/`), and its output must equal the result
saved when it first ran. A field added to a script after that run may appear only in the re-run; any other difference
stops the run. The rest is computed in `reproduce.py` from the raw rows, and `numbers.json` records the outcome of every
check under `checks`.

## What is where

| File | What it is |
|---|---|
| `look_when_unsure.tex` | The paper (LaTeX, pdfTeX). |
| `site_summary.md` | The on-site summary. |
| `reproduce.py` | Recomputes every number; writes `numbers.json`. |
| `check_numbers.py` | Lists any number in the text (or in `site_summary.md`) not found in `numbers.json`. |
| `make_figs.py` | The figures, every value read from `numbers.json`. |
| `analysis/` | The analysis scripts as they ran, the same code as when each result was first produced. |
| `recomputed/` | The re-run outputs (written by `reproduce.py`). |
| `prereg/` | The plans of the training rounds, loop tests, guard set and the paper's experiment, as sealed. |

The plans of every test, sealed by SHA-256 before each run, are listed in the paper's appendix and in
`../PREREG_sha256.txt`; `reproduce.py` checks that each plan (`../PREREG_*.md`, `prereg/*.md`) still matches its seal.
