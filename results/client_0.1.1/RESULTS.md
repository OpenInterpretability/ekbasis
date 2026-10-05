# ekbasis client 0.1.1 (candidate): the git guard sees what it was blind to

Pre-registered in [SPEC.md](SPEC.md) (sha256 `b31c0aa9…d1d0a`, 2026-10-04 23:58 BRT) before any code change. The model
is unchanged (Ekbasis-27B release weights, w4a5 bf16, served by serve.py 1.3); only the client changes. **Not
published**: publishing is Caio's decision (commands at the end).

## What changed

**Facts** (in the state the client shows the model, only when they exist or a command could touch them; every other
line is byte-identical to 0.1.0, checked on 340 descriptions): ignored files, for `clean -x/-X`, `stash -a`,
`sparse-checkout`, or a target ref that tracks the same path; untracked or ignored files that a target ref also has,
with "the same" or "different content"; linked worktrees and submodules with their own `git status`; whether a
conflicted file still has conflict markers or was resolved by hand; cherry-pick, revert and am sessions, which 0.1.0
did not name (it called an am session a rebase); ahead/behind the upstream, and `pull.rebase`/`pull.ff`, for `pull` and
`push`.

**Notes**: one plain-text git rule per command form that needs it, added after the command list. Notes cover only forms
the training data did not cover (`switch -f`, `reset --merge <commit>`, `rebase --abort`, `clean -x`, `worktree remove`,
`submodule update`, `git pull` with no mode, ...), plus two triggered by the facts (an untracked file in the way, an
ignored file a target would overwrite). Trained command forms get no note, so their prompts are unchanged. API: `check(...,
facts=True, notes=True)` (False/False reproduces 0.1.0); `repo_state()` keeps its signature; new `inspect()`.

## Protocol

1. Dev = the 507 git_wild scenarios. Every configuration reads the same throwaway repository before the commands run,
   and the truth comes from running them (git 2.43).
   - **Pass 1**: 0.1.0 (C0), facts (C1), facts + notes (C2), notes only (C3).
   - **Pass 2**: three wordings were fixed after pass 1 (the `--abort`/`--skip` note raised false alarms on unresolved
     conflicts; a merge was wrongly taken to overwrite an untracked file; same/different content). Pass 2 compared
     where the notes go: after the preamble, as a state line, or after the commands.
2. **Decision rule fixed in the SPEC** (notes go in if C2 beats C1 with false alarms ≤ C0 + 2 points): met in both
   passes. Placement: after the commands, the most work-losing items flagged (120/128) with false alarms below 0.1.0's.
3. **Frozen** 2026-10-05 00:25 BRT ([FROZEN.sha256](FROZEN.sha256)).
4. Then the confirmation set was generated: [confirm_wild.py](scripts/confirm_wild.py), built by
   [make_confirm_wild.py](scripts/make_confirm_wild.py) from git_wild.py with every replacement asserted.
   - Another project (billing-api) with other files, branches and ignored paths, and a new seed.
   - The 67 git_wild command types plus 8 it does not have: `checkout -m`, `submodule deinit [-f]`, `clean -fdx -e`,
     `switch -`, `stash pop` onto a re-created file, `branch -D`/`checkout` of a branch busy in a worktree,
     `reset --hard <ref>` and `merge` over an ignored file.
   - 334 scenarios. A truth-only dry pass found 0 setup errors, and **one** model pass found 0 unstable truths.

## Confirmation set (334 scenarios, 87 lose work; 0.1.0 and 0.1.1 on the same repositories)

| | 0.1.0 | **0.1.1** |
|---|---|---|
| Work-losing flagged (P(lost) ≥ 0.2), all | 52/87 (59.8%) | **76/87 (87.4%)** |
| … where the state shows the deciding fact | 41/49 (83.7%) | **46/49 (93.9%)** |
| … where 0.1.0's state hid it | 11/38 (28.9%) | **30/38 (79.0%)** |
| False alarms at 0.2 | 22/247 (8.9%) | **20/247 (8.1%)** |
| `lost` right at 0.5 | 275/334 (82.3%) | 305/334 (91.3%) |
| `fails` right, per command | 323/397 (81.4%) | 361/397 (90.9%) |
| `in_progress` right | 307/324 (94.8%) | 309/324 (95.4%) |
| Final branch right | 129/140 (92.1%) | 131/140 (93.6%) |
| Wrong `lost` decisions made at confidence ≥ 0.9 | 49 of 59 | 22 of 29 |
| Wrong `fails` decisions made at confidence ≥ 0.9 | 50 of 74 | 23 of 36 |
| Median seconds per check (4 replicas, shared) | 2.5 | 2.8 |

- A keyword list of destructive commands flags 61/87 (70.1%) with 69/247 (27.9%) false alarms.
- **Per decision:** 69 are right with 0.1.1 and wrong with 0.1.0; 5 go the other way (listed below).
- **On the 8 new command types:** 69/84 decisions right, against 60/84.
- **Errors are fewer but still mostly confident:** the "check when sure" advice stands.

**Criteria (SPEC):**
1. Hidden ≥ 60% and ≥ C0 + 30 points: 79.0%, +50.1 points. **Pass.**
2. Visible ≥ C0: 93.9% against 83.7%. **Pass.**
3. False alarms ≤ C0 + 2 points: 8.1% against 8.9%. **Pass.**
4. Release checks: **pass** (below).

Per family (work-losing flagged · false alarms · `fails` right), 0.1.0 → 0.1.1:

