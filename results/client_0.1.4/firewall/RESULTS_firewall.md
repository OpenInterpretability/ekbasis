# WS-U firewall (06/10): WS-U's evaluation items against every training file of w4a5's lineage — NO OVERLAP

**Question (coordinator).** Do any of WS-U's evaluation items repeat, exactly or nearly, an item from the training
data of the released model? The concern: small generators repeat items regardless of seed, and the paper's 15,008
"new" items did overlap V42's training file.

**What was checked** (`fw_u.py`, CPU only, item by item; WS-FX's firewall rules as F's Addendum 7 audit applies them):
- **Evaluation side:** 77,542 rows with 47,756 distinct evidences (the state text the server read):
  - dev: WS-P's dataset, all 10 suites, 29,029 rows;
  - confirm-1: 28,723 kept rows (19,825 in the five main suites + 8,898 planning);
  - confirm-2: 19,790 kept rows.
- **Training side:** every `ftrain*.jsonl` (21 files) plus `mined_wide` and `mined_chain`, 2.2M rows. This is a
  superset of the lineage: V42 = V41's checkpoint + `ftrain_mixG3` (= `ftrain_mixG2M` + `git3_train`); r4a = V42 +
  `mined_wide` + `mined_chain`; w4a5 = WiSE(V42, r4a).
- **Rules:**
  1. Identical: the normalised training floor or ceiling equals an evidence.
  2. Near-duplicate: the training floor's word 8-grams, minus the file's layout, are ≥ 50% contained in the evaluation
     set, then Jaccard ≥ 0.5 against one evidence.
  3. Action sequences and Python code apply only to rows with `struct`; no lineage row has one.

**Positive control** (the same code on the paper's `ce_items`, which F's audit found contaminated):
- T: 4,150 of 7,172 rows hit lineage files (F: 4,117);
- H: 1,227 of 2,472 (F: 1,219);
- U: 0 of 5,364 (F: 0).

The code finds the known contamination.

**Result: 0 rows flagged, in every set and suite** (dev, confirm-1, confirm-2; identical 0, near-duplicate 0).
- **ftrain_mixG3** (the lineage file): 193 candidates passed the containment prefilter; the best Jaccard was 0.254.
- **ftrain_all** (not in any run script, so not in the lineage): 15,223 candidates, best Jaccard 0.488 (p99 0.420),
  1,022 at ≥ 0.4. All are git_wild items (dev 574, confirm-1 231, confirm-2 28).
  - Their closeness is shared git layout ("Current branch: main", "Stash entries: 0", the preamble). The repositories,
    commits and files are different. ftrain_all's layout filter keeps those lines, because git is under 20% of that
    file.

**Consequence.** The confirm-1 (C1–C3) and confirm-2 (P1, P2, S1–S3; P3 failed) verdicts are computed on items with no
training overlap under FX's rules, so nothing needs recomputing.

**Not yet checked:** confirm-3. It is running; its rows are scanned when it finishes.

**Files:** `fw_u_dev_c1_c2.json` (summary, per training file), `fw_u_ce.json` (the control), `fw_near.py` (the
near-miss diagnostic).
