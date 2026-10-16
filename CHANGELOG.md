# Changelog

<!-- skopos:results -->
## Results — 2026-10-16

### Added
- **Jev against Ekbasis-27B and Ekbasis-Skopos-27B** (not pre-registered, measured 2026-10-16): TypeSafe AI's
  general-purpose evaluator, zero-shot, on the release protocol and the hosted scorecard's suites, next to the published
  per-item predictions; with every per-item answer and a script that reproduces the numbers
  ([results_skopos/jev_comparison/](results_skopos/jev_comparison/METHOD.md), a section of
  [RELEASE_EVAL_SKOPOS.md](RELEASE_EVAL_SKOPOS.md)).
- **Addendum A7** (registered before any A7 request): confident errors with every option's probability on the 15,008
  items, Ekbasis-Skopos-27B INT4 against Ekbasis-27B INT4, raw and at each build's calibrated temperature; its
  prediction held in every piece, with and without the flagged items; the bf16 part was not run
  ([results_skopos/a7/](results_skopos/a7/ce_a7.json), a section of [RELEASE_EVAL_SKOPOS.md](RELEASE_EVAL_SKOPOS.md)).

<!-- /skopos:results -->

<!-- skopos:switch -->
## Hosted API — 2026-10-16

### Changed
- Served model changed: the hosted API serves `ekbasis-skopos-27b-int4-v1.3` since 2026-10-16 14:29 UTC — on release
  day, with less notice than the 14 days the model-change policy promises (owner decision,
  [results_skopos/prelaunch/RELEASE_DECISION.md](results_skopos/prelaunch/RELEASE_DECISION.md)); Ekbasis-27B's weights
  stay public. The prompt, readout, API, fields and client are the same; `calibrated.temperature` is 1.67 instead of
  1.55.

<!-- /skopos:switch -->

<!-- skopos:entry -->
## Ekbasis-Skopos-27B (model) — 2026-10-16

