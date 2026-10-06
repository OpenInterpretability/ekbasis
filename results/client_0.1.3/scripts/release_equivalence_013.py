"""0.1.3 against the published 0.1.2: which requests stay byte-identical (CPU only, no server).

Same fixtures as the 0.1.2 release check (eval/release_equivalence.py of client_012): ten repository states (clean,
dirty with ignored files, a target that tracks an ignored file, a merge, a rebase and a cherry-pick stopped on a
conflict, a merge resolved by hand, a linked worktree, a submodule, a diverged remote) and its 25 command lists, plus
the world prompts and simulate. Added for 0.1.3:

- the shell guard's prompt for 24 shell lines in each state (a fixed fingerprint key, so two versions can be compared);
  on Linux, with no `where=`, the only allowed difference is the coreutils text ("9.4" -> "GNU coreutils 9.4"), and
  with an explicit `where=` the prompts must be identical;
- the Claude Code hook, in process with a recording client, on each command list joined into one line, on each shell
  line, on mixed lines and on lines 0.1.2 could not follow. Where 0.1.3 asks the same guard about the same commands,
  the request must be identical; what it skips or adds is counted by kind.

usage: python3 release_equivalence_013.py <0.1.2 package dir> <0.1.3 package dir>   (prints one JSON line)
"""
import importlib
import importlib.util
import io
import json
import os
import platform
import random
import re
import subprocess
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from types import SimpleNamespace
from unittest import mock

REL, NEW = sys.argv[1], sys.argv[2]
ENV = dict(os.environ, GIT_AUTHOR_NAME="Dev", GIT_AUTHOR_EMAIL="dev@example.invalid", GIT_COMMITTER_NAME="Dev",
           GIT_COMMITTER_EMAIL="dev@example.invalid", LC_ALL="C", GIT_EDITOR="true", GIT_CONFIG_NOSYSTEM="1")
KEY = b"release-equivalence-0.1.3"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, os.path.join(path, "__init__.py"), submodule_search_locations=[path])
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    imp = lambda m: importlib.import_module(f"{name}.{m}")  # noqa: E731
    return SimpleNamespace(E=mod, G=imp("git"), P=imp("prompts"), Sim=imp("simulate"), C=imp("client"), S=imp("shell"),
                           H=imp("claude_code_hook"))


V0, V1 = load("ekbasis_012", os.path.realpath(REL)), load("ekbasis_013", os.path.realpath(NEW))
assert V0.E.__version__ == "0.1.2" and V1.E.__version__ == "0.1.3", (V0.E.__version__, V1.E.__version__)
LINUX = platform.system() == "Linux"


class Recorder:
    def __init__(self, Answer):
        self.Answer, self.requests = Answer, []

    def ask(self, state, questions, read_once=False, images=None):
        self.requests.append((state, json.dumps(questions, sort_keys=True)))
        out = {}
        for k, q in questions.items():
            if q["type"] == "noul":
                out[k] = self.Answer(value=False, confidence=0.9, probabilities={"yes": 0.1, "no": 0.9}, p_yes=0.1)
            else:
                lab = sorted(q["criteria"])[0]
                out[k] = self.Answer(value=lab, confidence=0.9, probabilities={lab: 0.9})
        return out


