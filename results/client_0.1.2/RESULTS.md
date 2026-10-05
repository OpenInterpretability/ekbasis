# Client 0.1.2 candidate: results

Measured 2026-10-05 on the rig with the released weights (w4a5, bf16) behind the shared eval server (serve.py 1.3,
one vLLM replica on GPU 1, at most 16 requests in flight); the truth from running bash 5.2 and GNU coreutils 9.4. Plan,
criteria and data: [SPEC.md](SPEC.md), written before any model run. The client was frozen at 13:37 BRT
([FROZEN.sha256](FROZEN.sha256)) after the dev pass and before the confirmation set was generated. Nothing is
published. 0.1.1 has no shell guard, so "before" is what an agent has without it: the keyword lists, always "no", and
on the dev set the capability map's own run (the released model, the same scenarios, the full file contents shown,
no facts and no notes).

## Shell guard

Questions: is any file content lost for good (scored at 0.5; flagged at the guard's 0.2), does each line fail. Counts
in brackets.

**Confirmation set** (292 scenarios, 28 families, 46 command forms that shell_wild does not have, 133 that lose
content; generated once after the freeze, run once):

| | Content lost: right | Losses flagged (0.2) | False alarms (0.2) | Fails: right | Errors at ≥ 0.9 |
|---|---|---|---|---|---|
| **Guard (0.1.2, with notes)** | **91.4%** (267/292), CI 87.7–94.1 | **93.2%** (124/133) | **11.9%** (19/159) | **96.2%** (281/292) | 72.2% (26/36) |
| Guard without the notes | 87.7% (256/292) | 86.5% (115/133) | 11.3% (18/159) | 94.9% (277/292) | 72.5% (37/51) |
| Keyword list, cautious | 54.8% (160/292) | 82.0% (109/133) | 67.9% (108/159) | — | — |
| Keyword list, narrow | 54.5% (159/292) | 22.6% (30/133) | 18.9% (30/159) | — | — |
| Always "no" | 54.5% (159/292) | 0% | 0% | — | — |

Criteria: C1 no file content in any prompt (0 of 292, and 0 of 2 × 408 on dev) **met**; C2 ≥ 85% and ≥ 5 points above
the best baseline (91.4% vs 54.8%) **met**; C3 recall ≥ 85% with false alarms ≤ 15% (93.2% / 11.9%) **met**; C4 fails ≥
85% (96.2%) **met**; C5 no "cannot judge" (0) **met**.

What it still gets wrong on the confirmation set:
- **Copies and moves into a folder that replace a same-named file**: `cp -a SRC DEST` when DEST/SRC holds a file of the
  same name (5 of 5 missed), `cp -t DIR FILE` (3 of 3) and `mv -t DIR A B` (1) when DIR holds one. The guard writes out
  rsync's target folder but not cp's and mv's.
- **False alarms where the outcome depends on content it does not show**: `head -n 9 f > f.tmp && mv f.tmp f` on a file
  of 9 lines or fewer (4), `perl -pi -e 's/x/y/'` when no line matches (4; the pattern counts cover sed and grep only),
  and a backup taken before (`cp f f.orig && head … && mv`, 4).
- Other false alarms: `rsync --remove-source-files` with no collision (3), `truncate -s +N` (3), `rsync --delete
  --exclude` keeping the excluded file (1).
- "Fails" errors: `xargs -I{} mv {} DIR/ < list` and `xargs mv -t DIR < list` (10 of 11 errors).
- Errors come with confidence: 26 of its 36 errors at ≥ 0.9.

**Dev set** (shell_wild's 408 scenarios, 84 forms; designed on, so optimistic):

| | Content lost: right | Losses flagged (0.2) | False alarms (0.2) | Fails: right |
|---|---|---|---|---|
| Capability map's run (contents shown, no facts, no notes) | 85.5% (349/408) | 85.2% (109/128) | 14.3% (40/280) | 92.3% (410/444) |
| Guard, first design, without / with notes | 89.2% / 92.9% | 93.8% / 99.2% | 13.6% / 11.4% | 90.3% / 94.1% |
| **Guard, frozen design, without / with notes** | 91.9% / **96.6%** | 93.8% / **100%** (128/128) | 9.3% / **6.1%** (17/280) | 91.9% / **97.7%** |
| Keyword lists (cautious / narrow), always "no" | 45.6% / 68.1%, 68.6% | 91.4% / 55.5% | 75.4% / 26.1% | — |

Changes between the first design and the freeze, each from a dev failure and stated in general terms, none written for
a confirmation form:
- facts of where rsync copies (the contents or the folder itself), what `--delete` removes, and dry runs;
- for sed and grep, how many lines a pattern from the command matches in the files it names (counts only);
- what `find … | xargs` passes here (names split at spaces, or no name at all), for the find expressions the guard
  can follow;
- the refuse note extended (a folder moved or copied onto a file, several sources without a folder, ln onto a name
  that exists);
- new notes for `rm -f` and `cp -u`, and for `cat f >> f`;
- the `-n` note corrected: on coreutils 9.4, `cp -n` exits 0 and `mv -n` exits 1. It had said both fail; this was
  measured on the rig, and the note now names exit statuses only for 9.4.

## Recap (dev, fresh items; no confirmation in this round)

| Items | No recap (as 0.1.1) | Recap of the deciding rule | Fixed | Broken |
|---|---|---|---|---|
| habit_vs_rule worlds, variants 8–11 (988) | 97.4% | 98.6% | 12 | 0 |
| rules_stress rule kinds, new seed (1,120) | 86.7% | 88.9% | 51 | 26 |

R1 (broken ≤ 1% of items): met on habit (0%), **not met on rules_stress (2.3%)**, mostly in captures along a line and
short chains. Recap stays opt-in; the docs say it helps on balance and is best kept to the rule known to decide.

## Compare in code (dev, 1,299 fresh accumulation items)

| | All items | At the limit (d = −1, 0) | Both sides of the limit right |
|---|---|---|---|
| A: asking the model the outcome once | 84.4% | 77.6% | 54.1% |
| B: 0.1.1's `simulate`, the model's own outcome | 91.8% | 87.2% | 73.7% |
| **T: `threshold`, the outcome decided in code** | **98.2%** | **98.2%** | **96.3%** |

T1 (≥ 97% overall, ≥ 95% at the limit) and T2 (≥ B + 5 points at the limit: +11.0) **met**. Weakest kind: budgets,
188/205 (91.7%), where the running total itself goes wrong.

## No regression and fail closed

- **Release prompts**: with the defaults, 0.1.2 sends the same requests as 0.1.1. The check covers git.check's
  description, notes, prompt and questions on 10 repository situations × 25 command lists, the 0.1.0 description with
  commit hashes and messages, 500 world prompts and simulate's requests. It passed offline
  (`results/release_equivalence_offline.log`) and on the rig against the frozen client
  (`results/release_equivalence.log`).
- **Fail closed**: the 58 package tests pass, on the Mac and on the rig. They include an unparseable command, a missing
  directory, a server that is down and a timeout, each giving "cannot judge" (exit 3; the hook asks), and the opt-outs.
- **Docs**: README, SECURITY.md and the hook's docs say the guard is a warning layer that can be wrong, not a security
  boundary.

## Files

`results/`:
- shell: `shell_confirm_items.jsonl`, `shell_confirm_{notes,no_notes}.jsonl`, `shell_confirm_summary.{json,md}`,
  `shell_dev_*` (frozen design) and `pass1_shell_dev_*` (first design);
- recap: `recap_dev.jsonl`, `recap_dev_summary.json`;
- threshold: `threshold_dev.jsonl`, `threshold_dev_summary.json`;
- checks: `offline_checks.json` and the equivalence logs.

Every prompt the guard sent is in the shell result files.
