# Agent-study benchmark: tasks, apps, adapters and judges

The materials to re-run the studies of *When Does a Consequence Model Make AI Agents Safer? Pre-registered Studies on
Demo Apps, Real Self-Hosted Apps and a Real Terminal*, not only to recompute them (`../reproduce.py` does that from
`../data/`). Every file here is a file that ran, at the same relative path, except for the edits listed in
`MANIFEST.json`: machine paths, a server's address, a user name and a provider id were replaced by environment
variables, and a few lines were made configurable (the bridges' server URL, the path of Python 3.12, the run prefixes of
the mail re-judge). `python3 verify_benchmark.py` checks every file against the manifest and, where the original was
hashed at a freeze, against `../prereg/freeze/`.

License: Apache-2.0, as the repository. Third-party software is referenced, not redistributed: the app images by digest,
τ-bench and the terminal study's repositories by URL and commit.

## What is here

| Folder | Study (paper section) | Contents |
|---|---|---|
| `launch_video/` | demo apps (§5–6) | the demo desktop (`desktop/`, plain JavaScript apps), the stages that run it in a real Chromium (`stage.mjs`; `stage_x.mjs` for the controls and the fresh set), the agent's tools as an MCP server (`agent_mcp.mjs`; `agent_mcp_glm.mjs` for opencode), the forecast bridge to Ekbasis (`foresee.py`), the agent runner and system prompts |
| `mission/X/agent/` | demo apps (§5–6) | the original set (`tasks.jsonl`, `tasks/`: 47 tasks, 42 harm and 5 controls, on 7 apps) and the fresh set (`tasks_fresh.jsonl`, `tasks_fresh/`: 35 tasks, 30 harm and 5 controls, on 5 apps), their generators and descriptions, the judges, the desktop copy with the fresh apps (`web/`), the study runners for Claude (`run_study.py`) and for opencode models (`run_study_glm.py`), the forecasters of the controls (`oracle_llm.py`; the placebo and `oracle_truth` are in `stage_x.mjs` and `web/desktop/apps/truth.js`), and a validator that needs no model |
| `mission/X/haiku/` | Claude Haiku on the demo apps (addendum D) | the driver and its analyses; `AL/run_al.py` is the one file of its copy of `mission/AL` that differs (it reads `AL_MODEL`) |
| `mission/X/tau/` | τ-bench (§8) | the episode runner, the MCP server with τ-bench's retail tools, the scorer |
| `mission/AL/` | look-ahead and state tracker (§8) | tasks, desktop, stage, tools, forecast bridge, judge, validators |
| `mission/RA/` | real apps (§9) | `apps/`: the Docker Compose file with the official images pinned by digest, the admin helpers, seeding and cleanup; `tasks/`: tasks, seeding and judges (`ra_tasks.py`), the verifier and its records; `adapters/spec_server.py`: the hand-written adapter; `harness/`: the stage (a real browser on the real app), the agent's tools, the forecast bridge, the runners |
| `mission/RA2/` | follow-up (§10) | the 32 fresh tasks with the simulated user's scripts, the adapter with request-aware questions and safer ways (`adapters/spec_server2.py`), the stage with the six conditions, the runners, the verifier and its records, and the normalised mail judge (`analysis/rejudge_mail_norm.py`) |
| `capability/real_terminal/` | real terminal (§11) | `harness/` (client 0.1.2) and `harness_013/` (the 0.1.3 re-run): the 12 tasks, preparation of the pinned repositories, the sandboxed Claude Code session with the hook wrapper, the ground truth, the offline replay, the study runner and analyses |

The plans that governed each study, with their freeze files, are in `../prereg/`.

## Requirements

- **Node.js 22** and, in this folder, `npm install` (Playwright 1.63.0, the MCP SDK 1.32.0, zod 4.6.5), then
  `npx playwright install chromium`.
- **Python 3.9 or later** and `pip install -r requirements.txt`. The terminal study and the Haiku driver used Python 3.12
  (`PY312`, default `/opt/homebrew/bin/python3.12`).
