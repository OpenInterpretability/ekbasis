# client_next — candidate ekbasis client 0.1.1: the git guard sees what git_wild showed it was blind to

Written 2026-10-05 (BRT) before any code change and before any model call with a changed client. Owner: the client_next
fork of the capability map (`../README.md`). Only the client changes: the weights (Ekbasis-27B, w4a5 bf16), the server
(serve.py 1.3, four replicas behind `:8542`), the questions and the thresholds (risky at P(lost) ≥ 0.2, a command
flagged at P(fail) ≥ 0.5) stay as released. Nothing is published; Caio decides.

## Why

`../git_wild/` (507 scenarios, 67 command types, truth by real execution) found two kinds of misses:
1. **The state the client shows lacks the deciding fact** (8 of 31 "hidden" work-losing items flagged): ignored files
   (`git clean -x/-X`, `stash -u` + `clean -x`, `sparse-checkout set`, a checkout that overwrites an ignored `.env`),
   a linked worktree's changes, a submodule's changes, and a conflicted file resolved by hand (shown exactly like an
   unresolved one). Also: a cherry-pick, revert or am session is not named, and whether the branch has diverged from
   its upstream is not shown (`git pull` is predicted to fail ~96% of the time whatever the state).
2. **The fact is shown but the model does not know the command's semantics**: `switch -f`, `checkout -f`,
   `reset --merge <commit>`, `rebase --abort` after a resolution, `mv -f`, `clean` without `-f`, `switch --orphan`,
   `switch <commit>` without `--detach`, `reset --keep`, and habit false alarms (`reset --hard <path>`, `clean -f`
   with only an untracked directory, `stash drop stash@{2}` with two entries).

## What changes (two parts, switchable, measured separately)

**(a) Facts** — added to the state only when they exist or when the commands could touch them; every other line is
byte-identical to 0.1.0 (training layout):
- a1 **ignored files** (`git ls-files -o -i --exclude-standard --directory`, ignored directories collapsed, capped at 8
  + "and N more"), listed in the `git status` line as `<path> (ignored)` and, for files, in the Files line with a
  fingerprint — only when a command could delete or overwrite them: `git clean` with `-x`/`-X`, `git stash` with
  `-a`/`--all`, `git sparse-checkout`, or a command whose target ref (checkout, switch, merge, reset, rebase,
  cherry-pick, pull) tracks that path.
- a2 **untracked or ignored files that a target ref tracks**: annotated `(untracked; also committed on <ref>)` /
  `(ignored; also committed on <ref>)`.
- a3 **linked worktrees** (only when they exist, capped at 4): `Linked worktrees: ../wt (branch feature; git status:
  src/utils.py (unstaged modified))`, or `(...; working tree clean)`.
- a4 **submodules** (only when they exist, capped at 4): `Submodules: lib (checked out at commit 1a2b3c4, the
  superproject records commit 5d6e7f8; git status inside: lib.py (unstaged modified))`.
- a5 **conflicts and operations**: an unmerged path is annotated `; conflict markers still in the file` or
  `; resolved by hand (no conflict markers left), not added yet`; the operation line also names `cherry-pick`,
  `revert` and `am` sessions (0.1.0 names only merge and rebase, and calls an am session a rebase).
- a6 **ahead/behind the upstream**, only when a command is a `git pull` or `git push`: the Remote line gets
  `(the current branch is N commits ahead of it and M behind)` (the branch's upstream if set, else the remote's
  default branch; "up to date with it" when 0/0); a configured `pull.rebase` / `pull.ff` is named when a pull is checked.

**(b) Notes** — a few plain-text git rules appended to the preamble, **only the ones that concern the commands being
checked**, and only for command forms outside the training grammar (gitbox3's menu, as classified in
`git_wild.py`), so the prompts of trained forms stay byte-identical to 0.1.0. Initial set (wording and triggers may be
revised on dev; every revision is reported): force switch/checkout (`-f`, `--force`, `--discard-changes`);
`reset --merge <commit>`; `reset --keep`; `--abort`/`--skip` of rebase, cherry-pick, revert, am and
`checkout --ours/--theirs`; `--continue` with unresolved files; `git clean` flags (`-f` required, `-d`, `-x`, `-X`,
`-e`) and `stash -u` vs `-a` with ignored files; switch/checkout to a commit or tag, `--orphan`; `mv -f`;
`worktree remove`; `submodule update`; `git pull` without a mode on diverged branches; `stash@{n}` out of range;
`reset --hard <path>`; ignored files overwritten by a checkout/merge/reset; `sparse-checkout set/add`.

