"""facts=False must give client 0.1.0's description byte for byte, and notes=None its prompt: the released package and
the candidate read the same repositories (clean, dirty, ignored files, a target that tracks them, a merge and a rebase
stopped on a conflict, a cherry-pick, a linked worktree, a submodule, a diverged remote) with many command lists.
python3 test_equivalence.py [released package dir] [candidate package dir]"""
import importlib.util
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REL = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "..", "release_clean", "code_eikos", "ekbasis", "ekbasis")
NEW = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "ekbasis", "ekbasis")
ENV = dict(os.environ, GIT_AUTHOR_NAME="Dev", GIT_AUTHOR_EMAIL="dev@example.invalid", GIT_COMMITTER_NAME="Dev",
           GIT_COMMITTER_EMAIL="dev@example.invalid", LC_ALL="C", GIT_EDITOR="true", GIT_CONFIG_NOSYSTEM="1")


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, os.path.join(path, "__init__.py"), submodule_search_locations=[path])
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return importlib.import_module(name + ".git"), importlib.import_module(name + ".prompts")


G0, P0 = load("ekbasis_010", os.path.realpath(REL))
G1, P1 = load("ekbasis_next", os.path.realpath(NEW))


def sh(cmd, cwd):
    subprocess.run(["bash", "-c", cmd], cwd=cwd, env=ENV, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


CMDS = [["git status"], ["git clean -fdx"], ["git stash -a", "git clean -fdx"], ["git checkout dev"], ["git checkout -f dev"],
        ["git merge --abort"], ["git rebase --abort"], ["git cherry-pick --abort"], ["git pull"], ["git push --force origin main"],
        ["git worktree remove --force ../wt"], ["git submodule update --force"], ["git reset --hard notes.md"],
        ["git switch HEAD~1"], ["git sparse-checkout set src"], ["git stash drop stash@{3}"], ["git checkout dev -- app.py"]]


def compare(repo, label):
    n = 0
    for cmds in CMDS:
        for ct in ("hash", "message"):
            a = G0.repo_state(repo, cmds, commit_text=ct)
            b = G1.repo_state(repo, cmds, commit_text=ct, facts=False)
            assert a == b, (label, cmds, ct, a[0], b[0])
            n += 1
        assert P0.git_state(a[0], cmds) == P1.git_state(b[0], cmds), (label, cmds)
    return n


def main():
    n = 0
    with tempfile.TemporaryDirectory() as root:
        w = os.path.join(root, "work")
        os.makedirs(w)
        sh("git init -q -b main && git config commit.gpgsign false && printf '.env\\nbuild/\\n' > .gitignore && echo v1 > app.py "
           "&& git add -A && git commit -qm init && git init -q --bare ../origin.git && git remote add origin ../origin.git "
           "&& git push -q -u origin main", w)
        n += compare(w, "clean")
        sh("echo e > .env && mkdir -p build && echo b > build/x && echo n > notes.md && echo edit >> app.py", w)
        n += compare(w, "dirty+ignored")
        sh("git stash -q && git checkout -q -b dev && echo k > .env && git add -f .env && echo d >> app.py && git commit -qam dev "
           "&& git checkout -q main && echo e > .env && echo mine >> app.py && git commit -qam mine", w)
        n += compare(w, "target tracks ignored")
        sh("git merge dev", w)
        n += compare(w, "merge conflict")
        sh("echo resolved > app.py", w)
        n += compare(w, "merge resolved by hand")
        sh("git merge --abort && git checkout -q dev && git rebase main", w)
        n += compare(w, "rebase conflict")
        sh("git rebase --abort && git checkout -q main && git cherry-pick dev", w)
        n += compare(w, "cherry-pick conflict")
        sh("git cherry-pick --abort && git worktree add -q ../wt dev && echo w >> ../wt/app.py", w)
        n += compare(w, "linked worktree")
        sh("git init -q ../lib && cd ../lib && echo 1 > lib.py && git add -A && git commit -qm l1", w)
        sh("git -c protocol.file.allow=always submodule add -q \"$(cd .. && pwd)/lib\" lib && git commit -qm sub && echo x >> lib/lib.py", w)
        n += compare(w, "submodule")
        sh("git clone -q ../origin.git ../peer && cd ../peer && echo r >> app.py && git commit -qam r && git push -q", w)
        sh("git fetch -q", w)
        n += compare(w, "diverged remote")
    print(f"identical: {n} descriptions (facts=False) and their prompts (no notes), 0.1.0 vs candidate")


if __name__ == "__main__":
    main()
