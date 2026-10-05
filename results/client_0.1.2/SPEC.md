# Client 0.1.2 candidate: SPEC

Written 2026-10-05 12:42 BRT, before any model run of 0.1.2. Base: the public client 0.1.1 (GitHub b6682c2), copied to
`client_012/ekbasis/`; `release_clean/` is untouched. Same model weights and server; only the client changes. Nothing is
published, pushed or used for training.

## What changes

1. **Rule recap (opt-in).** `prompts.recap(question, rules)`, `recap_all`, `simulate(..., recap=...)`,
   `ekbasis predict --recap / --recap-rule`: the rule that decides the answer, repeated right before the question in the
   wording measured in the capability map (`habit_vs_rule` M2: "Remember this rule: …"; Hanoi's size rule 0/8 → 8/8,
   no right answer broken).
2. **Compare in code.** `simulate.threshold(...)` follows a quantity with the released `simulate` and decides
   `quantity <op> limit` in code (`when="end" | "ever" | "before_last"`), returning the value, the decision, the trace
   and the chain confidence; `prompts.number` builds numeric questions. From `accumulation`: carried totals 98–100%
   right, comparisons near the limit 46%, compare in code 99.0%.
3. **Shell guard prototype.** `ekbasis.shell.check`, `ekbasis shell-check`, the hook's opt-in `EKBASIS_SHELL_GUARD=1`.
   State: a listing of the paths a line could touch and their parents (names, types, sizes, ages, links and targets,
   hidden names), never file contents (an HMAC fingerprint per file, keyed anew per check), plus facts the shell decides
   (glob expansion here, unquoted words split at spaces, other files with the same content). Bash notes, one sentence
   each, only when a line needs them: `>` truncation of a file the line also reads, `;`/`||` sequencing after `cd`,
   rsync trailing slash and --delete, `cp -r SRC/.`, a link with a trailing slash, unquoted spaces, unquoted patterns in
   `find -name`, zsh no-match, noclobber, commands that refuse folders, `-n`/--no-clobber exit status, xargs, `tar -x`.
   Questions: content lost for good (p_lost), each line fails (p_fail); exit codes as `git-check`.
4. **Fail closed** (requested by the coordinator from the security review, 2026-10-05). When a command cannot be parsed,
   the repository or folder cannot be read, the server is unreachable or does not answer in time, the guard returns
   "cannot judge", treated as risky: CLI exit 3 (`--fail-open` → 0 with a warning), `CannotJudge` in Python (or a
   shell verdict with `cannot_judge=True`), and the Claude Code hook asks for confirmation (JSON, exit 0, since an exit
   code other than 2 does not block) unless `EKBASIS_FAIL_OPEN=1`. The hook also cannot judge lines it does not follow
   (a non-leading `cd`, `pushd`/`popd`, subshells, nested shells, `xargs git`, `GIT_DIR=`, variables in a git command
   other than a commit message), git `-C`/`--git-dir`/`--work-tree` and git aliases, and enforces its own deadline
   (`EKBASIS_HOOK_DEADLINE`, default 25 s, below the hook's 30 s timeout).
5. **Docs** (same request): README, SECURITY.md and the hook's docs say plainly that the guard is a warning layer that
   can be wrong, not a security boundary, to be used with confirmations, backups and least privilege.

**Defaults unchanged.** With the defaults, every prompt 0.1.1 sends is unchanged: `world_state`, `yes_no`, `choice`,
`git.check`'s requests (description, notes, prompt, questions) on ten repository situations × 25 command lists, the
0.1.0 description, and `simulate` without recap (`eval/release_equivalence.py`, CPU only). A code diff shows that
`git_state`, `git_notes` and `inspect` are untouched; the release evaluation's prompts are pre-rendered by the trainer,
so they cannot change.

## Questions

- **Q1 (shell).** With a listing that never shows contents, facts and notes, does the released model foresee content
  loss and failures of shell lines on command forms the guard was not designed on?
- **Q2 (recap).** On fresh items, does recapping the deciding rule fix answers without breaking right ones?
- **Q3 (compare in code).** On fresh items, does `threshold()` reproduce the accumulation gain?
- **Q4.** Defaults identical (above); fail-closed behaviour as specified (unit tests).

## Data

**Dev (design; looked at and iterated on):**
- Shell: `capability/shell_wild/items.jsonl`, 408 scenarios, 84 forms, truth from bash. In the capability map these
  were asked with the full file contents shown; the guard never shows contents, so that run is context, not a
  criterion.
- Recap: habit_vs_rule's 90 archetypes at variants 8–11 (the published run used 0–7) × familiar/invented ×
  agrees/contradicts, and rules_stress's rule-kind factor (14 levels, base and flip) with seed 77012501 (published:
  20261005); any text identical to a published item is dropped.
