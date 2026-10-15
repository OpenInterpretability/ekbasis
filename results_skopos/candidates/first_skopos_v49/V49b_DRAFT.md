# V49b: DRAFT (not registered; registered only after V49's stage verdict)

**Disclosure, first.** This draft was written on 2026-10-07, after five V49 quick readouts were seen: v49a raw, w75
and w50; v49f raw and w75. Choosing its world criterion also used those numbers (see 2). **Its protection is the fresh
items it reads, not the selection.**

## 1. Why

Under the registered V49 rule, each run keeps the largest λ (raw > w75 > w50) whose validation numbers pass:
- cal48_guard false alarms ≤ w4a5 + 1.0;
- flagged ≥ w4a5 − 1.0;
- m3val ≥ w4a5 − 0.5.

Raw passes for v49a and v49f, so raw gets their full readouts. On the quick, raw v49f lost ce by −1.4.

V49 is followed as registered. V49b is a second selection, registered separately, with a criterion for the old
worlds.

## 2. Selection (validation only)

Per run, the largest λ (raw > w75 > w50) that passes all of:
- **cal48_guard** as in V49: false alarms ≤ base + 1.0, flagged ≥ base − 1.0;
- **m3val** ≥ base − 0.5;
- **ce49b_val**, new, under gate 1's own ce rule:
  - accuracy ≥ base − 0.5;
  - ECE ≤ base + 0.01;
  - confident errors per 100 (conf ≥ 0.9 and wrong) in groups T and U ≤ base × 1.10.

A run with no passing λ gets no V49b readout.

**Why not v44val_world.** In V49's quicks it moves against ce:

| Candidate | ce | v44val_world |
|---|---|---|
| v49f raw | −1.36 | +1.34 |
| v49f_w75 | −0.73 | +0.67 |
| v49a raw | −0.47 | +0.59 |

It measures V44's gap families (comparisons, lines, no-rule, sums), which FX improves, so it would pick v49f raw again.

**No ce validation split existed.** hq_ce (gate 1's ce) is drawn from ce_items, and both are evaluation sets.

**ce49b_val:**
- **Generator:** confident_errors.py's own: worldgen families × question types × 1–3 actions, `fbalanced` with change
  balance. Groups: T = trained family and question type; H = trained family, held question type; U = families never
  trained.
- **Seeds:** new tags (`-V49B-VAL-20261007`).
- **Firewall:** `v48/firewall_cal.py`. It checks every training file of the lineage, V48's and V49's included, and
  drops rows identical to any evaluation floor.
- **Size:** 1,000 rows per group.

## 3. Readouts of each selected candidate

- **The full readout:** Addendum 9 (a)+(b) as registered, with multi.changed in gate 1.
- **The image readout** (PLAN_v49 Addendum E).
- **The fresh confirmation, ce49b_fresh:**
  - other seeds (`-V49B-FRESH-20261007`);
  - the same firewall, which also drops rows identical to ce49b_val;
  - 1,000 rows per group;
  - gate 1's ce rule against w4a5, read on the same rows.
- **Proposed, if the generators allow:** fresh regenerations, with new seeds, of the G3 sets (lines, chain4) and of
  the rules-flip set. These are the metrics that split the arms in the quicks (v49a −2 to −7 on lines, v49f +7). Each
  is held to its own G1–G6 or gate-4 rule.

## 4. Ship rule: single stage, fixed before any fresh number exists (coordinator's decisions, 2026-10-07 ~18:15 UTC)

**Scope.**
- Every V49b candidate is judged by the same rule. Skopos (v48a_w50) is read and judged under it as a reference.
- V48's and V49's verdicts stay under their registered rules, untouched.

**One principle.** Every (a) component with a generator is decided on its own fresh set alone, for every candidate.
- The old rows are reported diagnostics: they can neither rescue nor sink a candidate.
- Nobody gets a second look.

| Component | Fresh set (firewalled, never read) | Decided by |
|---|---|---|
| ce | ce49b_fresh_all: 6,626 rows (T 3,012, H 1,211, U 2,403); near-duplicates checked against the whole selection set; sha f4a6733a… | accuracy = simple mean of the T, H and U group accuracies ≥ base − 0.5 (point estimate; within-group bootstrap CI reported); ECE (equal group weights) ≤ base + tol_ECE; confident errors per 100 ≤ base + tol_T (group T) and ≤ base + tol_U (group U) |
| G3.lines, G3.chain4 | g3_fresh49b: 4,500 rows (lines 1–4 and chain4, 300 pairs per level, 4 × ho_rules; seed 20261010); 0 flagged; sha 3e0ef0cf… | the current bounds: ≥ base − 1.0 each |
| rules flips (rules.base_flip; G4 from the same rows) | ho_rules_fresh49b: 9,075 rows (the whole rules_stress battery with its addendum, same plan, seeds 20261008/9); 0 flagged; sha c6cb88bd… | the current bound: ≥ base − 1.0 |
| multi.changed | multi_fresh49b: 2,371 items, 13,571 questions (gen_multi.py's never-trained families, 4 × 600, seed 49008); 29 identical to old evaluation floors dropped; sha 6e44da7c… | the current bound: ≥ base − 0.5 |

**The calibrated tolerances.** tol_T, tol_U and tol_ECE are frozen in the registration.
- **Source:** the base's own resampled variability at ce49b_fresh's group sizes. Two independent resamples of w4a5's
  reads of ce49b_val_all (the selection set, same generator, never a test), 10,000 pairs, default_rng(9).
- **Rule:** each tolerance is the 95th percentile of the difference, so a no-change candidate fails at most 5% of the
  time.
- **ECE:** if the registered +0.01 already gives ≤ 5%, it stays.
- **Kept bounds:** the same computation reports the false-fail rate of each kept bound (G3, rules flips, multi) at its
  fresh size.
- **Status:** `v49b/calibrate_v49b.py`. It runs once w4a5's read of ce49b_val_all exists, on an idle GPU after V49's λ
  choice (`v49b/base_val_spec.json`).

**Selection (section 2)** uses ce49b_val_all (9,568 rows) with the same frozen bounds.

**Everything else:**
- (a) as registered on the full readout;
- image no-regression as a blocking gate;
- (b) and (c) as registered.

**Disclosure.** The move to fresh sets as the deciders, and to larger ones, was motivated by V49's quick results. On
hq_ce after masks (1,914 rows), v49f_w75's −0.73 has a CI of [−1.72, +0.26]: the set is too small to decide at ±0.5.

## 5. Status (2026-10-07 18:05 UTC)

The two ce sets are built on the CPU (`v49b/make_ce_sets.py`, `build_ce_sets.sh`, `refirewall_fresh.sh`).

| Set | Generated | Dropped by the firewall | Kept | Sample | sha |
|---|---|---|---|---|---|
| ce49b_val | 15,001 | 5,433 (176 identical to training, 5,210 near-duplicates, 47 identical to an existing evaluation floor) | 9,568 | 3,000 | a7b799d7… |
| ce49b_fresh | 14,999 | 7,570 | 7,429 | 3,000 | cb3a577a… |

- Each sample holds 1,000 rows per group T/H/U.
- ce49b_fresh is also checked against ce49b_val (identical or near-duplicate rows dropped), so the confirmation never
  re-tests the selection set.
- The near-duplicate share of the first pass, about 36%, is close to hq_ce's masked share, 1,086 of 3,000.
- No model has read either set. Registration (hash) comes after V49's verdict.
