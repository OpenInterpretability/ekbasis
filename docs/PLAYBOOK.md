# Ekbasis day to day

**The idea: autonomy with a brake.** The bottleneck of working with agents is rarely their intelligence; it is
approving every step, because some steps cannot be undone. Ekbasis answers, before an action runs, *what will this do
here?*, with a calibrated probability, in about 0.1 s. Routine actions go through; risky or uncertain ones come to you
with the reason.

## Setup (once)

Serve the model and install the client as in the [README](../README.md#quick-start), then pick what fits your tools:

| You use | Add |
|---|---|
| Claude Code | the git hook (`ekbasis-claude-hook`) in `~/.claude/settings.json` |
| Any MCP client (Claude Desktop, IDEs, your own agent) | `ekbasis-mcp` |
| Scripts, CI, your own code | the `ekbasis` CLI or the Python client |

## Six recipes

### 1. Let the agent run, with a brake

Run your coding agent with fewer approval prompts and keep the Ekbasis hook in `ask` mode: commands that may lose
uncommitted work come to you with the probability and the reason; everything else goes through. Measured on 16 fresh
real-repository scenarios: all 3 that would have destroyed work were flagged at the 0.2 threshold, with 1 false alarm
among the other 13 ([RELEASE_EVAL.md](../RELEASE_EVAL.md)).

### 2. Pre-flight before anything irreversible

Before rewriting history, bulk resets or cleaning, ask first:

```bash
ekbasis git-check --fetch -- "git rebase main" "git push -f origin feature"
```

If it says RISKY, save the work first (`git commit`, or `git stash -u`) and check again.

### 3. Plan by simulating

When several sequences of actions could reach the goal, simulate each one step by step (`ekbasis.simulate`) and keep
the one whose final state is what you want **and** whose *chain confidence* is high. Measured on 180 hard planning
puzzles (8–12 actions): searching with Ekbasis alone, with no LLM, 98.9% of the plans worked when run for real, in
about 11 s each; the same base model writing the plan while reasoning step by step reached 97.8%, and 38.3% answering
at once.

### 4. Cheap first, expensive when unsure

Ask Ekbasis first; send to a large reasoning model only the questions where its confidence is low. Measured on short
consequence checks (Ekbasis alone 96.7%): 99.6% accuracy while sending only 10% of the questions to the reasoning
model (cut at 0.95), 100% sending 21% (cut at 0.99).

### 5. Long sessions: predict, observe, correct

For long operations, keep the state as typed variables and update it after every action with Ekbasis. Where errors
fade (refills, switches) chains recover by themselves; where they never fade (orderings) they compound. Give the
simulation a way to read the real state (a `git status`, a screenshot, a sensor reading) and Ekbasis decides when to
look, then continues from what it saw.

```python
from ekbasis import simulate

sim = simulate(client, rules, state, actions, questions, render,
               observe=lambda t: read_the_real_state(),  # {variable: value}, or None if it cannot look now
               ordering=list(questions))                 # an ordering: read the most probable valid one
print(sim.final, sim.looks, sim.surprises)               # when it looked, and which looks found the forecast wrong
```

By default it looks when the chain confidence (the product of every answer's confidence since the last look) falls
below 0.9, and it checks the forecast now and then: after 8 actions without a look, a gap that doubles up to 64 while
the forecasts hold; a look that finds the forecast wrong (a surprise) brings the gap back to 8 and looks again after
the next action, until a look finds it right. `look_below`, `look_step_below`, `look_every` and `checks` set other
rules. Without `observe`, `sim.horizon()` gives how many actions the forecast holds.

Measured on chains of 100 and 200 actions: card orderings, a world it never saw, ended exact in 0 of 8 and 2 of 8
chains never looking and 8 of 8 with the default (33–42 looks per 100 actions); looking on a fixed schedule (every 50
actions) did not help (0 and 4 of 8). In the worlds it was trained on it looks 2.9–3.5 times per 100 actions and every
chain ended exact. On 200 more chains with new seeds, 198 ended exact; of the two that did not, a container chain of
100 actions went wrong at action 87 with a confidence of 0.99, after the last check, and stayed wrong to the end (its
final answer right); a card chain of 200 actions missed only its last action, which the loop never checks, and the
model had flagged it (that step's probability 0.0006). Prefer the chain confidence to a per-step threshold, and keep
the checks: they find the errors that come with confidence. The full table: the README, Look when unsure.
For an ordering, give `where={value: question}` too (where is each value? the options are the ordering's variables):
read with the direct answers, it halved the looks on card orderings with every chain exact.

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
looked more often, and all but three of 144 chains ended exact, those three on their last action. Measure on your own
environment before relying on it.)

- **Coding and devops agents:** the state of a repository, files and infrastructure across a long session, with
  `git status` only when unsure.
- **Browser and computer-use agents:** the screen after each action, with a screenshot only when unsure (Ekbasis already
  reads a starting state from a picture of a simple world; real screens are not measured yet).
- **Business processes:** orders, stock and balances after a sequence of transactions, reconciled with the database only
  when unsure.
- **Digital twins and IoT:** machine states between sensor reads; read the sensor when unsure.
- **Finance operations:** positions and margins after a sequence of orders, checked with the broker when unsure.

### 6. Teach it your environment

A frontier model does not know your systems. Ekbasis learns them from executions:

1. a sandbox where your actions run for real (as the git sandbox here: throwaway repositories, an unprivileged user,
   synthetic content);
2. thousands of generated situations and actions, with the outcome observed after running them;
3. training on those, with some action types held out;
4. measuring on the held-out types before trusting it.

Your team's incidents are the best seeds: each "never do X when Y" becomes situations where the model learns the
consequence.

## Reading the numbers

- **Probabilities are calibrated** on the domains it was trained on: when it says 99% it is right about 99% of the
  time (measured: 189 of 189 right at 99% and above); between 90% and 99% it is overconfident (96.9% said, 91.4%
  right), so treat that band as "check".
- **In a chain, use the chain confidence** (the product of every step's confidence), not the last step's.
- **Thresholds**: 0.2 on P(lost) for a guard (missing a destructive action costs more than a question); 0.5 for
  plain decisions.

## Don't

- Treat "no objection" as approval for actions outside what it was trained on (today: git, and worlds whose rules you
  write in the prompt).
- Leave out of the state what decides the outcome.
- Chain orderings or permutations for long without looking at the real state again.
- Use it as a security boundary: see [SECURITY.md](SECURITY.md).
