"""Ekbasis client: ask a served Ekbasis what happens if an action is taken (typed, calibrated answers in one pass),
chain it over long sequences, and guard git commands (and, as a prototype, shell command lines) before they run.
Standard library only."""
from .client import Answer, Ekbasis, EkbasisError
from .prompts import choice, git_state, number, recap, world_state, yes_no
from .simulate import Simulation, Threshold, simulate, threshold

__version__ = "0.1.5"
__all__ = ["Answer", "Ekbasis", "EkbasisError", "Simulation", "Threshold", "choice", "git_state", "number", "recap",
           "simulate", "threshold", "world_state", "yes_no"]
