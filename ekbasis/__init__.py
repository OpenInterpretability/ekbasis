"""Ekbasis client: ask a served Ekbasis what happens if an action is taken (typed, calibrated answers in one pass),
chain it over long sequences, and guard git commands before they run. Standard library only."""
from .client import Answer, Ekbasis, EkbasisError
from .prompts import choice, git_state, world_state, yes_no
from .simulate import Simulation, simulate

__version__ = "0.1.0"
__all__ = ["Answer", "Ekbasis", "EkbasisError", "Simulation", "choice", "git_state", "simulate", "world_state", "yes_no"]