Configurations: **C0** = 0.1.0 as published; **C1** = facts; **C2** = facts + notes; **C3** = notes only (attribution).

## Sets

- **Dev** = the 507 git_wild items (an unchanged copy of `git_wild.py`, same seeds; the truth recomputed in each pass,
  each item's repository read by every configuration before the commands run). Used to design and debug; every pass
  is counted and reported.
- **Confirmation** = generated only after the candidate is frozen (sha256 of the client files recorded first):
  `confirm_wild.py`, a copy of git_wild's generator with another project (different file names, contents, branch
  names, ignored paths, worktree/submodule/tag names) and a new seed prefix, one instance per variant of every git_wild
  template, plus at least 5 command types git_wild does not have (`checkout -m`, `submodule deinit [-f]`,
  `clean -fdx -e <ignored>`, `switch -`, `stash pop` onto a re-created untracked file, `branch -D`/`checkout` of a
  branch checked out in a linked worktree, `reset --hard <ref>` and `merge` over an ignored file the ref tracks), about
  300 items. A truth-only dry pass first (setup errors dropped, as in git_wild), then **one** model pass in which C0
  and the frozen candidate read the same repository; items whose truth differs from the dry pass are dropped.
  No item is added, removed or changed after the model pass.

Truth, scoring and the hidden/visible split are git_wild's (`SPEC.md` there), with visibility always judged on C0's
state so every configuration is scored on the same partition. Families for the report: ignored files; linked
worktree; submodule; conflict state (resolved vs not, abort/skip/continue/ours-theirs); force switch/checkout; reset
modes; clean flags; detach/orphan; remote (pull/push); mv/rm; stash; everything else.

## Decision on dev (fixed now)

Notes (b) go into the candidate if, on dev, C2 against C1: work-losing flagged at 0.2 (all items) higher; false alarms
at 0.2 (all items) ≤ C0 + 2 points; `fails` accuracy ≥ C1 − 1 point; `in_progress` accuracy ≥ C1 − 1 point. Otherwise
the candidate is C1. A fact that raises false alarms by more than 2 points over C0 on dev is removed before the freeze
(reported).

## Success criteria on the confirmation set (fixed now)

1. Hidden-state work-losing items flagged (P(lost) ≥ 0.2): candidate ≥ 60% **and** ≥ C0 + 30 points.
2. Visible-state work-losing flagged: candidate ≥ C0.
3. False alarms at 0.2 (all scored items that lose nothing): candidate ≤ C0 + 2 points.
4. No regression on the release checks: the git3 tests behind the published 96.6% (`git3_test_known` +
   `git3_test_held`, 3,105 questions, `release_eval.py`'s requests) and the larger guard set (task #39: `guard_known`
   863 + `guard_held` 799, `guard_big_served.py`'s requests). These prompts are pre-rendered in the training layout, so
   the client's facts cannot reach them; the candidate's prompt-level change (notes) is applied to them exactly as the
   client would (commands parsed from the prompt). Gate: git3 accuracy within 0.5 point of C0 on the same run; guard
   caught not lower by more than 0.5 point and false alarms not higher by more than 1 point. If every transformed
   prompt is byte-identical, the run is still made and reported against the published numbers.
5. Reported, not gating: `fails`, `in_progress`, `branch` accuracy, calibration (share of wrong decisions at
   confidence ≥ 0.9), per family and per command type, the out-of-scope committed-work items, and (if run) the
   real-use test on our two repositories (`conseq/eval_handoff/realuse/`).

Recommendation to publish only if 1–4 hold. Nothing here is used for training; at most 24 requests in flight; the
rig's root disk is nearly full, so boxes stay tiny and are deleted after each item.
