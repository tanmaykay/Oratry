# PostgreSQL development and migration verification

The active runtime schema is owned exclusively by Alembic. The SQL files in
`db/migrations/` are design-reference artifacts and must never be applied to
the same database as Alembic.

## Current verification status

The live suite has passed against a local PostgreSQL 17 disposable database.
It verified the full active Alembic chain from an empty database to head and
back to base, then removed the test-owned Alembic version table so the database
was empty again. CI runs the same suite against PostgreSQL 17. The offline
PostgreSQL Alembic SQL rendering and SQLite clean upgrade/downgrade checks also
pass.

## Start a local service

From the repository root, start PostgreSQL 17:

```powershell
docker compose up -d postgres
docker compose ps
```

The Compose service uses database `oratry`, user `oratry`, and a development-
only password. It persists data in the `oratry-postgres-data` Docker volume.
Set the current PowerShell session to use it:

```powershell
$env:DATABASE_URL = "postgresql+psycopg://oratry:oratry-local-only@localhost:5433/oratry"
alembic upgrade head
python -m app.seed
```

Use `alembic current` and `alembic history` to inspect the migration state.
Do not put the local password in production configuration.

## Run the destructive PostgreSQL migration suite

The integration suite requires an **empty disposable database** and verifies:

- upgrade from empty database to Alembic head;
- downgrade back to base;
- tables, indexes, unique constraints, and foreign keys;
- PostgreSQL JSON and `timestamp with time zone` round trips; and
- recording retention/deletion columns and one-recording-per-attempt integrity.

Create a dedicated non-superuser role and disposable database, then run the
suite. Substitute a locally chosen test password; do not add it to `.env` or
source control.

```powershell
docker compose exec postgres psql -U oratry -d oratry -c "CREATE ROLE oratry_test LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION PASSWORD '<test-password>';"
docker compose exec postgres createdb -U oratry -O oratry_test oratry_test
docker compose exec postgres psql -U oratry -d oratry_test -c "GRANT USAGE, CREATE ON SCHEMA public TO oratry_test;"
$env:ORATRY_POSTGRES_TEST = "1"
$env:ORATRY_POSTGRES_TEST_DATABASE_URL = "postgresql+psycopg://oratry_test:<test-password>@localhost:5433/oratry_test"
.\.venv\Scripts\python.exe -m pytest -q tests/test_database_schema.py
```

The test fails before making changes if the public schema already contains
tables. It performs its own downgrade cleanup after a successful run. To start
over after an interrupted test, explicitly drop and recreate only the named
disposable database:

```powershell
docker compose exec postgres dropdb -U oratry --if-exists oratry_test
docker compose exec postgres createdb -U oratry -O oratry_test oratry_test
```

Stop the local service with `docker compose down`. Add `-v` only when you
intentionally want to discard all local PostgreSQL data.

## Managed PostgreSQL

Supabase and other managed PostgreSQL services use the same standard
`postgresql+psycopg://` URL. Run Alembic through the deployment process with a
least-privileged migration role; this repository has no Supabase-specific SQL
or runtime dependency.
