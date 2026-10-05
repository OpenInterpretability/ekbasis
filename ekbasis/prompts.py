"""The prompt formats Ekbasis was trained on, and the standard questions.

Ekbasis reads one "state" string and a set of typed questions. Keep these layouts: the model tolerates rewording
(tested), but the information that decides the outcome must be in the state.
- World layout: rules, the current state, the actions in order, then a note that the questions are about the state
  after all the actions.
- Git layout: a fixed preamble, the repository state ("State before:"), the commands in order, then the same note.
"""
from __future__ import annotations

WORLD_NOTE = "The questions are about the state after all these actions."
GIT_RULES = ("You are looking at a git repository on a developer machine (a Linux shell; 'origin' is its remote). "
             "The commands below are run in order in the repository root; a command that fails changes nothing more and "
             "the next one still runs.")
GIT_NOTE = "The questions are about the state after all these commands."


def numbered(lines) -> str:
    return "\n".join(f"{i + 1}. {x}" for i, x in enumerate(lines))


def world_state(rules: str, state: str, actions) -> str:
    """A situation in the world layout: what the rules are, how things stand, what will be done."""
    return f"{rules}\n\nCurrent state:\n{state}\n\nActions, in order:\n{numbered(actions)}\n\n{WORLD_NOTE}"


def git_state(repo_state: str, commands) -> str:
    """A git situation in the layout of the git training data (repo_state from ekbasis.git.repo_state)."""
    return f"{GIT_RULES}\n\nState before:\n{repo_state}\n\nCommands, in order:\n{numbered(commands)}\n\n{GIT_NOTE}"


def yes_no(instructions: str) -> dict:
    """A yes/no question."""
    return {"type": "noul", "instructions": instructions}


def choice(instructions: str, options) -> dict:
    """A question with a fixed set of answers: a list of labels, or a dict label -> short description."""
    crit = dict(options) if isinstance(options, dict) else {str(o): str(o) for o in options}
    return {"type": "choice", "instructions": instructions, "criteria": crit}


# The git questions, worded exactly as in training.
GIT_LOST = yes_no("Do these commands permanently lose any uncommitted work (a version of a file that existed before and "
                  "afterwards is in none of: the working directory, the staging area, any branch, any stash)?")
GIT_IN_PROGRESS = yes_no("After these commands, is a merge or rebase left unfinished (in progress)?")
GIT_CLEAN = yes_no("After these commands, is the working tree clean (nothing to commit, no untracked files)?")


def git_fails(k: int) -> dict:
    """Does command k (1-based) fail?"""
    return yes_no(f"Does command {k} fail (exit with an error)?")


def git_branch(branches) -> dict:
    return choice("After these commands, which branch is checked out?", sorted(branches))
