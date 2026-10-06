# Check when sure: `ekbasis.verify` (since client 0.1.4)

## What it decides

For an answer the model gives with confidence ≥ 0.9: should you check it by real execution (or by looking) before
acting on it? Answers below 0.9 already fall under "look when unsure", and `check` returns `verify=True` for them with
no extra request.

## The policy (frozen; `ekbasis/verify_policy.json`)

| Signal | Value | Cost |
|---|---|---|
| family | (errors + 1) / (observed + 2) for the answer's question family, from `FamilyTracker` | none |
| stability | 1 − the lower probability of the same answer when the options are shown in reverse order and when the question gets the prefix "Answer from the rules and the state above. " (both in one request) | 1 request |
| self-check | P(no) to `Consider this question: "<question>" Is "<answer>" the correct answer?` (options yes/no) | 1 request; not for git and shell |

How the decision is made:
- Each value is placed at its percentile among fixed reference answers: a weighted mid-ECDF of the development answers
  of the test.
- The score is the mean of these percentiles; verify when the score reaches the threshold of `rule`.

| `rule` | Threshold | How it was fitted (development data only) |
|---|---|---|
| `"domain"` (default) | rules 0.6056, sql 0.4836, shell 0.6571, git 0.7675, totals 0.7361; any other domain 0.6414 | equal recall in every domain, the largest one whose overall verified share is ≤ 25% |
| `"conformal"` | per family group: a family with ≥ 10 development errors, else the domain's rest | the k-th smallest error score, k = ⌊0.15 (n + 1)⌋; per group P(caught \| confident error) ≥ 0.85 under exchangeability |
| `"global"` | 0.6414 | maximise min(caught − 0.80, 0.30 − verified) |
- The self-check is not used for git and shell, a choice also made on development data before the test. On fresh git
  it was misleading: AUROC 0.33.

`check_steps` (questions about several actions):
- Ask the question directly about all the actions, then follow them one at a time with `simulate`.
- Verify when |P_direct(answer) − P_step_by_step(answer)| ≥ 0.0334.

## The test it passed (pre-registered: [`SPEC_confirm.md`](../results/client_0.1.4/SPEC_confirm.md), 2026-10-06)

- **Items.** New items came from new seeds of five capability generators (rules, SQL, shell, git, running totals),
  checked by hash to share neither prompt nor state with any development question.
- **Population.** 18,642 confident answers, 1,224 of them wrong, weighted to the development mix of the suites.

| | Caught | Verified | AUROC |
|---|---|---|---|
| Policy at τ | 84.9% (82.7–87.0) | 23.4% (22.8–24.0) | 0.909 |
| Confidence alone | 80% needs 50.9% verified | — | 0.771 |
| `check_steps` on running totals | 87.9% (82.7–92.5) | 22.8% (20.6–25.1) | 0.948 |

Per suite at τ (caught / verified):
- rules 81.9% / 10.3%;
- SQL 68.9% / 27.7%;
- shell 82.4% / 24.2%;
- git 94.2% / 33.5%;
- running totals 98.1% / 59.5% (`check_steps` is the better tool there).

## What the numbers do not cover

- **Family keys.**
  - The test used the evaluation's family labels, e.g. the git scenario type and the question.
  - The client's keys are different: `git_family` gives the git subcommands plus the question, `shell_family` the
    programs plus the question, or you supply your own.
  - The client's keys are not measured yet.
- **History.**
  - The test started from 29,029 evaluation answers and then learned online.
  - An empty tracker gives every family 0.5, so new families are checked more until outcomes come in.
  - A cold start was also measured in the test: AUROC 0.889, 85.0% caught with 27.3% verified. It still assumed every
    earlier outcome was known.
- **Blocked actions.**
  - A guard that blocks a command never sees what it would have done. Call `unobserved()` for it, never `observe()`.
  - The blocked commands are the ones that looked risky, so a family's observed error rate can be too low. The reasons
    say when a family has unobserved answers.
  - Label some of them: `audit(rate)` picks a random share of the blocked actions to replay in a sandbox (a copy of the
    repository or folder). Only that real outcome goes to `observe()`. Audits of accepted answers work the same way.
  - Blocking also changes what an agent proposes next, so rates and thresholds learned offline may not hold in a live
    loop. That needs a live agent study.
- **Model version.** The reference distributions and thresholds belong to w4a5 and were measured on its bf16 build;
  with the FP8, INT4 and MLX builds they are untested. A new model version needs them re-fitted: conformal-style
  guarantees hold per model version.
- **Domains and traffic.** New kinds of questions and real traffic are not measured.

## Second fresh test (confirm-2, 2026-10-06; [`SPEC_confirm2.md`](../results/client_0.1.4/SPEC_confirm2.md))

New seeds, excluding by hash every item of dev and of the first test. 18,615 confident answers, 1,202 of them wrong.

| Rule | Caught | Verified | Pre-registered criterion |
|---|---|---|---|
| `domain` (now the default) | 84.5% | 22.6% | ≥ 80% / ≤ 30%, every domain ≥ 75%: passed |
| `conformal` | 86.3% | 26.2% | ≥ 85%, every domain ≥ 80%: passed |
| `global` (the first default) | 83.5% | 23.4% | the first test replicated |
| Confidence alone, at 23.4% verified | 65.7% | 23.4% | |
| Abstain instruction ("choose unsure if unsure") | 1.0% | 0.1% | the score beats it |

Per domain under `domain`, caught / verified:
- rules 85.5 / 12.8;
- sql 87.6 / 50.3;
- shell 79.9 / 21.6;
- git 83.7 / 20.1;
- totals 87.0 / 44.4.

A Learn-then-Test acceptance rule did not pass as pre-registered:
- **Target:** ≤ 2% errors among the answers acted on without checking.
- **Overall:** 1.16%.
- **Where it failed:** rare rule families that fell back to their suite's threshold reached 3.4%.

The fix is pre-registered for a third test.

## Overlap with training

The items of the development set (29,029 rows), of the first test (19,825) and of confirm-2 (19,790) were checked
against every training file of w4a5's lineage: 2.2M rows, a superset of what the model was trained on. No item was
identical to a training item, and none was a near-duplicate (word 8-grams, Jaccard ≥ 0.5). The same code, run on an
item set known to overlap a training file, finds that overlap. Report:
[results/client_0.1.4/firewall](../results/client_0.1.4/firewall/RESULTS_firewall.md).

Pre-registrations, frozen hash lists, deviations, analysis code and result files:
[results/client_0.1.4](../results/client_0.1.4/RESULTS.md).
