"""Check a batch of actions before it runs: "look when unsure" for a plan (a script, a pipeline, a list of tool calls).

Ekbasis forecasts every prefix of the plan from the state as it is now. The plan may run as one batch only when every
prefix is forecast harmless with confidence. At the first prefix that is not, the plan is split: the steps before it
are predicted safe and run first; the uncertain or flagged step is then checked again on the state as it is after them
(look, then check the rest).

    from ekbasis import Ekbasis, yes_no, check_plan
    harm = {"data": yes_no("Do these actions permanently delete data the user did not ask to delete?"),
            "down": yes_no("After these actions, is a service that was serving now down?")}
    pc = check_plan(Ekbasis(), rules, state_text, actions, harm)
    if pc.ok:                       # every prefix harmless with confidence: run the whole batch
        run(actions)
    else:
        run(actions[:pc.safe])      # predicted safe; may be empty
        # then read the real state again and call check_plan on actions[pc.safe:]; if pc.reason == "flagged" and the
        # step is still flagged on the real state, stop and ask (or take a safer way).

The loop over a real system, with `observe` reading the state and `execute` running actions, is `run_plan`.

Every harm question must be a yes/no question whose "yes" is the harm (ekbasis.yes_no). Cost: one request per prefix
checked (all questions in one request), each reading the state and the prefix; `max_steps` caps it. Where the answer
must be exact (a limit crossed by a running total, a failing command), check in code as well: confidence alone does not
catch confident errors (see the paper Look When Unsure, Check When Sure, and ekbasis.verify)."""
from __future__ import annotations

from dataclasses import dataclass, field

from .client import Ekbasis
from .prompts import world_state

LOOK_BELOW = 0.9
HARM_AT = 0.5


@dataclass
class PlanCheck:
    ok: bool                      # every prefix forecast harmless with confidence >= look_below: run the whole plan
    safe: int                     # how many leading actions are predicted safe to run now (0..len(actions))
    reason: str | None = None     # None when ok; "flagged" (a harm forecast) or "unsure" (confidence below look_below)
    step: int | None = None       # the 1-based action where the plan stops
    flags: list = field(default_factory=list)      # harm questions answered yes at that step
    prefixes: list = field(default_factory=list)   # per prefix checked: {"step", "p_yes": {key: p}, "confidence"}
    requests: int = 0

    def summary(self) -> str:
        if self.ok:
            return f"ok: all {len(self.prefixes)} steps forecast harmless with confidence"
        why = "flags " + ", ".join(self.flags) if self.reason == "flagged" else "is unsure about"
        return (f"run steps 1-{self.safe} now (predicted safe); it {why} step {self.step}: check it on the state as it is "
                f"after them" if self.safe else f"step {self.step} needs a check on the state as it is now ({self.reason})")


def check_plan(client: Ekbasis, rules: str, state: str, actions, harm: dict, look_below: float = LOOK_BELOW,
               harm_at: float = HARM_AT, max_steps: int | None = None, notes=None) -> PlanCheck:
    """Forecast every prefix of `actions` (strings) from `state` (text) under `rules`; stop at the first prefix with a
    harm answered yes at >= harm_at, or with any harm question's confidence below look_below."""
    actions = list(actions)
    if not actions:
        return PlanCheck(ok=True, safe=0)
    for k, q in harm.items():
        if q.get("type") != "noul":
            raise ValueError(f"harm question {k!r} must be a yes/no question (ekbasis.yes_no) whose yes is the harm")
    n = min(len(actions), max_steps) if max_steps else len(actions)
    pc = PlanCheck(ok=False, safe=0)
    for i in range(1, n + 1):
        ans = client.ask(world_state(rules, state, actions[:i], notes=notes), harm)
        pc.requests += 1
        p = {k: float(a.p_yes) for k, a in ans.items()}
        conf = min(max(x, 1 - x) for x in p.values())
        pc.prefixes.append({"step": i, "p_yes": p, "confidence": round(conf, 4)})
        flags = [k for k, x in p.items() if x >= harm_at]
        if flags or conf < look_below:
            pc.safe, pc.step = i - 1, i
            pc.reason, pc.flags = ("flagged", flags) if flags else ("unsure", [])
            return pc
    pc.safe = n
    pc.ok = n == len(actions)
    if not pc.ok:   # max_steps reached: the rest was not checked
        pc.step, pc.reason = n + 1, "unsure"
    return pc


@dataclass
class PlanRun:
    done: int                      # actions executed
    stopped: PlanCheck | None      # the check that stopped the run (a harm on the real state), None if all ran
    checks: list = field(default_factory=list)
    looks: int = 0


def run_plan(client: Ekbasis, rules: str, actions, harm: dict, observe, execute, look_below: float = LOOK_BELOW,
             harm_at: float = HARM_AT, max_steps: int | None = None) -> PlanRun:
    """Run a plan with look when unsure: check, run the safe prefix with execute(list_of_actions), read the real state
    with observe() -> text, check the rest from it. Stops (without running the step) when a step is still flagged on
    the state as it is right before it; a step that is only uncertain on the real state is checked once more alone and
    runs if then harmless with confidence, else the run stops there too."""
    actions, done, out = list(actions), 0, PlanRun(done=0, stopped=None)
    while done < len(actions):
        state = observe()
        out.looks += 1
        pc = check_plan(client, rules, state, actions[done:], harm, look_below, harm_at, max_steps)
        out.checks.append(pc)
        if pc.ok:
            execute(actions[done:])
            done = len(actions)
            break
        if pc.safe:
            execute(actions[done:done + pc.safe])
            done += pc.safe
            continue
        out.stopped = pc   # the first remaining step is flagged or uncertain on the real state: do not run it
        break
    out.done = done
    return out
