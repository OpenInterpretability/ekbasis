# PLAN_v49b: a second, separately registered selection and decision for V49's arms

Registered 2026-10-07, after Caio's approval relayed by the coordinator, before any model read any fresh set.

## Disclosure, first

- This plan was written after V49's quick readouts were seen: v49a raw, w75 and w50; v49f raw, w75 and w50; v49g raw.
- Three choices here were motivated by those results:
  - its world criterion (ce49b_val_all, not v44val_world, which moved against ce in V49's quicks);
  - the switch of the generator-backed (a) components to fresh sets;
  - those sets' larger sizes.
- On hq_ce after masks (1,914 rows), v49f_w75's ce drop of −0.73 has a 95% CI of [−1.72, +0.26]: too small a set to
  decide at ±0.5.
- **The protection of this plan is the fresh items, which no model has read, not its selection.**

## 1. Scope

- **Arms:** V49's trained arms v49a, v49f, v49g and v49h. Each is considered at λ ∈ {raw, w75, w50}, the WiSE mixes
  with w4a5, built as the orchestrator builds them (`wise_lora.py <w4a5> <run ckpt> <λ> <out>`).
- **Skopos:** v48a_w50 (`/root/decis/release_skopos/adapter_v48a_w50`, sha cef17c98…) is judged by the same rule as a
  reference.
- **Untouched verdicts:** V49's stage verdict stays under PLAN_v49's registered rule, and V48's under PLAN_v48's.
- **Base:** w4a5 (`/dev/shm/conseq/wise_w4a5`) on every row.
- **Reader:** the trainer's evaluation (`v50/train_conseq_v50.py MODE=eval_adapter`, the same code as every V49
  readout) in /opt/sglang's environment, for every model.

## 2. Selection (validation only)

