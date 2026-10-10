"""The prompt formats Ekbasis was trained on, and the standard questions.

Ekbasis reads one "state" string and a set of typed questions. Keep these layouts: the model tolerates rewording
(tested), but the information that decides the outcome must be in the state.
- World layout: rules, the current state, the actions in order, then a note that the questions are about the state
  after all the actions.
- Git layout: a fixed preamble, the repository state ("State before:"), the commands in order, then the same note.
"""
from __future__ import annotations

import os
import re
import shlex

WORLD_NOTE = "The questions are about the state after all these actions."
GIT_RULES = ("You are looking at a git repository on a developer machine (a Linux shell; 'origin' is its remote). "
             "The commands below are run in order in the repository root; a command that fails changes nothing more and "
             "the next one still runs.")
GIT_NOTE = "The questions are about the state after all these commands."


def numbered(lines) -> str:
    return "\n".join(f"{i + 1}. {x}" for i, x in enumerate(lines))


def world_state(rules: str, state: str, actions, notes=None, notes_label: str = "Rules for these actions") -> str:
    """A situation in the world layout: what the rules are, how things stand, what will be done. notes: plain-text rules
    placed after the action list, the way git_state places its notes (the shell guard's bash notes); none gives the
    training layout exactly."""
    acts = numbered(actions) + (f"\n\n{notes_label}: {' '.join(notes)}" if notes else "")
    return f"{rules}\n\nCurrent state:\n{state}\n\nActions, in order:\n{acts}\n\n{WORLD_NOTE}"


NOTES_AT = "commands"  # where the notes go: "commands" (after the command list), "state" (a last state line), "rules"


def git_state(repo_state: str, commands, notes=None, notes_at: str | None = None) -> str:
    """A git situation in the layout of the git training data (repo_state from ekbasis.git.repo_state). notes: plain-text
    git rules for these commands (git_notes); none gives the training layout exactly."""
    at = notes_at or NOTES_AT
    text = " ".join(notes) if notes else ""
    rules = GIT_RULES + (" " + text if text and at == "rules" else "")
    state = repo_state + (f"\nGit rules for these commands: {text}" if text and at == "state" else "")
    cmds = numbered(commands) + (f"\n\nGit rules for these commands: {text}" if text and at == "commands" else "")
    return f"{rules}\n\nState before:\n{state}\n\nCommands, in order:\n{cmds}\n\n{GIT_NOTE}"


# ---- notes: how git behaves for command forms the training data did not cover (one sentence each, added only when a
# command being checked needs it, so the prompts of trained command forms are unchanged)
NOTE_FORCE = ("git switch or git checkout with -f, --force or --discard-changes throws away uncommitted changes to tracked "
              "files and overwrites untracked files that the target has, instead of stopping.")
NOTE_RESET_MERGE = ("git reset --merge <commit> throws away staged changes; it keeps unstaged changes, but fails and changes "
                    "nothing if a file with unstaged changes differs between HEAD and <commit>.")
NOTE_RESET_KEEP = ("git reset --keep <commit> keeps uncommitted changes, staged or not, but fails and changes nothing if a "
                   "file with such changes differs between HEAD and <commit>.")
NOTE_RESET_PATH = "git reset --hard cannot take file paths: given a path it fails and changes nothing."
NOTE_ABORT = ("--abort (rebase, cherry-pick, revert, am) and --skip put every file back as it was before the step that "
              "stopped: a file with 'conflict markers still in the file' loses nothing (the markers are git's output, not "
              "work), while a resolution made since the stop (a file 'resolved by hand', or staged with git add) is thrown "
              "away.")
NOTE_OURS = ("git checkout --ours or --theirs <file> replaces the file with that side's version: a file with 'conflict "
             "markers still in the file' loses nothing, while a resolution made by hand in it is thrown away.")
NOTE_UNTRACKED = ("An untracked file at a path that the target has stops git checkout, switch, merge, pull, rebase and "
                  "cherry-pick: the command fails and changes nothing; only -f, --force, --discard-changes or git reset "
                  "--hard <target> overwrite it.")
NOTE_CONTINUE = ("--continue fails while a conflicted file is not yet marked resolved with git add; once every file is "
                 "added, it finishes the step.")
NOTE_CLEAN = ("git clean deletes nothing and fails without -f (-n or --dry-run only lists what it would delete); without -d "
              "it leaves untracked directories alone.")
NOTE_CLEAN_X = ("git clean -x also deletes ignored files and -X deletes only ignored files (-e <pattern> keeps the files "
                "that match); git stash -u does not save ignored files, git stash -a does.")
