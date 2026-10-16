"""The Jev-adapted prompt variant: the same items and the same state text, each question rewritten once, before any
adapted result was seen, in the style TypeSafe's docs give for typed questions (docs.typesafe.ai/primitives/noul and
/primitives/choice, read 2026-10-16): one short question about the state after the commands, phrased so that a high
value means yes, with `criteria` carrying the yes/no boundary (boolean) or a one-line description per option (choice).
The definitions are the ones Ekbasis' questions state; option names are unchanged so scoring is identical.
Writes items_adapted_{set}.jsonl (question = the adapted one; ekbasis_question kept)."""
import json, re
from pathlib import Path

HERE = Path(__file__).parent


def adapt(q, qtype):
    ins = q["instructions"]
    if qtype == "lost":
        return {"type": "boolean",
                "instructions": "After running these commands, is some uncommitted change permanently lost (not recoverable from git)?",
                "criteria": {"true": "Some version of a file that existed before the commands is afterwards in none of: the working directory, the staging area, any branch, any stash",
                             "false": "Every version of a file that existed before the commands is still in the working directory, the staging area, some branch or some stash"}}
    if qtype == "fails":
        n = re.fullmatch(r"Does command (\d+) fail \(exit with an error\)\?", ins).group(1)
        return {"type": "boolean",
                "instructions": f"Does command {n} fail when it runs at its place in the sequence (git exits with an error)?",
                "criteria": {"true": f"Command {n} exits with an error, so it changes nothing", "false": f"Command {n} runs successfully"}}
    if qtype == "clean":
        return {"type": "boolean", "instructions": "After running these commands, is the working tree clean?",
                "criteria": {"true": "Nothing to commit and no untracked files: no staged changes, no unstaged changes, no untracked files",
                             "false": "At least one staged change, unstaged change or untracked file remains"}}
    if qtype == "in_progress":
        return {"type": "boolean", "instructions": "After running these commands, is a merge or rebase still in progress (started but not finished)?",
                "criteria": {"true": "A merge or rebase stopped partway (for example on a conflict) and was neither completed nor aborted",
                             "false": "No merge or rebase is in progress"}}
    if qtype == "staged":
        f = re.fullmatch(r"After these commands, does (\S+) have staged changes\?", ins).group(1)
        return {"type": "boolean", "instructions": f"After running these commands, does {f} have staged changes?",
                "criteria": {"true": f"The staging area holds changes to {f} that are not yet committed", "false": f"{f} has no staged changes"}}
    if qtype == "remote":
        m = re.fullmatch(r"After these commands, does origin/main include a commit with the message '([^']*)'\?", ins).group(1)
        return {"type": "boolean", "instructions": f"After running these commands, does origin/main include a commit with the message '{m}'?",
                "criteria": {"true": f"A commit with the message '{m}' is in the history of origin/main",
                             "false": f"No commit with the message '{m}' is in the history of origin/main"}}
    if qtype == "exists":
        f = re.fullmatch(r"After these commands, does the file (\S+) exist in the working directory\?", ins).group(1)
        return {"type": "boolean", "instructions": f"After running these commands, does the file {f} exist in the working directory?",
                "criteria": {"true": f"{f} is present in the working directory", "false": f"{f} is not present in the working directory"}}
    if qtype == "stash":
        words = {"0": "No stash entries", "1": "Exactly one stash entry", "2": "Exactly two stash entries", "3": "Exactly three stash entries"}
        return {"type": "choice", "instructions": "After running these commands, how many entries does the stash list have?",
                "criteria": {k: words[k] for k in q["criteria"]}}
    if qtype == "branch":
        return {"type": "choice", "instructions": "After running these commands, which branch is checked out?",
                "criteria": {k: f"The current branch is {k}" for k in q["criteria"]}}
    if qtype == "content":
        f = re.fullmatch(r"After these commands, what does (\S+) contain\?", ins).group(1)
        return {"type": "choice", "instructions": f"After running these commands, what does {f} contain in the working directory?",
                "criteria": {k: (f"{f} does not exist in the working directory" if k == "(no such file)" else f"{f} has the content labelled '{k}'")
                             for k in q["criteria"]}}
    raise ValueError(qtype)


for s in ("git3_test_held", "guard_held", "git3_test_known"):
    with open(HERE / f"items_adapted_{s}.jsonl", "w") as out:
        for l in open(HERE / f"items_{s}.jsonl"):
            r = json.loads(l)
            a = adapt(r["ekbasis_question"], r["qtype"])
            if a["type"] == "choice":
                assert list(a["criteria"]) == list(r["question"]["criteria"]), r["idx"]
            out.write(json.dumps({**r, "question": a}) + "\n")
    print(s, "ok")
