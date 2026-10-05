"""0.1.2 must not change any prompt 0.1.1 sends with its defaults: the released package (0.1.1) and the candidate read
the same repositories (clean, dirty, ignored files, a target that tracks them, a merge, a rebase and a cherry-pick
stopped on a conflict, a linked worktree, a submodule, a diverged remote) with many command lists, and must give the same
repository description (facts on and off), the same notes, the same git prompt, and the same questions in git.check;
world_state, yes_no, choice and simulate (no recap) must give the same text. CPU only, no server.
python3 eval/release_equivalence.py [0.1.1 package dir] [0.1.2 package dir]"""
import importlib
import importlib.util
import json
import os
import random
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REL = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "..", "..", "release_clean", "code_eikos", "ekbasis", "ekbasis")
NEW = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "..", "ekbasis", "ekbasis")
ENV = dict(os.environ, GIT_AUTHOR_NAME="Dev", GIT_AUTHOR_EMAIL="dev@example.invalid", GIT_COMMITTER_NAME="Dev",
           GIT_COMMITTER_EMAIL="dev@example.invalid", LC_ALL="C", GIT_EDITOR="true", GIT_CONFIG_NOSYSTEM="1")


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, os.path.join(path, "__init__.py"), submodule_search_locations=[path])
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod, importlib.import_module(name + ".git"), importlib.import_module(name + ".prompts"), \
        importlib.import_module(name + ".simulate"), importlib.import_module(name + ".client")


E0, G0, P0, S0, C0 = load("ekbasis_011", os.path.realpath(REL))
E1, G1, P1, S1, C1 = load("ekbasis_012", os.path.realpath(NEW))
assert E0.__version__ == "0.1.1" and E1.__version__ == "0.1.2", (E0.__version__, E1.__version__)


class Recorder:
    """Records each request; answers every question with a fixed, neutral answer."""

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


def compare(repo, label, counts):
    """git.check with its defaults sends the same request (description, notes, prompt, questions); the 0.1.0
    description (facts=False) is unchanged too. Commit messages instead of hashes: one command list per repository."""
    for i, cmds in enumerate(CMDS):
        r0, r1 = Recorder(C0.Answer), Recorder(C1.Answer)
        G0.check(cmds, repo=repo, client=r0)
        G1.check(cmds, repo=repo, client=r1)
        assert r0.requests == r1.requests, (label, cmds)
        counts["check_requests"] += 1
        assert G0.repo_state(repo, cmds, facts=False) == G1.repo_state(repo, cmds, facts=False), (label, cmds)
        counts["descriptions_facts_off"] += 1
        if i == 0:
            assert G0.repo_state(repo, cmds, commit_text="message") == G1.repo_state(repo, cmds, commit_text="message")
            counts["descriptions_messages"] += 1


def world_layout(counts):
    rng = random.Random(7)
    words = ["lamp", "red", "the box", "fill A", "pour A into B", "x" * 30, "é ü 中", "line\nbreak", ""]
    for _ in range(500):
        rules, state = rng.choice(words) + ".", rng.choice(words)
        acts = [rng.choice(words) for _ in range(rng.randint(1, 4))]
        assert P0.world_state(rules, state, acts) == P1.world_state(rules, state, acts)
        q = rng.choice(words) + "?"
        opts = rng.sample(words, 3)
        assert P0.yes_no(q) == P1.yes_no(q) and P0.choice(q, opts) == P1.choice(q, opts)
        counts["world_prompts"] += 1
    probs = {"a": {"0": 0.6, "1": 0.4}, "b": {"0": 0.2, "1": 0.8}}

    class Fixed(Recorder):
        def ask(self, state, questions, read_once=False, images=None):
            self.requests.append((state, json.dumps(questions, sort_keys=True)))
            return {k: self.Answer(value=max(probs[k], key=probs[k].get), confidence=max(probs[k].values()),
                                   probabilities=dict(probs[k])) for k in questions}

    qs0 = {k: P0.choice(f"What is {k}?", ["0", "1"]) for k in ("a", "b")}
    qs1 = {k: P1.choice(f"What is {k}?", ["0", "1"]) for k in ("a", "b")}
    r0, r1 = Fixed(C0.Answer), Fixed(C1.Answer)
    render = lambda s: f"a={s['a']} b={s['b']}"  # noqa: E731
    S0.simulate(r0, "R.", {"a": "0", "b": "0"}, ["x", "y", "z"], qs0, render)
    S1.simulate(r1, "R.", {"a": "0", "b": "0"}, ["x", "y", "z"], qs1, render)
    assert r0.requests == r1.requests
    counts["simulate_requests"] += len(r0.requests)


def main():
    counts = {"check_requests": 0, "descriptions_facts_off": 0, "descriptions_messages": 0, "world_prompts": 0,
              "simulate_requests": 0}
    world_layout(counts)
    with tempfile.TemporaryDirectory() as root:
        w = os.path.join(root, "work")
        os.makedirs(w)
        sh("git init -q -b main && git config commit.gpgsign false && printf '.env\\nbuild/\\n' > .gitignore && echo v1 > app.py "
           "&& git add -A && git commit -qm init && git init -q --bare ../origin.git && git remote add origin ../origin.git "
           "&& git push -q -u origin main", w)
        compare(w, "clean", counts)
        sh("echo e > .env && mkdir -p build && echo b > build/x && echo n > notes.md && echo edit >> app.py", w)
        compare(w, "dirty+ignored", counts)
        sh("git stash -q && git checkout -q -b dev && echo k > .env && git add -f .env && echo d >> app.py && git commit -qam dev "
           "&& git checkout -q main && echo e > .env && echo mine >> app.py && git commit -qam mine", w)
        compare(w, "target tracks ignored", counts)
        sh("git merge dev", w)
        compare(w, "merge conflict", counts)
        sh("echo resolved > app.py", w)
        compare(w, "merge resolved by hand", counts)
        sh("git merge --abort && git checkout -q dev && git rebase main", w)
        compare(w, "rebase conflict", counts)
        sh("git rebase --abort && git checkout -q main && git cherry-pick dev", w)
        compare(w, "cherry-pick conflict", counts)
        sh("git cherry-pick --abort && git worktree add -q ../wt dev && echo w >> ../wt/app.py", w)
        compare(w, "linked worktree", counts)
        sh("git init -q ../lib && cd ../lib && echo 1 > lib.py && git add -A && git commit -qm l1", w)
        sh("git -c protocol.file.allow=always submodule add -q \"$(cd .. && pwd)/lib\" lib && git commit -qm sub && echo x >> lib/lib.py", w)
        compare(w, "submodule", counts)
        sh("git clone -q ../origin.git ../peer && cd ../peer && echo r >> app.py && git commit -qam r && git push -q", w)
        sh("git fetch -q", w)
        compare(w, "diverged remote", counts)
    print(json.dumps({"identical": counts, "versions": [E0.__version__, E1.__version__]}))


if __name__ == "__main__":
    main()