For each arm, take the largest λ (raw > w75 > w50) that passes all of:
- **cal48_guard** (V49's rule): false alarms on its "lost" rows at 0.2 ≤ base + 1.0; flagged ≥ base − 1.0.
- **m3val** accuracy ≥ base − 0.5.
- **ce49b_val_all** (all 9,568 rows) under the ce rule of section 3, with the tolerances frozen by Addendum A.

An arm with no passing λ gets no decision reads. The cal48_guard and m3val numbers are those of V49's quick readouts.
Reading ce49b_val_all needs each arm's three λ.

## 3. Decision: single stage, the same for every selected candidate and for v48a_w50

### 3.1 Components with a generator: decided on their fresh set alone

Every (a) component with a generator is decided on its own fresh set alone. Their old rows are reported diagnostics:
they can neither rescue nor sink a candidate. Nobody gets a second look.

**ce**, on ce49b_fresh_all (6,626 rows: T 3,012, H 1,211, U 2,403):
- accuracy = simple mean of the T, H and U group accuracies ≥ base − 0.5 (point estimate). The paired CI is reported,
  bootstrapped within groups (10,000 resamples, `default_rng(9)`).
- ECE, with T, H and U weighted equally (gate 1's ten equal confidence bins), ≤ base + tol_ECE.
- confident errors (wrong at confidence ≥ 0.9) per 100: group T ≤ base + tol_T, group U ≤ base + tol_U.

**G3.lines and G3.chain4**, on g3_fresh49b (base and flip rows: lines 2,400, chain4 600): each ≥ base − 1.0.

**rules.base_flip**, on ho_rules_fresh49b (base and flip rows, 5,850): ≥ base − 1.0.

**G4.blind**, on ho_rules_fresh49b (blind rows, 2,925): ≥ base − 1.0. The rows come from the same fresh battery as
the rule flips, so the one-principle decision covers them too.

**multi.changed**, on multi_fresh49b (changed questions in multi mode): ≥ base − 0.5.

### 3.2 Everything else in (a), as registered (PLAN_v45 Addendum 9), on the candidate's full readout

- the rest of gate 1;
- the rest of G1–G6;
- gate 4.

G1 (hanoi), G2 (accum), G6 (apps flips), habit, apps and lang have generators but no fresh set was built for them.
They stay on the full readout's rows, as registered.

### 3.3 Image no-regression: blocking

On the image readout (PLAN_v49 Addendum E's script, its items and settings):
- single-step image accuracy and read accuracy (adapter on) ≥ base − 1.0;
- chain accuracy from the image start ≥ base − 1.0;
- whole-start read rate ≥ base − 1.0;
- ECE of the image answers and of the read answers ≤ base + 0.02.

### 3.4 (b) and (c), as registered

- (b): on the full readout, at least one family's held-out gain has a paired cluster-bootstrap 95% CI > 0.
- (c): the same family confirmed on fresh firewalled items, pre-registered per family.

### 3.5 Verdict per candidate

ships = (a) [3.1 + 3.2] and 3.3 and (b) and (c).

## 4. Tolerance calibration (the procedure, fixed here; the numbers come in Addendum A)

**Source:** w4a5's read of ce49b_val_all, the selection set. It comes from the same generator as ce49b_fresh_all and
is never a test.

**A no-change candidate** is modeled as an independent second draw: two independent resamples, with replacement, of
w4a5's rows at ce49b_fresh_all's group sizes. Then:
- tol_T and tol_U, per 100, are the 95th percentiles of the difference in confident errors per group (10,000 pairs);
- tol_ECE = max(0.01, the 95th percentile of the difference in equally weighted ECE) (2,000 pairs). A no-change
  candidate therefore fails each at most 5% of the time;
- `default_rng(9)`, script `v49b/calibrate_v49b.py` (sha d90aeddb…).

**Reported with the numbers:** the false-fail rate of the bounds kept as registered at their fresh sizes:
- accuracy −0.5;
- G3, rules flips and G4 −1.0;
- multi −0.5.

The G3, rules and multi rates come from w4a5's reads of the old sets, now diagnostics.

**Addendum A** (the frozen numbers, hashed) is written after w4a5's read of ce49b_val_all and before any model reads
any fresh set.

## 5. Fresh sets (frozen; no model has read them)

| Set | Rows | Generator and seeds | sha256 |
|---|---|---|---|
| ce49b_val_all (selection) | 9,568 | `confident_errors.py`'s cell(), tag V49B-VAL-20261007 | 0274f2f6… |
| ce49b_fresh_all | 6,626 | the same, tag V49B-FRESH-20261007; near-duplicates checked against all of ce49b_val_all | f4a6733a… |
| g3_fresh49b | 4,500 | rules_stress `gen_line`/`gen_chain`, 300 pairs per level, seed 20261010 | 3e0ef0cf… |
| ho_rules_fresh49b | 9,075 | rules_stress battery and addendum, seeds 20261008 and 20261009 | c6cb88bd… |
| multi_fresh49b | 2,371 items | `gen_multi.py` never-trained families, seed 49008 | 6e44da7c… |

**Firewall:** every set passed `v48/firewall_cal.py` (sha ad52479f…): every training file of the lineage, V48's and
V49's included, and rows identical to any evaluation floor dropped. Reports are in `v49b/data/`.

**Scripts:**

| Script | sha |
|---|---|
| `make_ce_sets.py` | 630567ed… |
| `refirewall_fresh_vs_valall.sh` | 1e5e1654… |
| `make_rules_multi_fresh.py` | 7b8e5dd9… |
| `firewall_multi.sh` | 3870ccad… |

The validation sets are cal48_guard (3200e70c…) and m3val (c6a143d8…).

## 6. Order and schedule

1. w4a5 on ce49b_val_all → calibration → **Addendum A, hashed**.
2. Each arm's raw, w75 and w50 on ce49b_val_all → selection (section 2).
3. For each selected candidate, for v48a_w50 and for w4a5:
   - the four fresh sets;
   - the full readout, reusing V49's when it is the same candidate;
   - the image readout.
4. The verdict (section 3.5).

**Schedule:** only on GPUs idle for 5 min (`v50env/retest/idle_sched.py`, sha 5d593954…). V49's registered readouts
and the V49 image reads go first.

## Note 1 (2026-10-07 ~19:34 UTC): a format correction, before any model read any fresh set

**The bug.** `confident_errors.py`'s cell() writes yes/no golds as the strings "yes"/"no". The trainer's
gold_index() expects booleans for yes/no ("noul") questions, as ce_items and hq_ce hold them. It reads any non-empty
string as True, so every gold "no" was scored as "yes".

**Found** in w4a5's read of ce49b_val_all, the validation set: accuracy 11.0% on gold-"no" rows against 91.1% on
gold-"yes" rows.

**Fixed** (`v49b/fix_ce_gold.py`):
- On noul rows only, gold becomes True or False. The rows, their order and every other field are unchanged.
- ce49b_val_all: 3,982 golds; sha 0274f2f6… becomes 6e0b032d….
- ce49b_fresh_all: 2,747 golds; sha f4a6733a… becomes ee50e3b7…. No model has read it.

**Rescoring.** w4a5's read of ce49b_val_all is rescored from its saved outputs. The chosen option and the probabilities
do not depend on the gold field. 1,970 rows changed `ok`, exactly the gold-"no" rows.

**Effect.** Its equal-weight accuracy becomes 89.35, close to hq_ce's 89.03. The calibration (section 4) is run on the
rescored read; the first run, on string golds, is kept as `data/calibration_with_string_golds_INVALID.json`.

**Checked:** none of the other fresh sets is affected. g3_fresh49b and ho_rules_fresh49b hold choice questions with
string golds, and multi_fresh49b keeps gen_multi.py's own golds.

## Addendum A (2026-10-07 ~19:40 UTC): the frozen tolerances, before any model read any fresh set

Frozen as registered, on the coordinator's go relayed from Caio.
- **Calibration:** section 4's procedure, on w4a5's rescored read of ce49b_val_all (Note 1).
- **Files:** `v49b/data/calibration.json`, computed by `v49b/calibrate_v49b.py` (sha d90aeddb…).
- **Input:** `v49b/base_val/preds_ce49b_val_all_floor.rescored.jsonl`.

**Base (w4a5) on ce49b_val_all:**
- equal-weight accuracy 89.35: T 96.86, H 86.43, U 84.77;
- confident errors per 100: T 1.74, H 4.92, U 3.95.

**Frozen:**
- **tol_T = 0.5644 per 100.** Group T confident errors ≤ base + 0.5644 per 100.
- **tol_U = 0.9176 per 100.** Group U confident errors ≤ base + 0.9176 per 100.
- **tol_ECE = 0.01.** The registered value stays: the null p95 is 0.0083 ≤ 0.01.

**Every other limit unchanged:**
- ce accuracy (equal-weight T/H/U) ≥ base − 0.5;
- G3.lines and G3.chain4 ≥ base − 1.0;
- rules.base_flip ≥ base − 1.0;
- G4.blind ≥ base − 1.0;
- multi.changed ≥ base − 0.5.

**Information only (not a rule): false-fail rates for a no-change candidate at the fresh sizes.**
- **Independent-draw null** (section 4's model; an upper bound, since base and candidate are read on the same rows):
  w4a5's own resamples, from `calibration.json`.
- **Paired null:** a real candidate's discordance with w4a5 on the same old rows, scaled to the fresh size. SE =
  √(q/n); false-fail = Φ(−limit/SE).
  - v49f_w50's quick reads of hq_ce and hq_rules for ce, G3, rules flips and G4;
  - v48a_w50's full read of multi_test_testfam for multi.
  - Computed by `v49b/paired_null_info.py` into `data/paired_null_info.json`.
  - The old rows are diagnostics, and hq_rules holds only 600 line and 150 chain4 rows, so these estimates are rough.

| Limit | Independent-draw null | Paired null |
|---|---|---|
| ce accuracy −0.5 | 20.8% | 3.1% (SE 0.27) |
| ce confident errors T +0.5644 | 5% (by construction) | 0.3% |
| ce confident errors U +0.9176 | 5% (by construction) | ≈0% |
| ce ECE +0.01 | 2.4% | — |
| G3.lines −1.0 | 22.9% | 10.8% (SE 0.81; discordance 15.7%) |
| G3.chain4 −1.0 | 32.2% | 9.0% (SE 0.75) |
| rules.base_flip −1.0 | 1.0% | 1.8% |
| G4.blind −1.0 | — | ≈0% |
| multi.changed −0.5 | 23.9% | 4.8% (SE 0.30) |

When the selection reads exist, the same paired estimate on ce49b_val_all itself is reported as a note, for information.

## Addendum B (2026-10-07 ~19:50 UTC): v48a_w50 removed as a reference, before any fresh-set read

**What changes.** On Caio's request ("focus forward, not on the previous Skopos"), relayed by the coordinator,
v48a_w50 is no longer read or judged in V49b:
- no fresh-set reads;
- no full readout;
- no image readout.

**Why it changes no decision.** It was a reference only. Every other candidate's verdict is computed against w4a5
alone and does not depend on it.

**Where the time goes.** The freed GPU time goes to V49's and V49b's candidates, then to the kernel re-test.

**Kept.** Its adapter stays on disk: `/root/decis/release_skopos/adapter_v48a_w50`, sha cef17c98…. Nothing is deleted.

**State when hashed.** No model has read any fresh set: `v49b/fresh/` does not exist.

## Addendum C (2026-10-07 20:29 UTC; revised 20:41 UTC, before any read of the new image sets): the image gate on fresh, larger image sets

**Disclosure, first.** This addendum was written after seeing v49f_w50's image readout on the old small sets (120
single-step items, 60 chains):
- one chain fewer correct from the image start;
- three chains fewer with the whole start read right;
- 95% CIs including 0.

Under 3.3's registered bounds (−1.0 point), one chain of 60 (1.67 points) already fails. **The protection of this
addendum is that the image decision moves to fresh data that no model has read.** It applies to every candidate. The
coordinator decided it, extending the principle Caio approved for V49b.

**What changes.**
- Section 3.3's image no-regression is decided on the fresh image sets below, with the tolerances calibrated below.
- The old 120 items and 60 chains become diagnostics. The results already read on them (w4a5, v49f_w50) stay reported
  as they are.
- V49b schedules no new reads of the old sets. Reads of them, existing or scheduled under PLAN_v49 Addendum E, are
  reported as diagnostics.

**The fresh image sets.**
- **Generators:** image_eval.py's and image_chain.py's, as `img/image_readout.py` runs them, with new seeds. Each set
  is a seed, a size and an exclusion list.
- **Firewall** (`img/img_firewall.py`), on each item's and chain's text prompt (rules, state in text, every action),
  by the Addendum 8 rules: identical after normalization, or word 8-gram near-duplicate with Jaccard ≥ 0.5 after
  removing the set's own layout. Checked:
  - against every training file of the lineage, by v48/firewall_cal.py with V49's files;
  - against the old image sets;
  - for the decision set, against the calibration set.
- **Files:** exclusions in `img/data/img49b_{val,fresh}_exclude.json`; counts and the largest Jaccard values in
  `img/data/img49b_counts.json`.

| Set | Single step | Chains (10–20 actions) |
|---|---|---|
| **img49b_val** (calibration only) | Random(49301): 300 generated, 296 kept | seeds 48000+i: 150, all kept |
| **img49b_fresh** (the decision) | Random(49303): 600 generated, **594** kept (296 lamps, 298 jugs) | seeds 49000+i: **300** (150 per world), all kept |

**Flags.**
- All 10 flagged items were flagged against the lineage: 1 identical to a training prompt, 9 near-duplicates.
- Nothing was flagged against the old sets (largest Jaccard 0.39).
- For the decision set, nothing was flagged against the calibration set (largest Jaccard 0.41).

**What is read** (`FRESH=1`):
- single step with the adapter on, the image and read prompts;
- chains from the image start, including the start read.

This takes about 50 min of GPU per model on img49b_fresh and about 25 min on img49b_val. Both are estimated from the
old run's 30.4 min; the chains take most of it.

**The gate.** Each candidate is compared against w4a5 on the same img49b_fresh rows:
- single-step image accuracy ≥ base − tol_img;
- single-step read accuracy ≥ base − tol_read;
- chain accuracy from the image start ≥ base − tol_chain;
- whole-start read rate ≥ base − tol_start;
- ECE of the image answers ≤ base + tol_ece_img;
- ECE of the read answers ≤ base + tol_ece_read.

**The tolerances: Addendum A's procedure, frozen before any model reads img49b_fresh.**
- **Source:** w4a5's read of img49b_val.
- **No-change model:** a no-change candidate is an independent second draw at img49b_fresh's sizes (594 items, 300
  chains).
- **Rates:** two independent Binomial(n, p) draws, 100,000 pairs.
  - This is Addendum A's resampling of rows, applied to a yes/no metric.
  - p = (k+1)/(m+2) from w4a5's val counts, so that a 100% base rate does not give a zero-width null.
  - tol = max(1.0, the 95th percentile of base − candidate).
- **ECE:** two independent resamples with replacement of w4a5's val rows at 594 rows, 10,000 pairs. tol = max(0.02,
  the 95th percentile of candidate − base).
- **Randomness:** one `default_rng(9)`, used in the order above. Script `img/calibrate_img.py`.
- **Result:** a no-change candidate fails each component at most 5% of the time.
- **Reported with the numbers, for information only:**
  - the false-fail rates of 3.3's registered bounds at the fresh sizes;
  - a paired-null estimate from v49f_w50's discordance with w4a5 on the old sets (`img/paired_null_img.py`), as
    Addendum A did.

**Order.**
1. When every V49b selection read has started, w4a5 reads img49b_val on an idle GPU (`img/cal_img_spec.json`, output
   `img/val49b/w4a5`).
2. `img/calibrate_img.py` writes `img/data/calibration_img.json`.
3. The frozen numbers go into an appendix of this addendum, hashed in `v49b/PLAN_v49b.addendumC_frozen.sha256`. The
   fresh stage's image jobs wait for that file (`v49b/make_fresh_spec.py`).
4. In the fresh stage, w4a5 and every selected candidate read img49b_fresh (`img/fresh49b/<model>`).

**Revision, before any read of the new sets.** The first version was hashed at 20:29:37 UTC; its text is kept in
`v49b/PLAN_v49b.addendumC_v1.txt`. It had three faults:
- a heading time later than the hash;
- the firewall against the old sets described as identity only;
- an estimate of about 40 min per model.

The near-duplicate check was added. It flagged nothing, so the exclusion lists are byte-identical. The estimate was
corrected, and the order and the information-only items were made explicit.

## Addendum C appendix (2026-10-07 20:54 UTC): the frozen image rule, paired, before any read of the new image sets

**Decision.** The coordinator decided that the image gate uses a paired rule. The decision came before any model read
img49b_fresh or img49b_val.

The paired rule replaces Addendum C's unpaired tolerances: its section "The tolerances" and steps 1–3 of "Order".
Everything else in Addendum C stays:
- the fresh sets;
- the firewall;
- what is read;
- the old sets as diagnostics.

**The rule.** Each candidate is compared with w4a5 on img49b_fresh.
- **Components:**
  - single-step image accuracy;
  - single-step read accuracy;
  - chain accuracy from the image start;
  - whole-start read rate;
  - ECE of the image answers;
  - ECE of the read answers.
- **Paired bootstrap, 10,000 resamples.**
  - Items are resampled for the four single-step components, and chains for the two chain components.
  - For each candidate, a new `default_rng(9)` draws the item indices first, then the chain indices.
- **A rate component fails iff both hold:**
  - (i) the observed drop (base − candidate) is more than 1.0 point;
  - (ii) the 95th percentile of the bootstrap (candidate − base) is below 0.
- **An ECE component fails iff both hold:**
  - (i) the candidate's ECE is worse by more than 0.02;
  - (ii) the 5th percentile of the bootstrap (candidate − base) is above 0.
- **The image gate passes iff no component fails.** It blocks shipping, as registered in 3.3.
- **Code:** `img/gate_img49b.py`, which writes `img/GATE_img49b.json`. It was tested on synthetic copies of w4a5's
  old-set read:
  - an identical copy passes every component, with every bootstrap difference at 0;
  - a copy with 8 image answers and 4 start reads made wrong fails single_image, start_read and ece_image.

**Disclosure.**
- **Timing.**
  - The rule was chosen before any read of img49b_fresh or img49b_val: `img/fresh49b/` and `img/val49b/` do not
    exist.
  - Like Addendum C, it was written after seeing v49f_w50's result on the old small sets.
- **Reason.** The unpaired tolerances (about 2–5 points; see below) would let real 2–3 point drops pass. The paired rule
  catches those drops.
- **False-fail.**
  - A candidate identical to w4a5 never fails: every bootstrap difference is 0.
  - Some candidates have no shift but still differ from w4a5 on some rows. For them, the per-component false-fail rate
    was simulated (`img/paired_rule_null.py`, `img/data/paired_rule_null.json`, information only):
    - 3.0–4.5% at v49f_w50's discordance with w4a5 on the old sets (1.7–5.8% of rows);
    - 0.9–5.2% on a grid of discordance from 1% to 10%, the largest at 10% and 594 rows, within simulation error of 5%.
  - For the ECE components no simulation was run. Condition (ii) is a one-sided 5% bootstrap test.

**Information only, not a rule: the unpaired tolerances.** `img/calibrate_img.py` ran on w4a5's read of the old sets as
a stand-in for img49b_val, at the fresh sizes. Output: `img/data/unpaired_info_oldsets.json`.

| Component | Unpaired tolerance | Registered bound's false-fail at the fresh size |
|---|---|---|
| single-step image | 3.87 points | 35% (−1.0) |
| single-step read | 2.36 points | 26% (−1.0) |
| chains from the image | 1.67 points | 13% (−1.0) |
| whole-start read | 5.00 points | 35% (−1.0) |
| ECE image | 0.033 | 16% (+0.02) |
| ECE read | 0.020 | 2.5% (+0.02) |

If w4a5's img49b_val read runs later, its unpaired numbers are added as a note, for information.

**Order now.**
- The fresh stage's image jobs need only this appendix's hash (`v49b/PLAN_v49b.addendumC_frozen.sha256`), so they can
  start right after the selection.
- w4a5's img49b_val read runs only on a GPU that would otherwise sit idle (`img/cal_img_spec.json`): after V49b's fresh
  stage, V49's verdict and V49's image queue, on a GPU idle for 15 minutes. Nothing waits on it.

## Note 2 (2026-10-07 20:59 UTC): the old-set diagnostic of the frozen image rule (information only, after the freeze)

After the appendix was hashed, `img/gate_img49b.py` ran on the old image sets (120 items, 60 chains; diagnostics only)
for v49f_w50 against w4a5 (`img/GATE_img49b_oldsets_diagnostic.json`).
- **start_read would fail:** −5.0 points. There are 3 discordant chains, all against v49f_w50, and the bootstrap 95th
  percentile is −1.67.
- **Every other component passes:**
  - single-step image +0.83;
  - read +1.67;
  - chains from the image −1.67 (1 discordant chain; bootstrap 95th percentile 0);
  - ECE image +0.012;
  - ECE read −0.024.

With so few discordant pairs the percentile bootstrap is anti-conservative: here 3 of 3 discordant chains against
v49f_w50 have an exact sign-test p of 0.125, yet the bootstrap calls the drop clear. At the fresh sizes the margin
condition (i) covers this, and the appendix's simulation gives at most 5.2% false-fail across 1–10% discordance, so the
rule is unchanged.

The decision stays on img49b_fresh.

## Addendum D (2026-10-07 21:02 UTC): the image gate informs and does not block (Caio), before any fresh image read

**Caio's decision, verbatim, relayed by the coordinator:** "não precisamos de que seja 100% com imagens, nosso propósito
de ser um modelo de consequências para agents é muito foda já com texto, código, apps... imagens é um a mais por
enquanto". In English: we do not need it to be 100% with images; our purpose, a consequence model for agents, is already
very strong with text, code and apps; images are an extra for now.

**What changes.**
- **Section 3.3 no longer blocks.** The V49b verdict does not depend on it. Section 3.5 becomes:
  ships = (a) [3.1 + 3.2] and (b) and (c).
  - This supersedes "blocking" in 3.3's heading and "It blocks shipping" in Addendum C's appendix.
- **The measure stays.** Addendum C's appendix rule is unchanged (`img/gate_img49b.py`).
  - Its outcome is reported for every candidate.
  - It goes on the card in plain words, e.g. "image: start-state reading X vs Y, a clear drop" or "no clear drop".
- **The fresh image reads stay.** w4a5 and every selected candidate read img49b_fresh, about 50 min each. These are the
  reported image numbers.
- **Order: the image reads run after the text fresh sets.** In the fresh stage (`v49b/make_fresh_spec.py`), each image
  job:
  - waits for every text fresh-set job of every model (ce49b_fresh_all, g3 and multi; ho_rules);
  - is listed after all text jobs, so a ready text job always goes first.

**State when hashed.** No model has read img49b_fresh or img49b_val. The fresh stage has not started.

## Note 3 (2026-10-07 22:17 UTC): ho_rules_fresh49b read in two parts, as the full readout reads ho_rules

**What happened.** The first fresh-stage reads of ho_rules_fresh49b, for w4a5 and for v49a, read the whole split at
EVAL_BS 16. Both ran out of GPU memory on its 675 long "manual" items at 22:11–22:12, before writing any predictions
(`v49b/fresh/{w4a5,v49a}_b.log`). The scheduler's dependency rule then skipped every image job and both WiSE clean-ups.

**What was done.**
- **The scheduler.** It was stopped by its exact PID (957205) before it started any other read. The two running
  `_a` reads (ce49b_fresh_all, g3_fresh49b, multi_fresh49b), started at 21:47:31, were left untouched.
- **The two-part read.** ho_rules_fresh49b is now read for every model exactly as the registered full readout reads
  ho_rules (V44 Addendum 2):
  - floors over 1,536 tokens go to `ho_rules_fresh49b__l` (675 rows, all "manual", 1,802+ tokens) and are read one at
    a time (EVAL_BS 1);
  - the rest go to `ho_rules_fresh49b__s` (8,400 rows, at most 1,168 tokens) and are read at EVAL_BS 16;
  - `v46/merge_readout.py` puts the two back in the split's order.
- **Code and hashes.** `v49b/split_long_rules.py` made the parts. Their sha256: `__s` 4c3b551c…, `__l` 4ecc50dd…. The
  split itself is unchanged (c6cb88bd…).
- **The restarted stage** (`v49b/make_fresh_spec2.py`, `fresh_spec2.json`) is the same stage with this one change:
  - it waits for the two running `_a` reads;
  - the image reads still come after every text fresh-set read (Addendum D).

**What it changes.** The same reader, code and rows apply to the base and to every candidate. No decision rule
changes. No model has been read twice on any decision set, because neither failed read wrote a prediction.