NOTE_DETACH_SWITCH = "git switch only switches to branches: to a commit or a tag it fails unless --detach is given."
NOTE_DETACH_CHECKOUT = ("git checkout <commit or tag> detaches HEAD and keeps uncommitted changes, failing only if a changed "
                        "file differs in that commit.")
NOTE_ORPHAN = ("git switch --orphan <name> fails if tracked files have uncommitted changes, and otherwise empties the "
               "working tree of tracked files; git checkout --orphan <name> keeps the files and the staging area.")
NOTE_MV = ("git mv -f overwrites the destination even if it has uncommitted changes; without -f, moving onto an existing "
           "file fails.")
NOTE_WORKTREE = ("git worktree remove fails if the linked worktree has uncommitted changes or untracked files; with --force "
                 "it deletes them.")
NOTE_SUBMODULE = ("git submodule update checks out, in each submodule, the commit the superproject records; it fails if that "
                  "would overwrite uncommitted changes in the submodule, and --force throws them away.")
NOTE_PULL = ("git pull with no --rebase, --no-rebase or --ff-only fails when the current branch and its upstream have "
             "diverged (each has commits the other lacks), unless pull.rebase or pull.ff is configured; a branch that is "
             "only behind is fast-forwarded. --ff-only fails on diverged branches; --no-rebase merges.")
NOTE_STASH_REF = ("Stash entries are numbered from 0: with N entries, stash@{N} does not exist and a command naming it "
                  "fails.")
NOTE_IGNORED = ("Ignored files are not protected: a checkout, switch, merge or reset that brings in a tracked file at the "
                "same path overwrites the ignored file without asking.")
NOTE_SPARSE = ("git sparse-checkout set <dirs> removes from the working tree the tracked files outside those directories, "
               "but keeps files with uncommitted changes and untracked files; ignored files there are deleted. git "
               "sparse-checkout add fails if no sparse checkout was set up.")


def tokens(command: str) -> list:
    try:
        return shlex.split(command, posix=True)
    except ValueError:
        return command.split()


def parse_git(command: str):
    """(git subcommand, its arguments) for a git command; (None, tokens) for anything else. Global options such as
    `-C <dir>` or `-c key=value` before the subcommand are skipped."""
    t = tokens(command)
    if not t or os.path.basename(t[0]) != "git":
        return None, t
    i = 1
    while i < len(t) and t[i].startswith("-"):
        i += 2 if t[i] in ("-C", "-c", "--git-dir", "--work-tree", "--namespace") else 1
    return (t[i], t[i + 1:]) if i < len(t) else (None, t)


def short_flags(args, stop: str = "") -> set:
    """The letters of the short options (`-fdx` -> f, d, x); a letter in `stop` takes the rest of its cluster (or the
    next argument) as its value, so `-e notes.md` or `-mmsg` add no letters after it."""
    out, skip = set(), False
    for a in args:
        if skip:
            skip = False
            continue
        if a == "--":
            break
        if a.startswith("-") and not a.startswith("--") and len(a) > 1:
            for k, ch in enumerate(a[1:]):
                out.add(ch)
                if ch in stop:
                    skip = k == len(a) - 2
                    break
    return out


def _positional(args, value_opts=()) -> list:
    """Arguments before `--` that are not options (and not the value of an option in value_opts)."""
    out, skip = [], False
    for a in args:
        if skip:
            skip = False
            continue
        if a == "--":
            break
        if a in value_opts:
            skip = True
            continue
        if not a.startswith("-"):
            out.append(a)
    return out


