# Changelog

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
