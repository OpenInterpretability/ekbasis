# PLAN_v49: FX breadth on the recipe that keeps the guard

Registered 2026-10-07 ~11:20 UTC, before any V49 data exists. The release rule is PLAN_v45 Addendum 9 and the masks are
Addendum 8, both unchanged. The data rule is Caio's of 06/10.

## What V45–V48 taught (the inputs; `v48/V48_RESULTS.md`, `v48/VERDICT_v48a_w50.md`)

- **The guard.** Fresh guard-style git items with their right labels (the anchor) fix the guard's hedging:
  - v48a: safe-row log-odds back to w4a5's, AUROC above w4a5's;
  - soft targets do not: V47's replay, v48k's KL, the v48r/v48s2 repairs.
- **The old git replay holds "flagged".** v48w cut it from 0.245 to 0.095 and lost 3–3.5 points of flagged.
- **The world replay holds ce.**
  - v48a: world 0.17, ce −1.67;
  - v48w: world 0.245, ce −0.73;
  - v46b: world 0.245, anchor 0.10, ce −0.11 on the full readout.
- **The halfway WiSE mix (v48a_w50) keeps the guard and ce, but:**
  - its gains shrink: only SQL has a CI above 0;
  - multi drops: −0.71 [−1.88, +0.42], the one failing gate-1 metric.

  v46b (anchor 0.10) had the best multi: 79.33 against w4a5's 78.09.

## Goals

(a) as registered. Beyond (a):
- broader (b) gains: sql, shell, git, habit, accumulation, as v48w_w50 showed;
- multi at or above w4a5's.

## Arms

Common to all arms:
- start from w4a5 (INIT, rank 128);
- LR 1.5e-5, SEED 2, BS 8, JEPA as before;
- V47's trainer copy (`v47/train_conseq_v47.py`): the base trainer with "replay*" kinds on the soft path;
- TRAIN ftrain_mixG3.