- Threshold: accumulation items with seed 77012502 (published: 20261005); identical items dropped.

**Confirmation (shell only; generated only after the freeze, run once):** `eval/shell_confirm_gen.py`, 28 families, 46
command forms of which none is among shell_wild's 84 (two are labeled controls with the same command as a shell_wild
form: `tar -xzf` and `rsync -a SRC/ DEST/`), seed 77012503, new names and contents, about 290 scenarios, each built and
run twice in bash on the rig (Linux; the truth as in shell_wild: a line of content that was in some file before and is
in no file after; exit codes; questions unstable between the two runs dropped). Its code was written before any model
run (sha256 `130a74eb3c357049…`); the bash notes were not written, and will not be changed, for its forms. Recap and
threshold get no separate confirmation in this round: the decision is only whether to document them as opt-in
recipes; making recap a default would need its own confirmation.

## Metrics and baselines (shell)

`lost`: accuracy at 0.5; recall and false alarms at the guard's threshold 0.2 (and 0.5); recall on judged items only.
`fails`: accuracy at 0.5 per command line. Share of errors with confidence ≥ 0.9. Cannot-judge count. Content leaks:
any line of any file's content found in a prompt. Baselines on the same scenarios: always "no", shell_wild's two keyword
lists; the guard without notes (`no_notes`); dev only, the capability map's own run.

## Success criteria (fixed now)

Shell guard, confirmation set, `notes` condition:
- **C1** zero content leaks in every prompt, dev and confirmation (hard requirement).
- **C2** `lost` accuracy at 0.5 ≥ 85% and ≥ 5 points above the best of always-"no" and the two keyword lists.
- **C3** recall of content loss at 0.2 ≥ 85% with false alarms at 0.2 ≤ 15%.
- **C4** `fails` accuracy at 0.5 ≥ 85%.
- **C5** cannot-judge on 0 scenarios (the set has no variables, subshells or nested shells by construction).
- Reported without a threshold: notes vs no notes; errors at confidence ≥ 0.9.
If C2–C4 fail, the shell guard stays a prototype in the docs with its measured numbers and no further claim.

Recap (dev, fresh items):
- **R1** no harm: items right without recap and wrong with the `relevant` recap ≤ 1% of the items, habit and
  rules_stress separately.
- **R2** reported: fixes, accuracy by cell, Hanoi-like prohibitions.

Threshold (dev, fresh items):
- **T1** `T` accuracy ≥ 97% overall and ≥ 95% on the boundary items (d ∈ {−1, 0}).
- **T2** `T` ≥ `B` + 5 points on the boundary.

No regression and fail closed:
- **N1** `eval/release_equivalence.py` passes and every package test passes.
- **F1** the four cases (unparseable command, missing directory, server down, timeout) give "cannot judge" (exit 3, the
  hook asks) and the opt-outs work: `tests/test_fail_closed.py`.
- **F2** the warning-layer statement is in README, SECURITY.md and the hook's docs.

## Freeze

After the dev runs, and only design changes justified by dev failures, `python3 eval/freeze.py` writes
`FROZEN.sha256` (sha256 of every module of the package). The confirmation generator and the confirmation run refuse to
start without it, or if the code changed since. A change after the freeze means a new freeze and a new confirmation
seed, reported as such.

## Limits

One wording per question. Measured on Linux with bash and GNU tools only; macOS (BSD tools) and zsh are untested. The
guard does not see what programs and scripts do to files, nor permissions and ownership. The truth "content lost" is
line-based (shell_wild's definition), so binary content is not covered. Recap was measured only on habit and
rules_stress worlds, in one wording.

Hashes of the evaluation scripts at writing time: shell_confirm_gen.py `130a74eb3c357049`, shell_run.py
`1a4c14c366b7c90a`, analyze_shell.py `90474fae906d12b2`, recap_dev.py `5024df372d0fac82`, threshold_dev.py
`d704271e0b74936b`. The vendored generators and their originals' hashes: `eval/vendor/PROVENANCE.sha256`,
`eval/vendor/ORIGINALS.txt` (the only edits: a seed and an output path read from the environment).