- **Docker** for the real apps (the studies used Docker 29 on macOS, arm64; the image digests are multi-architecture).
- **macOS** for the terminal study: its sessions run under `sandbox-exec` and snapshot with APFS clones.
- **An agent.** The studies used Claude Code 2.1.289 (2.1.292 for the follow-up's last Sonnet runs) with
  `claude-sonnet-5-5` and `claude-haiku-4-5-20251001` (the CLI aliases `sonnet` and `haiku`), and opencode 1.18 for
  GLM-5.3-Flash and Qwen 3.5. Every runner calls the agent in one shell script, so another agent can take its place
  (below). Claude Code runs are charged to your account.
- **An Ekbasis server.** Serve Ekbasis-27B as in the repository's README (`Ekbasis-27B/serve.py`; the studies used the
  Hugging Face revision `e0675dd` and `serve.py` 1.3) and point the bridges at it with `EKBASIS_URL`.
- **The client.** `requirements.txt` installs client 0.1.3. The bridges call `ekbasis.prompts.world_state`, `choice`
  and `yes_no` and `Ekbasis.ask`; the requests these send are the same in every release from 0.1.0 to 0.1.4. To use a
  local checkout instead, set `EKBASIS_CLIENT_SRC` to the folder that contains the `ekbasis` package.

## Run one task end to end

### Real apps: the follow-up (§10), with your agent and your Ekbasis server

1. Install: `npm install && npx playwright install chromium && pip install -r requirements.txt`.
2. Start the apps: `mission/RA/apps/bootstrap.sh`. It writes fresh random credentials to `mission/RA/apps/.env`
   (mode 600, never printed, git-ignored), starts Gitea 1.24.7, Nextcloud 31.0.14, Roundcube 1.7.4 and
   docker-mailserver 15.1.0 on 127.0.0.1:3330, :8481 and :8491 (the mail server has no route out), creates the admin
   accounts, applies the Nextcloud settings the studies ran with and adds the people every run shares (about two
   minutes from nothing). To start over: `docker compose down -v` in `mission/RA/apps`, then delete
   `mailconf/postfix-*.cf` and `.env`.
3. Start the forecast bridge and the adapter:
   `EKBASIS_URL=http://<host>:<port> mission/RA2/harness/services.sh start` (bridge on :8791, adapter on :8793).
   If the server is reachable only over SSH, set `EKBASIS_SSH="-p <ssh port> <user>@<host>"` and
   `EKBASIS_REMOTE_PORT=<server port>` instead, and the script opens a tunnel on :18574.
4. Check the task with no agent and no model: `python3 mission/RA2/tasks/verify_ra2.py --only g2_public_1`. It seeds a
   fresh world, drives the scripted harmful and safe paths through the stage, judges both from the app's own state,
   removes what it made, and writes `mission/RA2/tasks/verify/g2_public_1.json`.
5. Run an agent: from `mission/RA2`,
   `python3 harness/run_study_ra2.py --agent haiku0 --conds ask_ekbasis --seeds 1 --only g2_public_1 --prefix try --parallel 1 --cap 1`.
   The runner seeds a fresh world, starts the stage (a real Chromium, signed in as the task's user, every request to
   another origin blocked), runs the agent through `harness/run_agent_ra2.sh`, judges the run from the app's state,
   removes the run's objects, and appends one row to `results/runs_try.jsonl`; the stage's log and the agent's transcript
   go to `results/sessions/try/`. The conditions are `blind`, `guard`, `guard_goal`, `guard_alt`, `ask_ekbasis` and
   `ask_always`; `--tasks frozen` (the default) is the verified set.
6. Another agent: `harness/run_agent_ra2.sh` is the only place the agent is called. Replace its `claude -p` command with
   yours, giving it the MCP server in `mission/RA/harness/agent_mcp_real.mjs` (with `STAGE_URL` as in the script) and
   nothing else, the condition's system prompt (`harness/agent_system_*.txt`) and the task; then add the agent to `AGENTS`
   in `harness/run_study_ra2.py`. The stage records every look, click and answer; the judge reads only the app.

The simulated user's answer comes back to the agent as the result of the paused click, as in the study; the paper's
limits section explains why a product should deliver it through the user's channel instead.

The real-apps study itself (§9) runs the same way from `mission/RA`: `harness/services.sh start` (bridge :8781,
adapter :8783; `start oracle` adds the Claude forecaster on :8782), `python3 tasks/verify_tasks.py`, and
`python3 harness/run_study_ra.py --agent haiku0 --conds see --seeds 1 --only g_team_1 --prefix try --cap 1`.

### Demo apps (§5–6)

1. Forecast bridge: `EKBASIS_URL=http://<host>:<port> PORT=8761 python3 mission/X/agent/foresee_x.py`.
2. Without any model: from `mission/X/agent`, `python3 validate_tasks.py` drives the scripted harmful and safe paths of
   every original task with a mock forecaster; for the fresh set,
   `VSTAGE=stage_x.mjs VTASKS=tasks_fresh.jsonl VTASKDIR=tasks_fresh VJUDGE=judge_fresh VOUT=validation_fresh.json python3 validate_tasks.py`.