**Protected shares**, kept at their working values in every arm except v49h, which keeps their example counts instead:
- world replay 0.245: multi 0.0735, floor 0.049, floor3 0.0343, read 0.0196, replay 0.0686 (v46b's);
- git replay 0.245: floorG3 0.1715, floorG2 0.049, floorG 0.0245 (v46b's);
- anchor floorGA 0.25 (v48a's).

The anchor pool is v46_anchor plus **v49_anchor2**: v48_softpool's 1,398 rows (firewalled for PLAN_v48) with their own
right labels, kind floorGA. That is 3,610 fresh guard-style rows, so more steps do not mean more repeats.

**New data: the remaining 0.26.** To make room without cutting the protected shares, steps go from 600 to **900**. The
new-data examples per run are then 0.26 × 7,200 = 1,872, about v46b's 1,968.

| Arm | New-data bucket (0.26) | Steps | Knob |
|---|---|---|---|
| **v49a** | F's factory data (floorGV, floorRXsh, floorRXgit, floorRXsql, floorC), v46b's proportions × 0.26 / 0.41 | 900 | control: the protections at their working shares, no FX |
| **v49f** | F's factory 0.13 + **FX 0.13** (kind floorFX) | 900 | FX breadth, half of the new data |
| **v49g** | **FX 0.26** | 900 | FX breadth as all the new data |
| **v49h** | v49f's composition with FX raised by steps: the protected example counts of v49f kept, FX 3,360 examples. Shares: world 0.184, git 0.184, anchor 0.1875, F 0.0975, FX 0.35 | 1,200 | FX dose with the protected *counts* fixed; also tests count against share |

The v47b calibration arm does not fit without cutting a protected share, so it is not run. The lesson stays noted for
V50.

## FX data (`v49/make_v49_data.py`, after this hash)

**Source:** FX's packed training file, `/dev/shm/fx/data/fx_train.jsonl.gz` (SHA256SUMS in FX/data).

**Kept:**
- every family except **ext_webworld**, which is excluded (Caio's rule);
- py_numeric is empty in the pack;
- F's retired Python generator is not used: FX's py_* rows are FX's firewalled pack.

**Sampling,** with `random.Random(49)`, stratified by family and question type:
- **each FX-own family:** up to **400 rows**, split evenly across its question types (the qtype head), every row if
  fewer;
- **ext_cwm_python:** 2,000 rows, about 10% of the floorFX pool;
- **ext_shio_cmds:** 600 rows, about 3% of the pool.

The trainer draws uniformly within a kind, so these pool shares are the sources' shares of the FX bucket.

**Firewall before any training:** `v48/audit_v48.py`, i.e. the Addendum 7/8 rules (identical prompt or read prompt;
word 8-gram near-duplicate with Jaccard ≥ 0.5; equal sequences of 2+ commands), against every evaluation file. That
covers 1,143+ files: cf_sql, cf2_sql, cal48_guard and the FX held-out readouts below. It runs on both `v49_fx` and
`v49_anchor2`; flagged rows are dropped and counted.

**Attribution** for any published card: the FX/RESULTS.md text, without the WebWorld clause. CWM and ShIO are CC-BY-4.0.

## Readouts and the choice of λ (validation only)

**Quick readouts:** Addendum 4's quick list plus cal48_guard, plus three new splits:
- **m3val** (300, validation);
- **fxe_family:** 200 per held-out FX family × 13, from `fx_eval_family`, `random.Random(49)`;
- **fxe_app:** 800 Memos rows, from `fx_eval_app`.

w4a5 reads the three new splits as base extra readouts. fxe_* are **reported, not gates**: Addendum 9's families stay
as registered. Before use, fxe_* are checked against every training file of V49 (identical and near-duplicate),
v49_fx included.

**Candidates per arm:** the raw run, w75 and w50. v49h has the same three.

**λ is chosen on validation only.** The choice is the **largest λ** (1.0 > 0.75 > 0.5) whose numbers satisfy all of:
1. **guard on cal48_guard** ("lost" rows, 0.2 threshold): false alarms ≤ w4a5's + 1.0 and flagged ≥ w4a5's − 1.0;
2. **m3val accuracy** ≥ w4a5's − 0.5. m3val is a validation proxy for multi; its worlds are related to multi's
   never-trained machines, but it is not the same construct.

No test split enters the choice. An arm with no qualifying candidate gets no full readout.

**Full readout:** each arm's chosen candidate. The verdict follows Addendum 9: (a) on the full readout; (b); (c)
pre-registered per family before its fresh items are generated.

## Schedule

- V49's trainings go first on every GPU as it frees.
- The V48 full readouts still pending are deferred, recorded as a deviation, and run when GPUs are idle.
- The V47 stage's full readout of v47a cannot run: its checkpoint was deleted. It is marked failed.
- Out of memory: a run that dies of OOM is retried with SEED + 1, as in V48.

Hash: computed over this file and written with the time to `PLAN_v49.sha256`.

## Addendum A (2026-10-07 ~11:12 UTC; before any V49 data exists): anchor 0.20

**Why.** The coordinator's note, after this plan's hash:
- **v46c (anchor 0.15, quick):**
  - (b) is broad: sql +2.00, shell +1.29, habit +0.54, accumulation +1.39, all with CI > 0;
  - false alarms are inside the bars: 4.63 / 5.01;
  - (a) fails only on known flagged (93.86) and apps.harm_safe.
- **Proposal:** anchor about 0.15–0.20 with the old git replay at full share as V49's base, with FX on top.
- **The dose-response so far:**

  | Anchor | Run | Gains | Known flagged | Other |
  |---|---|---|---|---|
  | 0.10 | v46b | | | false alarms over the bar, best multi |
  | 0.15 | v46c | broad | 93.86 | |
  | 0.25 | v48a | narrow | | ce lost while world replay was cut |

**Change.**
- **Every arm:** the anchor goes from **0.25 to 0.20**. World replay (0.245) and git replay (0.245) stay at full share.
  The 0.05 freed goes to the new-data bucket, which becomes **0.31**:

  | Arm | New-data bucket |
  |---|---|
  | v49a | F 0.31 |
  | v49f | F 0.155 + FX 0.155 |
  | v49g | FX 0.31 |

- **Steps:** 900 for v49a, v49f and v49g. New-data examples are 0.31 × 7,200 = 2,232.
- **v49h:** keeps v49f's protected example counts (world 1,764, git 1,764, anchor 1,440, F 1,116) and raises FX to
  3,360 examples. The step count is computed by `v49/make_runs_v49.py`.

Everything else in PLAN_v49 is unchanged: FX sampling and firewall, validation-only λ, readouts, gates and schedule.

Hash: computed over the text of this addendum (from its heading to the end of the file) and over the whole PLAN_v49.md,
and written with the time to `PLAN_v49.addendumA.sha256`.

## Addendum B (2026-10-07 ~11:20 UTC): the data as built (a record; nothing in the design changes)

- **FX sample** (`v49/make_v49_data.py`, 15 s): 19,800 rows from 45 families (WebWorld excluded): 43 FX-own × 400, CWM
  2,000, ShIO 600.
- **Firewall of the training side** (`v48/audit_v48.py`; 1,147 evaluation files, 255,736 items; `v49/audit_v49.json`):
  **2,175 rows flagged and dropped.**

  | Family | Dropped | Why |
  |---|---|---|
  | vk_tasks_repeat_done, vk_projects_archive_delete, vk_labels_buckets, se_vikunja | all 1,600 | near-duplicates through the Vikunja app's state layout against held-out Vikunja items (vk_sharing_teams) |
  | py_strings_seq | 321 | identical to evaluation prompts: F's retired Python generator repeats its prompts |
  | py_control_exc | 202 | same |
  | py_alias_mutation | 51 | same |
  | se_sql | 1 | |

  - **v49_fx:** 17,625 rows, 41 families. CWM is 11.3% of the floorFX pool and ShIO 3.4%, a little above the planned
    ~10% / ~3% because the pool shrank.
  - **v49_anchor2:** 1,398 rows, 0 flagged.
- **Evaluation side.** fxe_* were checked against every training file (eval_masks.TRAIN, v48_softpool, v49_fx,
  v49_anchor2):
  - **fxe_app:** 800 kept.
  - **fxe_family:** 404 of 2,600 near-duplicates removed; 2,196 kept.
    - Removed: py_classes 154, py_collections 142, pg_ddl_cascade 58, pg_txn_abort 50.
    - The other nine families are whole at 200.
- **Training started:** v49a on GPU 1 at 11:14:09 UTC. v49f, v49g and v49h start on GPUs 0, 2 and 3 as they free.

**Deviation from the V48/V47/V46 schedules.**
- The two V48 full readouts already running (v48w on GPU 2, v48s2 on GPU 3) finish.
- v46c_w50's quick (GPU 0) finishes.
- Every later V46–V48 readout (V47's full of v47b, V46c's remaining) waits behind V49's trainings.
- V47's full of v47a cannot run: its checkpoint was deleted.

## Note (2026-10-07 ~11:40 UTC): an infrastructure error of mine and its fix (no design change)

**What happened.**
- At ~11:12 I rewrote `v46/readout_job_v46.sh` in place to add m3val, fxe_family and fxe_app to the readout lists.
- Bash reads a running script through the same inode, so three readouts already executing it had their offsets moved.
- **v48s2's full readout** stopped with a syntax error at the end of its part a (11:33), rc −1, marked failed. No
  command ran from the moved offset.

**Fix.**
- The original bytes are back in place, same inode, so v48w's full and v46c_w50's quick finish normally.
- The new lists wait in `readout_job_v46.sh.new`. `v49/swap_readout_job.sh` installs them by an atomic rename (new
  inode) once those two readouts exit, before any V49 quick readout.
- **v48s2's full readout** is re-run when GPUs are idle, with the other deferred V46–V48 readouts. It cannot change
  (a): its quick guard rows are the full guard rows, and they already fail.

From now on, scripts that jobs are running are replaced only by an atomic rename.

## Addendum C (2026-10-07 ~12:18 UTC): memory fallback for a training arm (registered before any arm needs it)

If a V49 arm runs out of GPU memory again after its SEED+1 retry, it is rerun with **micro-batch 4 × gradient
accumulation 2** (`v49/train_conseq_v49.py`, `MICRO=4`): the registered SEED, the same 8 items per step in the same
order with the same option permutations, the same LR, steps, mix, data and JEPA weight; each micro-batch's loss is
scaled so the summed gradient is the batch-8 gradient (cross-entropy summed ÷ 8, the JEPA term weighted by the
micro-batch's share of the step's floor items), with one clip, optimizer and scheduler step per 8 items. Only the
floating-point order and the LoRA-dropout draws differ. A further OOM halves the micro-batch again (2 × 4). Every use
is recorded as a deviation in that arm's verdict.

## Note (2026-10-07 ~12:35 UTC): Addendum C in use, and the trainer every V49 retry runs (no design change)

- **v49g** ran out of memory again on its SEED+1 retry (12:17:47). The orchestrator, not yet changed, started a third
  batch-8 attempt (SEED 4) at 12:18:30, after Addendum C was hashed. I stopped it at 12:22 by its exact PID (moved to
  `v49/runs/v49g.stopped3`) and queued v49g for Addendum C: micro-batch 4 × accumulation 2 at SEED 2. **This is a
  deviation, to be recorded in v49g's verdict.**
- **v49h** ran out of memory on GPU 0 at ~12:23 (step ~45, beside systemone_v4's 1.3 GB). It gets the registered SEED+1
  retry on another GPU.
- **`v49/train_conseq_v49.py` was checked before use** (`v49/test_micro/`): a tiny random Qwen3.5 with Eikos-27B's
  architecture and tokenizer, float32, LoRA dropout 0, v49g's mix and data, 4 steps.
  - With MICRO unset, its step-0 gradient equals the V47 copy's exactly.
  - With MICRO 4, 2 and 1, the gradients differ from batch 8 by ≤ 8 × 10⁻⁷ (relative L2), and the logged losses agree to
    6 decimals.
  - A negative control with the wrong scale (cross-entropy averaged within each micro-batch) differs by 31–47%.
- **The V47 copy keeps the previous step's hidden states alive during the next step's forward:** the student's and the
  teacher's, all 65 layers. The V49 copy frees them. This changes no arithmetic, so **every V49 retry, the SEED+1 retry
  included, runs the V49 copy**; with MICRO unset it computes what the V47 copy computes. Arms already running keep the
  V47 copy.

## Note (2026-10-07 ~12:39 UTC): v49h also on Addendum C (no design change)

- v49h's SEED+1 retry (V49 trainer, batch 8, GPU 2) ran out of memory at 12:35:39, step ~20. Freeing the previous step's
  hidden states was not enough: the peak is inside a step.
- The orchestrator then applied Addendum C. Since 12:36:22, v49h runs micro-batch 4 × accumulation 2 at SEED 2. **This
  is a deviation, to be recorded in v49h's verdict.**
- **v49g and v49h now train the registered optimization (SEED 2, 8 items per step), up to floating-point order and
  LoRA-dropout draws.** v49a and v49f run as registered (V47 trainer, batch 8, SEED 2).
- **Micro-batch 4 is faster here:** v49g runs at 9.3 s per step against 11.4–15.3 for the batch-8 arms. Each micro-batch
  is padded only to its own longest item.

## Addendum D (2026-10-07 ~13:23 UTC): micro-batch at an arm's first OOM (before any V49 result)

**Why.**
- v49f ran out of memory at step ~500 of 900 at 13:20:53 (batch 8, SEED 2), losing ~1.75 h of training.
- v49g and v49h had each run out of memory twice at batch 8.
- Batch 8 is at the memory edge for every V49 mix with FX items, so a SEED+1 retry at batch 8 is likely to lose hours
  again.

**The new rule.**
- From now on, a V49 arm that runs out of memory is rerun at once with **micro-batch 4 × accumulation 2 at its
  registered SEED** (Addendum C's arithmetic).
- A further OOM halves the micro-batch again: 2 × 4, then 1 × 8. The SEED+1 retry at batch 8 is dropped.
- This keeps the registered optimization (SEED 2, the same 8 items per step) closer than SEED+1 does.

**Applied now.**
- v49f's SEED+1 retry (started 13:21:36) is stopped right after this hash, by its exact PID, and moved to
  `v49/runs/v49f.stopped2`.
- No V49 result exists yet. The deviation is recorded in v49f's verdict.

## Addendum E (2026-10-07 ~14:43 UTC): an image readout, reported (before any V49 image number exists)

**Why.** Ekbasis reads a state as text or as an image: the card says so, there is a vision tower, and the release eval
had image chains. No V45–V49 readout or gate contains an image item. The LoRA touches only the language-model layers,
but those layers read the image tokens too.

**What.** From now on, every V49 candidate that reaches the full readout is also read on images. **This is reported
only; it is not a V49 gate. Addendum 9 is unchanged for V49.**

**The readout.** The release eval's image scripts, with their items, metrics and settings. No new items.
- **Single step** (`/root/decis/conseq/image_eval.py`):
  - 120 items: 60 lamp worlds and 60 container worlds, from Random(303). Half are items where the actions change the
    answer.
  - Three prompts per item: the state in text; the state as an image; the final state as an image (can the picture be
    read).
  - Run with the adapter on and off.
  - Measured: accuracy on all items and on changed items. Each answer's confidence is also kept, for ECE.
- **Chains** (`/root/decis/conseq/image_chain.py`):
  - 60 chains: 30 per world, seeds 7000+i, 10–20 actions.
  - Measured: final-answer accuracy for a chain started from the text state, from the image read in a step of its own,
    and from the image read together with the first action. Also: whether the whole starting state is read right, and
    the share of variables read right.

**How.**
- Both run through transformers on one GPU with the API's decision rule (one prompt per question, the letter readout),
  for every model alike.
- The release eval ran the chains through vLLM on the merged w4a5. The w4a5 run here is checked against that run on
  the same items, and the adapter-off single-step answers against the stored release run.
- **Models:** w4a5 (the base); v48a_w50 (= Ekbasis-Skopos-27B) and v46b, as records; each V49 candidate at the full
  readout.
- **Reported:** every metric with its difference against w4a5 and a paired bootstrap CI (10,000 resamples; items, or
  chains, as the units).
- **When:** it runs on the first GPU a V49 training frees, held for it, before that GPU's next V49 readout.

## Note (2026-10-07 ~19:50 UTC): Addendum E's v48a_w50 record dropped (no design change)

On Caio's request ("focus forward, not on the previous Skopos"), relayed by the coordinator, v48a_w50's image readout,
one of Addendum E's records, is not run. Addendum E's other reads are unchanged: w4a5 (done), v46b and V49's
candidates at the full readout. v49f_w50, the current private Skopos, is read on GPU 2 as the coordinator asked.

## Note (2026-10-07 ~20:09 UTC): a scheduling deviation, V49's full readouts after V49b (no design change)

**What was stopped and why.** On the coordinator's order (Caio: focus forward), V49's raw full readouts were stopped by
their exact PIDs at 20:08: v49a (GPU 0) and v49f (GPU 3), started 20:06, and v49g (GPU 1), started 20:06:45. With
v49h, which had not started, they were deferred (`v46/defer.json`). Their partial folders were moved aside
(`v46/readout/<arm>.stopped_2008`).

**What runs instead.** The GPUs go to V49b, in this order:
1. the selection reads;
2. the fresh-set, full and image reads of the selected candidates;
3. V49's raw full readouts, for the record;
4. the kernel re-test.

**What does not change.**
- They are the same readouts, run later.
- V49's verdict is still computed by its registered rule, on the full readouts of the λ that `v49/val_choice.json`
  chose: raw for all four arms.
- If V49b selects a raw candidate, that candidate's full readout serves both plans.

**Also deferred.** The V49 image queue (Addendum E, V49's chosen candidates and v46b) was stopped before it started any
job. It restarts after V49b. v49f_w50's image read on GPU 2 continues.
