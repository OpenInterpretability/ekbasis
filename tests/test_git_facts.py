"""Offline tests (no server) for the facts and notes of client 0.1.1: what `git status` does not show is added only when
it exists or when the commands could touch it, and the notes appear only for the commands that need them.
Run: python -m pytest tests  (or python tests/test_git_facts.py)."""
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from ekbasis import git as G  # noqa: E402
from ekbasis import prompts as P  # noqa: E402

ENV = dict(os.environ, GIT_AUTHOR_NAME="Dev", GIT_AUTHOR_EMAIL="dev@example.invalid", GIT_COMMITTER_NAME="Dev",
           GIT_COMMITTER_EMAIL="dev@example.invalid", LC_ALL="C", GIT_EDITOR="true", GIT_CONFIG_NOSYSTEM="1")


def sh(cmd, cwd, check=True):
    subprocess.run(["bash", "-c", cmd], cwd=cwd, env=ENV, check=check, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def repo_with_remote(root):
    repo = os.path.join(root, "work")
    os.makedirs(repo)
    sh("git init -q -b main && git config commit.gpgsign false && git config protocol.file.allow always "
       "&& printf '.env\\nbuild/\\n' > .gitignore && echo v1 > app.py && echo a > README.md && git add -A && git commit -qm init", repo)
    sh("git init -q --bare -b main ../origin.git && git remote add origin ../origin.git && git push -q -u origin main", repo)
    return repo


def test_ignored_files_only_when_a_command_can_touch_them():
    with tempfile.TemporaryDirectory() as root:
        repo = repo_with_remote(root)
        sh("echo SECRET=1 > .env && mkdir -p build && echo x > build/out.txt", repo)
        for cmds in (["git clean -fd"], ["git status"], ["git stash -u"]):
            state, _ = G.repo_state(repo, cmds)
            assert "ignored" not in state, cmds
            assert "git status: nothing to commit, working tree clean" in state
        for cmds in (["git clean -fdx"], ["git clean -fX"], ["git stash -a", "git clean -fdx"], ["git stash push --all"],
                     ["git sparse-checkout set src"]):
            state, _ = G.repo_state(repo, cmds)
            assert "git status: nothing to commit, working tree clean; .env (ignored); build/ (ignored)" in state, cmds
            assert ".env (h" in state  # its fingerprint, in the Files line
        state, _ = G.repo_state(repo, ["git clean -fd -e .env"])
        assert "ignored" not in state


def test_ignored_or_untracked_file_a_target_tracks():
    with tempfile.TemporaryDirectory() as root:
        repo = repo_with_remote(root)
        sh("git checkout -q -b dev && echo API=1 > .env && echo n > notes.md && git add -f .env notes.md && git commit -qm env "
           "&& git checkout -q main && echo SECRET=1 > .env && echo mine > notes.md", repo)
        state, _ = G.repo_state(repo, ["git checkout dev"])
        assert ".env (ignored; also committed on dev, with different content)" in state
        assert "notes.md (untracked; also committed on dev, with different content)" in state
        assert P.NOTE_IGNORED in P.git_notes(["git checkout dev"], G.inspect(repo, ["git checkout dev"]).info)
        state, _ = G.repo_state(repo, ["git switch -c other"])
        assert "ignored" not in state and "also committed" not in state


def test_linked_worktree_and_submodule():
    with tempfile.TemporaryDirectory() as root:
        repo = repo_with_remote(root)
        sh("git branch feature && git worktree add -q ../wt feature && echo edit >> ../wt/app.py", repo)
        state, _ = G.repo_state(repo, ["git worktree remove ../wt"])
        assert "Linked worktrees: ../wt (branch feature; git status: app.py (unstaged modified))" in state
        sh("git init -q ../lib && cd ../lib && echo 1 > lib.py && git add -A && git commit -qm l1", repo)
        sh("git -c protocol.file.allow=always submodule add -q \"$(cd .. && pwd)/lib\" lib && git commit -qm sub", repo)
        sh("cd ../lib && echo 2 >> lib.py && git commit -qam l2", repo)
        sh("cd lib && git -c protocol.file.allow=always pull -q origin HEAD 2>/dev/null || git -c protocol.file.allow=always fetch -q && git checkout -q FETCH_HEAD", repo, check=False)
        sh("echo local >> lib/lib.py", repo)
        state, _ = G.repo_state(repo, ["git submodule update"])
        line = [l for l in state.splitlines() if l.startswith("Submodules: ")]
        assert line and "lib (" in line[0] and "git status inside: lib.py (unstaged modified)" in line[0], state
        assert "Submodules" not in G.repo_state(repo, ["git submodule update"], facts=False)[0]


def test_conflict_markers_and_operations():
    with tempfile.TemporaryDirectory() as root:
        repo = repo_with_remote(root)
        sh("git checkout -q -b feature && echo theirs > app.py && git commit -qam f && git checkout -q main "
           "&& echo ours > app.py && git commit -qam m", repo)
        sh("git merge feature", repo, check=False)
        state, _ = G.repo_state(repo, ["git merge --abort"])
        assert "app.py (staged unmerged (conflict), unstaged unmerged (conflict); conflict markers still in the file)" in state
        sh("echo resolved > app.py", repo)
        state, _ = G.repo_state(repo, ["git merge --abort"])
        assert "; resolved by hand (no conflict markers left), not added yet)" in state
        sh("git merge --abort && git cherry-pick feature", repo, check=False)
        state, _ = G.repo_state(repo, ["git cherry-pick --abort"])
        assert "Operation in progress: cherry-pick (unfinished)" in state
        assert "Operation in progress" not in G.repo_state(repo, ["git cherry-pick --abort"], facts=False)[0]


def test_ahead_behind_only_for_pull_and_push():
    with tempfile.TemporaryDirectory() as root:
        repo = repo_with_remote(root)
        sh("git clone -q ../origin.git ../peer && cd ../peer && echo r >> README.md && git -c commit.gpgsign=false commit -qam r && git push -q", repo)
        sh("echo l >> app.py && git commit -qam l && git fetch -q", repo)
        assert "ahead" not in G.repo_state(repo, ["git status"])[0]
        state, _ = G.repo_state(repo, ["git pull"])
        assert "(the current branch is 1 commit ahead of it and 1 behind)" in state
        sh("git config pull.rebase true", repo)
        state, _ = G.repo_state(repo, ["git pull"])
        assert "(this repository sets pull.rebase=true)" in state


# a concrete command for every command form of the git training grammar (gitbox3's menu, as git_wild classifies it)
TRAINED = ["echo x >> app.py", "rm app.py", "mv app.py b.py", "cp app.py b.py", "git add app.py", "git add -A",
           "git commit -m wip", "git commit -am wip", "git checkout feature", "git switch -c tmp", "git branch -D feature",
           "git merge feature", "git reset --hard", "git reset --soft HEAD~1", "git restore --staged app.py",
           "git restore app.py", "git stash", "git stash pop", "git rm --cached app.py", "git rm app.py",
           "git push origin main", "git pull origin main", "git revert --no-edit HEAD", "git clean -fd", "git stash drop",
           "git reset --hard HEAD~1", "git checkout -- .", "git stash -u", "git checkout -- app.py", "git reset HEAD app.py",
           "git commit --amend --no-edit", "git switch feature", "git merge --abort", "git cherry-pick feature",
           "git checkout -b tmp", "git branch tmp", "git stash apply", "git stash --keep-index", "git reset HEAD~1",
           "git push -f origin feature", "git fetch origin", "git merge --ff-only feature", "git merge --squash feature",
           "git revert --no-commit HEAD", "git clean -n", "git commit --allow-empty -m x",
           "git restore --staged --worktree app.py", "git checkout HEAD -- app.py", "git reset --merge",
           "git rebase feature", "git restore --source=HEAD~1 app.py"]


def test_no_note_for_trained_command_forms():
    info = {"nonbranch_targets": ["HEAD~1", "HEAD"], "path_args": ["app.py", "b.py", "."], "branches": ["feature", "main"]}
    for c in TRAINED:
        assert P.git_notes([c], info) == [], c
    assert P.git_state("s", ["git status"], notes=[]) == P.git_state("s", ["git status"])


def test_notes_for_the_forms_git_wild_found():
    info = {"nonbranch_targets": ["HEAD~1", "v1.0"], "path_args": ["config.yaml"], "pull_config": {}}
    want = {"git switch -f dev": P.NOTE_FORCE, "git checkout -f dev": P.NOTE_FORCE, "git switch --discard-changes dev": P.NOTE_FORCE,
            "git reset --merge HEAD~1": P.NOTE_RESET_MERGE, "git reset --keep HEAD~1": P.NOTE_RESET_KEEP,
            "git reset --hard config.yaml": P.NOTE_RESET_PATH, "git rebase --abort": P.NOTE_ABORT, "git rebase --skip": P.NOTE_ABORT,
            "git cherry-pick --abort": P.NOTE_ABORT, "git checkout --theirs a.py": P.NOTE_OURS,
            "git merge --continue": P.NOTE_CONTINUE, "git clean -d": P.NOTE_CLEAN, "git clean -fdx": P.NOTE_CLEAN_X,
            "git switch HEAD~1": P.NOTE_DETACH_SWITCH, "git checkout v1.0": P.NOTE_DETACH_CHECKOUT,
            "git switch --orphan x": P.NOTE_ORPHAN, "git mv -f a.py b.py": P.NOTE_MV, "git worktree remove ../wt": P.NOTE_WORKTREE,
            "git submodule update --force": P.NOTE_SUBMODULE, "git pull": P.NOTE_PULL, "git stash drop stash@{2}": P.NOTE_STASH_REF,
            "git sparse-checkout set src": P.NOTE_SPARSE}
    for c, n in want.items():
        assert n in P.git_notes([c], info), c
    assert P.git_notes(["git switch --detach HEAD~1"], info) == []
    assert P.git_notes(["git checkout HEAD~1 -- a.py"], info) == []
    assert P.git_notes(["git clean -fd -e notes.md"], info) == [P.NOTE_CLEAN]
    prompt = P.git_state("s", ["git switch -f dev"], notes=P.git_notes(["git switch -f dev"], info))
    assert prompt == (P.GIT_RULES + "\n\nState before:\ns\n\nCommands, in order:\n1. git switch -f dev\n\nGit rules for these commands: "
                      + P.NOTE_FORCE + "\n\n" + P.GIT_NOTE)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("ok")