3. One task with Claude: from `mission/X/agent`,
   `python3 run_study.py --runner x --tasks tasks_fresh.jsonl --task-dir tasks_fresh --judge judge_fresh --conds blind see --seeds 1 --only bank_h1 --prefix try --cap 1`.
   Rows go to `runs_try.jsonl`, stage logs and transcripts to `launch_video/sessions/try/`. The original set is
   `--tasks tasks.jsonl --task-dir tasks --judge judge`; the controls are `--conds placebo oracle_truth oracle_llm`
   (`oracle_llm` needs `oracle_llm.py` on :8762, which asks Claude Sonnet); `--model haiku` runs Claude Haiku.
4. Models behind an OpenAI-compatible endpoint, through opencode: `run_agent_glm.sh` and `run_study_glm.py` (conditions
   `blind`, `see`, `router`). Set `GLM_BASEURL`, the provider and model ids `GLM_PID` and `GLM_MID`, and
   `GLM_MODEL=<GLM_PID>/<GLM_MID>`.
5. Another agent: replace the `claude -p` command in `run_agent_x.sh` (or `launch_video/run_agent.sh`, the `lv` runner)
   with yours, giving it the MCP server `launch_video/agent_mcp.mjs` and only its tools.

### Look-ahead and state tracker (§8)

`EKBASIS_URL=http://<host>:<port> python3 mission/AL/foresee_al.py` (port 8771), then from `mission/AL`
`python3 validate_al.py` (no model) and
`python3 run_al.py --tasks tasks_la.jsonl --task-dir tasks_la --conds blind ahead --seeds 1 --only adm_ci_token --prefix try --cap 1`;
the state-tracker study is `--tasks tasks_st.jsonl --task-dir tasks_st --conds alone tracker`. The Haiku runs used a copy
of this folder: `rsync -a --ignore-existing mission/AL/ mission/X/haiku/AL/` makes it (keeping the shipped `run_al.py`),
and `mission/X/haiku/haiku_driver.py` runs both Haiku studies (bridges on :8761 and :8781; create an empty
`mission/X/haiku/spend.jsonl` first, where the driver keeps its US$5 budget).

### τ-bench (§8)

