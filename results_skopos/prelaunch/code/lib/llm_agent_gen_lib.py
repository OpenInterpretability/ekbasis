"""Shared pieces of the LLM-agent experiment: the valid actions of a world, reading a goal condition, checking a goal, running a plan in the true simulator."""


def all_actions(fam, w):
    """Every valid action of a world, as {text: action}."""
    if fam == "jugs":
        acts = [{"op": o, "x": x} for x in w.names for o in ("fill", "empty")]
        acts += [{"op": "pour", "x": x, "y": y} for x in w.names for y in w.names if x != y]
    elif fam == "toggles":
        acts = [{"b": b} for b in w.wiring]
    else:
        acts = [{"op": "tick"}] + [{"op": o, "d": d} for d in w.devs for o in ("tick1", "reset")]
    return {w.render_action(a): a for a in acts}


GET = {"jugs": lambda w, s, k: str(s["v"][k]), "toggles": lambda w, s, k: w.states[s["st"][k]],
       "machines": lambda w, s, k: w.cycle[s["st"][k]]}
KEYS = {"jugs": lambda w: list(w.names), "toggles": lambda w: list(range(w.n)), "machines": lambda w: list(w.devs)}
SAY = {"jugs": lambda w, k, v: f"{k} holds exactly {v} liters", "toggles": lambda w, k, v: f"{w.lamp} {k + 1} is {v}",
       "machines": lambda w, k, v: f"{k} is {v}"}


def holds(fam, w, s, goal):
    return all(GET[fam](w, s, k) == v for k, v in goal)


def run_plan(w, s, plan):
    for a in plan:
        s, _ = w.step(s, a)
    return s
