# Migration guard

Before a pull request is merged: will its new PostgreSQL migrations **lose data** or **fail** on the existing database?
`ekbasis migrate-check` answers from facts, and a GitHub Action posts the answer on the pull request.

## What it reads

- **The schema.** The migrations the base branch already has are applied, in order, to a scratch PostgreSQL. The
  scratch server is `EKBASIS_PG_URL`; a database `ekbasis_mg_*` is created there and dropped afterwards. The guard
  writes the catalog of the tables a new migration names, and of the tables linked to them by foreign keys, as DDL.
- **Statistics, optional.** These come from a read-only replica (`EKBASIS_DB_STATS_URL`), from the planner's
  statistics only:
  - estimated rows per table (`pg_class.reltuples`);
  - the fraction of NULLs per column (`pg_stats.null_frac`);
  - the number of distinct values per column (`pg_stats.n_distinct`).

  No value is ever read, and `most_common_vals` is never queried. Without a replica, the state says that the tables
  hold production data and that the row count is unknown.
- **How the file runs.** Prisma Migrate, Diesel and golang-migrate run a migration file as one transaction on
  PostgreSQL. If any statement fails, nothing in the file is applied.
  - Diesel wraps each migration in a transaction unless `run_in_transaction = false`.
  - Prisma and golang-migrate send the file as one multi-statement batch, which PostgreSQL runs as one implicit
    transaction.

  The guard writes this rule into the state. `--autocommit` (`autocommit: true` in the Action) switches to `psql -f`
  semantics, where each statement commits on its own and the next one runs after a failure. Files with `CONCURRENTLY`,
  `VACUUM`, `ALTER SYSTEM`, or their own `BEGIN`/`COMMIT` are checked with autocommit rules, and the verdict says so.
- **A fact decided in code.** Each new migration is first run on the schema alone, with no rows. If it fails there
  (a missing column, a typo, a wrong type), it fails in production too. That decides the verdict, with PostgreSQL's
  error, and in a transactional file the model is not asked.
- **The questions** are the ones of the pre-registered study the guard comes from:
  - data lost (a value stored before is in no table afterwards);
  - a statement fails;
  - left half applied, asked only under autocommit.

  SQL comments are removed from what the model reads. Prisma writes "All the data in the column will be lost" there,
  and the study measured the model without it.

Which files are migrations? By default:
- `*migrations/*/migration.sql` (Prisma);
- `*migrations/*/up.sql` (Diesel);
- `*.up.sql` (golang-migrate and others);
- `*migrations/*.sql` and `*migrate/*.sql`.

`down.sql` files and files for other databases (`.mysql.`, `.sqlite.`) are skipped. Use `--glob` to set your own.
When a pull request edits a migration that already exists on the base, the guard adds a note: a database that already
applied it will not run the change.

## Command line

```bash
export EKBASIS_URL=https://openinterp.org/api/v1 EKBASIS_API_KEY=ekb_...
export EKBASIS_PG_URL=postgresql://postgres@127.0.0.1:5432/postgres     # a scratch server, not production
ekbasis migrate-check --base origin/main                  # the migrations this branch adds
ekbasis migrate-check db/migrations/0042_drop_x.up.sql     # these files; the schema comes from the files before them
ekbasis migrate-check --base origin/main --json --show-state
```

The exit codes are those of the other checks:
- 0: no risk found.
- 2: risky. P(data lost) ≥ `--lost-threshold`, or P(fails) ≥ `--fail-threshold` (both 0.5 by default), or the
  migration fails on the schema alone.
- 3: cannot foresee. The schema could not be built, the server did not answer, or the state is too long. Treat it as
  risky. `--fail-open` turns it into 0, with a warning.

`--json` prints `files[]`, each with:
- `path`, `tool`, `transaction`;
- `p_lost`, `p_fail`, `p_half`;
- `schema_error`, `risky`, `cannot_foresee` (also as `cannot_judge`);
- `reason`, `notes`, `tables`.

Only `psql` is used to talk to PostgreSQL: set `EKBASIS_PSQL`, or put `psql` on `PATH`. The client stays standard
library only.

## GitHub Action

```yaml
# .github/workflows/migration-guard.yml
name: migration guard
on:
  pull_request:
    paths: ["**/migrations/**", "**/*.sql"]
permissions:
  contents: read
  pull-requests: write          # the comment
jobs:
  guard:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0        # the base branch's migrations build the schema
      - uses: OpenInterpretability/ekbasis/actions/migration-guard@main
        with:
          api-key: ${{ secrets.EKBASIS_API_KEY }}
          # db-stats-url: ${{ secrets.READ_REPLICA_URL }}   # optional: planner statistics only
          # mode: both          # comment | check | both
          # fail-on: risky      # risky | never
```

The Action:
1. installs the client at the Action's own version;
2. starts `postgres:16` on the runner;
3. fetches the base branch;
4. runs `migrate-check`;
5. writes a single pull request comment and updates it on each push. If the pull request has no migration and no
   comment yet, it writes nothing.

The comment has one line per migration: its verdict and the reason. The reason is decided in code from the two answers:
- "may fail on existing data (80%); nothing in the file would be applied", plus "; if it ran, it would also lose data
  (90%)" when loss is also likely;
- "may lose existing data (97%)" when no failure is foreseen;
- "fails on the base branch's schema before touching any data: column "x" does not exist (an error in the pull request
  itself, e.g. it depends on a migration missing from the base, or a typo)".

