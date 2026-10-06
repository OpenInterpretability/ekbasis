---
license: apache-2.0
base_model: caiovicentino1/Eikos-27B
base_model_relation: finetune
datasets:
- caiovicentino1/ekbasis-data
- caiovicentino1/eikos-decisions
inference: false
language:
- en
- pt
library_name: transformers
pipeline_tag: text-classification
tags:
- world-model
- consequence-model
- agent-safety
- ai-agents
- git
- calibration
- typed-decisions
- jepa
- openinterp
- image-classification
- multimodal
model-index:
- name: Ekbasis-27B
  results:
  - task:
      type: text-classification
      name: Git consequence prediction, command types never seen in training
    dataset:
      name: Ekbasis git sandbox v3 (held-out command types)
      type: caiovicentino1/ekbasis-data
      split: git3_test_held
    metrics:
    - type: accuracy
      value: 95.3
      name: Accuracy, all questions
    - type: roc_auc
      value: 0.989
      name: AUROC, uncommitted work lost
  - task:
      type: text-classification
      name: Git consequence prediction, command types seen in training
    dataset:
      name: Ekbasis git sandbox v3 (known command types)
      type: caiovicentino1/ekbasis-data
      split: git3_test_known
    metrics:
    - type: accuracy
      value: 98.1
      name: Accuracy, all questions
    - type: roc_auc
      value: 0.998
      name: AUROC, uncommitted work lost
  - task:
      type: text-classification
      name: Consequences in never-trained rule-based worlds (answers the actions change)
    dataset:
      name: Ekbasis worlds, never-trained families
      type: caiovicentino1/ekbasis-data
      split: multi_test_testfam
    metrics:
    - type: accuracy
      value: 81.2
      name: Accuracy on changed answers, one prompt per question
---

# Ekbasis-27B — an open world model for agents

