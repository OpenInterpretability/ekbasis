# Client 0.1.6: preflight, confirmed on new tasks (the study ran the 0.1.5.dev0 candidate; changes after it are listed under Limits)

Pre-registered study (SPEC_confirmation.md, frozen before the first session): Claude Code agents (`claude -p`, sandboxed,
`bypassPermissions`) on 20 new hand-written tasks (14 traps, 6 controls; none overlaps any training set or the first
preflight study). In a trap, the obvious way (the script or SQL the user names) fails midway and leaves the change half
applied. Arms: no hook (C), preflight v2 (PF), and a placebo that pauses on every multi-step change (PL). Truth from
the final state, read by code. US$ 5.84 for 186 sessions.

| Agent, arm | Damage in traps | Tasks done | Controls warned | Warnings (right) |
|---|---|---|---|---|
| Haiku 4.5 (no extended thinking), none | 23/28 | 17/40 | 0/12 | 0 |
| **Haiku 4.5, preflight** | **3/28** | **34/40** | **0/12** | 27 (26) |
| Haiku 4.5, placebo pause | 18/28 | 17/40 | 12/12 | 60 |
| Sonnet 5.5, none | 5/14 | 8/20 | 0/6 | 0 |
| **Sonnet 5.5, preflight** | **1/14** | 7/20 | **0/6** | 7 (7) |
| Sonnet 5.5, placebo pause | 1/14 | 6/20 | 5/6 | 17 |

Pre-registered bars (paired bootstrap over tasks, 95% CI), all passed:
- H1, Haiku damage, preflight − none: −71.4 points [−92.9, −50.0], a cut of 87%.
- H2, Haiku tasks done: +42.5 points [+22.5, +65.0].
- H3, Haiku controls warned: 0 of 12.
- H4, Haiku damage, preflight − placebo: −53.6 points [−75.0, −32.1].
- H5, Sonnet sessions with a needless warning: 0 of 20.

Sonnet's damage fell by 28.6 points [−50.0, −7.1]. Its tasks done changed by −5.0 points [−15.0, 0.0] (one session):
with any pause it stops and asks.

How the warnings were made:
- **Most traps (9 of 14) ran on a copy,** which is exact.
- **Commands that cannot run on a copy** (here, scripts that call a local HTTP endpoint or use a tool outside the local
  allowlist) were caught in 58 of 69 cases. Code-stated facts decided 37 of those; 4 of 51 warnings were needless.
- **The model alone caught** an unzip into a folder where a name is a file (17 of 17).
- **The model alone missed** macOS (BSD) `sed -i` taking the next word as a suffix (3 of 14).

Limits:
- **The tasks are ours.** The requests name the script or SQL to run.
- **One machine:** macOS 26.3 on Apple silicon, with the sqlite3 shell 3.51.0.
  - The agents' sessions ran inside a sandbox of their own. sandbox-exec cannot nest, so preflight's runs on a copy
    ran confined by that session sandbox, not by preflight's own.
  - Of the 9 traps that ran on a copy, 6 are SQL and 3 are shell (photo_backup, unpack_batch, app_config); 2 of the 6
    controls are shell plans that ran on a copy. On Linux, shell plans are always judged by Ekbasis (see the change
    below), and that path was not measured with agents on those 3 traps and 2 controls. On the first study's 20 task
    commands, with copies off, it warned on 14 of 14 traps and on 0 of 6 controls.
  - SQL plans run on a copy on Linux where the sqlite3 command-line tool is installed (unit tests only).
- **A destructive plan that does not fail is not preflight's subject.** One agent, warned correctly, deleted orders to be
  able to delete a customer.
- **Change after the study (not measured with agents, covered by a test).** A command that was warned once goes through
  when run again in the same session. That rule now keys on the command and on what it would run, so an edited script
  or SQL file is checked again.
- **Change after the study: runs on a copy never touch real files.** It was found before release.
  - **The problem.** Without a sandbox, the run on a copy executed shell steps unconfined. A step that wrote an
    existing file outside the folder wrote the real file during the check (reproduced on Linux). Such a step uses an
    absolute path, `..`, a symbolic link or `xargs` over a list.
  - **Shell steps now.** They run on a copy only inside sandbox-exec, which allows no network and writes only in the
    copy; the per-user temporary folder is no longer writable either. Without the sandbox, or when it cannot start,
    Ekbasis judges the plan. Nor does a step run on a copy if it would start a program outside the allowlist (`xargs`
    or `find -exec` with one, `awk` with `system()`, options of tar, zip, sort or git that name a program). A write the
    sandbox refuses sends the plan to Ekbasis too, instead of counting as the step's failure.
  - **SQL now.** SQL that writes other files (VACUUM INTO, zipfile) no longer runs on a copy, and SQL copies run inside
    the sandbox on macOS. Without the sqlite3 command-line tool, a sqlite3 line fails before any statement runs:
    preflight says so and does not warn.
  - **What changed in the results.** Nothing measured. Re-run on every multi-step command of both studies (637 plans,
    on the snapshot taken before each command), no plan moved between the copy and the model, and all 496 runs on a
    copy found the same first failure ([copy_regress_summary.json](copy_regress_summary.json)).

The first study (0.1.4.dev0, not released): the same design on 20 other tasks cut Haiku's damage (16/28 → 6/28 trap
sessions), but interrupted Sonnet 25 times needlessly and missed three kinds of shell trap. That is what led to this
version.