def git_notes(commands, info=None) -> list:
    """The notes the commands need, in order, each once. info (from ekbasis.git.inspect): nonbranch_targets (refs the
    commands target that are commits or tags, not local branches), path_args (arguments that are existing paths),
    pull_config, ignored_overwrite (a target ref tracks a path that is an ignored file here)."""
    info = info or {}
    out = []

    def add(n):
        if n not in out:
            out.append(n)

    nonbranch = set(info.get("nonbranch_targets", ()))
    paths = set(info.get("path_args", ()))
    for c in commands:
        sub, args = parse_git(c)
        if sub is None:
            continue
        a = set(args)
        if sub in ("switch", "checkout"):
            fl = short_flags(args, stop="bBc" if sub == "checkout" else "cC")
            if a & {"--force", "--discard-changes"} or "f" in fl:
                add(NOTE_FORCE)
            if "--orphan" in a:
                add(NOTE_ORPHAN)
            if sub == "checkout" and a & {"--ours", "--theirs"}:
                add(NOTE_OURS)
            pos = _positional(args, value_opts=("-b", "-B", "-c", "-C", "--orphan"))
            creates = a & {"-b", "-B", "-c", "-C", "--create", "--force-create", "--orphan", "--detach"} or "d" in fl
            if pos and pos[0] in nonbranch and not creates and "--" not in a:
                add(NOTE_DETACH_SWITCH if sub == "switch" else NOTE_DETACH_CHECKOUT)
        elif sub == "reset":
            pos = _positional(args)
            if "--merge" in a and pos:
                add(NOTE_RESET_MERGE)
            if "--keep" in a:
                add(NOTE_RESET_KEEP)
            if "--hard" in a and any(p in paths for p in pos):
                add(NOTE_RESET_PATH)
        elif sub in ("rebase", "cherry-pick", "revert", "am") and a & {"--abort", "--skip"}:
            add(NOTE_ABORT)
        elif sub == "clean":
            if args not in (["-fd"], ["-n"]):
                add(NOTE_CLEAN)
            if short_flags(args, stop="e") & {"x", "X"}:
                add(NOTE_CLEAN_X)
        elif sub == "mv" and ("--force" in a or "f" in short_flags(args)):
            add(NOTE_MV)
        elif sub == "worktree" and args[:1] == ["remove"]:
            add(NOTE_WORKTREE)
        elif sub == "submodule" and "update" in a:
            add(NOTE_SUBMODULE)
        elif sub == "pull" and args != ["origin", "main"]:
            cfg = info.get("pull_config") or {}
            add(NOTE_PULL + (" This repository sets " + ", ".join(f"{k}={v}" for k, v in sorted(cfg.items())) + "." if cfg else ""))
        elif sub == "stash" and any(re.fullmatch(r"stash@\{\d+\}", x) for x in args):
            add(NOTE_STASH_REF)
        elif sub == "sparse-checkout":
            add(NOTE_SPARSE)
        if "--continue" in a and sub in ("rebase", "cherry-pick", "revert", "am", "merge"):
            add(NOTE_CONTINUE)
    if info.get("untracked_collision") and any(parse_git(c)[0] in ("checkout", "switch", "merge", "pull", "rebase", "cherry-pick", "reset")
                                               for c in commands):
        add(NOTE_UNTRACKED)
    if info.get("ignored_overwrite"):
        add(NOTE_IGNORED)
    return out


def yes_no(instructions: str) -> dict:
    """A yes/no question."""
    return {"type": "noul", "instructions": instructions}


def choice(instructions: str, options) -> dict:
    """A question with a fixed set of answers: a list of labels, or a dict label -> short description."""
    crit = dict(options) if isinstance(options, dict) else {str(o): str(o) for o in options}
    return {"type": "choice", "instructions": instructions, "criteria": crit}


def number_label(v) -> str:
    """A number as an answer label: 3 and 3.0 both read "3"; other floats keep their digits."""
    f = float(v)
    return str(int(f)) if f.is_integer() else repr(f)


def number(instructions: str, values) -> dict:
    """A question whose answers are numbers (choice over their labels), for quantities a caller compares in code
    (see simulate.threshold)."""
    return choice(instructions, [number_label(v) for v in values])


# ---- rule recap: repeat the rule that decides the answer right before the question. Measured in the capability map
# (habit_vs_rule, mitigation M2: "Remember this rule: <rule>" before the question): Hanoi's size rule went from 0/8 to
# 8/8 and no item that was right before went wrong. Opt-in: without it every prompt is byte-identical to 0.1.1.
RECAP_ONE = "Remember this rule: "
RECAP_MANY = "Remember these rules: "


def rule_lines(rules: str) -> list:
    """The rules one per line ("- " bullets and blank lines dropped); a one-line text is one rule."""
    out = [l.strip()[2:].strip() if l.strip().startswith("- ") else l.strip() for l in rules.splitlines()]
    return [l for l in out if l]


def recap(question: dict, rules) -> dict:
    """The question with rules repeated right before it, in the measured wording. rules: one rule (a string), several
    (a list of strings; pass the ones that decide the answer when you know them), or a whole rules text whose lines
    are each a rule (rule_lines). Returns a new question; the one passed in is not changed."""
    lines = rule_lines(rules) if isinstance(rules, str) else [str(r).strip() for r in rules if str(r).strip()]
    if not lines:
        return dict(question)
    head = (RECAP_ONE + lines[0]) if len(lines) == 1 else (RECAP_MANY + " ".join(lines))
    return {**question, "instructions": f"{head}\n{question['instructions']}"}


def recap_all(questions: dict, rules) -> dict:
    """recap() for every question of a request."""
    return {k: recap(q, rules) for k, q in questions.items()}


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