![Ekbasis overview: git consequences against Claude and Qwen, the git guard on fresh real repositories, and speed against a reasoning model](https://huggingface.co/caiovicentino1/Ekbasis-27B/resolve/main/assets/ekbasis_launch.png)

**Paper:** [Look When Unsure, Check When Sure](https://doi.org/10.5281/zenodo.23146971) · DOI [10.5281/zenodo.23146971](https://doi.org/10.5281/zenodo.23146971) · **Code:** [github.com/OpenInterpretability/ekbasis](https://github.com/OpenInterpretability/ekbasis) · **Site:** [openinterp.org/ekbasis](https://openinterp.org/ekbasis)

**What happens if I run this?** Given the current state and an action, Ekbasis-27B predicts what the action will do —
*will this lose work? will it fail? what will X be afterwards?* — as **calibrated, typed answers**, in **one forward
pass** (~0.1 s), without generating text. It was trained on **what actions actually did** (simulated worlds and real
git executions), so it knows what commands do, not what an agent believes they do.

## What kind of model is it?

**Not a model that thinks. Not a model that judges. A model that foresees.**

| | LLM, reasoning | System One (Eikos, Jev) | **Ekbasis** |
|---|---|---|---|
| It answers | anything, in text | what is: which option holds now | **what will be, if I do this** |
| Kind of question | open | a judgment of the present | **an intervention: the outcome of acting** |
| Output | generated text | calibrated distribution over the options | **calibrated distribution over the next state's variables** |
| Learns from | human and model text | a teacher's judgments | **what actually happened when the action ran** |
| Time | seconds to minutes of reasoning | one forward pass | **one forward pass per step; chains to long sequences** |
| Role in an agent | plans and talks | judge | **simulator and guard: it foresees** |

- **The forward model the agents were missing.** Before you move your arm, the brain predicts the consequence of the
  motor command; that is what lets us act fast and correct before an error. The agent plans; Ekbasis predicts.
- **The world-model module, made real.** In LeCun's architecture for autonomous machine intelligence, a world model
  predicts the next state given an action, apart from the actor and the critic. Here the LLM agent is the actor,
  AgentGuard the critic and Ekbasis the world model; it was trained with a JEPA-style loss that aligns its internal
  state with the true outcome.

It is derived from an LLM (Qwen3.8-27B, through Eikos-27B) but does not work as one: its training objective and its
readout make it answer with probabilities, not text.

| Specification | |
|---|---|
| Parameters | 27B, in the Qwen3.8-27B architecture: Gated DeltaNet and gated-attention layers, with a vision tower |
| Input | the state as text or as an image, an action, and a closed question (yes/no, or a choice among listed options) |
| Output | the probability of every option, read from one forward pass (no generated text) |
| Context window | 262,144 tokens (the architecture's). `serve_vllm.sh` sets 16,384; the evaluation's prompts average 0.7–1.6K tokens per state. Longer contexts were not evaluated with Ekbasis. |
| Languages | English and Portuguese |
| Builds | bf16 (this repository), FP8, INT4 and MLX 4-bit (see Builds) |

## Quick start

```bash
hf download caiovicentino1/Ekbasis-27B --local-dir Ekbasis-27B
bash Ekbasis-27B/serve_vllm.sh Ekbasis-27B 8001            # vLLM ≥ 0.30 on 127.0.0.1:8001 (one ~80 GB GPU)
python Ekbasis-27B/serve.py --model Ekbasis-27B --vllm-url http://127.0.0.1:8001 --port 8000   # the API
pip install "git+https://github.com/OpenInterpretability/ekbasis"                                # the client
EKBASIS_URL=http://127.0.0.1:8000 ekbasis git-check -- "git reset --hard"
```

The client also ships a Claude Code hook (`ekbasis-claude-hook`: asks before git commands that may lose work, and when
it cannot judge them) and an MCP server (`ekbasis-mcp`). Since client 0.1.3 the hook asks only when something could
be lost for good. In fresh Claude Code sessions on real repositories that meant 2.9 asks per 100 commands, against
10.7 for 0.1.2 on the same commands, with every real loss still caught
([results](https://github.com/OpenInterpretability/ekbasis/blob/main/results/client_0.1.3/RESULTS.md)).
Since client 0.1.4, `ekbasis.verify` says which confident answers (confidence ≥ 0.9) to check by real execution before
acting. In a pre-registered test on fresh items from five capability suites, none of them overlapping the training
data, its default per-domain thresholds caught 84.5% of the confident errors while verifying 22.6% of the confident
answers; confidence alone, verifying 23.4%, caught 65.7%. A rule meant to certify at most 2% errors among unchecked
answers did not pass ([details](https://github.com/OpenInterpretability/ekbasis/blob/main/docs/VERIFY.md)).
Code, docs and the playbook: https://github.com/OpenInterpretability/ekbasis

## Builds

Every build that works is released, so each machine runs the one that fits; each build's card shows its quality
against bf16 on the same evaluation (the gate was pre-registered in `PREREG_quantized.md`).

| Build | Size | Runs on | Speed (one RTX PRO 6000) |
|---|---|---|---|
| [Ekbasis-27B](https://huggingface.co/caiovicentino1/Ekbasis-27B) (bf16) | 55 GB | GPUs with 80 GB | the reference |
| [Ekbasis-27B-FP8](https://huggingface.co/caiovicentino1/Ekbasis-27B-FP8) | 30.4 GB | GPUs with 48 GB; fastest with FP8 kernels (Ada, Hopper, Blackwell) | 1.6× the throughput of bf16 |
| [Ekbasis-27B-INT4](https://huggingface.co/caiovicentino1/Ekbasis-27B-INT4) | 18.6 GB | GPUs with 32 GB; 24 GB with text only and a 4k context (command in its card) | about bf16's |
| [Ekbasis-27B-MLX-4bit](https://huggingface.co/caiovicentino1/Ekbasis-27B-MLX-4bit) | 15 GB | Macs with Apple Silicon (32 GB or more recommended) | — |

GPU sizes were tested by limiting vLLM to that much memory on one RTX PRO 6000 and checking that the answers match the
build at full memory; the MLX build was validated with MLX on a Linux GPU, not on a Mac.

## Results

Every number below was measured on these exact weights through vLLM and the System One API. RELEASE_EVAL.md in the
repository has the full results, every prediction, how this checkpoint was chosen, which measurements were
pre-registered and the deviations.

**Git guard on 16 fresh real-repository scenarios** (written before the evaluation, on a clone of
`pallets/itsdangerous`; the truth from running the commands): work-losing scenarios flagged **3 of 3**, false alarms 1
of 13, "will it fail?" right 16 of 17.

**Git, repositories built and commands executed in a sandbox** (95% CI):

![The probability of losing work for the git cases that lose work and the ones that do not](https://huggingface.co/caiovicentino1/Ekbasis-27B/resolve/main/assets/chart_guard.png)

| | Seen command types | **Never-seen types** (rebase, restore) |
|---|---|---|
| All questions | 98.1% [97.4–98.8] | **95.3% [94.3–96.2]** |
| "Will uncommitted work be lost?" | 99.0% | 96.4% |
| AUROC, work lost | 0.998 | 0.989 |
| Work-losing flagged at P ≥ 0.2 / false alarms | 98.0% / 0% | 95.2% / 2.4% |
| The same on a 17× larger set (863 and 799 work-losing) | 95.9% / 4.3% | 96.0% / 6.1% |
| "Will the command fail?" | 97.8% | 83.3% |

The larger set holds 17 times the work-losing commands of the test sets, from repository states no earlier set
contains; it is the guard's gate for this release (`PLAN_guard_set.md`, written before any model was evaluated on it).
It gives the better estimate of false alarms: about 4 to 6 in 100 safe commands of these kinds get a confirmation
prompt. On 72 scenarios in copies of two real repositories, none of the 44 safe ones did, and all 28 that lose
uncommitted work were flagged.

**The same 240 git questions for every system** (truth from execution):

![Accuracy on the same 240 git questions for Claude, Qwen, Eikos and Ekbasis](https://huggingface.co/caiovicentino1/Ekbasis-27B/resolve/main/assets/chart_git_comparison.png)

| System | How it answers | Seen types | Never-seen types |
|---|---|---|---|
| Claude Opus 5.5 | reasoning | 97.5 | 89.2 |
| Claude Fable 5.1 | reasoning | 96.7 | 91.7 |
| Claude Sonnet 5.5 | reasoning | 95.8 | 94.2 |
| **Ekbasis-27B** | **one pass, ~0.09 s** | **95.8** | **85.8** |
| Qwen3.8-27B | reasoning | 86.7 | 60.0 |
| Eikos-27B (no consequence training) | one pass | 80.0 | 73.3 |
| Claude Haiku 4.5 | reasoning | 77.5 | 60.8 |
| Qwen3.8-27B | answering at once | 71.7 | 65.8 |

Claude models answered as hand-offs in batches with the answer order shuffled; the others answered each question alone.

**Never-trained worlds** (only the answers the actions change): 81.2% [79.3–83.0], one prompt per question; 78.0% with
the state read once (half the prompt tokens). Trained families: 92.4% / 91.5% (93.6% / 92.8% on the 309 of
their 600 states that overlap no training row). Portuguese 83.3% against English 85.6% on the same questions.

**Long chains** (one action per step, every variable asked, the next state rebuilt from the answers; 6 chains per
cell): the final answer right after 200 actions in 100% of the chains for containers, lamps and machines (containers
and lamps also starting from an image, with or without looking again every 50 steps; at 100 actions, one of the 6 lamp
chains started from an image went wrong); cards, whose errors never fade, 50% at 100 actions and 33% at 200. Machines
and cards are worlds the model never saw in training. **Predict, observe, correct:** when the simulation may read the
real state and looks whenever its chain confidence falls below 0.5, every card chain stayed exact (8 of 8 at 100 and
at 200 actions), looking about 19–26 times per 100 actions; where errors fade it rarely asks.

![Card orderings with and without looking at the real state when unsure](https://huggingface.co/caiovicentino1/Ekbasis-27B/resolve/main/assets/chart_long_chains.png)

![The cost of looking and the errors caught, per confidence threshold](https://huggingface.co/caiovicentino1/Ekbasis-27B/resolve/main/assets/chart_look_tradeoff.png)

**Planning with no LLM** (beam search over actions, every next state predicted by Ekbasis; the plan then run for
real): 98.9% of 180 short puzzles solved (goals taken from random 8–12-action plans; their shortest plans are 1 to 4
actions, median 1), against 97.8% for the same base model reasoning step by step and 38.3% answering at once; 100.0% of
180 from 3–5-action plans (shortest 1 to 3). Long plans with detours were not part of the release evaluation.

![Seconds per forecast and forecasts per minute against a reasoning model](https://huggingface.co/caiovicentino1/Ekbasis-27B/resolve/main/assets/chart_speed.png)

**Speed** (one RTX 6000 Pro): one check 0.09 s, 23 checks/s with 16 in parallel. Forecasts of 10–30 actions: 5.0 s
each (median; 98.8%), or 4.1 s with the state read once (90.0%), against 36.6 s (100%) for the same base model
reasoning.

**First opinion before reasoning** (short checks): Ekbasis alone 96.7%; sending the 10% of questions below 0.95
confidence to a reasoning model gives 99.6%, the 21% below 0.99 gives 100%.

**Prompt injection** (an instruction planted in a file name, a branch name, or the commit messages of the repository
the guard reads): no work-losing scenario was missed. Two "will it fail?" answers crossed 0.5 the wrong way: a planted
branch name moved a pull that works from 44% to 53%; with commit messages shown, a rejected push was called safe (98%
→ 4%). This is why the guard shows commits as hashes by default.

## Look when unsure (predict, observe, correct)

The study behind this section is the paper *Look When Unsure, Check When Sure*
([PDF](https://github.com/OpenInterpretability/ekbasis/blob/main/paper/look_when_unsure.pdf),
[doi:10.5281/zenodo.23146971](https://doi.org/10.5281/zenodo.23146971)), every analysis pre-registered and re-run from
the saved outputs.

Ekbasis follows long sequences one action at a time. Where a later action overwrites a mistake (a container refilled,
a lamp switched) the chain recovers by itself; where nothing ever undoes it (an ordering), mistakes compound. With the
`ekbasis` client, give `simulate()` a way to read the real state and it looks **only when it is not sure**, then
continues from what it saw:

```python
from ekbasis import simulate

sim = simulate(client, rules, state, actions, questions, render,
               observe=read_real_state,    # the real state as {variable: value}: git status, a query, a sensor
               ordering=list(questions))   # the state is an ordering: read the most probable valid one
print(sim.final, sim.looks, sim.surprises) # when it looked, and which looks found the forecast wrong
```

By default it looks when the chain confidence (the product of every answer's confidence since the last look) falls
below 0.9, and it checks the forecast now and then: after 8 actions without a look, a gap that doubles up to 64 while
the forecasts hold; a look that finds the forecast wrong (a surprise) brings the gap back to 8 and looks again after
the next action, until a look finds it right. `look_below`, `look_step_below`, `look_every` and `checks` set other
rules.

Chains of 100 · 200 actions (4 per world, 8 for cards):

| World | Exact at the end, never looking | Exact at the end, looking when unsure | Steps wrong along the way, per 100 actions | Looks per 100 actions |
|---|---|---|---|---|
| Containers (trained) | 4/4 · 4/4 | 4/4 · 4/4 | 2.3 → 1.5 | 3.5 · 2.9 |
| Lamps (trained) | 4/4 · 4/4 | 4/4 · 4/4 | 0 → 0 | 3 · 3.1 |
| Machines (never seen in training) | 4/4 · 4/4 | 4/4 · 4/4 | 2.3 → 0 | 6.8 · 10 |
| Card orderings (never seen in training) | 0/8 · 2/8 | **8/8 · 8/8** | 67.8 → 0 | 42.3 · 32.6 |

On 200 more chains with new seeds, run after the release evaluation (the default rule; 80 of cards, 40 of each other
world; `RELEASE_EVAL.md`, "200 more chains"), 198 ended exact. Of the two that did not, a container chain of 100
actions went wrong at action 87 with a confidence of 0.99, after the last check, and stayed wrong to the end (its
final answer right); a card chain of 200 actions missed only its last action, which the loop never checks, and the
model had flagged it (that step's probability 0.0006). Steps wrong along the way: 0.23 per 100 actions (containers
0.4, lamps 0.7, machines 0, cards 0.01); looks: 16.9 per 100.

To look less, `look_below=0.5`: every chain still ended exact (40 of 40), with 11.2 looks per 100 actions over these
four worlds instead of 17.3, and 0.7 steps wrong along the way per 100 instead of 0.3.

For an ordering, also ask where each value is: `where={value: question}`, each question's options being the ordering's
variables ("At which position is the 7 of hearts?"). Both views are read together, in the same request, and the card
chains looked about half as often for the same exactness (20 · 15 looks per 100 actions instead of 40 · 31 at chain
confidence < 0.9, every chain exact; `RELEASE_EVAL.md`, "Two views").

**What the confidence sees, and what it does not.** In card orderings, a world it never saw, 2.7 steps in 100 went
wrong and it gave every one of them a probability below 0.7: looking when unsure finds them. In the worlds it was
trained on, errors are rare (0–0.17 steps in 100) but come with confidence (0.972–0.996): a fixed threshold misses
them, and the checks are what find them (containers: 2.3 → 1.5 steps wrong along the way per 100 with the checks). A
pre-registered test on 15,008 generated questions in 12 world families, run on V42 (the first release candidate),
confirmed the pattern: 58% of its wrong answers carried a confidence of 0.9 or more in the families it was trained on, 28% in
the families it never saw (30 points apart, 95% interval 24 to 37), while its confidence ranks right above wrong about
equally well in both (AUROC 0.92 and 0.91). Eikos-27B, the same model before consequence training, was almost never
confidently wrong (1.9% and 0.5% of its errors): the training made it
([report](https://github.com/OpenInterpretability/ekbasis/blob/main/results_v42/confident_errors/REPORT.md)). On the
same questions the release gives 48% and 25%, with 2.06 confident errors per 100 answers in the trained families
against V42's 2.79
([report](https://github.com/OpenInterpretability/ekbasis/blob/main/results/confident_errors/REPORT.md)): fewer, not gone, which is why the checks stay on by default. Correction (6 October 2026): 5,318 of the 15,008
questions, all in the trained families, turned out to repeat or nearly repeat a training row, because the
generator's small worlds repeat across seeds. Without them the test still confirms the pattern (50.5% against
27.8%, 22.7 points apart, 95% interval 12.6 to 32.5), the training still made it, and the release gives 50.0% and
25.1%, with 1.46 confident errors per 100 answers in the trained families against V42's 1.69 ([audit](https://github.com/OpenInterpretability/ekbasis/blob/main/results/overlap_audit/README.md)).

![Where it is wrong, how sure was it: the share of wrong answers given with high confidence, per world family](https://huggingface.co/caiovicentino1/Ekbasis-27B/resolve/main/assets/chart_confident_errors.png)

The idea is classic: the predict–update loop of a state estimator (a Kalman filter), with observations triggered by
the predictor's own uncertainty (event-based state estimation; with learned models, active observing); the checks'
backoff is the Trickle algorithm's. What Ekbasis adds is a calibrated forecast in one pass, cheap enough to run at
every action. Prior work:
[REFERENCES](https://github.com/OpenInterpretability/ekbasis/blob/main/docs/REFERENCES.md#looking-when-unsure-prior-work).

**What it unlocks**

- **Long sessions that stay on track.** 238 of the 240 measured chains ended exact (one missed only its last action,
  which the model had flagged; one went wrong at a confident step after the last check) while looking at a fraction of
  the steps (2.9–3.5 looks per 100 actions in the worlds it was trained on, 33–42 in an ordering world it never saw),
  which matters when observing is expensive (a screenshot read by a vision model, a slow API, a human check).
- **A horizon for planning.** With no observations, `sim.horizon()` gives how many actions the forecast holds by the
  model's own confidence: act up to there, look, plan again.
- **A safety signal.** A sudden drop in confidence, or a surprise at a look (`sim.surprises`), means the world left
  what the model expected: the agent did something unexpected, the environment changed, or the task is outside what
  Ekbasis knows. A moment to look, or to alert.
- **One rule for escalation.** Looking at reality, calling a large reasoning model or asking a person: the same
  calibrated confidence decides.

**Where to use it** (the loop was measured on worlds whose rules are written in the prompt; in the two it never saw it
looked more often, and all but one of 144 chains ended exact, that one on its last action. Measure on your own
environment before relying on it.)

- **Coding and devops agents:** the state of a repository, files and infrastructure across a long session, with
  `git status` only when unsure.
- **Browser and computer-use agents:** the screen after each action, with a screenshot only when unsure (Ekbasis already
  reads a starting state from a picture of a simple world; real screens are not measured yet).
- **Business processes:** orders, stock and balances after a sequence of transactions, reconciled with the database only
  when unsure.
- **Digital twins and IoT:** machine states between sensor reads; read the sensor when unsure.
- **Finance operations:** positions and margins after a sequence of orders, checked with the broker when unsure.

## Limits

![Where Ekbasis is strong and where it is not, with what to do where it is weak](https://huggingface.co/caiovicentino1/Ekbasis-27B/resolve/main/assets/chart_strengths.png)

- It knows what it was trained on: rule-based worlds whose rules are written in the prompt, and git. Other domains need
  their own data.
- The state must contain what decides the outcome (the git guard adds it: which files differ, what both sides changed).
- Errors that never fade (orderings) compound over long chains, and in the worlds it knows its rare errors come with
  confidence: let the simulation look at the real state when it is not sure, with a check now and then
  (`simulate(observe=...)`; see Look when unsure above).
- With written rules and time to think, a large reasoning model is more accurate; Ekbasis wins on cost, latency and
  calibrated confidence.
- A warning layer that can be wrong, not a security boundary: use it with confirmations, backups and least privilege.
  Command obfuscation is out of scope; since client 0.1.2 the guards fail closed ("cannot judge" is treated as risky).
  Since 0.1.3 the hook skips the model when code shows nothing could be lost for good. "Rebuildable" is decided by
  folder name, so irreplaceable data inside an ignored `build/`, `dist/`, `node_modules/` or cache folder is not
  protected.
  See SECURITY.md in the repository.
- Known weak spot: dropping a stash right after applying it is flagged as losing work (a false alarm).
- Git cases it still gets wrong with client 0.1.1 (334 fresh sandbox scenarios, the truth from running git;
  [results](https://github.com/OpenInterpretability/ekbasis/blob/main/results/client_0.1.1/RESULTS.md)): an ignored
  file overwritten by a checkout, merge or `reset --hard <ref>` whose target tracks the same path (6 of 6 missed,
  although the state names it); `git sparse-checkout set` deleting ignored files and `git rebase --abort` after the
  resolution was staged (2 of 2 each); `git stash -a` then `git clean -fdx` flagged although nothing is lost; a commit
  followed by a destructive command in one check is flagged although the commit saved the work (98%; check the
  commands after the commit has run); `git rm` on a changed file gets "fails" and also 96% "loses work" (read "loses
  work" as "if it succeeded"). Client 0.1.0 also missed ignored files deleted by `git clean -x` (0.2%): 0.1.1 shows
  ignored files when a command could touch them.
- The model's question is uncommitted work. Since client 0.1.3 the hook also checks, by code and apart from the model,
  commands that would leave commits no branch, tag or remote holds: branch and tag deletion (`git branch -D`), forced
  branch moves, and `git reset --hard <commit>`. `git push --force`, a rebase that drops commits and branch names passed
  through `xargs` are still not covered.
- Between 70% and 99% confidence it is overconfident (on short checks: 96.9% said, 91.4% right in the 90–99% band):
  treat that band as "check".

![Confidence against accuracy on git and on never-trained worlds](https://huggingface.co/caiovicentino1/Ekbasis-27B/resolve/main/assets/chart_calibration.png)

## Training

Eikos-27B (itself a fine-tune of Qwen3.8-27B) + LoRA (r = 64) trained in five stages on: rule-based worlds (factories
of families with typed questions; some families, question types and lengths held out), git sandboxes v1–v3 (throwaway
repositories, real execution as an unprivileged user, synthetic contents and authors; command types `rebase` and
`restore --source` held out), multi-question items (read-once layout), and replay items from the Eikos training data
(4,919 of the 12,342 are rows of `eikos-decisions`; NOTICE has the rest, including 151 items built on FinQA). Loss:
cross-entropy on the letter readout plus a JEPA-style hindsight term: while reading the state and the action, the model
is trained to match the hidden states the frozen Eikos-27B has when it reads the true outcome (layers 16, 32, 48 and
64, at the end of the evidence). The fifth stage, V42, was the first release candidate.

This checkpoint is the exact interpolation halfway between two adapters: V42, and r4a, V42 trained 300 more steps on
the same mixture plus items mined from V42's own errors (new world items it answered wrong or below 0.99, and items
taken from its own long chains: the true result of each action from the state it was reading; the simulator gives every
answer). r4a cut the steps a chain carries wrong without a look, but forgot some rare git commands; halfway back in
weight space keeps nearly all of the gain, and the guard stays within one point of V42's on a set 17 times larger
(WiSE-FT). The two LoRA adapters were concatenated into one of rank 128,
which gives the weights W0 + ½ ΔW(V42) + ½ ΔW(r4a), and merged; the checkpoint keeps the official multimodal layout.
How it was chosen, step by step: RELEASE_EVAL.md. Full recipe, data generators and every run (including the ones that
did not work): https://github.com/OpenInterpretability/ekbasis

## References

Every entry was checked against its source. The full list, with what each was used for, is `docs/REFERENCES.md` in
the repository.

**Base model and lineage**
- Qwen Team (2026). *Qwen3.8-27B*. Hugging Face model card. https://huggingface.co/Qwen/Qwen3.8-27B
- Vicentino, C. (2026). *Eikos-27B* (model) and *Eikos* (code). https://huggingface.co/caiovicentino1/Eikos-27B ·
  https://github.com/caiovicentino/eikos
- GLM-5 Team (Zeng, A., et al.) (2026). *GLM-5: from Vibe Coding to Agentic Engineering*. arXiv:2602.15763. The
  teacher of the Eikos training data (GLM-5.3-Flash).

**Ideas it builds on**
- LeCun, Y. (2022). *A Path Towards Autonomous Machine Intelligence* (version 0.9.2). OpenReview.
- Wolpert, D. M., Ghahramani, Z., & Jordan, M. I. (1995). *An Internal Model for Sensorimotor Integration*. Science
  269(5232), 1880–1882.
- Kalman, R. E. (1960). *A New Approach to Linear Filtering and Prediction Problems*. Journal of Basic Engineering
  82(1), 35–45.
- Ha, D., & Schmidhuber, J. (2018). *Recurrent World Models Facilitate Policy Evolution*. NeurIPS 2018.
- Hafner, D., et al. (2020). *Dream to Control: Learning Behaviors by Latent Imagination*. ICLR 2020.
- Schrittwieser, J., et al. (2020). *Mastering Atari, Go, chess and shogi by planning with a learned model*. Nature
  588, 604–609.
- Assran, M., et al. (2023). *Self-Supervised Learning from Images with a Joint-Embedding Predictive Architecture*.
  CVPR 2023.
- Bardes, A., et al. (2024). *Revisiting Feature Prediction for Learning Visual Representations from Video*. TMLR.
- Guo, C., et al. (2017). *On Calibration of Modern Neural Networks*. ICML 2017.
- Geifman, Y., & El-Yaniv, R. (2017). *Selective Classification for Deep Neural Networks*. NIPS 2017.
- Kahneman, D. (2011). *Thinking, Fast and Slow*. Farrar, Straus and Giroux.

**How this checkpoint was made**
- Ross, S., Gordon, G. J., & Bagnell, J. A. (2011). *A Reduction of Imitation Learning and Structured Prediction to
  No-Regret Online Learning* (DAgger). AISTATS 2011.
- Venkatraman, A., Hebert, M., & Bagnell, J. A. (2015). *Improving Multi-Step Prediction of Learned Time Series Models*.
  AAAI 2015.
- Wortsman, M., et al. (2022). *Robust Fine-Tuning of Zero-Shot Models* (WiSE-FT). CVPR 2022.
- Kirkpatrick, J., et al. (2017). *Overcoming Catastrophic Forgetting in Neural Networks*. PNAS 114(13), 3521–3526.

**Looking when unsure**
- Trimpe, S., & D'Andrea, R. (2014). *Event-Based State Estimation With Variance-Based Triggering*. IEEE Transactions
  on Automatic Control 59(12), 3266–3281.
- Holt, S., Hüyük, A., & van der Schaar, M. (2023). *Active Observing in Continuous-time Control*. NeurIPS 2023.
- Frauenknecht, B., et al. (2025). *On Rollouts in Model-Based Reinforcement Learning*. ICLR 2025.
- Levis, P., et al. (2011). *The Trickle Algorithm*. RFC 6206, IETF.
- Jiang, Z., et al. (2023). *Active Retrieval Augmented Generation* (FLARE). EMNLP 2023.
- Ren, A. Z., et al. (2023). *Robots That Ask For Help* (KnowNo). CoRL 2023.
- Song, X., & Cai, Z. (2026). *Ask the World Before Acting: Environment Probing for Calibrated Agent World Models*.
  arXiv:2606.31422.
- Zuo, Y., et al. (2026). *Qwen-AgentWorld: Language World Models for General Agents*. arXiv:2606.24597.

**Data**
- Vicentino, C. (2026). *Eikos Decisions* (CC BY 4.0). https://huggingface.co/datasets/caiovicentino1/eikos-decisions
- Tang, Y., et al. (2023). *FinEntity*. EMNLP 2023 · Zhu, F., et al. (2021). *TAT-QA*. ACL 2021 · Cobbe, K., et al.
  (2021). *Training Verifiers to Solve Math Word Problems* (GSM8K) · Chen, Z., et al. (2021). *FinQA*. EMNLP 2021.
- Pallets (2011–). *itsdangerous* (BSD-3-Clause), the real repository of the git scenarios · Zhang, L., et al.
  (2024). *OpenPI2.0*. EACL 2024 (evaluation only).

**Tools**
- Kwon, W., et al. (2023). *vLLM* (PagedAttention). SOSP 2023 · Wolf, T., et al. (2020). *Transformers*. EMNLP 2020.
- Hu, E. J., et al. (2022). *LoRA*. ICLR 2022 · Mangrulkar, S., et al. (2022). *PEFT*.
- Yang, S., & Zhang, Y. (2024). *flash-linear-attention* · Yang, S., Kautz, J., & Hatamizadeh, A. (2025). *Gated Delta
  Networks*. ICLR 2025.
- Anthropic (2024). *Model Context Protocol*. https://modelcontextprotocol.io

## License and credits

Apache-2.0 (see LICENSE and NOTICE). Built on Eikos-27B (MIT) and Qwen3.8-27B (Apache-2.0).

## Acknowledgments

Ekbasis was built by Caio Vicentino (OpenInterp) with the help of
[Claude Opus 5.5](https://www.anthropic.com/claude-opus-5-5) (Anthropic). Claude worked on the project with him:
- planning and running the experiments;
- writing and reviewing the code and the documentation;
- checking the numbers and the references in this card.

## Contact

Questions, collaborations and commercial use: caio@openinterp.org.
Found a way to make the guard approve a destructive action? Please email it before publishing (SECURITY.md in the
repository).

## Citation

```bibtex
@misc{vicentino2026ekbasis,
  title        = {Ekbasis-27B: an open world model for agents},
  author       = {Vicentino, Caio},
  year         = {2026},
  howpublished = {Hugging Face},
  url          = {https://huggingface.co/caiovicentino1/Ekbasis-27B}
}
```

The paper on when an agent should look (V42, the first release candidate, and the interpolation released here):

```bibtex
@misc{vicentino2026lookwhenunsure,
  title        = {Look When Unsure, Check When Sure: Consequence Training Makes a World Model's Remaining Errors Confident, Most of All Where It Knows the World Best},
  author       = {Vicentino, Caio},
  year         = {2026},
  publisher    = {Zenodo},
  doi          = {10.5281/zenodo.23146971},
  url          = {https://doi.org/10.5281/zenodo.23146971}
}
```
