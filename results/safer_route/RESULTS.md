# Safer route on the classic losses (hosted API, 2026-10-10)

`run.py` builds a throwaway repository per scenario (main pushed to a local bare `origin`, a `feature` branch, an
`unmerged` branch with its own commit), checks the command, searches the safer route (`ekbasis.safer.search`), times
the Claude Code hook with `EKBASIS_SAFER=0` and `=1` on the same state, then **runs the route** in the repository and
checks that what the original would lose is still there. Server: `https://openinterp.org/api/v1`. 3 repetitions of 9
scenarios (27 rows in [runs.json](runs.json)); the table shows repetition 0 and notes where the others differ.

| Scenario | Command | Risky? (model p_lost / code) | Route offered | Route p_lost | Route ran, work kept |
|---|---|---|---|---|---|
| uncommitted edit | `git reset --hard` | RISKY 99% | `git stash push && git reset --hard` | 0.3% | exit 0, edit in the stash |
| unpushed commit + edit | `git reset --hard HEAD~1` | RISKY 99%; code: drops 1 commit | `git stash push && git branch backup/main && git reset --hard HEAD~1` | 0.4% | exit 0, edit in the stash, commit on backup/main |
| edit | `git checkout -- app.py` | RISKY 99% | `git stash push -- app.py && git checkout -- app.py` | 0.8% | exit 0, edit in the stash |
| edit | `git restore app.py` | RISKY 99% | `git stash push -- app.py && git restore app.py` | 2.8% | exit 0, edit in the stash |
| edit, app.py differs on feature | `git checkout -f feature` | RISKY 99% | `git stash push && git checkout feature` | 0.3% | exit 0, on feature, edit in the stash |
| untracked file and folder | `git clean -fd` | RISKY 99% | `git stash push -u -- notes.txt scratch/` | 0.3% | exit 0, files gone from the tree, both in the stash |
| unmerged branch | `git branch -D unmerged` | ok 0.04%; code: deletes 1 commit | `git branch -m unmerged backup/unmerged` | 0.04% | exit 0, commit on backup/unmerged |
| one stash entry | `git stash drop` | RISKY 99% | none in reps 0 and 2 (the one candidate, `git branch backup/stash-0 stash@{0} && git stash drop`, did not pass; in separate probes it scored 0.21–0.22); offered in rep 1 at 16% | 16% (rep 1) | rep 1: exit 0, entry on backup/stash-0 |
| remote has a fetched commit the local branch lacks | `git push --force` | ok 0.04%; code: overwrites 1 remote commit | none (3/3): in a separate probe the model gave the push 0.86 to fail after the backup branch, 0.98 alone; `--force-with-lease` alone also fails the code check | – | – |

Every offered route (22 of 27 rows) ran with exit 0 and kept the work. No route was offered that had not passed both
the model and the code checks.

**`--force-with-lease` does not protect fetched commits** (the route for force-push changed in the second run below). Run alone on the push scenario (a fresh copy, 3/3): exit 0
and the remote's commit was overwritten (`origin/main` now ends at the local commit). The lease compares with the
remote-tracking ref, which already holds that commit. So the safer route counts `--force-with-lease` as a force in
its code check, and the hook's message no longer suggests it as the fix.

## Latency (27 rows, seconds; median, min–max)

| | median | range |
|---|---|---|
| `git.check` on the original | 4.25 | 2.47–7.93 |
| safer-route search (candidates in parallel) | 4.91 | 2.49–8.83 |
| hook, `EKBASIS_SAFER=0` | 3.60 | 0.08–7.37 |
| hook, `EKBASIS_SAFER=1` | 8.28 | 3.69–14.29 |
| hook: added by the route (same row) | 4.84 | −0.80–9.06 |

The search costs about one more round trip, only when a line is flagged (rows with code-only findings skip the
model for the original, so the hook goes from 0.08–0.09 s to 3.7–4.8 s there). The server was slower during this run
than in a probe earlier the same day (1.3 s for one check, 0.8–1.1 s per candidate); it overlapped a benchmark sending
4 parallel requests to the same API, so these latencies are an upper bound, not the API's usual speed. With the default
`EKBASIS_HOOK_DEADLINE=25` no search ran out of time; a search that does is dropped and the warning goes out without a
route.

## Limits

- 9 scenarios on small synthetic repositories, one server; not an agent study. Whether agents follow the route more
  than the warning is not measured here.
- `stash drop`: the model's score for the backup-branch route sits around the threshold (0.16 in rep 1, 0.21–0.22 in probes), so it is offered
  in some runs only. `push --force`: the model predicts that the protected push fails, which is wrong here (it
  succeeds), so no route passes. In both cases the client says "none passed" instead of guessing.
- `git-check` and the MCP tool look for a route only when the model finds the commands risky; branch deletion and
  force-push are flagged by code in the hook only, so their routes appear in the hook (and via `ekbasis.safer.search`).

## Second run: force-push, remote branch deletion, `rebase --onto` (1 repetition, [runs_2.json](runs_2.json))

After an outside tester's report: `--force-with-lease`, alone or with an expected value read from the same state,
overwrote a fetched remote commit on a bare remote (unit test `tests/test_remote_rebase_loss.py`), while
`--force-with-lease --force-if-includes` (git >= 2.30; here git 2.50) refused it and, once the branch was rebased onto
the remote, went through. The force-push route is now that command; its refusal is the safe outcome, so the model's
"fails" for that step does not reject it. Also new: deleting a remote branch whose commits no other ref holds, and
`git rebase --onto` dropping commits, are lost work checked by code; a force-push is checked against the branch its
refspec names (before: origin/HEAD, a false alarm on a new branch).

| Scenario | Command | Flagged by | Route offered | Route p_lost | Route ran |
|---|---|---|---|---|---|
| fetched remote commit on main | `git push --force` | code: overwrites 1 commit | `git push --force-with-lease --force-if-includes` | 0.06% | refused (exit 1), remote still has the commit |
| remote-only branch with 1 commit | `git push origin --delete gone` | code: deletes 1 commit | none: the model gives `git branch backup/origin-gone origin/gone` 0.99 to fail | – | – |
| 3 unpushed commits | `git rebase --onto HEAD~3 HEAD~1` | code: drops 2 commits | none: the model gives the rebase 0.85 to fail | – | – |
| new branch, no upstream, origin/main moved | `git push -f origin topic` | not flagged (was flagged against origin/main before) | – | – | – |

`--force-with-lease` alone on the first scenario's state, for comparison: exit 0, the remote's commit overwritten.
For the two "none" rows the state does not list remote branches other than the default one, which is a likely reason
the model expects the backup branch on `origin/gone` to fail; the client says "none passed" there instead of guessing.
