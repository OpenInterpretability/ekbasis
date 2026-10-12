# Migration guard

Before a pull request is merged: will its new PostgreSQL migrations **lose data** or **fail** on the existing database?
`ekbasis migrate-check` answers from facts, and a GitHub Action posts the answer on the pull request.

## Who decides (0.1.22)

By default (`--policy rule`, Action input `policy: rule`) **a rule written from the PostgreSQL documentation decides**
whether a migration fails the check, over exactly the facts described below. Ekbasis reads the same facts and gives a
**second opinion**: when the rule finds no risk and the model does, the migration is marked **review** in the comment
and in the JSON, without failing the check. `--policy model` restores the 0.1.21 behavior (the model decides).

Why: in pre-registered tests, a rule written from the documentation over the same facts matched or beat the model.
On data seeded the way real databases look (duplicates, sentinel values, orphan rows), on 307 Rails migrations it was
more accurate (false alarms 4.4% against 7.5%), and the rule-decides-model-reviews policy had the best accuracy
(0.967) with recall 98.6% counting reviews. The value of the guard is in the facts it builds; the model stays as a
second opinion. Studies: [migrations-rich-rule](https://github.com/OpenInterpretability/ekbasis-cookbook/tree/main/studies/migrations-rich-rule).

## What it reads

- **The schema.** The migrations the base branch already has are applied, in order, to a scratch PostgreSQL. The
  scratch server is `EKBASIS_PG_URL`; a database `ekbasis_mg_*` is created there and dropped afterwards. The guard
  writes the tables a new migration touches as DDL (found by parsing its statements, with no cap), each table linked
  to them by a foreign key in one line, the views that depend on them, their triggers and trigger functions, and the
  sequences, enums and domains they use; every other table is only counted. A migration the parser cannot follow
  (dynamic SQL, an unknown statement or name) gets the tables whose names appear in it and their foreign-key
  neighbors, at most 8, and a note says so. `EKBASIS_SCHEMA_CUT=off` always does that.
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
  `VACUUM`, `ALTER SYSTEM`, or their own `BEGIN`/`COMMIT` statements are checked with autocommit rules, and the
  verdict says so. A `BEGIN` inside a function body does not count.
  - goose files (`-- +goose Up` / `-- +goose Down`): only the Up sections are run, and `-- +goose NO TRANSACTION`
    switches that file to autocommit rules.
- **A fact decided in code.** Each new migration is first run on the schema alone, with no rows. If it fails there
  (a missing column, a typo, a wrong type), it fails in production too. That decides the verdict, with PostgreSQL's
  error, and in a transactional file the model is not asked.
- **Probes, in code, on copies of the scratch** (never on the replica). A migration that passes on the base schema can
  still fail on rows production has. The guard runs it on copies of the scratch and reports PostgreSQL's own error:
  - *key collision*: an `INSERT` without `ON CONFLICT` into a table that has a unique key is run twice; the second
    run's error is what happens when the key already exists;
  - *missing or present source rows*: the tables the migration reads are emptied on a copy (when earlier migrations
    inserted rows there) or get one made-up row (when they are empty); a NOT NULL error is what happens then;
  - *rows still referenced*: before a `DELETE` (or a key update) on a table a foreign key references with `NO ACTION`
    or `RESTRICT`, a made-up row of the referencing table is added on a copy; a foreign key error shows the mechanism.
    Without one, the foreign key itself is stated.

  Made-up rows have fixed values (`ekbasis_probe_*`) the guard chooses; nothing is read from production. They are
  hypothetical, so their results are facts for the model, worded as a condition ("if ..., action K fails with: ...").
  A failure is decided in code only from the replica's statistics: a `DELETE` of every row of a table whose
  referencing table holds non-NULL references, and `SET NOT NULL` on a column the replica shows NULLs in that nothing
  earlier in the file fills.
- **"Fails" when the rows cannot matter** (0.1.21). If the migration ran on the schema alone without error and every
  statement can fail only because of the schema, existing rows cannot make it fail either, and P(fails) is set to 0
  (the model's answer is kept as `p_fail_model`, and the file gets a note). That covers drops, renames, new tables
  and their indexes, plain (non-unique, column-list) indexes, nullable or defaulted new columns, dropping a default or
  NOT NULL, constraints on a table the same migration created, and a foreign key or unique constraint on columns it
  just added as nullable. It does not cover UPDATE/INSERT/DELETE, SET NOT NULL, type changes, constraints or unique,
  partial or expression indexes on existing rows, or generated columns. Before, the model
  sometimes said "may fail" for a drop that could only lose data.
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
When a pull request **edits** a migration that already exists on the base, the guard checks the new content on the
schema of the base's migrations that come before it, and the verdict says that databases that already applied it will
not run the change: the verdict is for a database that has not applied it yet (a new environment, CI, a self-hosted
install). Tools that checksum migrations (Prisma, golang-migrate's dirty flag) may also refuse to deploy.

**Setup SQL** (`--setup-sql PATH`, `setup-sql:` in the Action). Some platforms create schemas, roles or extensions
outside the migrations (Supabase's `auth` schema and `supabase_auth_admin` role, `pg_stat_statements`). Without them
the base's migrations do not apply and every check is "cannot foresee". The setup SQL runs with the scratch server's
admin connection in the throwaway database, before the base's migrations; `:guard_role` names the role the migrations
run as (for example `GRANT ALL ON SCHEMA auth TO :"guard_role";`).
- **Security.** With `--base` the file is read from the **base** ref (`git show <base>:PATH`), never from the pull
  request's head, because it runs with privileges: a pull request that changes it takes effect only once merged. With
  migration files and no `--base`, it is read from the working tree. **Do not use that mode with `--setup-sql` in CI
  for pull requests from forks**: the working tree is the pull request's, so it would control SQL run as the scratch
  admin. The Action always passes `--base`.
- Roles it creates stay on the scratch server (the Action's is a throwaway container); write it so it can run twice
  (`CREATE SCHEMA IF NOT EXISTS`, `DO $$ ... IF NOT EXISTS (SELECT FROM pg_roles ...) $$`).

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
- `reason`, `notes`, `tables`;
- `decided` (a failure decided in code from the replica's statistics) and `edited` (the pull request edits this
  migration).

Only `psql` is used to talk to PostgreSQL: set `EKBASIS_PSQL`, or put `psql` on `PATH`. The client stays standard
library only.

## Alembic and Rails (supported) and Django (experimental), opt-in

**Status.** Alembic and Rails are supported with `on-code: warn`: each met every pre-registered target. **Django is
experimental.**
It missed the pre-registered recall target (28 of 34 risky migrations caught, lower bound 0.665 against 0.85). The
migrations it let through failed on values out of range for a narrower column and on a foreign key violated by copied
rows. When `framework: django` is used, the comment and the CLI output say so: "Django support is experimental: in its
evaluation it missed 6 of 34 risky migrations." All three stay opt-in (`framework:`); the default is plain SQL.

These frameworks keep migrations as code (Python), so the SQL a migration will run has to come from the
framework itself, which means **running the pull request's code**. That is far more dangerous than running its SQL. The
guard runs it only inside a container that it builds for the job, and that it takes off the network before any of the
project's code runs.

1. **Network.** An internal Docker network is created, with no route out. A scratch PostgreSQL joins it.
2. **Generator container.** It starts from your image (`--image`), gets the base and head trees as plain files from
   `git archive` (no `.git`, no credentials), and runs your `--setup` with network: installing dependencies needs it,
   as in any CI job.
3. **The cut.** The generator is moved to the internal network. It is checked to have no route out (it cannot resolve
   a public name), and the guard refuses to go on otherwise. From then on it reaches the scratch PostgreSQL and nothing
   else. **No secret is ever in its environment**: no API key, no token, only the scratch database's URL. Migrations
   run as a throwaway role that is not a superuser.
4. **Base schema.** At the base tree, the framework migrates the scratch database (`manage.py migrate`,
   `alembic upgrade head`; `--migrate` overrides it). Then `pg_dump --schema-only` gives the
   base schema.
5. **Rendering**, at the head tree:
   - **Django:** `sqlmigrate` for each new migration. `atomic = False` migrations are checked with autocommit rules.
   - **Alembic:** offline mode, `upgrade --sql <previous>:<new>` (`--command "flask db"` for Flask-Migrate). The
     `alembic_version` bookkeeping is dropped.
   - **Rails:** Rails has no offline mode. Each new migration runs on the base schema, which has no rows, and the SQL
     it sends is kept; reads and Rails' bookkeeping (`schema_migrations`, `ar_internal_metadata`) are dropped.
     Ruby beyond the schema DSL (models, `find_each`, `update_all` on classes, loops) does nothing without rows, so it
     is listed as code not foreseen.
6. **What is not SQL is not guessed.** A Django `RunPython`, or an Alembic migration that reads the database
   (`op.get_bind()`) and so has no offline SQL, is listed as **code not foreseen**: "contains code the guard cannot
   foresee: review it by hand". It is never shown as "ok".
   - **`on-code: warn` (default):** it does not fail the check. The Action's `verdict` output is `code-not-foreseen`.
   - **`on-code: block`:** it is "cannot foresee" and fails the check, as before.

   Its SQL is not sent to the model, but it is applied to the scratch schema, so the next migration sees it. A file
   the framework could not render for another reason (not loaded, a crash) is always "cannot foresee".
7. **Cleanup.** The containers and the network are removed. The result is a bundle (JSON): the base schema and, per
   migration, its SQL.

The second half needs the API key and never runs the pull request's code: `migrate-check --bundle` checks the bundle
the way it checks SQL files.

```bash
ekbasis migrate-gen --framework django --base origin/main \
  --setup "pip install -r requirements.txt" --env DB=postgres -o bundle.json     # no API key needed here
ekbasis migrate-check --bundle bundle.json                                        # EKBASIS_API_KEY, EKBASIS_PG_URL
```

The generator gets `DATABASE_URL`, `DB_HOST`/`DB_PORT`/`DB_NAME`/`DB_USER`/`DB_PASSWORD`, the `PG*` variables and
`POSTGRES_*` for the scratch database. Add what your settings read with `--env` (`${EKBASIS_DB_URL}` is replaced by
the URL). **Never put a secret in `--env` or `--setup`: the pull request's code can read them.**

**Redis.** Some projects need a Redis just to boot (Sidekiq, Action Cable, a cache store). With `--redis auto` (the
default; Action input `redis: auto|on|off`) the guard starts one when the project uses it: a `redis`, `sidekiq` or
similar gem in the `Gemfile`, or `redis`/`celery`/`rq` in `requirements.txt` or `pyproject.toml` (at the root or in
the working directory). `on` always starts it, `off` never does. It is isolated like the scratch PostgreSQL: a
throwaway `redis:7-alpine` with no password and nothing in it, on the same internal network with no route out, no
port published on the host, and removed with the rest at the end. The generator gets `REDIS_URL`, `REDIS_HOST` and
`REDIS_PORT`, and the bundle records whether it was started (`services.redis`).

In the Action:

```yaml
      - uses: OpenInterpretability/ekbasis/actions/migration-guard@v0.1.13
        with:
          api-key: ${{ secrets.EKBASIS_API_KEY }}
          framework: django                 # or alembic
          # on-code: warn                   # warn (default) or block
          image: python:3.12-slim
          setup: |
            apt-get update -qq && apt-get install -y -qq libpq5
            pip install -r requirements.txt
          env: |
            DJANGO_SETTINGS_MODULE=myproject.settings
```

**How well it works.** This was first measured, with `on-code: block`, in a pre-registered evaluation of 390 real migrations from healthchecks,
NetBox, Wagtail (Django), Airflow 2.10 and Prefect 3.4 (Alembic). Each migration was run by its own framework,
RunPython included, on a seeded database; labels come from what happened.

| | Django (235) | Alembic (155) |
|---|---|---|
| Verdict accuracy (rules on the rendered SQL) | 0.762 (0.762) | **0.884** (0.768) |
| Recall on risky migrations | 0.942 | 0.960 |
| Reason right, on risky migrations flagged | 0.490 | 0.583 |
| False alarms on benign migrations | 0.290 | 0.131 |
| Code not foreseen (counted as risky under `block`) | 30.6% | 12.9% |

Neither framework met every pre-registered target. Alembic passed accuracy and recall; Django passed recall only.
- **Almost all of the gap is the "cannot foresee" policy.** RunPython and migrations that do not render count as risky
  with no reason, and most of them were benign.
- **On the migrations it answers** (298 of 390), the guard is right 95.0% of the time, its reason is right 95.0% of
  the time, and it raises false alarms on 4.3% of benign migrations.
- **That is why the default became `on-code: warn`.** With `block`, 29% false alarms on Django make the check unusable.
  The warning stays visible, so nothing is hidden; it just does not fail the check.

**With `on-code: warn`, on new projects.** A second pre-registered evaluation (571 migrations from saleor, babybuddy,
paperless-ngx, MLflow 3.1 and Superset 4.1) measured the default.

| On the migrations the guard answers | Django (242) | Alembic (141) |
|---|---|---|
| Verdict accuracy (rules) | **0.955** (0.826) | **0.986** (0.773) |
| Recall on risky migrations | 0.824 (28/34) | 1.000 (13/13) |
| Reason right, on risky migrations flagged | 1.000 | 1.000 |
| False alarms on benign migrations (rules) | 0.024 (0.202) | 0.016 (0.250) |
| Code not foreseen: listed for review by hand | 23.7% of all migrations | 44.5% |
| Recall over all risky migrations, review-by-hand counted as missed | 0.483 | 0.310 |

- **Alembic met every pre-registered target, and is supported. Django missed one, so it is experimental:** recall
  0.824 against 0.85. The 6 misses are
  failures and one loss. Most of the failures come from values the synthetic test data put in (a number out of range
  for a narrower column, a foreign key the copied rows violate).
- **Much of the risk is in data-migration code.** About half the risky Django migrations and two thirds of the Alembic
  ones contain code the guard does not foresee. The comment lists them for a person; it does not check them.
- **Both adapters stay opt-in** (`framework:`).

**Rails.** Two pre-registered evaluations, each migration run by Rails itself (`ctx.run(:up)`, callbacks and Ruby
included) on a seeded database.

| On the migrations the guard answers | v6: Mastodon, Maybe (140) | v7: Redmine, OpenProject, Consul Democracy (307) |
|---|---|---|
| Verdict accuracy (rules) | 0.886 (0.607) | **0.896** (0.730) |
| Recall on risky migrations | 0.976 (40/41) | 1.000 (119/119) |
| Reason right, on risky migrations flagged | 0.825 (33/40) | **0.992** (118/119) |
| False alarms on benign migrations (rules) | 0.152 (0.525) | 0.170 (0.441) |
| Code not foreseen: listed for review by hand | 16.7% of all migrations | 10.5% |
| Recall over all risky migrations, review-by-hand counted as missed | 0.800 | 0.902 |

- **v6 missed the reason target** (0.825 against 0.85). In 5 cases it said "may fail" for migrations that only lost
  data: drops and renames that had already run on the base schema, where no row can make them fail. Since 0.1.21 that
  is decided in code ("fails" when the rows cannot matter, under "What it reads"), and the generator has a Redis (the
  other 2 misses).
- **v7 met every target**, on new projects, with the code of 0.1.20 (schema cut, code probes) plus this rule; the
  probes decided 2 of the 4 failures. Accuracy 0.896 [0.860, 0.928], +0.166 over the rules; false alarms 0.170
  [0.123, 0.230], close to the 0.20 target. Its caveats: Consul Democracy holds 108 of the 119 risky migrations, most
  of them column drops, and only 4 risky migrations failed rather than lost data, so the "fails" side is barely
  tested. Most false alarms (28 of 32) are OpenProject data migrations; 10 of them rewrite duplicate names before
  adding a unique index, and the synthetic rows had no duplicates, so nothing was overwritten.



**Residual risk:**
- **The setup step runs with network.** It installs the pull request's dependencies, as your test job already does.
  Keep it to dependency installation.
- **Container escape.** A bug in the container runtime or the kernel could let code escape the container. The
  runner's lifetime of one job limits what it could reach.
- **Forks:** as with SQL, forks get no secrets (see Security below). The render step itself needs none.

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
          # setup-sql: db/guard-setup.sql   # optional: read from the base branch, run as the scratch admin
          # mode: both          # comment | check | both
          # fail-on: risky      # risky | never
```

**Verdict cache.** A migration already checked is not sent to the model again. The answer is reused, with no model
call and no tokens billed, when all of these are the same: the migration file's text (byte for byte), the whole
scratch schema built from the base branch, the client version, the transaction mode, whether replica statistics were
used, the exact text the model would read (so new statistics values are a miss too), and the server URL. The key is
sha256 over all of them. Only the probabilities are stored, never the SQL or the schema, and the verdict is decided
again with the current thresholds. Entries expire after 30 days.
- The Action keeps it in the GitHub Actions cache (`verdict-cache: true`, the default): each push to a pull request
  reuses the answers of the previous push, and a pull request can read the caches of its base branch. GitHub scopes a
  pull request's caches to that pull request, so one pull request cannot write answers another one reads.
- On your machine, `migrate-check` keeps it in `~/.cache/ekbasis/verdicts` (or `$EKBASIS_CACHE_DIR/verdicts`).
  `EKBASIS_VERDICT_CACHE=<folder>` moves it, `EKBASIS_VERDICT_CACHE=off` or `--no-cache` turns it off.
- A reused answer is marked: the file gets the note "its answer was reused (no model call)" in the comment and
  `"cached": true` in `--json`.

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

**Probes, edited migrations and setup SQL (pre-registered evaluation, 2026-10-11).**
- **No regression on the 184 held-out migrations.** False alarms on the 128 benign ones stay at 20/128 with a replica
  and 19/128 without one. Recall on the 56 risky ones stays at 54/56. On these migrations the probes changed the state
  of 5 files (2 failures decided in code from the replica's NULL fractions, both correct) and no verdict.
- **The gain on new real incidents was NOT demonstrated.** The test set had 4 incidents from 11 repositories never used
  before, and none of them had the shape the probes cover. The check was underpowered and showed no change.
- **What the mechanism looks like, as an illustration and not as evidence:** on two incidents from the development set,
  the probe's fact turned a miss into a hit.
  - A `DELETE` of rows still referenced by a foreign key went from P(fails) 0.13 to 0.92.
  - An `INSERT ... SELECT` that omits a NOT NULL column went from P(fails) 0.25 to 0.97.
- **Edited migrations and the setup SQL** are covered by unit and end-to-end tests. One of them runs against
  supabase/auth's real migrations, which need the `auth` schema and the `supabase_auth_admin` role: without the setup
  SQL every check is "cannot foresee"; with it the base applies cleanly.


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

The 0.1.21 rule ("fails" when the rows cannot matter) was checked for non-inferiority on the same 184 migrations,
with answers obtained again and the 0.1.20 code and the new code applied to the same answers (their states checked
byte for byte identical): accuracy 0.897 → 0.902, false alarms 17 → 16, recall 54 → 54 of 56, reason right 48 → 48
of 54. One verdict changed, a plain index built concurrently
on an existing table, from "fails" to "ok", which was right.

Every target was met. Not every subset is good:
- **Destructive-looking migrations** (stratum A, 84): accuracy is **0.786**, against 0.679 for the rules. That is
  where the decisions are hard.
- **Benign-looking migrations** (37): the rules never fire, and the guard raised 2 false alarms.
- **The study's other bars are still missed.** The loss probability alone is not calibrated (ECE 0.18), and the model
  does not compose "fails" with "nothing is applied" by itself. The code does that.

The labels come from synthetic rows (NULLs at 25%, random foreign-key pairs). Real data may fail or lose differently.
Data, plans and scripts are in the cookbook (`studies/migrations`, sections 7 and 8).

**Limits:**
- **PostgreSQL only.**
- **Django and Alembic are rendered, not read.** The result depends on your `--setup` reproducing the project's
  environment. Other code-based migrations (TypeScript ORMs, Go code) are not covered.
- **Rails runs each migration on an empty schema to render it.** Ruby that loops over rows sends no SQL there; it is
  listed as code not foreseen only when the pattern is recognised. In the v7 evaluation, 10.5% of the migrations were
  listed for review by hand.
- **The scratch schema is built from the SQL files alone.** Objects created outside them (extensions provided by the
  platform, roles, data migrations in code) are missing, and the verdict notes when earlier migrations did not apply
  cleanly.
- **Statistics are estimates.** Without them, the model knows only that the tables hold data.
- **A low probability is not proof of safety.**