Fetch τ-bench at the commit the study used:
`git clone https://github.com/sierra-research/tau-bench mission/X/ext/tau-bench-main && git -C mission/X/ext/tau-bench-main checkout 59a200c6d575d595120f1cb70fea53cef0632f6b`.
Make a Python environment with `mcp==1.30.0` and the client, then from `mission/X/tau`:
`TAU_PYTHON=<that environment's python> EKBASIS_URL=http://<host>:<port> python3 run_tau.py --n 1 --conds ekbasis --parallel 1 --cap 1`
(the agent and τ-bench's user simulator both run through `claude -p`).

### Real terminal (§11, macOS)

1. Work root: `EKB_RT_WORK` (default `/tmp/ekb_rt`; it must be on APFS). The harness expects the Ekbasis server at
   `http://127.0.0.1:18642`: forward your server there, or set `EKB_RT_TUNNEL_SSH="-p <ssh port> <user>@<host>"` and
   `EKB_RT_TUNNEL_FORWARD=18642:127.0.0.1:<server port>` and the runner opens the tunnel.
2. From `capability/real_terminal/harness`: `python3.12 prepare.py all` clones the three repositories at their pinned
   commits, installs client 0.1.2 from GitHub (commit `c67ebed`) and builds each task's start state; then
   `python3.12 run_study.py`.
3. The 0.1.3 re-run (`harness_013`) also needs client 0.1.3 in `$EKB_RT_WORK/ekbasis013_venv`:
   `python3.12 -m venv $EKB_RT_WORK/ekbasis013_venv && $EKB_RT_WORK/ekbasis013_venv/bin/pip install git+https://github.com/OpenInterpretability/ekbasis@43b9a78`
   (the modules of that commit have the SHA-256 recorded in `../prereg/freeze/terminal_FROZEN_013.sha256`).

The repositories: `more-itertools/more-itertools` at `1ea82a711c69f590054987b5cb194157f8ce8ac4`, `spf13/pflag` at
`c966cfef47379dcb01e7929504d66d94b540945b`, `chalk/chalk` at `47fc05abd46171b235e24174cd2dba83d25bf037`. Each session's
sandbox denies reads of the user's private folders; `EKB_RT_DENY_DIR` adds one more path to that list.

## Environment variables

| Variable | Used by | Meaning |
|---|---|---|
| `EKBASIS_URL` | every forecast bridge, `services.sh` | the Ekbasis server (`serve.py`) |
| `EKBASIS_CLIENT_SRC` | the bridges | a local client checkout to import instead of the installed package |
| `EKBASIS_SSH`, `EKBASIS_REMOTE_PORT` | `mission/RA*/harness/services.sh` | optional SSH tunnel to the server |
| `QWEN_SSH` | `mission/RA/harness/services.sh` with `QWEN=1` | SSH destination of the Qwen servers of the exploratory arm |
| `GLM_MODEL` and the other `GLM_*` | `run_agent_glm.sh`, `run_study_glm.py` | opencode provider, model and endpoint |
| `TAU_PYTHON` | `run_tau.py` | Python with `mcp` and the client, for the τ-bench MCP server |
| `PY312` | the terminal harness, `haiku_driver.py` | Python 3.12 |
| `EKB_RT_WORK`, `EKB_RT_TUNNEL_SSH`, `EKB_RT_TUNNEL_FORWARD`, `EKB_RT_DENY_DIR` | the terminal harness | work root, tunnel, one more denied path |

## Planted test data

- Two follow-up tasks (`g2_public_1`, `g2_public_2` in `mission/RA2/tasks/ra2_tasks.py`) plant short fake credentials
  (a `DEPLOY_TOKEN=ghp_…` line and an `sk_live_…` key, each under 16 characters) in a repository's history on purpose: the
  harm is making that history public. The demo key-manager app and its tasks (`keys.js`, `tasks_fresh/keys_*.json`) show
  fake `sk_live_…` keys. Secret scanners may flag them; none is a real credential.
- The e-mail addresses, people and companies in the tasks are made up (the demo database tasks use addresses at public
  mail domains, all fictitious).

## Not included

- Transcripts, stage logs and run outputs; the per-run tables the paper analyses are in `../data/`.
- The real apps' credentials and the mail server's account files (made at setup).
- The follow-up's exploration notes (`dev/`), and the scripts that read the request counters of the remote model
  server during the terminal re-run (`server_probe.py`, `requests_013.py`; they measure nothing about the guard).
- Materials of work the paper does not report: the preflight study, the automatic-adapter study, and the AgentWorld item
  sets (the comparison's per-item results are in `../data/`).

## Known limits, kept as they ran

- The mail judges of both real-app studies match text in the raw message body, so text the webmail wraps across lines
  can be missed. `mission/RA2/analysis/rejudge_mail_norm.py [run prefix ...]` re-judges the follow-up's mail runs from
  the recipients' mailboxes with whitespace- and quote-normalised bodies (addendum C; in the study it changed 1 of 135
  verdicts, not a harm verdict). Run it after your mail runs.
- The adapters and the safer ways are written by hand for these apps and these families; the simulated user answers by
  rules written with each task. See the paper's limits.

## What was tested before release

From a clean copy of this folder, with `npm install` and `pip install -r requirements.txt`:

- the demo-app validator on both sets (47/47 and 35/35 tasks pass: the scripted harmful path is judged harmful, the safe
  path a safe success) and the look-ahead and state-tracker validators (30/30 and 12/12), with the mock forecaster;
- `bootstrap.sh` from nothing, on a separate Docker stack (its ports moved so it could run beside the studies' own),
  then `verify_ra2.py` on four follow-up tasks (one Gitea, one Nextcloud, one mail, one control) and `verify_tasks.py`
  on three tasks of the first real-apps study, all verified;
- the forecast bridges, with the installed client and with `EKBASIS_CLIENT_SRC`, against a stand-in server that answers
  the client's API (no model);
- the terminal study's `prepare.py all`: it cloned the three repositories at their pinned commits, installed client
  0.1.2 from GitHub and built every task's start state, and all 12 study tasks start not done.

Agent runs were not repeated for the release: they need an agent and a running Ekbasis server.

## Checking the files

`python3 verify_benchmark.py` re-hashes every file and compares it with `MANIFEST.json`. A file copied unchanged has the
hash of the file that ran; if that hash was recorded at a freeze, the freeze file must contain it. A file whose edits are
all published in the manifest is turned back into the original and checked the same way. A file with a redacted edit
is listed with what was replaced.
