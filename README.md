# Ekbasis

![Ekbasis overview: git consequences against Claude and Qwen, the git guard on fresh real repositories, and speed against a reasoning model](assets/ekbasis_launch.png)

**Paper:** [Look When Unsure, Check When Sure](https://doi.org/10.5281/zenodo.23146971) · DOI [10.5281/zenodo.23146971](https://doi.org/10.5281/zenodo.23146971) · **Code:** [github.com/OpenInterpretability/ekbasis](https://github.com/OpenInterpretability/ekbasis) · **Site:** [openinterp.org/ekbasis](https://openinterp.org/ekbasis)

**Ekbasis** (ἔκβασις, *"how an action turns out"*) is an open **consequence model** for agents: given the current
state and an action, it answers typed questions about what will happen — *will this command lose work? will it fail?
what will X be afterwards?* — with a **calibrated probability**, in **one forward pass** (no generated text).

It is the consequence layer of the Eikos family (Eikos decides; Ekbasis foresees), trained on synthetic worlds and on
**real executions** of git commands in throwaway repositories, so its answers come from what actually happened, not
from what an agent believes.

> Every number on this page was measured on the exact release weights. [RELEASE_EVAL.md](RELEASE_EVAL.md) has the
> results, every prediction, how this checkpoint was chosen, which measurements were pre-registered
> ([PREREG_release_eval.md](PREREG_release_eval.md), [paper/prereg/](paper/prereg/)) and the deviations.

## What kind of model is it?

**Not a model that thinks. Not a model that judges. A model that foresees.**

Ekbasis is a **world model for agents** in the precise sense: an action-conditioned model of how the state changes.
It answers *what will be, if I do this*, as calibrated distributions over the next state's variables, in one forward
pass.

| | LLM, reasoning | System One (Eikos, Jev) | **Ekbasis** |
|---|---|---|---|
| It answers | anything, in text | what is: which option holds now | **what will be, if I do this** |
| Kind of question | open | a judgment of the present | **an intervention: the outcome of acting** |
| Output | generated text | calibrated distribution over the options | **calibrated distribution over the next state's variables** |
| Learns from | human and model text | a teacher's judgments | **what actually happened when the action ran** |
| Time | seconds to minutes of reasoning | one forward pass | **one forward pass per step; chains to long sequences** |
| Role in an agent | plans and talks | judge | **simulator and guard: it foresees** |

Two ways to picture it:

- **The forward model the agents were missing.** Before you move your arm, the brain predicts the consequence of the
  motor command; that is what lets us act fast and correct before an error. One part plans, another predicts. The
  agent plans; Ekbasis predicts.
- **The world-model module, made real.** LeCun's architecture for autonomous machine intelligence separates a world
  model (it predicts the next state given an action) from the actor and the critic. The LLM agent is the actor,
  AgentGuard the critic, Ekbasis the world model. It was trained with a JEPA-style loss that aligns its internal state
  with the true outcome.

It is derived from an LLM (Qwen3.8-27B, through Eikos-27B) but does not work as one: its training objective and its
readout make it answer with probabilities, not text.

## What it is for

- **A check before acting**: ~0.1 s per question on one GPU, calibrated, so an agent can check *every* action and
  escalate only the risky or uncertain ones.
- **A git guard** for coding agents: the state of your real repository is described in the format the model was trained
  on (including what decides a conflict), and the commands are checked before they run.
- **Simulation and state tracking**: chain it one action at a time to follow long sequences; given a way to read the
  real state, it looks only when unsure (see [Look when unsure](#look-when-unsure-predict-observe-correct)).
- **A fast first opinion before expensive reasoning**: answer from Ekbasis when it is confident, escalate to a large
  reasoning model when it is not.

## Quick start

1. **Serve the model** (one GPU with ~80 GB; vLLM ≥ 0.30). The model folder ships its serving code; run it in the
   Python environment where vLLM is installed:

   ```bash
   hf download caiovicentino1/Ekbasis-27B --local-dir Ekbasis-27B
   bash Ekbasis-27B/serve_vllm.sh Ekbasis-27B 8001             # vLLM on 127.0.0.1:8001
   python Ekbasis-27B/serve.py --model Ekbasis-27B --vllm-url http://127.0.0.1:8001 --port 8000
   ```

2. **Install the client** (standard library only, Python ≥ 3.9), anywhere that can reach the server:

   ```bash
   pip install "git+https://github.com/OpenInterpretability/ekbasis"   # ekbasis, ekbasis-claude-hook (MCP: below)
   export EKBASIS_URL=http://127.0.0.1:8000
   ekbasis health
   ```

3. **Check git commands before running them** (in any repository):

   ```bash
   ekbasis git-check -- "git checkout -- app.py"
   # Ekbasis: RISKY  (lose uncommitted work: 99%)
   #     0% fails  git checkout -- app.py
   #   - may permanently lose uncommitted work (99%)
   ```

   Exit code 0 when no risk is found, 2 when the commands may lose uncommitted work, 1 on errors.

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

## Python

```python
from ekbasis import Ekbasis, world_state, choice, yes_no, simulate
from ekbasis import git

client = Ekbasis()                                     # EKBASIS_URL or http://127.0.0.1:8000

# a git guard
v = git.check(["git stash", "git checkout feature", "git stash pop"], repo=".")
print(v.risky, v.p_lost, v.p_fail, v.summary())

# any world whose rules you can write down
rules = ("World: containers A (holds 5 liters), B (holds 3 liters) of water. 'fill X' fills X to the top; "
         "'empty X' empties X; 'pour X into Y' moves water from X to Y until X is empty or Y is full, "
         "whichever comes first.")
ans = client.ask(world_state(rules, "A: 5 of 5 liters, B: 0 of 3 liters", ["pour A into B"]),
                 {"a": choice("How many liters are in A?", [str(k) for k in range(6)])})
print(ans["a"].value, ans["a"].confidence)

# a long sequence: one action at a time, every variable asked after each action
render = lambda s: f"A: {s['a']} of 5 liters, B: {s['b']} of 3 liters"
qs = {"a": choice("How many liters are in A?", [str(k) for k in range(6)]),
      "b": choice("How many liters are in B?", [str(k) for k in range(4)])}
sim = simulate(client, rules, {"a": "5", "b": "0"}, ["pour A into B", "empty B", "pour A into B"], qs, render)
print(sim.final, sim.confidence)   # use the chain confidence, not the last step's
```

## Look when unsure (predict, observe, correct)

The study behind this section is the paper *Look When Unsure, Check When Sure* ([PDF](paper/look_when_unsure.pdf),
[doi:10.5281/zenodo.23146971](https://doi.org/10.5281/zenodo.23146971)), every analysis pre-registered and re-run from
the saved outputs.

Ekbasis follows long sequences one action at a time. Where a later action overwrites a mistake (a container refilled,
a lamp switched) the chain recovers by itself; where nothing ever undoes it (an ordering), mistakes compound. Give
`simulate()` a way to read the real state and it looks **only when it is not sure**, then continues from what it saw:

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
pre-registered test on 15,008 new questions in 12 world families, run on V42 (the first release candidate), confirmed
the pattern: 58% of its wrong answers carried a confidence of 0.9 or more in the families it was trained on, 28% in
the families it never saw (30 points apart, 95% interval 24 to 37), while its confidence ranks right above wrong about
equally well in both (AUROC 0.92 and 0.91). Eikos-27B, the same model before consequence training, was almost never
confidently wrong (1.9% and 0.5% of its errors): the training made it
([report](results_v42/confident_errors/REPORT.md)). On the same questions the release gives 48% and 25%, with 2.06
confident errors per 100 answers in the trained families against V42's 2.79
([report](results/confident_errors/REPORT.md)): fewer, not gone, which is why the checks stay on by default.

The idea is classic: the predict–update loop of a state estimator (a Kalman filter), with observations triggered by
the predictor's own uncertainty (event-based state estimation; with learned models, active observing); the checks'
backoff is the Trickle algorithm's. What Ekbasis adds is a calibrated forecast in one pass, cheap enough to run at
every action. Prior work: [REFERENCES](docs/REFERENCES.md#looking-when-unsure-prior-work).

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

## Claude Code and MCP

- **Claude Code hook** — Claude Code asks you to confirm (or blocks) git commands that may lose uncommitted work, with
  the reason; it stays silent otherwise and never blocks when the server is unreachable. In `.claude/settings.json`
  (one project) or `~/.claude/settings.json` (all):

  ```json
  {"hooks": {"PreToolUse": [{"matcher": "Bash",
    "hooks": [{"type": "command", "command": "ekbasis-claude-hook", "timeout": 30}]}]}}
  ```

  Environment: `EKBASIS_URL`, `EKBASIS_LOST_THRESHOLD` (0.2), `EKBASIS_GUARD_MODE` (`ask` or `deny`),
  `EKBASIS_FETCH=1` (fetch first so the state shows the real remote).

- **MCP server** (`pip install "ekbasis[mcp] @ git+https://github.com/OpenInterpretability/ekbasis"`, Python ≥ 3.10):
  the command `ekbasis-mcp` exposes `check_git_commands` and `predict_consequences` to any MCP client. In Claude Code:

  ```bash
  claude mcp add --scope user ekbasis -e EKBASIS_URL=http://127.0.0.1:8000 -- ekbasis-mcp
  ```

  or a project `.mcp.json`:

  ```json
  {"mcpServers": {"ekbasis": {"type": "stdio", "command": "ekbasis-mcp", "env": {"EKBASIS_URL": "http://127.0.0.1:8000"}}}}
  ```

  If the client was installed in a virtualenv, use the absolute path of the command (`which ekbasis-mcp`), in
  `.mcp.json` and in other MCP clients' configuration files.

## Read-once

When a request carries several questions about the same state, `client.ask(..., read_once=True)` reads the state once
and answers every question in the same forward pass: about half the prompt tokens, for 0.9–3.1 points of accuracy on
the answers the actions change (never-trained worlds: 710 instead of 1,442 prompt tokens per state, 78.0% instead of
81.2%; trained ones: 91.5% instead of 92.4%). Text only.

## Limits (read before relying on it)

![Where Ekbasis is strong and where it is not, with what to do where it is weak](assets/chart_strengths.png)

- **It knows what it was trained on**: rule-based worlds you describe in the prompt, and git. On command types it never
  saw, accuracy drops (85.8% against 95.8% on the 240-question git comparison). Other domains need their own data.
- **The state must contain what decides the outcome.** The git guard adds it for you; in your own uses, include it.
- **Errors that never fade compound** in long chains (orderings), and in the worlds it knows its rare errors come with
  confidence: give `simulate()` a way to read the real state (`observe=`) and it looks when it is not sure, with a
  check now and then. Card orderings, 200 actions: 8 of 8 chains exact with about 33 looks per 100 actions, against 2
  of 8 never looking. See [Look when unsure](#look-when-unsure-predict-observe-correct).
- **With written rules and time to think, large reasoning models are more accurate** (100% against 96.7% on short
  checks); Ekbasis wins on cost, latency and calibrated confidence there.
- **Three git cases it gets wrong**, found after the release evaluation in fresh sandbox repositories
  ([results/release_eval/git_limits.json](results/release_eval/git_limits.json)):
  - A commit followed by a destructive command in one check is flagged although the commit saved the work
    (`git commit -am wip` then `git reset --hard`: 96% "loses work"; nothing was lost). Check the commands after the
    commit has run: the guard reads the repository as it is.
  - `git rm` on a file with uncommitted changes: 98% "fails" (right: git refuses) and also 95% "loses work" (nothing
    is lost, since it fails). When "fails" is high, read "loses work" as "if it succeeded".
  - `git clean -fdx` deleted an ignored `.env` and the guard gave 0.2%: the client builds the state from `git status`,
    which does not list ignored files, so the model never sees them (`git clean -fd` on the same repository, which
    keeps ignored files, was right). Run `git clean -n` with the same flags first, or treat `-x`/`-X` as risky when
    ignored files exist.
- **It is a safety net, not a security boundary.** See [docs/SECURITY.md](docs/SECURITY.md) for the threat model, the
  measured injection results and the recommended defense-in-depth stack.

More: [docs/PLAYBOOK.md](docs/PLAYBOOK.md) (how to use it day to day) · [docs/REFERENCES.md](docs/REFERENCES.md)
(credits) · [PREREG_release_eval.md](PREREG_release_eval.md).

## Contact

Questions, collaborations and commercial use: caio@openinterp.org. Security problems with the guard: see
[docs/SECURITY.md](docs/SECURITY.md#reporting-a-problem) (email first, please).

## Acknowledgments

Ekbasis was built by Caio Vicentino (OpenInterp) with the help of
[Claude Opus 5.5](https://www.anthropic.com/claude-opus-5-5) (Anthropic). Claude worked on the project with him:
- planning and running the experiments;
- writing and reviewing the code and the documentation;
- checking the numbers and the references.