def sh(cmd, cwd):
    subprocess.run(["bash", "-c", cmd], cwd=cwd, env=ENV, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


CMDS = [["git status"], ["git clean -fdx"], ["git stash -a", "git clean -fdx"], ["git checkout dev"], ["git checkout -f dev"],
        ["git merge --abort"], ["git rebase --abort"], ["git cherry-pick --abort"], ["git pull"], ["git push --force origin main"],
        ["git worktree remove --force ../wt"], ["git submodule update --force"], ["git reset --hard notes.md"],
        ["git switch HEAD~1"], ["git sparse-checkout set src"], ["git stash drop stash@{3}"], ["git checkout dev -- app.py"],
        ["git reset --hard"], ["git stash", "git checkout dev", "git stash pop"], ["git commit -am wip", "git reset --hard HEAD~1"],
        ["git rebase main"], ["git merge dev"], ["git restore --staged app.py"], ["git rm app.py"], ["git mv app.py b.py"]]
SHELL_LINES = ["rm -rf build", "rm notes.md", "rm -f missing.txt", "mv app.py old.py", "cp app.py notes.md",
               "cp -r build out", "sed -i 's/v1/v2/' app.py", "sed -n 1p app.py > first.txt", "echo x > notes.md",
               "echo x >> notes.md", "cat app.py > app.py", "find . -name '*.md' -delete", "find build -type f",
               "tar czf build.tgz build && rm -rf build", "truncate -s 0 app.py", "ln -sf app.py notes.md",
               "rsync -a build/ out/", "rm -r build/ notes.md", "cd build && rm -f x", "mkdir -p out && mv build out/",
               "touch new.txt", "perl -pi -e 's/v1/v2/' app.py", "ls | xargs rm", "rm -rf ./*"]
MIXED = ["git diff > out.patch", "git status && rm notes.md", "sed -i 's/v1/v2/' app.py && git diff --stat",
         "git stash && rm -rf build", "git add -A && git commit -qm x && rm notes.md"]
FOLLOWED = ["cd .. && git -C work status", "git -C . reset --hard", "(cd build && ls); git checkout -- app.py",
            "git worktree add -q ../wt2 main && cd ../wt2 && git log -1", "mkdir -p x && cd x && ls",
            "git branch --merged main | grep -v main | xargs git branch -d"]


def compare_git(repo, label, counts):
    """git.check with its defaults sends the same request; the 0.1.0 description (facts off) is unchanged too."""
    for i, cmds in enumerate(CMDS):
        r0, r1 = Recorder(V0.C.Answer), Recorder(V1.C.Answer)
        V0.G.check(cmds, repo=repo, client=r0)
        V1.G.check(cmds, repo=repo, client=r1)
        assert r0.requests == r1.requests, (label, cmds)
        counts["check_requests"] += 1
        assert V0.G.repo_state(repo, cmds, facts=False) == V1.G.repo_state(repo, cmds, facts=False), (label, cmds)
        counts["descriptions_facts_off"] += 1
        if i == 0:
            assert V0.G.repo_state(repo, cmds, commit_text="message") == V1.G.repo_state(repo, cmds, commit_text="message")
            counts["descriptions_messages"] += 1


def norm(text):
    """0.1.3's Linux text with the coreutils fix undone, to compare with 0.1.2's."""
    return text.replace(", GNU coreutils ", ", ")


def compare_shell(repo, label, counts, diffs):
    where = "a Linux machine (bash 5.2 with default options, GNU coreutils 9.4, findutils, sed, tar, rsync)"
    for line in SHELL_LINES:
        for w in (None, where):
            a = V0.S.shell_prompt(V0.S.inspect([line], repo, salt=KEY, where=w))
            b = V1.S.shell_prompt(V1.S.inspect([line], repo, salt=KEY, where=w))
            if a == b:
                counts["shell_prompts_identical"] += 1
            elif w is None and LINUX and norm(b) == a:
                counts["shell_prompts_coreutils_text_only"] += 1
            else:
                counts["shell_prompts_other_difference"] += 1
                diffs.append((label, line, w))


def run_hook(V, line, cwd):
    rec, out = Recorder(V.C.Answer), io.StringIO()
    stdin = io.StringIO(json.dumps({"tool_name": "Bash", "tool_input": {"command": line}, "cwd": cwd}))
    env = {**ENV, "EKBASIS_SHELL_GUARD": "1", "EKBASIS_URL": "http://127.0.0.1:9", "EKBASIS_HOOK_DEADLINE": "60"}
    with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(V.H, "Ekbasis", lambda **k: rec), \
            mock.patch.object(V.S, "_key", lambda salt=None: KEY), mock.patch("sys.stdin", stdin), \
            redirect_stdout(out), redirect_stderr(io.StringIO()):
        V.H.main()
    return rec.requests


def compare_hook(repo, label, counts, diffs):
    lines = [(" && ".join(c), "git") for c in CMDS] + [(l, "shell") for l in SHELL_LINES] + \
            [(l, "mixed") for l in MIXED] + [(l, "followed") for l in FOLLOWED]
    for line, kind in lines:
        a, b = run_hook(V0, line, repo), run_hook(V1, line, repo)
        if LINUX:
            b = [(norm(s), q) for s, q in b]
        counts[f"hook_{kind}_lines"] += 1
        if a == b:
            counts[f"hook_{kind}_identical"] += 1
        elif all(x in a for x in b):
            counts[f"hook_{kind}_0.1.3_asks_less"] += 1          # every 0.1.3 request is one 0.1.2 sends
        elif kind in ("mixed", "followed") or not a:
            counts[f"hook_{kind}_new_requests"] += 1              # the shell part of a git line, or a line 0.1.2 could not follow
        else:
            counts[f"hook_{kind}_changed"] += 1
            diffs.append((label, line, kind))


def world_layout(counts):
    rng = random.Random(7)
    words = ["lamp", "red", "the box", "fill A", "pour A into B", "x" * 30, "é ü 中", "line\nbreak", ""]
    for _ in range(500):
        rules, state = rng.choice(words) + ".", rng.choice(words)
        acts = [rng.choice(words) for _ in range(rng.randint(1, 4))]
        assert V0.P.world_state(rules, state, acts) == V1.P.world_state(rules, state, acts)
        q = rng.choice(words) + "?"
        opts = rng.sample(words, 3)
        assert V0.P.yes_no(q) == V1.P.yes_no(q) and V0.P.choice(q, opts) == V1.P.choice(q, opts)
        counts["world_prompts"] += 1
    probs = {"a": {"0": 0.6, "1": 0.4}, "b": {"0": 0.2, "1": 0.8}}

    class Fixed(Recorder):
        def ask(self, state, questions, read_once=False, images=None):
            self.requests.append((state, json.dumps(questions, sort_keys=True)))
            return {k: self.Answer(value=max(probs[k], key=probs[k].get), confidence=max(probs[k].values()),
                                   probabilities=dict(probs[k])) for k in questions}

    qs0 = {k: V0.P.choice(f"What is {k}?", ["0", "1"]) for k in ("a", "b")}
    qs1 = {k: V1.P.choice(f"What is {k}?", ["0", "1"]) for k in ("a", "b")}
    r0, r1 = Fixed(V0.C.Answer), Fixed(V1.C.Answer)
    render = lambda s: f"a={s['a']} b={s['b']}"  # noqa: E731
    V0.Sim.simulate(r0, "R.", {"a": "0", "b": "0"}, ["x", "y", "z"], qs0, render)
    V1.Sim.simulate(r1, "R.", {"a": "0", "b": "0"}, ["x", "y", "z"], qs1, render)
    assert r0.requests == r1.requests
    counts["simulate_requests"] += len(r0.requests)


def main():
    from collections import Counter
    counts, diffs = Counter(), []
    world_layout(counts)
    with tempfile.TemporaryDirectory() as root:
        w = os.path.join(root, "work")
        os.makedirs(w)

        def step(label):
            compare_git(w, label, counts)
            compare_shell(w, label, counts, diffs)
            compare_hook(w, label, counts, diffs)

        sh("git init -q -b main && git config commit.gpgsign false && printf '.env\\nbuild/\\n' > .gitignore && echo v1 > app.py "
           "&& git add -A && git commit -qm init && git init -q --bare ../origin.git && git remote add origin ../origin.git "
           "&& git push -q -u origin main", w)
        step("clean")
        sh("echo e > .env && mkdir -p build && echo b > build/x && echo n > notes.md && echo edit >> app.py", w)
        step("dirty+ignored")
        sh("git stash -q && git checkout -q -b dev && echo k > .env && git add -f .env && echo d >> app.py && git commit -qam dev "
           "&& git checkout -q main && echo e > .env && echo mine >> app.py && git commit -qam mine", w)
        step("target tracks ignored")
        sh("git merge dev", w)
        step("merge conflict")
        sh("echo resolved > app.py", w)
        step("merge resolved by hand")
        sh("git merge --abort && git checkout -q dev && git rebase main", w)
        step("rebase conflict")
        sh("git rebase --abort && git checkout -q main && git cherry-pick dev", w)
        step("cherry-pick conflict")
        sh("git cherry-pick --abort && git worktree add -q ../wt dev && echo w >> ../wt/app.py", w)
        step("linked worktree")
        sh("git init -q ../lib && cd ../lib && echo 1 > lib.py && git add -A && git commit -qm l1", w)
        sh("git -c protocol.file.allow=always submodule add -q \"$(cd .. && pwd)/lib\" lib && git commit -qm sub && echo x >> lib/lib.py", w)
        step("submodule")
        sh("git clone -q ../origin.git ../peer && cd ../peer && echo r >> app.py && git commit -qam r && git push -q", w)
        sh("git fetch -q", w)
        step("diverged remote")
    print(json.dumps({"versions": [V0.E.__version__, V1.E.__version__], "platform": platform.system(),
                      "counts": dict(sorted(counts.items())), "unexpected": diffs[:20],
                      "ok": not diffs and counts["shell_prompts_other_difference"] == 0}))


if __name__ == "__main__":
    main()
