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
  `ALTER TYPE ... ADD VALUE`, `VACUUM`, or their own `BEGIN`/`COMMIT` are checked with autocommit rules, and the
  verdict says so.
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

The comment has one line per migration: its verdict and the reason, such as "may lose existing data (97%)" or "fails
even on an empty database: column "x" does not exist".

With `mode: check` or `both` and `fail-on: risky`, the job fails when a migration is risky or cannot be foreseen. That
fail-closed behavior is the same as the rest of the client, so the job can be a required status check. The result
also goes to the job summary and to the outputs `verdict` (`ok`, `risky`, `cannot-foresee`) and `result` (the JSON
path).

**What it never sends or prints:**
- **Data values:** none are read.
- **Secrets:** the API key and the replica URL travel only as environment variables. The replica's URL and password
  are removed from any error the guard prints.
- **What the comment shows:** file paths, probabilities, reasons and PostgreSQL error messages about the schema.

## How well it works

The guard's questions come from a pre-registered study on 582 real migrations from 12 open-source projects. The study
is in the cookbook under `studies/migrations`. Each migration was executed on a seeded database, and the labels come
from what happened.
- **Loss:** on the migrations that look destructive, AUROC 0.948 and F1 0.836. A copy-aware regex gets F1 0.785.
- **Failure:** AUROC 0.963 and F1 0.692; the regex gets 0.397.
- **Calibration of the loss probability:** failed its pre-registered bar (ECE 0.142 against 0.10).
- **Main weakness:** under autocommit rules, when a migration failed, the model still tended to predict that its
  destructive statement ran (27 of 61 false alarms on loss). That is why the guard writes the transactional rule by
  default.

The effect of that change, and of the product's state (statistics instead of rows), is measured in a second
pre-registered evaluation. See the cookbook and `CHANGELOG.md`.

**Limits:**
- **PostgreSQL only.**
- **SQL migrations only.** Migrations written in application code (Django, Alembic, Rails, TypeScript) are not read.
- **The scratch schema is built from the SQL files alone.** Objects created outside them (extensions provided by the
  platform, roles, data migrations in code) are missing, and the verdict notes when earlier migrations did not apply
  cleanly.
- **Statistics are estimates.** Without them, the model knows only that the tables hold data.
- **A low probability is not proof of safety.**