With `mode: check` or `both` and `fail-on: risky`, the job fails when a migration is risky or cannot be foreseen. That
fail-closed behavior is the same as the rest of the client, so the job can be a required status check. The result
also goes to the job summary and to the outputs `verdict` (`ok`, `risky`, `cannot-foresee`) and `result` (the JSON
path).

**Security.**
- **Trigger on `pull_request`, never on `pull_request_target`** with a checkout of the pull request's code. Under
  `pull_request_target`, untrusted code runs with the base repository's secrets and a write token.
- **Pull requests from forks get no secrets.** The API key is empty there, so the guard ends in "cannot foresee" and,
  with `fail-on: risky`, fails the check. The fork's read-only token cannot comment either; that step only warns, and
  the result is in the job summary. Choose one:
  - set `fail-on: never` for forks:
    `fail-on: ${{ github.event.pull_request.head.repo.full_name == github.repository && 'risky' || 'never' }}`;
  - or run the job only for branches of the repository itself:
    `if: github.event.pull_request.head.repo.full_name == github.repository`.
- **Minimal permissions.** The workflow needs `contents: read` and `pull-requests: write`, nothing else.
- **The pull request's SQL is untrusted, and it runs.** The guard runs it as a throwaway role made for each check: not
  a superuser, no CREATEDB, CREATEROLE, REPLICATION or BYPASSRLS, owner of its throwaway database only. The Action
  runs that PostgreSQL in a container on an internal Docker network, with no route out and no published port, reached
  with `docker exec`.
  - `COPY ... TO/FROM PROGRAM`, `pg_read_file`, `lo_import`, untrusted languages (`plpython3u`, `plperlu`),
    `CREATE ROLE` and other statements that need privileges fail with "permission denied".
  - The guard then reports **cannot foresee**, with the reason. It never runs a migration with more privileges.
  - Trusted extensions (`pgcrypto`, `uuid-ossp`, `citext`, `pg_trgm`, `hstore`...) can be created by the database
    owner, so they still work.

  Residual risk: a bug in PostgreSQL itself that lets an ordinary role escape. The container's lack of network and
  the runner's lifetime of one job limit what that could reach.
- **On your own machine**, point `EKBASIS_PG_URL` at a scratch server, never at a database that matters. The guard
  needs a role there that can create databases and roles, which it drops afterwards.

**What it never sends or prints:**
- **Data values:** none are read.
- **Secrets:** the API key and the replica URL travel only as environment variables. The replica's URL and password
  are removed from any error the guard prints.
- **What the comment shows:** file paths, probabilities, reasons and PostgreSQL error messages about the schema. Paths
  and errors come from the pull request, so they are untrusted: they are cut to a few hundred characters, HTML and
  markdown are escaped, and @mentions and links are broken with a zero-width space.

## How well it works

The guard's questions come from a pre-registered study on 582 real migrations from 12 open-source projects. The study
is in the cookbook under `studies/migrations`. Each migration was executed on a seeded database, and the labels come
from what happened.
- **Loss:** on the migrations that look destructive, AUROC 0.948 and F1 0.836. A copy-aware regex gets F1 0.785.
- **Failure:** AUROC 0.963 and F1 0.692; the regex gets 0.397.
- **Calibration of the loss probability:** failed its pre-registered bar (ECE 0.142 against 0.10).
- **Main weakness:** when a migration fails, the model still tends to predict that its destructive statement ran.
  Under the study's autocommit rules, 27 of its 61 false alarms on loss came from that.

A second pre-registered evaluation (same 582 migrations, re-executed) measured this guard's own state: the
transactional rule, and planner statistics in place of sample rows.
- **Loss** (stratum A): AUROC 0.921 against 0.931 for the study's state. That is non-inferior (difference −0.010
  [−0.021, +0.002]). F1 is 0.803 against 0.768 for the copy-aware regex.
- **Failure:** AUROC 0.945. F1 is 0.637 against 0.397 for the rule, and recall is lower without sample rows.
- **The weakness is not fixed.** The transactional rule did **not** remove the false alarms. Of 45 destructive-looking
  migrations that fail and therefore lose nothing, 35 are still flagged for loss (36 with the study's state). The
  model reads the rule but does not compose "fails" with "nothing is applied". A risky verdict on such a file is still
  right to block the merge (it fails), but the reason it gives (loss) is wrong.
- **Calibration of the loss probability:** ECE 0.180, not within 0.10.

So the verdict and its reason are decided in code. A file is risky if P(fails) ≥ 0.5, or P(lost) ≥ 0.5, or it fails
on the base's schema. The reason says "fails" first. A third pre-registered evaluation ran this exact code
(`b18bb43`) on **184 migrations the study never drew**, with the scratch schema built as the non-superuser role:
- **Verdict accuracy** (risky vs ok, against "fails or loses data"): **0.875** [0.826, 0.924]. Regex rules (R3 or
  the failure rule) reach 0.696.
- **Recall on risky migrations:** 0.946 (53 of 56).
- **Reason** ("fails" vs "loses"), on risky migrations it flags: right on **92.5%** (49 of 53).
- **False alarms on benign migrations:** **15.6%** (20 of 128). The rules raise 43.0%.

Every target was met. Data, plans and scripts are in the cookbook (`studies/migrations`, sections 7 and 8).

**Limits:**
- **PostgreSQL only.**
- **SQL migrations only.** Migrations written in application code (Django, Alembic, Rails, TypeScript) are not read.
- **The scratch schema is built from the SQL files alone.** Objects created outside them (extensions provided by the
  platform, roles, data migrations in code) are missing, and the verdict notes when earlier migrations did not apply
  cleanly.
- **Statistics are estimates.** Without them, the model knows only that the tables hold data.
- **A low probability is not proof of safety.**
