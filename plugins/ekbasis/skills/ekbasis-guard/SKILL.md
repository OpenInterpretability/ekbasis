---
name: ekbasis-guard
description: Consult the Ekbasis consequence model BEFORE actions that are hard to undo (git history work, rm/mv over data without a backup, database DDL/DML without a narrow WHERE, killing processes you did not start, deleting cloud resources, payments, cancellations, sharing links, sending messages to many people). Use when about to run a command or click that could lose work, break production, move money or leak information, especially when you cannot see every effect. Ekbasis forecasts what the action will do in this state; it does not decide for you.
---

# Ekbasis guard: foresee before you act

Ekbasis is a consequence model: given the **state** of the world and an **action**, it returns **calibrated
probabilities** for typed questions (what happens, will work be lost, how many files keep their changes) in one
forward pass. It does not write text or decide. You decide, with the human, what to do with the forecast.

Full reference for agents (formats, errors, feedback): https://openinterp.org/ekbasis/agents.md

## When to consult

Before any action that is hard to undo:

- **git**: `reset --hard`, `checkout -f`, `checkout -- <path>`, `restore`, `clean -fd`, `branch -D`, `stash drop/clear`,
  `push --force`, history rewrites; anything touching uncommitted work or commits only one side has
- **files**: `rm`/`mv`/`>` over data that is not in git or backed up; globs; folders you did not create this session
- **databases**: `DROP`, `TRUNCATE`, `DELETE`/`UPDATE` without a narrow `WHERE`, migrations on real data
- **processes / infra**: `kill` of a PID you did not start (stale notes lie: check `ps` first), deleting namespaces,
  volumes or secrets, scaling down, `apply` with the wrong context
- **apps and messages**: transfers and payments, cancellations, sharing links, deleting cloud files, reply-all or
  sending outside the original circle, recurring calendar events

If the action only reads, creates something new, or is trivially undoable, **skip the consult**. Asking about
everything trains the human to click through warnings.

## How to consult

Setup: `pip install "git+https://github.com/OpenInterpretability/ekbasis"`, then
`EKBASIS_URL=https://openinterp.org/api/v1` and `EKBASIS_API_KEY=ekb_…` (key at https://openinterp.org/console), or
`EKBASIS_URL` pointing at your own server (open weights).

In the Claude Code plugin the `ekbasis` command is already on PATH (no pip needed). If it prints "Ekbasis plugin: not
set up" (exit 3), Ekbasis cannot foresee anything yet: tell the human, once, to get a key at
https://openinterp.org/console and set `EKBASIS_API_KEY` (or `EKBASIS_URL` for their own server), then restart Claude
Code, and treat irreversible actions as unchecked until then. Do not invent a key or a server.

**Git and shell commands — the CLI builds the state for you:**

```bash
ekbasis git-check -- "git reset --hard"
ekbasis shell-check -- "rm -r build/"            # prototype
ekbasis git-check -- "git checkout main" && git checkout main
```

Exit codes: `0` no risk found · `2` RISKY · `3` CANNOT FORESEE (**treat it like 2**) · `1` usage error.

**Anything else — the raw API:** `POST $EKBASIS_URL/v1/systemone` with `Authorization: Bearer $EKBASIS_API_KEY`:

```json
{"state": "Checking account available balance: $180.20. About to: transfer $250.00 to savings.",
 "questions": {
   "outcome": {"type": "choice", "instructions": "What happens with the transfer?",
               "options": ["transfer succeeds", "transfer fails: insufficient funds"]},
   "loss": {"type": "noul", "instructions": "Is any money lost or charged as a fee?",
            "criteria": {"true": "money is lost or a fee is charged", "false": "no money is lost"}}}}
```

Types: `choice` (list the outcomes, including the bad one), `noul` (yes/no with written criteria; `probability` is
P(true)), `score` (a count or level with each value described). Put several questions about one state in one request.
`"read_once": true` pays for the state once (3 questions: 261 input tokens instead of 420) but costs 0.9–3.1 points of
accuracy: use it to screen cheaply, and send the question that decides an irreversible action without it.

## The state you send

1. End with `About to: <exact command or click>`.
2. Put the numbers in: balances, sizes, counts, limits, dates with time zones.
3. Write the hidden consequences and rules you know of (the backup that exists, the fare rule that cancels the
   return flight, the subfolder a link also exposes).
4. Describe what is, not what you hope ("untracked: config.yaml", not "config is safe").
5. Only the facts the action touches.

## How to read the answer

| Answer | What to do |
|---|---|
| p(bad) ≥ 0.5, or RISKY (exit 2) | Do not run it. Tell the human the reason in one line and offer the safer route (stash first, add a WHERE, back up, `--force-with-lease`, a narrower link). Run only after explicit confirmation. |
| 0.2 ≤ p(bad) < 0.5 | For anything irreversible, treat as risky: ask, or take the safer route. |
| p(bad) < 0.2 | No warning. **Not proof of safety**: keep your normal confirmations, backups and the human's instructions. |
| Confidence ≈ 0.5–0.85 | The state is ambiguous or missing a fact. Collect it (read the file, `git status`, list the folder, read the policy) and ask again. Do not guess. |
| CANNOT FORESEE (exit 3), HTTP 401/402/403/5xx, timeout | Fail closed: treat as risky; do not run the irreversible action without the human. |

Never let Ekbasis override the human's explicit instruction or a policy you were given. When the request itself names
the harmful action, confirm before doing it.

## Measured reference (Ekbasis-27B-INT4, October 2026)

- **Not git-only**: 171 scenarios in 21 domains (money, files and shell, databases/SQL, email, calendar, cloud and
  Kubernetes, cloud storage, docker, CI, identity, network, data and ML pipelines, jobs, numbers, plans): 168 of 168
  scored right ([`examples/results.md`](https://github.com/OpenInterpretability/ekbasis-cookbook/blob/main/examples/results.md)). Scenarios written by us with the deciding facts in
  the state: put those facts in yours.
- Classic git losses: 8/8 flagged at 98–99%; 9 safe commands: 0 false alarms
- Force-push over commits the remote holds: flagged since client 0.1.7
- Agents in pre-registered studies: harmful actions fell for every model tested; Claude Sonnet on real apps 25.0% → 4.2%
  (https://doi.org/10.5281/zenodo.23197341); Kubernetes: Haiku 66.7% → 5.6% ([`docs/K8S_STUDY.md`](https://github.com/OpenInterpretability/ekbasis-cookbook/blob/main/docs/K8S_STUDY.md))
- Weak spots: domains far from training, never-seen command types, obfuscated commands; `shell-check` misses
  `curl … | bash` and `kill -9 -1`. A warning layer, not a security boundary.
- Latency: 0.4–2.5 s per check on the hosted API; 5–12 s on a Mac (MLX)

## After the action: feedback

When you learn how it turned out, report it (free; client 0.1.9+):
`ekbasis feedback --last --prevented-harm` · `--false-alarm` · `--correct` · `--wrong` (`--note "…"` optional, never secrets).

## Chaining in scripts

```bash
ekbasis git-check -- "git reset --hard" || { echo "Ekbasis: check first"; exit 2; }
```
