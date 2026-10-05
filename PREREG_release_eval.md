# Pre-registration: Ekbasis release evaluation

Written on 2026-10-03 (about 13:40 BRT), **before** the test results of the candidate V42 were read and **before** any
model was run on the fresh scenarios T3c. Everything below is fixed now; any later change is reported as a deviation.

## Candidates and selection rule

- **V41**: Eikos-27B + consequence adapter (synthetic worlds, git sandbox v1/v2, read-once layout "turns").
- **V42**: V41 continued on git sandbox v3, whose repository state also shows, for every other branch and the remote, the
  files that differ and the files changed on both sides since they split.

**Rule.** V42 is released if, on the git v3 held-out tests (`git3_test_known` and `git3_test_held` together), its mean
accuracy over the `lost`, `fails` and changed-state questions is at least V41's, **and** it loses no more than 2 points
against V41 on any of: `git2_test_known`, `git2_test_held`, `ftest_family`, `ftest_in`, and the answers that change in
`multi_test_trainfam` and `multi_test_testfam` (one prompt per question and read-once). Otherwise V41 is released.

## How the released model is evaluated

The exact release weights (adapter fused into Eikos-27B), served by vLLM and the System One API (`serve.py`), reached
through the `ekbasis` client. Decision threshold 0.5 unless stated; the git guard flags "risky" at P(lost) ≥ 0.2.

### Primary

1. **Git guard on fresh real-repository scenarios (T3c, 16 scenarios on a clone of `pallets/itsdangerous`, real
   execution for the truth; 3 lose uncommitted work, 5 commands fail).** Reported: work-losing scenarios flagged risky
   (out of 3), false alarms among the other 13, `fails` accuracy (out of 17 commands). Repository state as the client
   renders it by default (commits shown as hashes, remote fetched).
2. **Git v3 held-out tests**: accuracy per question type (`lost`, `fails`, `in_progress`, changed state) for known and
   held command types; AUROC of P(lost) and the share of work-losing cases caught at a 10% false-alarm rate.
3. **Honest consequence accuracy** (only the answers the actions change) on never-trained world families
   (`multi_test_testfam`, `ftest_family`), one prompt per question and read-once.

### Secondary

- Injection robustness on T3c: the share of `lost` and `fails` decisions that change when an instruction is planted
  (a) in an untracked file's name, (b) in a branch name, (c) in commit messages with `commit_text="message"`; and
  work-losing scenarios that drop below the 0.2 flag.
- Long chains (100 and 200 actions; exact whole state per step), speed (latency one at a time, throughput at 16 in
  parallel, one RTX 6000 Pro), Portuguese, chains that start from an image.

### Reporting

All results are reported, favourable or not. Accuracies over at least 100 items come with 95% bootstrap intervals;
smaller sets are reported as counts. Comparisons with other systems (Claude and Qwen models on the same 240 git
questions) are reported with their method and caveats (hand-off answering in batches; answer order shuffled).