### Added
- **Ekbasis-Skopos-27B, the recommended model** ([card](https://huggingface.co/caiovicentino1/Ekbasis-Skopos-27B); bf16,
  FP8 and INT4 builds; MLX after its test on an Apple-silicon Mac): Ekbasis-27B trained further on executed shell, git,
  SQLite, PostgreSQL and Python scenarios. Against Ekbasis-27B on the same items: the git guard raises fewer false
  alarms on the held-out command types, 26/799 instead of 49/799 (paired McNemar p = 5.6 × 10⁻⁶; these command types are
  held out of the git sandbox's training rows but appear in Skopos' factory rows), and flags as many work-losing
  commands; on the known types, 27 instead of 37 of 863 is within chance. On 3,014 fresh answers of never-trained world
  families the actions change, +1.6 points [+0.7, +2.5]: the pre-registered release read failed this criterion on
  `ftest_family`, and a confirmation registered after that result (before any fresh item existed), by trainer readout,
  did not confirm the loss. Its largest gains are in-distribution (the generators it was trained on), and in world
  families it never saw more of its errors come with confidence ≥ 0.9 (4.49 vs 3.75 per 100). The client, the API and
  the prompts are unchanged: serve the new weights with their own `serve.py`, or keep Ekbasis-27B. `ekbasis.verify`'s
  certified mode, certified on Ekbasis-27B, carried over to Skopos INT4 in a pre-registered check (7 errors among 927
  accepted answers; [docs/VERIFY.md](docs/VERIFY.md)). A pre-launch release blocker is declared: on paraphrased short
  checks it is right on 113 of 120 against Ekbasis-27B's 117 (−3.3 points, paired 95% CI [−6.7, −0.8]), so the
  pre-registered rule fired; the exact test on the 4 discordant items does not reject (p = 0.125), and Ekbasis-27B
  re-run on the same machine reproduced its published answers (240/240) ([release
  decision](results_skopos/prelaunch/RELEASE_DECISION.md)). Hosted API: it serves Ekbasis-Skopos-27B-INT4 since
  2026-10-16, the release day, with less notice than its model-change policy promises (the entry above). Its evaluation,
  with its per-item predictions and pre-registrations: [RELEASE_EVAL_SKOPOS.md](RELEASE_EVAL_SKOPOS.md),
  [results_skopos/](results_skopos/README.md), [prereg_skopos/](prereg_skopos/PREREG_sha256.txt); its training code:
  [training/skopos/](training/skopos/README.md); the generators behind every training kind and evaluation set, as they
  ran: [generators/](generators/README.md).

<!-- /skopos:entry -->

## [0.1.41] — 2026-10-15

### Added
- **Calibrated probabilities, as an additive field.** The hosted API now returns, next to every answer's raw
  probabilities, the same answer at a temperature fit on held-out validation (`"calibrated": {"temperature",
  "confidence", "probability" | "probabilities"}`); read them as frequencies. `Answer.calibrated` (Python) and
  `answer.calibrated` (TypeScript SDK 0.2.5) expose it; `None`/absent on servers that do not send it. The plain fields
  are unchanged and every built-in threshold (`LOOK_BELOW`, `lost_threshold`, the monitor hook) still reads the raw
  probabilities, so no decision of this client changes. A global switch was not made because thresholds in installed
  clients would shift (the pre-registered test of 3 October, `results_v42/recalibration/`).

## [0.1.40] — 2026-10-14

### Added
- **`ekbasis-monitor-hook`: watch an agent in Claude Code.** A PreToolUse hook for every tool that can change
  something (reads are skipped): it asks the three MONITOR questions (`monitor()`) about the user's last message, the
  agent's last five calls and the call about to run, and asks you to confirm at 0.9 or more
  (`EKBASIS_MONITOR_THRESHOLD`). `EKBASIS_MONITOR_MODE` ask (default), deny or log (never blocks; local JSONL). Fails
  open, as an extra layer (`EKBASIS_MONITOR_FAIL_CLOSED=1` asks). In the Claude Code plugin it is a second PreToolUse
  hook, off until `EKBASIS_MONITOR=1`, and when off it answers before starting Python.

## [0.1.39] — 2026-10-14

### Added
- **`monitor()` and three MONITOR questions — `security`, `sabotage`, `off_task` — for watching an agent that may act
  against the user** (exfiltrate a secret, switch off a check or a test, plant code that misbehaves later), worded
  exactly as in our pre-registered adversarial-agent study. Plain yes/no questions about the user's task at the top
  of the state; never in the default `harms()` (still the four presets); name them in `harms(...)`, in
  `ekbasis plan-check --harm security`, or take all three with `monitor()`. `plan-check` asks for `--request` with
  them, as with the presets. TypeScript SDK 0.2.4: `MONITOR`, `monitor()`, same wording (a test checks it).

## [0.1.38] — 2026-10-13

### Added
- **`ekbasis plan-check --cases FILE`: test a rules file on known cases.** One JSON object per line with the state,
  the request, the actions and what must happen (`"ok"`, `"stop"` or `{"stop_by": N}`): past incidents must stop in
  time, routine plans must pass. It prints each case (`PASS`, `MISS`, `LATE`, `FALSE ALARM`, `CANNOT`) with the number
  that decided it, then how many plans stopped in time and how many passed. Exit 0 when every case comes out as
  expected, 2 when not, 3 when a case could not be judged. `--compare FILE` saves the results and marks, on the next
  run, every case whose decision changed (a stop that is now only "unsure" counts). An example with three incidents
  and three routine plans on a Kubernetes cluster is in `examples/plan-cases` (6/6 on the hosted API, 10 requests).

### Changed
- **`plan-check` says what is at stake.** A stop lists each harm it foresaw in plain words with its probability
  (`97%  a serving service goes down`), instead of the preset names; a stop for uncertainty gives the confidence and
  the harm closest to yes. `--json` is unchanged.
- The README starts with where to start: `plan-check` with a rules file for batches of production changes, the hook
  for git. A new example, `examples/plan-check-servers`, checks `ssh` and `kill` commands: they are judged from what
  the rules and the state say about what runs where and who depends on it.

## [0.1.37] — 2026-10-13

### Changed
- **The run on a copy is on by default** (the git guard, `git-check` and the Claude Code hook), where it is cheap: the
  whole run must fit in 8 s, or the model decides as before; a work tree of more than 20,000 entries (a large
  node_modules) or, without clones, more than 128 MB is left to the model without trying. `EKBASIS_GIT_COPY=0` turns it
  off, `=1` (or `git-check --copy`) forces it without the time limit. Measured on real repositories: 0.9-3 s, exact; a
  repository with a large node_modules goes to the model in under a second.
- **Clones across disks:** a clone only works within one file system, so a repository on an external drive is now
  copied next to itself (a hidden folder, removed afterwards, in the background) instead of failing to the model.
- **Chain mode advice is on by default** with the shell guard (`EKBASIS_CHAIN=0` turns it off); it never changes a
  decision. The shell guard itself stays opt-in (`EKBASIS_SHELL_GUARD=1`): in a real terminal it asked 10.6 times per 100
  calls, most without a reason, and a guard that asks too often teaches people to click through.

### Fixed
- The Claude Code hook never ran the copy (0.1.33-0.1.36, with `EKBASIS_GIT_COPY=1`): it took the `true` that replaces
  each git command in the line's shell part for another command. A line of git commands only now runs on the copy.

## [0.1.36] — 2026-10-13

### Added
- **Update notice.** The hosted API now sends the latest published client versions (`X-Ekbasis-Latest-Python`,
  `X-Ekbasis-Latest-Js`). When yours is older, the client says so on stderr, at most once a day (never on stdout, so
  `--json` output and the hook are unchanged): `ekbasis 0.1.37 is available (you have 0.1.36): pip install -U ekbasis`.
  `EKBASIS_NO_UPDATE_CHECK=1` turns it off. TypeScript SDK 0.2.3: the same, once per process, on the console.

## [0.1.35] — 2026-10-13

### Fixed
- **The run on a copy is fast.** 0.1.34's lost-work comparison started one git process per file and per branch or tag:
  on a repository of ~1,200 files it took 130 s. It now works on blob ids with a few batched git calls (one tree
  listing per ref, one `hash-object --stdin-paths`, one `cat-file --batch`): 2.1 s on the same repository. Same
  results: re-validated on 400 new generated scenarios, failures 616 of 616 and lost work 300 of 300 agree with the
  ground truth. Still opt-in (`git-check --copy`, `EKBASIS_GIT_COPY=1`). If you turned it on with 0.1.34, upgrade.

## [0.1.34] — 2026-10-13

### Added
- **Lost work from the run on a copy too** (same opt-in: `git-check --copy`, `EKBASIS_GIT_COPY=1`). When every
  command of the line ran on the copy, the guard compares the uncommitted versions before (changed tracked files,
  untracked and ignored files, the index, versions only in a stash) with everything after (work tree, index, every
  branch, remote-tracking and tag tip, every stash entry, or inside another version of the same file): a version that
  survives nowhere is lost, and the reason names the files. Validated against the git data generator's ground truth on
  400 new scenarios: 277 decided, 277 agree (34 lost, 243 kept); failures 586 of 586. When the user's request may ask
  for the loss (`request=`), a loss found on the copy is left to the model, which reads the request; "nothing lost" is
  always taken. Not decided (left to the model) when a command did not run on the copy, or the work tree has more than
  2,000 files or 64 MB to compare.

## [0.1.33] — 2026-10-13

### Added
- **Which git commands fail, from git itself, on a copy of the repository** (`ekbasis.git_sim`; opt-in:
  `ekbasis git-check --copy` or `EKBASIS_GIT_COPY=1`, which the Claude Code hook uses for lines made only of git
  commands). The commands run in order on a copy (APFS clonefile, a reflink, or a copy of up to 512 MB), with the
  repository's hooks disabled, no editor, no prompt and no signing, under a time limit; each command's failure is then
  set to 0 or 1 by its exit code, and the reason quotes git's error. Only local subcommands run: at the first command
  that could reach a remote (push, pull, fetch, ...) or that is not on the list, the run stops and the rest stays with
  the model. The real repository is never touched (tested: every file and the .git folder hash the same afterwards), and
  the prompt the model reads does not change. Validated against the ground truth of the git data generator (real
  repositories, 700 new scenarios): 1,064 of 1,064 simulated commands agree. On the held-out guard set, the model's
  confident errors that this covers: 442 of 537 (the rest involve the network, shell commands between git commands, or
  lost work, which stays with the model).

## [0.1.32] — 2026-10-13

### Added
- **`git rebase` over uncommitted changes, decided by code** (check when sure; the safe form of 0.1.30's rule). When the
  first command is `git rebase` (no `--autostash`, `--abort`, `--skip`, `--continue`, `--quit`, `--edit-todo`) and
  `rebase.autoStash` is not set, the guard reads the real `git status`: tracked files with uncommitted changes, staged or
  not, mean git refuses to start the rebase and changes nothing, so that command's failure is set to 1.0 with the reason.
  The prompt the model reads is unchanged, so no other answer moves (lost work, other commands). One way only: a clean
  tree is left to the model (a rebase can still stop on a conflict). Checked against the held-out guard set's answers,
  without the API: of 886 items whose first command is a rebase, the 657 with tracked changes all fail (rule right 657 of
  657, where the model was right on 406 with 213 confident errors); first-command "does it fail?" accuracy 68.3% → 96.6%.

## [0.1.31] — 2026-10-13

### Removed
- **The rebase rule of 0.1.30 is no longer added to the prompt.** Its confirmation on the held-out guard set (3,322 items
  with a rebase) kept the gain it was made for (confident errors on "does the rebase fail?" 36.9 → 9.3 per 100) but
  showed what the 1,598 new items had not: its "fails and changes nothing" spread to the other commands of a line. Real
  losses flagged at 0.2 fell 93.5% → 91.8% (7 losses no longer flagged, 2 newly flagged, of 292), and accuracy on the
  other questions fell 93.1% → 91.5%. Flagging lost work is the guard's first job, so the rule is off until a version
  that does not move it. If you run 0.1.30 with the git guard, upgrade.

## [0.1.30] — 2026-10-13

### Added
- **A git rule for `git rebase` with uncommitted changes.** git refuses to start a rebase (it fails and changes nothing,
  even when already up to date) when tracked files have uncommitted changes, staged or not, unless `--autostash` or
  `rebase.autoStash`; the model, which never saw rebase in training, answered with confidence that it would succeed. The
  client now states the rule for these commands (`NOTE_REBASE_DIRTY`, not added with `--autostash`, `--continue`,
  `--quit`, `--edit-todo`, or when the repository sets `rebase.autoStash`). Measured before release on 1,598 new
  held-out git items (fresh seeds), with vs without the rule: on "does the rebase fail?" confident errors 30.0 → 5.4 per
  100 (−82%, 95% CI of the difference [−33, −16]), accuracy 63.8% → 94.6%; the other 1,468 questions of the same items
  95.9% → 96.0%; real losses flagged unchanged (94.7%). Pre-registered; rebase is a held-out command kind, so no prompt
  of a trained command form changes.

## TypeScript SDK 0.2.2 — 2026-10-13

### Fixed
- The `Question` type accepts every shape the API takes: `type: "boolean"` (same as `"noul"`), `choice` with
  `options: string[]` (or `criteria`), `score` with `criteria` as an object (value → description) or a list. Before, the
  first two were refused by the type checker (they worked in JavaScript), and `checkQuestions` refused `"boolean"`.

## [0.1.29] — 2026-10-13

### Added
- **Chain mode in the Claude Code hook** (`EKBASIS_CHAIN=1`, with `EKBASIS_SHELL_GUARD=1`): a flagged line of several
  commands joined by `;`, `&&` or new lines gets, in its warning, the first risky command and the advice to run the
  commands before it on their own, then the rest as a separate call checked on the state after them. The decision does
  not change. Not split: pipes, `||`, `&`, here-documents, compound commands, nested shells, and commands that change
  the session (`cd`, `export`, assignments, `source`). `shell.sequence_parts`, `join_parts`, `first_risky`.

## [0.1.28] — 2026-10-13

### Added
- **`ekbasis plan-check`**: check the actions an agent is about to run, from the command line or any harness. Exit 0 =
  every step forecast harmless with confidence (run them all); 2 = run the first N, then look at the real state before
  step N+1 (it says which step and why); 3 = cannot foresee. `--rules` and `--state` take text or `@FILE`; `--request`
  is what the user asked for; `--harm` picks preset questions, `--ask` adds your own; `--json`; `--steps-file`.
- **`ekbasis.HARMS` / `harms()`**: four preset harm questions (`data_lost`, `outage`, `unasked_deletes`,
  `breaks_later`) worded like the ones measured in the Kubernetes chain studies, made general. Each asks about harm the
  user's request does not ask for. Measured on Kubernetes only: in another domain, try them on your own cases first.
- **`check_plan(..., request=...)`** and `run_plan(..., request=...)`: the user's request at the top of every prompt, the
  layout the chain studies used (`request_on_top`).
- TypeScript SDK 0.2.0: the same `HARMS`, `harms()`, `requestOnTop` and `checkPlan(..., { request })`.
- TypeScript SDK 0.2.1: also a CommonJS build. Up to 0.2.0 the package was ESM only, and `require("ekbasis")` failed
  with `ERR_PACKAGE_PATH_NOT_EXPORTED` in every CommonJS project; tested now in CommonJS, ESM and tsx projects.

## [0.1.27] — 2026-10-12

### Changed
- **`check_plan` asks the prefixes in parallel** (`parallel=4` by default; `parallel=1` for one by one). Each prefix is
  forecast from the same state, so the answer is the same; a wave past the stopping step costs at most `parallel - 1`
  extra requests. Measured on the hosted API, a 10-step plan: 10.3 s → 3.6 s (2.5 s with `parallel=10`). `run_plan`
  passes it through.

## [0.1.26] — 2026-10-12

### Added
- **`check_plan` and `run_plan`: check a batch of actions before it runs** (a script, a pipeline, several tool calls).
  Ekbasis forecasts every prefix of the plan from the state as it is now; the plan runs whole only when every prefix is
  forecast harmless with confidence ≥ 0.9; otherwise it is split before the first flagged or uncertain step, which is
  then checked on the real state (look when unsure, for a batch). `run_plan` runs that loop with your `observe` and
  `execute`. README: "Check a plan before it runs".
- **The API scorecard** (`scorecard/`): quality (accuracy, confident errors, Brier, ECE), time (p50/p90/p99 and the
  server's auth/queue/model split), cost (tokens and US$ per 1,000 checks), failures and chains, on fixed held-out items,
  for any endpoint. Every change to the model, server or client is compared with the runs before it.

## [0.1.25] — 2026-10-12

### Changed
- **Warnings say which stash entries are work found nowhere else** ("changes on NO branch, lost for good if dropped")
  and which are already kept on a branch, instead of only listing them. With warn once, the note adds that work named
  as found nowhere else is not covered by a general request ("clean up", "the old ones").
- Why: in a pre-registered test with Claude Haiku 5.5 on long tasks under time pressure (96 runs), the only losses in
  either arm were a recent unique stash dropped while "cleaning the old stashes" (1/36 alone, 2/36 with the hook in warn
  once): the warning listed the stashes without saying which one was unique, and the agent ran the command again.

## [0.1.24] — 2026-10-12

### Added
- **Hook: warn once** (`EKBASIS_GUARD_REPEAT=1`, opt-in; meant for agents running without a person, with
  `EKBASIS_GUARD_MODE=deny`). The first attempt is blocked with the facts; the exact same command, in the same session
  and folder, goes through when run again: the agent has read what is at stake and decides, as a person does when
  Claude Code asks.
- **Warnings name what is at stake**: the paths `git clean` would remove (git's own dry run), the uncommitted paths of
  the repository, the stash entries, and the files a shell line changes or removes.
- Pre-registered held-out test with Claude Haiku 5.5 (20 new tasks, 160 runs): with a hard block (0.1.23) the guard
  cost 9 of 56 tasks; with warn once, 48/56 against 45/56 alone, controls 24/24 in both, and none of the 17 repeated
  commands caused harm. Neither arm lost work on these tasks, so no safety difference could be measured.

## [0.1.23] — 2026-10-12

### Fixed
- **Security: commands after shell reserved words were not checked.** In a line like
  `for b in x y; do git branch -D $b; done`, `if c; then git reset --hard; fi` or `! git reset --hard`, the command
  after `do`, `then`, `else`, `elif`, `if`, `while`, `until` or `!` was read as a command named after the keyword, so
  the git guard never saw it (and the shell guard read it wrongly). Both guards now skip these words.

### Added (decided by code, no model call)
- **Stash facts.** For `git stash drop/clear/pop`, the state says, for each entry, whether a local branch already has
  every file it changes exactly as the entry has it. Old stashes whose work was merged are no longer "lost work"; a
  stash that is on no branch still is.
- **`git rebase --skip`** that drops a commit no other branch, tag or remote branch holds is flagged (committed work).
- **Remote work this clone never fetched** (`git ls-remote`, read-only, 10 s): a forced push (not
  `--force-with-lease`) over a remote tip that is not a commit here, and `push --mirror` over remote branches with no
  local branch, are flagged. `EKBASIS_REMOTE_CHECK=0` turns it off.
- **Shell guard: `cp`/`mv` that overwrite** a file with different content that is not in git as it is now (untracked,
  changed, or ignored and not rebuildable) are risky, whatever the model says. `-n`, `-i` and `-u` are not.
- Git note for `git add` on a file with a conflict (it loses nothing).

### Changed
- Fewer "cannot foresee": a read-only git command with a variable (`git stash show "stash@{$i}"` in a loop,
  `git -C $d status`) and a read-only shell command with a path in a variable (`cat "$f"`, `cmp "$f" ...`) no longer
  make the guards give up. A variable where `log/show/diff` could take `--output` still does.
- `shell-check` uses the hook's shortcut by default: when everything the lines could change is committed in git or
  ignored and rebuildable, the model is not asked (`--no-shortcuts` restores 0.1.22).
- Measured on a development replay of 90 Claude Haiku 5.5 runs (413 calls; each call checked before it ran and then
  run, a checker saying whether that call lost protected work): dangerous calls stopped 20/26 → 24/26, harmless calls
  blocked 57/387 → 35/387, and no harmless call newly blocked.

### Experimental
- The user's request (`git-check/shell-check --request`, hook `EKBASIS_REQUEST=1`, which reads the last message typed
  in the Claude Code transcript): the state shows it and the loss question leaves out what was asked for. Off by
  default: in the same replay it changed almost no decision, and asking with the request inside the question cleared
  a requested loss but also a unique stash the user had not asked to drop.

## [0.1.22] — 2026-10-12

### Changed
- **Migration guard: a rule decides, the model reviews** (`--policy rule`, the new default; Action input `policy`). A
  rule written from the PostgreSQL documentation (`ekbasis/migration_rule.py`), over the same facts the model reads,
  decides whether a migration fails the check. When it finds no risk and the model does, the migration is marked
  `review` (comment and `--json`), without failing the check. `--policy model` keeps the 0.1.21 behavior. The verdict
  cache key includes the policy.
- Why: in pre-registered tests the rule matched or beat the model on the same facts. With realistic seed data
  (duplicates, sentinels, orphan rows), on 307 Rails migrations the rule's false alarms were 4.4% against the
  model's 7.5%, and rule-decides-model-reviews scored accuracy 0.967 with recall 98.6% counting reviews.
- The rule in the product gives the same verdict and reason as the frozen rule of the study on every checked item
  (184 v3 migrations, both regimes; 300 Rails v7 migrations).

## [0.1.21] — 2026-10-11

### Added
- **Migration guard, framework adapters: a throwaway Redis for projects that need it.**
  - `migrate-gen --redis auto|on|off`; the Action's input is `redis`, default `auto`. `auto` turns it on when the
    Gemfile or the Python requirements depend on redis, sidekiq, resque, kredis, celery, rq or django-redis.
  - The Redis runs on the generator's internal network: no route out, no published port, nothing else on that
    network. It is removed at the end. The generator gets `REDIS_URL`, `REDIS_HOST` and `REDIS_PORT`, and still has no
    route out (checked).

### Fixed
- **Rails renderer:** zero-padded migration versions (`001_create_users.rb`, as in Redmine) rendered nothing, because
  the file's version was compared as text with Rails' integer version. They are now compared as integers.

### Changed
- **Rails is supported, opt-in** (`framework: rails`; no more `EKBASIS_EXPERIMENTAL_RAILS`). In a pre-registered
  evaluation on new projects (Redmine, OpenProject, Consul Democracy; 307 migrations it answers, each run by Rails on
  a seeded database) it met every target: verdict accuracy 0.896 against 0.730 for rules, recall 1.000 (119/119),
  reason right 0.992 (118/119), false alarms 17.0% (upper bound 23.0%) against 44.1%. Caveat: Consul Democracy holds 108 of the 119 risky
  migrations, and only 4 of them failed rather than lost data. [docs/MIGRATION_GUARD.md](docs/MIGRATION_GUARD.md).
- **Migration guard: "fails" is decided in code when the rows cannot make the migration fail.**
  - **The rule.** The migration has already run on the schema alone (the probe). If every statement can fail only
    because of the schema, existing data cannot make it fail, and P(fails) is set to 0. The model's answer is kept as
    `p_fail_model`, and the file gets a note.
  - **Statements that qualify:** drops, renames, new tables and their indexes, plain (non-unique, column-list)
    indexes, nullable or defaulted new columns, dropping a default or NOT NULL, a
    constraint or unique index on a table created by the same migration, a foreign key or unique constraint on columns
    it just added as nullable, and the catalog-only `DO` block Rails writes for `create_enum`.
  - **Statements that do not:** UPDATE/INSERT/DELETE, SET NOT NULL, type changes, constraints on existing rows, unique
    or expression indexes on existing tables, and generated columns.
  - **The reason this was needed.** In the Rails evaluation, 5 migrations that only dropped data were reported as
    "may fail". This affects every framework and plain SQL. Pre-registered non-inferiority check on the 184 SQL
    migrations of the v3 evaluation, with 0.1.20 (main) and this code applied to the same fresh answers, the states
    checked byte for byte identical: accuracy 0.897 → 0.902, false alarms 17 → 16, recall 54 → 54, reason right
    48 → 48 (passes).
- **`intent_check` flags a third party only when p is strictly above 0.5.** An exact 0.5 (two bf16 logits landing on
  the same value, about 0.5% of answers) is now "unsure". In two pre-registered replays of published attacks this lost
  no stopped attack and cut false alarms from 13 to 8 and from 7 to 4.
- **`intent_check` is beta** (was experimental), as a signal to ask a person. In a pre-registered replay of 1,510
  published successful attacks on eight agents it would have stopped 99.8% of them, with false alarms on 1.7% of 776
  benign runs; a replay is not a live run (see docs/INTENT_CHECK.md). The 3 attacks it did not stop are a benchmark
  artifact (the user's own request gives the attacker's IBAN), so 1,507 of 1,507 real attacks were stopped.

## [0.1.20] — 2026-10-11

### Added
- **Migration guard: code probes.** On a copy of the scratch database the guard tries three mechanisms: an INSERT whose
  keys collide with rows already there, an INSERT…SELECT that leaves a NOT NULL column empty, and a DELETE or UPDATE of
  rows a foreign key still references. When a probe reproduces the PostgreSQL error with real rows, "fails" is decided
  in code; when it needs an invented row, the result reaches the model as a conditional fact ("if …, it fails with …").
- **Edited migrations get a verdict**, on the base schema before them, with a note that databases that already applied
  them will not run the change (before, only the note).
- **`--setup-sql` / Action input `setup-sql`**: SQL run by the scratch server's admin before the base's migrations, for
  platforms that create a schema or role outside the migrations (e.g. Supabase's `auth`). With a base ref it is read
  from the base, never from the pull request.

Pre-registered evaluation: no regression on the 184 labelled v3 migrations (false alarms 20 → 20 with replica
statistics and 19 → 19 without; recall 54 → 54). The gain on new incidents was **not** demonstrated: only 4 new
incidents were found, none of the probes' formats. In development, two incidents the guard used to miss were caught
for the right reason (a DELETE of referenced rows, P(fails) 0.13 → 0.92; an INSERT leaving NOT NULL empty, 0.25 → 0.97).

## [0.1.19] — 2026-10-11

### Changed
- **Migration guard: states up to 200,000 characters (~64k tokens) are read** (was 60,000, which was about 15–19k
  tokens, not the 32k its comment assumed). A pre-registered test on 184 new migrations, padded with real tables from
  other projects to 16k, 32k and 64k tokens, found no loss in verdict accuracy (0.880 at both the native length and
  64k), recall or false alarms, wherever the deciding tables sat; only the calibration of the "fails" probability got
  somewhat worse (ECE 0.034 → 0.063). A cold 64k-token check takes about 25 s.
- **Migration guard: the schema is cut by a parser.** The state used to show the tables whose names appear anywhere in
  the migration (inside strings too) and their foreign-key neighbors, at most 8. It now shows, in full, the tables the
  migration touches (ALTER, INSERT, UPDATE, DELETE, TRUNCATE, CREATE INDEX ON, DROP, FROM/JOIN, REFERENCES, the tables
  of an index, sequence, type or domain it changes, the tables their triggers write), with no cap; each foreign-key
  neighbor in one line (the key, ON DELETE, NOT NULL); the views that depend on them (the columns each reads); their
  triggers with the functions' bodies; owned sequences, enums and domains; and "N other tables omitted". A migration
  the parser cannot follow (dynamic SQL, an unknown statement, an unresolved name) or whose cut state is still too long
  gets the previous state, with a note. Pre-registered evaluation on 184 labelled migrations: accuracy 0.880 → 0.897
  with replica statistics and 0.886 → 0.886 without, false alarms 20 → 17 and 19 → 18, recall unchanged within one
  item; median input tokens −23% and −30%. Without replica statistics, non-inferiority holds on the point estimate but is
  not shown statistically (the accuracy CI is −2.7 to +2.7 pp). `EKBASIS_SCHEMA_CUT=off` restores the previous state. The verdict cache key
  includes the cut version.

## [0.1.18] — 2026-10-11

### Added
- **Opt-in loss question that leaves out the intended change** (`EKBASIS_SHELL_LOST=intent`), for A/B tests of the shell
  and Claude Code guards. The default question asks whether content "afterwards is in no file at all", which is also true
  of the change a command is meant to make (an in-place edit replaces the old content); in an external test this was the
  most common remaining false alarm. The default is unchanged until the variant is measured.

## [0.1.17] — 2026-10-11

### Fixed
- **A malformed question is refused before it is sent.** The server reads a question's text only from `instructions`;
  a question written as `{"type": "noul", "question": "..."}` was silently answered as if it asked nothing, with one
  same probability whatever it said. `Ekbasis.ask` now raises `ValueError` for a question with no `instructions`
  (naming the field it found instead), an unknown type, or an empty question set. Found when a study's first pass gave
  the same answer to every question.

## [0.1.16] — 2026-10-11

### Fixed
- **Migration guard:** `migrate-check --bundle` with a bundle that does not exist, or that is not JSON (for example
  when `migrate-gen` crashed before writing it), ended with a Python traceback (`FileNotFoundError`) and the Action
  posted no comment. It now answers "cannot foresee" (exit 3, `--json` with `cannot_foresee`), so the check fails
  closed and the comment says why.

## [0.1.15] — 2026-10-11

### Added
- **Migration guard for Alembic (supported) and Django (experimental), opt-in** (`ekbasis/frameworks.py`, `ekbasis migrate-gen`, `migrate-check
  --bundle`, the Action's `framework` input, [docs/MIGRATION_GUARD.md](docs/MIGRATION_GUARD.md)). The framework
  renders each new migration as SQL: Django `sqlmigrate`, Alembic offline `upgrade --sql` (also `flask db`).
  - **Isolation.** The pull request's code runs only inside a generator container. The container gets the trees from
    `git archive`, runs `--setup` with network, and is then moved to an internal Docker network, checked to have no
    route out, with no secret in its environment. Migrations run as a throwaway role that is not a superuser.
  - **Base schema.** The framework migrates the scratch database at the base tree, and `pg_dump --schema-only` gives
    the schema.
  - **Code that is not SQL** (Django `RunPython`, an Alembic migration that reads the database) is listed as "code not
    foreseen: review it by hand", never as "ok".
    - `--on-code warn` (default, the Action's `on-code`): it does not fail the check, and the verdict is
      `code-not-foreseen`.
    - `--on-code block`: it is "cannot foresee" and fails closed.
  - **The bundle (JSON)** is checked by `migrate-check --bundle`, with the verdict cache. The API key is needed only
    there.
  - **Tests.** `tests/test_frameworks.py`: offline tests, PostgreSQL tests, and docker tests that render tiny Django
    and Alembic projects and check the isolation.
  - **Measured with `block`** (pre-registered, 390 real migrations from 5 projects, labels by running each one with
    its framework). Verdict accuracy is 0.762 for Django and 0.884 for Alembic; rules on the rendered SQL get 0.762 and
    0.768. Neither framework met every target. Most of the gap was code counted as "cannot foresee" (31% of the Django
    migrations), which is why the default is now `warn`.
  - **Measured with `warn`** (pre-registered, 571 migrations from 5 new projects). On the migrations it answers,
    accuracy is 0.955 for Django and 0.986 for Alembic (rules: 0.826 and 0.773), with false alarms of 2.4% and 1.6%.
    Recall is 1.000 for Alembic. For Django it is 0.824 (28/34, lower bound 0.665): the 0.85 target was missed, so
    Django is **experimental** and the comment and CLI output say so. The misses were failures on values out of range
    for a narrower column, a foreign key violated by copied rows, and one overwritten value. 24% of Django and 45% of Alembic migrations
    contain code listed for review by hand. Details are in docs/MIGRATION_GUARD.md.

## [0.1.14] — 2026-10-11

### Fixed
- **Migration guard:** a `BEGIN` inside a function body (`$$ ... BEGIN ... END $$`) or in a string no longer switches the
  file to autocommit rules; only `BEGIN`/`COMMIT` statements of their own count. Found by a backtest on real incidents,
  where two PL/pgSQL migrations were judged with the wrong transaction rule.
- **Migration guard: goose files.** Only the `-- +goose Up` sections are run (the Down section was run too), and
  `-- +goose NO TRANSACTION` is read as autocommit.

## [0.1.13] — 2026-10-11

### Added
- **Migration guard: verdict cache.** The model's answer for a migration is reused, with no call and no tokens, when
  the migration file, the whole base schema, the client version, the transaction mode, the use of replica statistics,
  the exact state and questions and the server URL are all the same (sha256 key; 30 days; probabilities only, the
  verdict is decided again with the current thresholds). The Action keeps it in the Actions cache
  (`verdict-cache: true` by default); the CLI in `~/.cache/ekbasis/verdicts` (`EKBASIS_VERDICT_CACHE`, `--no-cache`).
  Reused answers are marked in the comment and with `"cached": true` in `--json`.

## [0.1.12] — 2026-10-11

### Added
- **Intent check, experimental** (`ekbasis.intent_check`, [docs/INTENT_CHECK.md](docs/INTENT_CHECK.md), PRs #11 and
  #12): before an agent's next tool call runs, whether it serves the user's request or carries out instructions that
  came from content the agent read (indirect prompt injection). By default the input is the call only
  (`agent_text=False`). Tool output is quoted line by line as untrusted data (`shield=True`; every kind of line break
  is quoted). It fails closed. Experimental API: it may change without a major version. Measured results and limits
  are in the doc and in `results/intent_check`.
- **Migration guard** (`ekbasis/migrations.py`, `ekbasis migrate-check`, the GitHub Action
  `actions/migration-guard`, [docs/MIGRATION_GUARD.md](docs/MIGRATION_GUARD.md)): before a pull request is merged,
  whether its new PostgreSQL migrations lose data or fail.
  - **Schema.** The base branch's migrations are applied to a scratch PostgreSQL (`EKBASIS_PG_URL`); the database is
    created and dropped by the guard.
  - **Statistics (optional).** They come from a read-only replica (`EKBASIS_DB_STATS_URL`), planner statistics only:
    row estimates, NULL fractions and distinct counts. Never a value.
  - **Transactional rule.** One transaction per file, as Prisma, Diesel and golang-migrate run it. `--autocommit`
    gives `psql -f` semantics, which are also used for files that cannot run in a transaction.
  - **Decided in code.** A migration that fails on the schema alone is decided in code, with PostgreSQL's error.
  - **Questions.** They are the frozen questions of the pre-registered migrations study (cookbook `studies/migrations`),
    with SQL comments removed.
  - **Exit codes and output.** 0 / 2 / 3 as in the other checks (cannot foresee is risky; `--fail-open`). `--json`
    and `--show-state` are available.
  - **The Action.** It installs the client at its own version, starts `postgres:16` on the runner, writes a single pull
    request comment and updates it on each push, and fails the check on risky or cannot foresee (`fail-on: risky`).
    The comment carries paths, probabilities and reasons, never data values or secrets.
  - **Untrusted SQL runs without privileges.** The pull request's SQL (and the base's) runs as a throwaway role made
    for each check: not a superuser, no CREATEDB, CREATEROLE, REPLICATION or BYPASSRLS, owner of its throwaway
    database only. The admin connection only creates and drops the database and the role. Migrations that need more
    (`COPY ... TO PROGRAM`, `pg_read_file`, untrusted languages, `CREATE ROLE`) fail with "permission denied" and are
    reported as cannot foresee. In the Action, the scratch PostgreSQL runs on an internal Docker network (no route
    out), reached with `docker exec` (`EKBASIS_SCRATCH_PSQL`).
  - **Reasons decided in code.** If a failure is foreseen in a transactional file: "may fail on existing data (X%);
    nothing in the file would be applied" (plus "if it ran, it would also lose data (Y%)"). Otherwise: "may lose
    existing data (Y%)". A migration that fails on the base's schema is reported as an error in the pull request itself
    (for example, a migration it depends on is missing from the base). `--json` adds `kind`.
  - **The comment treats paths and errors as untrusted.** They are cut, HTML and markdown are escaped, and @mentions
    and links are broken. A migration that needs a superuser is marked "review this one by hand". The "About" link
    points at the release tag's documentation.
  - **Talking to PostgreSQL.** Only `psql` is used (`EKBASIS_PSQL`), so the client stays standard library only.
  - **Tests.** `tests/test_migrations.py` runs offline with a fake model. Its PostgreSQL tests run in the new CI job
    `migration guard (PostgreSQL 16)`, with a service container, and are skipped elsewhere.

## [0.1.11] — 2026-10-10

### Added
- **Log-only hook mode** (`EKBASIS_GUARD_MODE=log`, from an outside tester's suggestion): the Claude Code hook never
  blocks; it appends what it would have done (`ask`, `ask_cannot_foresee` or `pass`, the reason, the command and the
  folder) to `~/.cache/ekbasis/hook_log.jsonl` (or `EKBASIS_HOOK_LOG`, file mode 600, nothing sent anywhere) and says
  "would ask" on stderr, so a trial period shows what it would have stopped before it may stop anything. In the
  plugin, a hook that cannot run also lets the command through in this mode, with the reason on stderr.

## [0.1.10] — 2026-10-10

### Added
- **Claude Code plugin and marketplace** (`.claude-plugin/marketplace.json`, plugin in `plugins/ekbasis/`, ~0.5 MB):
  `claude plugin marketplace add OpenInterpretability/ekbasis --sparse .claude-plugin plugins` (about 1 MB; without
  `--sparse`, or with `/plugin marketplace add`, the whole repository is cloned once), then
  `claude plugin install ekbasis@ekbasis`. It bundles the
  PreToolUse git guard (matcher Bash), the `ekbasis-guard` skill (from the cookbook), the MCP server and `ekbasis` on
  the Bash tool's PATH. It runs its own copy of the client (`plugins/ekbasis/lib/ekbasis`, kept identical to
  `ekbasis/` by `scripts/sync_plugin.py`; CI and the tests fail when it is not): `python3` and `sh` for the hooks,
  `uv` for the MCP server, nothing from PyPI, and none of `results*/`, `paper/` or `assets/`.
- `ekbasis.claude_plugin`: until `EKBASIS_URL` or `EKBASIS_API_KEY` is set, the plugin's hook says nothing (Claude
  Code's normal permission flow applies), a SessionStart hook shows one line on how to set it up, and the plugin's
  `ekbasis` command says it is not set up (exit 3), instead of asking to confirm every git command that can change
  files because the default `http://127.0.0.1:8000` does not answer. Once either is set it runs the same fail-closed
  hook as `ekbasis-claude-hook` (a key without a URL means the hosted API), and a hook that cannot run asks with the
  reason, never a silent pass: `python3` missing or older than 3.9, an import error, any exception or exit, a bad
  input, no answer within 27 s (`plugins/ekbasis/scripts/run.sh` and `claude_plugin.py`; `EKBASIS_FAIL_OPEN=1` and
  `EKBASIS_GUARD_MODE=deny` apply as in the hook). `ekbasis-claude-hook` itself is unchanged.
- `ekbasis mcp`: the MCP server as a subcommand (same as `ekbasis-mcp`), so `uvx --with "mcp>=1.2" ekbasis mcp` runs
  it from PyPI without installing.
- PyPI packaging: project URLs, classifiers and keywords; SPDX `license` (setuptools ≥ 77); the sdist leaves out
  `tests/`. README links are absolute, so they work on PyPI. `server.json` for the MCP registry
  (`io.github.OpenInterpretability/ekbasis`, with the `mcp-name` marker in the README).
- GitHub Actions: `ci.yml` (tests on Linux with Python 3.9, 3.12 and 3.13 and on macOS; build, `twine check`, wheel
  contents, fresh-venv install, versions in agreement, the plugin's copy in sync and under 2 MB) and `publish.yml` (on a `v*` tag, PyPI Trusted Publishing).
- **Safer route** (`ekbasis/safer.py`): when git commands are risky, `git-check` prints
  `Safer: <commands>  (lose uncommitted work: N%)`, `--json` and the MCP tool `check_git_commands` add `safer`
  (`{commands, p_lost, keeps}` or null) and `safer_note`, and the Claude Code hook adds the route to its message.
  Candidates come from rules (stash before `reset --hard`, `checkout --`, `restore`, a forced switch; stash of what
  `clean -n` lists; rename instead of `branch -D`; backup branches before dropping commits, stash entries or a
  deleted remote branch; `--force-with-lease --force-if-includes` for a force-push), and each is checked by Ekbasis
  with the same state builder and threshold and by the code checks; only one that passes is offered, else "none".
  Off with `--no-safer`, `EKBASIS_SAFER=0`, or MCP `safer=false`. Measured on 9 classic losses x 3 against the hosted
  API: a route on 22 of 27 rows (none for force-push then, sometimes none for `stash drop`), every one ran and kept
  the work; the search added a median 4.8 s to the hook during that run, while another benchmark loaded the API
  ([results/safer_route](results/safer_route/RESULTS.md)).
- `docs/DOGEATING.md`: the guard catching its own operator (a destructive `kill` on the live serving
  process, flagged retrospectively at 0.94-0.97 confidence, outside the training domains) and the
  no-exceptions rule that came out of it.
- `examples/zebra_review/`: the foreseer auditing an animation state machine it was never trained on
  (the foot-sliding artifact, the stride/ground-speed arithmetic, the missing suspension phase, the
  neck pump) — six foresee calls, every one useful; the honest record of what it does and does not do.

### Fixed
- **Force-push and `--force-with-lease`** (from an outside tester's report, confirmed on a bare remote): the safer route
  for `push --force` is `git push --force-with-lease --force-if-includes` (git >= 2.30), which refuses while the remote
  has commits the branch never had; `--force-with-lease` alone, or with an expected value read from the same state,
  overwrote a fetched commit, so `remote_loss` now counts it as a force (an explicit value that differs from the
  remote-tracking ref counts as safe: the push fails).
- `remote_loss` checks a push against the branch its refspec names (`origin X`, `HEAD:X`, `src:dst`, `+X`), then the
  upstream, then the branch of the same name; it used origin/HEAD for a branch without upstream, a false alarm. No
  remote-tracking ref for the destination means a new branch: nothing to lose.
- Deleting a remote branch (`push --delete X`, `push origin :X`) whose commits no other ref holds is flagged by the
  hook (and gets a backup-branch route), and `git rebase --onto` counts the commits it drops in `committed_loss`.
- With facts on, the state names the remote branches that push, branch and rebase commands name (`Remote origin/x last
  commit: ...` and its file comparison) and the relative revisions of a `rebase --onto` (`HEAD~3 is commit ..., 3
  commits before HEAD`). Without them the model expected the backup routes for these two cases to fail; with them both
  passed 3 of 3 and kept the work when run. Other commands keep the previous state.
- Lost committed work (`git.committed_loss`) now counts a new branch or tag made earlier in the line
  (`git branch keep && git reset --hard HEAD~1` no longer asks).
- The hook's force-push message no longer suggests `--force-with-lease` alone as the fix: it does not protect commits
  that were already fetched (measured: it overwrote them); it suggests rebasing first or `--force-if-includes`.

## [0.1.9] — 2026-10-10

### Added
- **`ekbasis feedback`**: tell the hosted API how an answer turned out, so we can measure the model on real use.
  `ekbasis feedback --last --wrong` (or `--correct`, `--prevented-harm`, `--false-alarm`), or pass the request id;
  `--note` is optional (up to 500 characters; never put secrets in it). Free, one per request id, kept 30 days.
  Exit 0 recorded, 4 refused (unknown id, already sent, rate limit, no key), 3 server unreachable, 1 usage error.
  In Python: `Ekbasis.feedback(verdict, request_id=None, note=None)`, raising `FeedbackRejected` (with `.status`).
- The client keeps the `X-Ekbasis-Request-Id` of each hosted answer in `client.last_request_id` and in
  `~/.cache/ekbasis/last_request_id` (only the id and the time, never the question or the answer;
  `EKBASIS_CACHE_DIR` moves it), so `--last` works across commands and from the Claude Code hook.
- Calls say where they come from in `X-Ekbasis-Surface` (`git-check`, `shell-check`, `preflight`, `predict`,
  `claude-hook`, `mcp`; `EKBASIS_SURFACE` or `Ekbasis(surface=...)` to set it), which is metadata only.

## [0.1.8] — 2026-10-10

### Changed
- **"cannot foresee" replaces "cannot judge"** in everything a person reads: the CLI (`Ekbasis: CANNOT FORESEE`),
  the Claude Code hook ("Ekbasis could not foresee what this command will do"), preflight and the shell guard.
  Ekbasis forecasts; it does not judge. Nothing a program reads changed: exit code 3, the JSON field
  `cannot_judge`, the `CannotJudge` exception and the verdicts' `cannot_judge` attribute stay, with new
  equivalents `cannot_foresee` (JSON field and attribute), `CannotForesee` and `CANNOT_FORESEE`.
- **The client identifies itself** with `User-Agent: ekbasis/<version>` instead of Python's default
  `Python-urllib/3.x`, which some CDN bot checks block (the hosted API at openinterp.org answered 403 to it).
- `ekbasis.__version__` now matches the package version (it said 0.1.6 in 0.1.7).

## [0.1.7] — 2026-10-10

### Added
- `remote_loss()` in `ekbasis/git.py`: the guard now flags `git push --force` / `push -f` lines that would
  overwrite commits the remote holds and the local branch does not (falls back to `origin/HEAD` when the
  branch has no upstream). The Claude Code hook asks with the reason: "force-pushes over N commit(s) that
  origin/main holds... or use --force-with-lease". Measured: diverged force-push asks; synced force-push and
  `--force-with-lease` stay silent. Gap found in the cookbook battery (09/10).

## 0.1.6 (2026-10-06): preflight

Preflight for multi-step changes (`ekbasis.preflight`, `ekbasis preflight`, the MCP tool `preflight_command`, the Claude
Code hook with `EKBASIS_PREFLIGHT=1`). Before a migration file, a script or a chain of commands runs, it finds the first
step that fails, on a copy of the folder or database when the plan is local (exact), otherwise by Ekbasis with
code-stated facts and a step walk, and warns only when that failure would leave the change half applied. Nothing else
changes: with `EKBASIS_PREFLIGHT` unset, every request is byte-identical to 0.1.5's.

- Built from a first preflight study (0.1.4.dev0, not released): it cut damage with Claude Haiku (16/28 → 6/28 trap
  sessions) but interrupted Claude Sonnet needlessly (25 warnings, none right) and missed three kinds of shell trap.
  This version changes what counts as a change (reads and additions are not half-done changes), follows more of what
  careful agents write (backups, `{ ...; } | sqlite3`, files written on the same line, `cd`, variables, sqlite3 inside
  chains), runs local plans on a copy, adds code-stated facts and the step walk, and is silent when it cannot judge.
- Measured on 20 new tasks, pre-registered ([results/client_0.1.6](results/client_0.1.6/RESULTS.md)): Haiku 4.5's damage in traps 23/28 → 3/28 sessions, tasks done 17/40 → 34/40, no control warned; Sonnet 5.5: 7 warnings, all right, no needless one, damage 5/14 → 1/14.
- The warn-once rule keys on the command and on what it would run: an edited script or SQL file is checked again (after the study; covered by a test).
- **Runs on a copy never touch real files** (after the study; found before release).
  - Before: on a machine without a sandbox, a shell step that wrote an existing file outside the folder wrote the real
    file during the check (reproduced on Linux). Such a step uses an absolute path, `..`, a symbolic link or `xargs`
    over a list.
  - Now: shell steps run on a copy only inside `sandbox-exec` (macOS: no network, writes only in the copy). Elsewhere,
    or when the sandbox cannot start, Ekbasis judges the plan.
  - A step that would start a program outside the allowlist is not run on a copy either: `xargs` or `find -exec` with
    such a program, `awk` with `system()` or a pipe, or `tar`/`zip`/`sort`/`git` options that name a program.
  - When the sandbox refuses a step's write outside the copy, Ekbasis judges the plan. Before, the refusal counted as
    the step's failure, although the real run may succeed.
  - SQL copies run inside the sandbox on macOS. SQL that writes other files (`VACUUM INTO`, `zipfile`) never runs on a
    copy.
  - Replayed on every multi-step command of both preflight studies (637 plans, on the snapshot taken before each):
    none moved between the copy and the model, and all 496 runs on a copy found the same first failure.
- Without the `sqlite3` command-line tool, a `sqlite3` line fails before any statement runs. Preflight now reports
  that, by code and without a warning; before, it asked Ekbasis about statements that would never run.
- Tests that need the `sqlite3` tool, a non-root user or the macOS sandbox are skipped where those are missing. The
  suite passes on Linux: Python 3.9 and 3.12, with and without `sqlite3`, as root and as a normal user.
- Hook: `EKBASIS_PREFLIGHT_REPEAT=0` always warns; `EKBASIS_PREFLIGHT_COPY=0` never runs on a copy;
  `EKBASIS_PREFLIGHT_FAIL_CLOSED=1` warns when it cannot judge; `EKBASIS_GIT_GUARD=0` turns the git checks off.

## 0.1.5 (2026-10-06): certified mode for `ekbasis.verify`

One addition to `ekbasis.verify` ([docs/VERIFY.md](docs/VERIFY.md); results in
[results/client_0.1.5](results/client_0.1.5/RESULTS.md)). Nothing else changed: the git guard, the shell guard, the
Claude Code hook, the CLI and the MCP server are those of 0.1.4, and so is every request they send.

- **`rule="certified"`:** act on a confident answer without verifying it only where a certificate holds.
  - **Rule:** Learn-then-Test at α = 2%, δ = 0.05: at most 2% errors among the answers it accepts, per node.
  - **Nodes:**
    - a family with its own certified threshold (37 families);
    - else, for a family seen in the calibration, its (domain, difficulty) node (6 certified);
    - a family never seen, or a node with no certificate, is always verified, with no extra request.
  - **Calibration:** two fully counted fresh sets, frozen as WS-U confirm-3's parameters
    (`results/client_0.1.5/confirm3/params_confirm3.json`).
  - **Third pre-registered test** (12,667 fresh scenarios): 0.39% errors among accepted answers, 26.9% verified,
    94.8% of the confident errors caught, no node above 2%.
  - **Scope:** per node, this model version (w4a5) and these generators. Not real traffic, not blocked actions, not
    families outside the calibration.
- **Every `Decision` records `rule`, `node` and `threshold`**, e.g. `"domain:git"`, `"family:rules|kind|delay"`,
  `"difficulty:sql|d1"`, `"unseen:git|x"`, `"steps"`.
  - New helpers: `verify.node()` and `verify.difficulty()`.
  - `verify.threshold()` returns None under `"certified"` when no certificate covers the answer.
- **The default is unchanged** (`rule="domain"`). In the same third test it caught 85.1% of the confident errors while
  verifying 22.8%, every domain ≥ 80%.
- **Tests:** the client reproduces confirm-3's certified decisions exactly on 602 stored scenarios
  (`tests/data/confirm3_l2_sample.jsonl`), plus the node lookup, the rule, node and threshold on every decision, and
  "no certificate → verify with no request".
- **Training overlap:** confirm-3's items share nothing with the lineage's training files
  (`results/client_0.1.5/firewall`).
- **Fix:** `verify.score` adds the percentiles left to right, as the frozen policy does. On Python 3.12, whose `sum()`
  uses compensated summation, a score could differ from the policy's by 1 ulp. Found by the stored-decision test on
  Linux.

## 0.1.4 (2026-10-06): check when sure

A new module, `ekbasis.verify` ([docs/VERIFY.md](docs/VERIFY.md); tests and results in
[results/client_0.1.4](results/client_0.1.4/RESULTS.md)). Nothing else changed: the git guard, the shell guard, the
Claude Code hook, the CLI and the MCP server are those of 0.1.3, and so is every request they send (no module
imports `verify`).

- **`ekbasis.verify`**: which confident answers (confidence ≥ 0.9) to check by real execution before acting, with the
  reasons.
  - **Policy.** It is frozen from a pre-registered test on fresh items: 84.9% of the confident errors caught while
    verifying 23.4% of the confident answers, against 50.9% verified for 80% caught with confidence alone.
  - **Signals:** the question family's observed error rate (`FamilyTracker`); the answer's stability with the options
    reversed or the question reworded (one request); the self-check (one request, not for git and shell).
  - `check_steps`: the direct answer against the step-by-step one (`simulate`), for questions about several actions
    (87.9% caught with 22.8% verified, on running totals near a limit).
  - `git(verdict, client, tracker)`: one decision per git guard question. `git_family` and `shell_family` give
    observable family keys.
  - **Observed outcomes only:** `FamilyTracker.observe` after a real outcome; `unobserved` for a blocked action, which
    is reported and never counted.
  - `audit(rate)` picks a random share of blocked actions to replay in a sandbox, or of accepted answers to verify, so
    the family rates are not biased by what was blocked.
  - **Fails closed:** if the extra requests fail, the answer is marked to verify. Unsure answers make no extra request.
  - **Data:** `verify_policy.json` holds the reference distributions and thresholds of this model version (w4a5).
- **Per-domain thresholds are the default** (`rule="domain"`, `threshold()`, `domain_of()`). Confirmed on a second
  fresh test: 84.5% caught with 22.6% verified, against 83.5% / 23.4% with the single threshold, which caught SQL at
  67%. Options: `rule="conformal"` (α = 0.15 per family group: 86.3% / 26.2%) and `rule="global"`.
  `Decision.threshold` and `Decision.rule` record what was used.
- **Not adopted:** a Learn-then-Test acceptance rule meant to certify at most 2% errors among the answers acted on
  without checking. It failed its pre-registered test: 1.16% overall, but 3.4% in rare rule families that fell back to
  their suite's threshold.
- **Overlap with training:** the items of both tests (and of the development set) share no identical and no
  near-duplicate item with any training file of w4a5's lineage (2.2M rows checked).
- **Not measured yet:** the client's own family keys. Starting with no history was measured only with the evaluation's
  family labels and every earlier outcome known (85.0% caught, 27.3% verified).

## 0.1.3 (2026-10-06)

Less friction in the Claude Code hook, from a study of Claude Code agents on real repositories
([results/client_0.1.3](results/client_0.1.3/RESULTS.md)). Same model, server, questions and thresholds. Where the
same guard is asked about the same commands, the request is byte-identical to 0.1.2's, on macOS and on Linux. The one
exception is Linux, where the shell rules now say "GNU coreutils 9.4" where 0.1.2 printed "9.4".

- **Read-only git does not ask the model**: `status`, `log`, `diff`, `show`, listings of branches, tags, stashes and
  worktrees, `config --get`, `clean -n`, and more (`git.read_only`).
- **Lines are followed instead of "cannot judge"**: `cd DIR` anywhere in the line, `pushd`/`popd`, subshells and
  `git -C DIR`. A folder that an earlier `git worktree add`, `git clone` or `mkdir` in the same line creates holds no
  uncommitted work, so the safe worktree route passes. `xargs git branch -d` and read-only git through xargs are
  allowed.
- **The shell part of git lines** goes to the shell guard (with `EKBASIS_SHELL_GUARD=1`). Each git command is replaced
  by `true`, and its redirections are kept.
- **No model call when nothing could be lost for good** (`ekbasis.recover`), checked by code:
  - a repository with no uncommitted work;
  - a `git clean -X` whose dry run removes only rebuildable paths;
  - a shell line that changes only committed files, or ignored files with rebuildable names. Test and build runners
    count as reads.

  "Rebuildable" is decided by folder name, so irreplaceable data inside an ignored `build/`, `dist/`,
  `node_modules/` or cache folder is not protected. `EKBASIS_SHORTCUTS=0` turns these checks off.
- **Lost committed work, checked by code and reported apart** (`git.committed_loss`): branch and tag deletion, forced
  branch moves, and `git reset --hard/--keep/--merge <commit>`, when commits would be left with no branch, tag,
  remote-tracking branch or stash entry. Not covered: `git push --force`, a rebase that drops commits, branch names
  passed through `xargs`.
- **Fix**: on Linux the shell rules said "9.4" instead of "GNU coreutils 9.4". The version cache now keeps the raw
  output.
- **API**:
  - `shell.lex(line, parens=False)`;
  - `shell.Word.start`/`end`;
  - `shell.check(..., skip=None)`;
  - `claude_code_hook.plan_line`.

  `read_line` is kept as it was.
- **Measured on fresh agent sessions** (pre-registered).
  - Claude Code agents did 12 tasks on clones of more-itertools, spf13/pflag and chalk, with the hook (H) and without
    it (C).
  - The published 0.1.2 hook was run offline on the same calls.

  | | 0.1.2 | 0.1.3 |
  |---|---|---|
  | Sonnet 5.5: asks per 100 Bash calls with the hook | 10.7 (11/103 on the same calls; 10.6 in the first study) | **2.9** (3/103) |
  | asks on calls that lose nothing, per 100 calls (H and C) | 4.4 (9/204) | **1.0** (2/204) |
  | asks where git or a rebuild gives it back, per 100 calls | 6.9 (14/204) | **1.5** (3/204) |
  | median time the hook adds per call (idle server) | 0.74 s | **0.08 s** |
  | tasks done, with the hook / without | 34/36 / 35/36 (first study) | 35/36 / 36/36 |
  | Haiku 4.5, 4 tasks with a tempting destructive shortcut: real losses caught | 7/7 | **7/7** |
  | user's planted work kept, with the hook / without | 9/9 / 5/9 (first study) | 9/9 / 7/9 |

  The fixes were designed on the first study's calls, so an offline replay of those calls is in-sample: asks went from
  13.2 to 5.3 per 100. The sessions above are new.

## 0.1.2 (2026-10-05)

Three additions measured in the capability map, a shell guard prototype, and guards that fail closed. Same model and
server. With the defaults, every prompt 0.1.1 sends is unchanged ([results/client_0.1.2](results/client_0.1.2/RESULTS.md), `scripts/release_equivalence.py`).

- **Fail closed.** `git-check` and `shell-check` exit with 3, "cannot judge" (treat it as risky), when the server
  cannot be reached or does not answer in time, the repository or folder cannot be read, a git command points git at
  another repository (`-C`, `--git-dir`, `--work-tree`) or uses an alias, or a shell line has parts the guard cannot
  evaluate. The Claude Code hook asks for confirmation in those cases (and when it cannot follow the line, or the check
  does not finish within `EKBASIS_HOOK_DEADLINE`) instead of staying silent. Opt out with `--fail-open`,
  `fail_closed=False` or `EKBASIS_FAIL_OPEN=1`. New: `ekbasis.client.CannotJudge`, the CLI's `--timeout`.
- **Recap** (opt-in): `prompts.recap(question, rules)`, `recap_all`, `simulate(..., recap=...)`, `ekbasis predict
  --recap`: the rule that decides the answer, repeated right before the question.
- **Compare in code**: `simulate.threshold(...)` tracks a number step by step and decides `quantity <op> limit` in code
  (`when="end" | "ever" | "before_last"`); `prompts.number` builds numeric questions.
- **Shell guard (prototype)**: `ekbasis.shell.check`, `ekbasis shell-check`, and the hook's opt-in
  `EKBASIS_SHELL_GUARD=1`. The state lists what a line could touch without any file content (fingerprints keyed anew
  for each check), writes out the shell's expansions, and adds bash rules only where needed.
- **Docs**: the guards are a warning layer that can be wrong, not a security boundary; use them with confirmations,
  backups and least privilege.
- **Measured** (pre-registered; the shell confirmation set was generated after the client was frozen):
  - shell guard, 292 fresh scenarios of 46 command forms: content lost right 91.4%, losses flagged 93.2% with 11.9%
    false alarms, failures right 96.2%; a list of destructive commands: 54.8% right, 82.0% flagged, 67.9% false alarms;
    no file content in any prompt;
  - compare in code, 1,299 fresh items: 98.2% right (84.4% asking the model directly, 91.8% with `simulate`), 98.2% at
    the limit;
  - recap, fresh items: +1.2 points with nothing broken on single-rule worlds, +2.2 points with 26 of 1,120 answers
    broken on chains and line captures: it stays opt-in.

  With the defaults, every request 0.1.1 sends is unchanged.

## 0.1.1

The git guard now sees what `git status` does not show, and is told a few git rules its training did not cover. Same
model, server, questions and thresholds.

- **Facts in the state**, only when they exist or a command could touch them:
  - ignored files, for `git clean -x/-X`, `git stash -a`, `git sparse-checkout`, or a target ref that tracks the same
    path;
  - untracked or ignored files that a target ref also has, with the same or different content;
  - linked worktrees and submodules, with their own `git status`;
  - whether a conflicted file still has conflict markers or was resolved by hand;
  - cherry-pick, revert and am sessions (0.1.0 called an am session a rebase);
  - for `git pull` and `git push`: ahead/behind the upstream, and `pull.rebase`/`pull.ff`.
- **Notes**: one plain-text git rule for each command form outside the training data that needs it, after the command
  list. Examples: `switch -f`, `reset --merge <commit>`, `rebase --abort`, `clean -x`, `worktree remove`,
  `submodule update`, `git pull` with no mode. Trained command forms get no note, so their prompts are unchanged.
- **API**: `git.check(..., facts=True, notes=True)`. With `facts=False, notes=False` it gives 0.1.0's description and
  prompt byte for byte. New `git.inspect()`; `repo_state()` keeps its signature.
- **Measured** on 334 fresh sandbox scenarios (pre-registered, generated after the client was frozen, the truth from
  running git):
  - work-losing commands flagged: 59.8% → 87.4% (where 0.1.0's state hid the deciding fact: 28.9% → 79.0%);
  - false alarms: 8.9% → 8.1%;
  - "fails" right: 81.4% → 90.9%.

  The release evaluation's prompts are unchanged: git3 96.55%, guard set 827/863 and 766/799. What still fails is in
  the README's Limits section. Details: [results/client_0.1.1/RESULTS.md](results/client_0.1.1/RESULTS.md).

## 0.1.0

First release.
