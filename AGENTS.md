# AGENTS.md

Guidance for AI agents that use Ekbasis or work on this client.

## Using Ekbasis from an agent

- Reference written for agents (formats, when to consult, decision rules, errors, feedback):
  https://openinterp.org/ekbasis/agents.md
- Installable skill and measured use cases: https://github.com/OpenInterpretability/ekbasis-cookbook
- `ekbasis git-check` / `shell-check` exit codes: 0 no risk found · 2 RISKY · 3 CANNOT FORESEE (treat like 2) · 1 usage
  error. With the hosted API set `EKBASIS_URL=https://openinterp.org/api/v1` and `EKBASIS_API_KEY=ekb_…`.

## Working on this repository

- The client is standard library only (`dependencies = []`, Python ≥ 3.9). Do not add runtime dependencies.
- Tests: `python3 -m pytest -q tests` (all must pass; the suite uses a fake server, no network or GPU).
- Stable interface — do not change without a major version: exit codes (0/1/2/3), the JSON fields printed by `--json`
  (including `cannot_judge`, kept next to `cannot_foresee`), `CannotJudge` (alias `CannotForesee`), and the hook's
  "ask" behavior when it cannot foresee (fail closed).
- User-facing wording: Ekbasis foresees, it does not judge. Write "cannot foresee" in anything a person reads.
- `paper/`, `results*/`, `PREREG_*.md` and `RELEASE_EVAL.md` are frozen records of pre-registered studies: never edit
  them to change a result; add new runs next to them instead. Past `CHANGELOG.md` entries stay as written.
- The client sends `User-Agent: ekbasis/<version>` (`ekbasis/_version.py`); bump the version in both `pyproject.toml`
  and `_version.py`.
