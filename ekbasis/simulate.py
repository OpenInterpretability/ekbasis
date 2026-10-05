"""Chained simulation: one action at a time, every variable of the state asked after each action, the next state built
from the answers. This is how Ekbasis follows long sequences.

Errors fade in some worlds (a later action overwrites the value: refills, resets, switches) and never fade in others
(orderings: nothing puts a card back in a known place), where they compound. The fix is the loop of a forward model with
a sensor: predict, observe, correct. Give `simulate` an `observe` function that reads the real state, and it looks when
its own confidence says so and continues from what it saw. By default it looks when the chain confidence falls below
0.9 (`LOOK_BELOW`), and it also checks the forecast now and then (`CHECKS`): after 8 actions without a look, a gap that
doubles up to 64 while the forecasts hold; a look that finds the forecast wrong (a surprise) brings the gap back to 8
and looks again after the next action, until a look finds it right. The checks catch the rare errors the model makes
with confidence, which no confidence rule sees. `look_below`, `look_step_below`, `look_every` and `checks` set other
rules. For states that are orderings, `ordering` reads the most probable VALID ordering from the answers' probabilities.

Use the chain confidence (the product of every answer's confidence since the last look), not the last step's: a
confident last step can sit on an earlier mistake. With no `observe`, `Simulation.horizon()` says how many actions the
forecast holds by the model's own confidence: act up to there, look, plan again.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .client import Ekbasis
from .prompts import recap_all, world_state

# The defaults with `observe` (RELEASE_EVAL.md, "Predict, observe, correct"): every measured chain ended exact, with the
# fewest steps wrong along the way.
LOOK_BELOW = 0.9
CHECKS = (8, 64)  # the first gap between checks, and the largest


@dataclass
class Simulation:
    final: dict
    steps: list = field(default_factory=list)  # [{"action", "state", "confidence", "chain", "looked"}] after each action
    confidence: float = 1.0                    # the chain confidence since the last look
    looks: list = field(default_factory=list)  # the actions (1-based) after which the real state was read
    surprises: list = field(default_factory=list)  # the looks that found the forecast wrong

    @property
    def weakest_step(self):
        return min(self.steps, key=lambda s: s["confidence"]) if self.steps else None

    def horizon(self, below: float = LOOK_BELOW) -> int:
        """How many actions the forecast holds by the model's own confidence: those before the chain confidence (since
        the last look) first fell below `below`; all of them if it never did."""
        return next((t for t, s in enumerate(self.steps) if s["chain"] < below), len(self.steps))


def assignment(cost: list) -> list:
    """Minimum-cost assignment on a square cost matrix (Hungarian algorithm, O(n^3)): the column of every row."""
    n, inf = len(cost), float("inf")
    u, v, p, way = [0.0] * (n + 1), [0.0] * (n + 1), [0] * (n + 1), [0] * (n + 1)
    for i in range(1, n + 1):
        p[0], j0 = i, 0
        minv, used = [inf] * (n + 1), [False] * (n + 1)
        while True:
            used[j0] = True
            i0, delta, j1 = p[j0], inf, 0
            for j in range(1, n + 1):
                if not used[j]:
                    c = cost[i0 - 1][j - 1] - u[i0] - v[j]
                    if c < minv[j]:
                        minv[j], way[j] = c, j0
                    if minv[j] < delta:
                        delta, j1 = minv[j], j
            for j in range(n + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while j0:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
    col = [0] * n
    for j in range(1, n + 1):
        if p[j]:
            col[p[j] - 1] = j - 1
    return col


def read_ordering(ans: dict, keys: list, where: dict | None = None) -> tuple[dict, float]:
    """The most probable valid ordering: every variable in `keys` takes a different value from the same set (positions
    holding distinct cards). where: {value: Answer} to the inverse questions (where is this value? the options are the
    variables in `keys`), read together with the direct answers: both views of each variable, normalized over its
    values. Returns ({variable: value}, its probability under the answers)."""
    values = list(ans[keys[0]].probabilities)
    if sorted(values) != sorted(set(values)) or len(values) != len(keys) or \
            any(sorted(ans[k].probabilities) != sorted(values) for k in keys):
        raise ValueError("ordering: every variable needs the same options, as many as the variables")
    logp = [[math.log(ans[k].probabilities.get(x, 0.0) + 1e-12) for x in values] for k in keys]
    if where:
        if sorted(where) != sorted(values) or any(sorted(where[x].probabilities) != sorted(keys) for x in values):
            raise ValueError("where: one question per value of the ordering, whose options are the ordering's variables")
        logp = [[lp + math.log(where[x].probabilities.get(k, 0.0) + 1e-12) for lp, x in zip(row, values)]
                for row, k in zip(logp, keys)]
        logp = [[v - max(row) - math.log(sum(math.exp(u - max(row)) for u in row)) for v in row] for row in logp]
    col = assignment([[-c for c in row] for row in logp])
    return {k: values[c] for k, c in zip(keys, col)}, math.exp(sum(logp[i][c] for i, c in enumerate(col)))


def simulate(client: Ekbasis, rules: str, state: dict, actions, questions: dict, render, read_once: bool = False,
             observe=None, look_below: float | None = None, look_step_below: float | None = None,
             look_every: int | None = None, checks: bool | None = None, ordering: list | None = None,
             where: dict | None = None, recap=None) -> Simulation:
    """state: {variable: value}. questions: {variable: typed question whose option labels are the variable's possible
    values} (ekbasis.prompts.choice / yes_no). render(state) -> the state as text, written the same way at every step.
    read_once=True reads each step's state once for all the questions (about half the tokens; on the models trained for
    it it costs 1-3 points of accuracy on the answers that change).

    observe(t) -> the real state after the first t actions ({variable: value}), or None if it cannot be read now. It is
    called after action t when the chain confidence since the last look is below `look_below` (LOOK_BELOW when no rule
    is given), when that step's confidence is below `look_step_below`, every `look_every` actions, or for a check
    (`checks`: on by default with `observe`, unless `look_every` sets a fixed schedule); the simulation then continues
    from the real state. ordering: the variables that hold an ordering (each a different value of the same set), read
    jointly. where: for an ordering, {value: question} asking where each value is (the options: the ordering's
    variables), asked in the same request and read together with the direct answers; on card orderings this halved the
    looks (RELEASE_EVAL.md, "Two views"). recap: repeat rules right before every question (prompts.recap): True for
    all of `rules`, or the rule lines that decide the answers; None (the default) leaves the prompts as in 0.1.1."""
    if observe is not None and look_below is None and look_step_below is None and not look_every:
        look_below = LOOK_BELOW
    if checks is None:
        checks = observe is not None and not look_every
    recheck, gap, since = False, CHECKS[0], 0
    cur, sim = dict(state), Simulation(final=dict(state))
    keys = [k for k in questions if not ordering or k not in ordering]
    wkeys = {x: f"where {j}" for j, x in enumerate(where or {})}  # the inverse questions, asked with the others
    if where and (not ordering or set(wkeys.values()) & set(questions)):
        raise ValueError("where needs an ordering, and no variable named 'where <n>'")
    asked = {**questions, **{wkeys[x]: q for x, q in where.items()}} if where else questions
    if recap is not None and recap is not False:
        asked = recap_all(asked, rules if recap is True else recap)
    for t, a in enumerate(actions, 1):
        ans = client.ask(world_state(rules, render(cur), [a]), asked, read_once=read_once)
        nxt, step = {k: ans[k].value for k in keys}, math.prod(ans[k].confidence for k in keys)
        if ordering:
            got, p = read_ordering(ans, list(ordering), {x: ans[wkeys[x]] for x in where} if where else None)
            nxt.update(got)
            step *= p
        cur = {k: nxt[k] for k in questions}
        sim.confidence *= step
        chain, looked = sim.confidence, False
        since += 1
        if observe is not None and t < len(actions) and (
                (look_below is not None and sim.confidence < look_below)
                or (look_step_below is not None and step < look_step_below)
                or (look_every and t % look_every == 0)
                or (checks and (recheck or since >= gap))):
            seen = observe(t)
            if seen is not None:
                surprised = any(str(cur[k]) != str(seen.get(k)) for k in questions)
                if surprised:
                    sim.surprises.append(t)
                if checks:  # look again after the next action until a look finds the forecast right
                    recheck, gap = surprised, CHECKS[0] if surprised else min(2 * gap, CHECKS[1])
                cur, sim.confidence, looked, since = dict(seen), 1.0, True, 0
                sim.looks.append(t)
        sim.steps.append({"action": a, "state": dict(cur), "confidence": step, "chain": chain, "looked": looked})
    sim.final = cur
    return sim


# ---- compare in code: the model tracks a number, the client decides the comparison. Measured in the capability map
# (accumulation): the running totals the model carried step by step were 98-100% right, while its own threshold
# judgments near the limit failed (46% within 5% of the limit); comparing the carried total with the limit in code gave
# 99.0% (pairs on both sides of the limit: 98.6%).
COMPARE = {">=": lambda a, b: a >= b, ">": lambda a, b: a > b, "<=": lambda a, b: a <= b, "<": lambda a, b: a < b,
           "==": lambda a, b: a == b, "!=": lambda a, b: a != b}


def as_number(v) -> float:
    """A number from an answer label ("12", "12.5", "1,200"); ValueError otherwise."""
    try:
        return float(str(v).replace(",", "").strip())
    except ValueError:
        raise ValueError(f"not a number: {v!r} (the quantity's question must have numeric options: prompts.number)") from None


@dataclass
class Threshold:
    value: float                     # the quantity after the last action, as the model carried it
    holds: bool                      # the comparison, decided in code (see `when`)
    confidence: float                # the chain confidence since the last look (Simulation.confidence)
    trace: list = field(default_factory=list)  # the quantity before the first action, then after each action
    first: int | None = None         # the first point where the comparison held (0: before any action); None: never
    simulation: Simulation | None = None


def threshold(client: Ekbasis, rules: str, state: dict, actions, questions: dict, render, quantity: str, op: str,
              limit: float, when: str = "end", **kw) -> Threshold:
    """Follow a quantity step by step with `simulate` and decide `quantity <op> limit` in code, not in the model.

    Use it when an effect depends on a running total crossing a limit: budgets and spending caps, timers and waits that
    add up, quotas and rate limits, attempts before a lockout, points before a reward. Ask the model for the number
    (questions[quantity], numeric options: prompts.number) and let this decide; asking the model "is the limit reached?"
    is where it fails, most of all one or two units short of the limit.

    state[quantity] is the value before the first action. when: "end" compares the value after the last action; "ever"
    is true if the comparison held at any point (effects that trigger once and stay: a lockout, an alarm, a cap that
    stops a service); "before_last" compares the value just before the last action (a rate limit deciding whether the
    last request is accepted). Other keyword arguments go to `simulate` (observe, look_below, read_once, recap, ...)."""
    if op not in COMPARE:
        raise ValueError(f"op must be one of {', '.join(COMPARE)}")
    if when not in ("end", "ever", "before_last"):
        raise ValueError('when must be "end", "ever" or "before_last"')
    if quantity not in questions or quantity not in state:
        raise ValueError(f"{quantity!r} must be a variable of the state and have a question")
    actions = list(actions)
    sim = simulate(client, rules, state, actions, questions, render, **kw)
    trace = [as_number(state[quantity])] + [as_number(s["state"][quantity]) for s in sim.steps]
    cmp = COMPARE[op]
    hits = [i for i, v in enumerate(trace) if cmp(v, float(limit))]
    if when == "end":
        holds = cmp(trace[-1], float(limit))
    elif when == "ever":
        holds = bool(hits)
    else:
        holds = cmp(trace[-2] if len(trace) > 1 else trace[-1], float(limit))
    return Threshold(value=trace[-1], holds=holds, confidence=sim.confidence, trace=trace,
                     first=hits[0] if hits else None, simulation=sim)
