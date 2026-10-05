# Changelog

## 0.1.1

The git guard now sees what `git status` does not show, and is told a few git rules its training did not cover. Same
model, server, questions and thresholds.

- **Facts in the state**, only when they exist or a command could touch them:
  - ignored files, for `git clean -x/-X`, `git stash -a`, `git sparse-checkout`, or a target ref that tracks the same
    path;
  - untracked or ignored files that a target ref also has, with the same or different content;
  - linked worktrees and submodules, with their own `git status`;
  - whether a conflicted file still has conflict markers or was resolved by hand;
  - cherry-pick, revert and am sessions (0.1.0 called an am session a rebase);
  - for `git pull` and `git push`: ahead/behind the upstream, and `pull.rebase`/`pull.ff`.
- **Notes**: one plain-text git rule for each command form outside the training data that needs it, after the command
  list. Examples: `switch -f`, `reset --merge <commit>`, `rebase --abort`, `clean -x`, `worktree remove`,
  `submodule update`, `git pull` with no mode. Trained command forms get no note, so their prompts are unchanged.
- **API**: `git.check(..., facts=True, notes=True)`. With `facts=False, notes=False` it gives 0.1.0's description and
  prompt byte for byte. New `git.inspect()`; `repo_state()` keeps its signature.
- **Measured** on 334 fresh sandbox scenarios (pre-registered, generated after the client was frozen, the truth from
  running git):
  - work-losing commands flagged: 59.8% → 87.4% (where 0.1.0's state hid the deciding fact: 28.9% → 79.0%);
  - false alarms: 8.9% → 8.1%;
  - "fails" right: 81.4% → 90.9%.

  The release evaluation's prompts are unchanged: git3 96.55%, guard set 827/863 and 766/799. What still fails is in
  the README's Limits section. Details: [results/client_0.1.1/RESULTS.md](results/client_0.1.1/RESULTS.md).

## 0.1.0

First release.
