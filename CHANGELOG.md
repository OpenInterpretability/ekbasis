# Changelog

## [Unreleased]

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
