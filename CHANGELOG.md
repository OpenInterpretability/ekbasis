# Changelog

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