| Family | Work-losing flagged | False alarms | `fails` right |
|---|---|---|---|
| Ignored files | 2/22 → 14/22 | 2/26 → 2/26 | 54/58 → 57/58 |
| Linked worktree | 0/2 → 2/2 | 0/20 → 0/20 | 10/22 → 20/22 |
| Submodule | 2/4 → 4/4 | 1/10 → 2/10 | 10/14 → 12/14 |
| Conflict state | 9/16 → 14/16 | 8/30 → 6/30 | 32/50 → 45/50 |
| Force switch/checkout | 3/4 → 4/4 | — | 11/14 → 14/14 |
| Reset modes | 5/7 → 7/7 | 2/11 → 1/11 | 18/22 → 20/22 |
| Detach/orphan | — | — | 7/15 → 9/15 |
| mv/rm | — | — | 11/16 → 13/16 |
| Remote, stash, clean, everything else | about unchanged | | |

## Release checks (criterion 4)

The prompts of the release evaluation are pre-rendered in the training layout, so the facts cannot reach them. The
candidate's notes were applied to them exactly as the client would: **0 of 13,985 prompts change**, since trained
command forms get no note, and every prompt round-trips through the parser. The rerun therefore measures only server
noise:
- git3, 3,105 questions: 96.55% (published 96.62%).
- Larger guard set, known part: 827/863 flagged, 37 false alarms (served release: 828/37).
- Larger guard set, held part: 766/799 flagged, 49 false alarms (767/49).
- Files: [release_prompts_report.json](release_prompts_report.json).

## Real use (reported, not gating)

The 36 scenarios of `conseq/eval_handoff/realuse` were run on our `code_eikos` repository as it is now: 7 modified and
347 untracked files. `openinterp_web` is clean today, and its scenarios need local changes. The truth was recomputed in
fresh copies.
- **0.1.0:** 14/14 work-losing caught, 0/22 false alarms, `fails` 46/48.
- **0.1.1:** 14/14, 0/22, 47/48. `git switch --discard-changes` is no longer predicted to fail.

## What still fails (0.1.1, confirmation set)

- **Ignored file overwritten by a ref that tracks the same path:** `checkout <branch>`, `merge`, `reset --hard <ref>`,
  6 of 6 missed. The state names the file ("ignored; also committed on X, with different content") and the note says it
  is overwritten, yet the model keeps its trained answer for these command forms. Advice in the docs: run
  `git status --ignored` before switching to such a branch.
- `sparse-checkout set` deleting ignored files: 2/2 missed.
- `rebase --abort` after `git add` of the resolution: 2/2 missed, at 0.11–0.16.
- `restore --staged` when index and working tree differ: 1 miss.
- `stash -a` then `clean -fdx`: flagged, though nothing is lost. The guard does not separate `-u` from `-a` here.
- **Habit false alarms, as in 0.1.0:**
  - `commit -am` then `reset --hard` in one check;
  - `git rm` on a changed file (fails);
  - `stash clear`/`drop`/`pop stash@{1}` after an apply;
  - `checkout-index -a`;
  - `rm -rf <dir>` then `checkout -- <dir>`;
  - `merge --abort` and `reset --hard` with unresolved conflicts;
  - `checkout --ours` then `add` and `commit`.
- **New mistakes against 0.1.0 (5 decisions):**
  - `git pull --rebase` on a dirty tree and `git pull` stopped by overlapping local changes are predicted to work. The
    pull note talks about diverged branches, not local changes.
  - `git checkout HEAD~1` when a changed file differs in that commit is predicted to work. The note states that case,
    but the model does not apply it.
  - `submodule deinit` without `-f` on a dirty submodule is flagged as losing work, though git refuses.
  - One `stash pop` in a four-command sequence.
- **Out of scope:** committed work (`branch -D`, `push --force`, `reset --hard origin/main`): 4 of 21 such scenarios
  flagged.
- **One note is inaccurate:** "-e <pattern> keeps the files that match" is true for `clean -x` but not for `clean -X`,
  where `-e` adds an ignore pattern and the file is deleted. The guard flagged that case anyway (0.1.1 caught
  `clean -fdX -e .env.local` in both instances). Fix the wording in a later version.

## Recommendation

**Publish.** All four pre-registered criteria pass, with large margins on what the guard is for: work-losing flagged
from 59.8% to 87.4% on unseen scenarios, with fewer false alarms. Nothing changes for trained command forms, and real
use on our repository shows no regression.

The publication should say what still fails (the Limits sections in the copy are updated) and keep "check when sure".
Worth a follow-up:
- a pull note that covers local changes;
- the `clean -X -e` wording;
- `submodule deinit`;
- the ignored-file-overwrite case, which no prompt change fixed. That one is a training-data gap.

## Files

In this folder: [SPEC.md](SPEC.md) (and its hash), [FROZEN.sha256](FROZEN.sha256) (the client files at the freeze;
paths relative to the research folder), the confirmation set's items, truth-only pass and results
(`confirm_items.jsonl`, `confirm_dry.jsonl`, `confirm_results.jsonl`, `confirm_summary.json`, `confirm_table.txt`), the
dev passes' summaries, `release_prompts_report.json`, and in [scripts/](scripts/) the generators (`git_wild.py`, the
capability map's; `make_confirm_wild.py` and the `confirm_wild.py` it builds), the runner (`cn_run.py`), the analysis
(`cn_analyze.py`), the release-prompt check (`cn_floor.py`) and the 0.1.0 equivalence test (`test_equivalence.py`).
Recompute the confirmation numbers with `python3 scripts/cn_analyze.py confirm_results.jsonl out.json --ref
confirm_dry.jsonl`. The dev passes' item-level files (git_wild's 507 items × 4–5 configurations) and the real-use files
(they name files of our working tree) are not included.
