# Production operations runbook

This runbook covers the modular-monolith V1 deployment. It does not replace a
managed provider's incident, backup, or security documentation.

## Required processes

Run the API, analysis worker, and retention worker as independently supervised
processes with the same release version and required configuration:

```text
FastAPI API:          uvicorn app.main:app
Analysis worker:      python -m app.worker --worker-id <stable-process-label>
Retention worker:     python -m app.retention_worker --poll-seconds 60
```

Use at least two analysis-worker replicas only after the PostgreSQL claim test
has passed for the deployed release. Every `run_once` claim has a unique lease
token; PostgreSQL `SKIP LOCKED` and conditional lease renewal prevent a stale
worker from completing another worker's job.

The repository CI job runs the same migration chain and a concurrent,
independent-session claim race against PostgreSQL. Before deploying a release,
run the database suite against a freshly created disposable database:

```powershell
$env:ORATRY_POSTGRES_TEST = "1"
$env:ORATRY_POSTGRES_TEST_DATABASE_URL = $env:TEST_DATABASE_URL
.\.venv\Scripts\python.exe -m pytest -q tests/test_database_schema.py
```

The retention worker may be a single supervised replica for V1. Its database
lease makes retries restart-safe, but duplicate replicas are not a substitute
for alerting on overdue deletion.

## Deployment checklist

1. Back up PostgreSQL and confirm a point-in-time restore procedure for the
   selected managed provider.
2. Run `alembic upgrade head` with a least-privileged migration identity.
3. Run `python -m app.worker --health` with the deployment configuration.
4. Start API and workers under a supervisor with restart-on-failure and
   structured stdout collection.
5. Perform a disposable R2 upload/delete canary using the retention worker's
   storage identity. Confirm the object cannot be read after deletion.
6. Upload a short consented recording and confirm the job reaches `completed`,
   the retention deadline is set, and private playback expires as expected.
7. Verify that an activation email is delivered through the configured provider.

## Minimum alerts

Alert on these conditions; alert payloads must not include transcript text,
signed URLs, raw provider responses, or recording object keys.

- `analysis_jobs` queued longer than 10 minutes.
- Any `analysis_jobs` row in `failed` state.
- A leased analysis job whose lease expired more than five minutes ago.
- A recording in `delete_failed`, or a scheduled recording overdue by more than
  15 minutes after its retention deadline.
- API, analysis-worker, or retention-worker process restart loops.
- PostgreSQL connection failure, migration failure, or backup failure.

Example read-only queries for an operator:

```sql
SELECT count(*) FROM analysis_jobs
WHERE status = 'queued' AND available_at < now() - interval '10 minutes';

SELECT count(*) FROM recordings
WHERE deletion_status IN ('delete_failed')
   OR (deletion_status = 'scheduled' AND retention_deadline < now() - interval '15 minutes');
```

## Recovery boundaries

- Requeue failed analysis jobs only through the authorized internal operation;
  do not create a public requeue API.
- A retrying evaluator reuses the persisted transcript and deterministic
  evidence. It must not submit the recording to STT again.
- Do not restore a deleted raw recording from backups merely to improve a
  learner review. Retained transcript/evidence is the source of truth after
  the raw-audio deadline.
- Test PostgreSQL restoration on a non-production environment before a pilot.
  A backup existing is not evidence that recovery works.

## What remains before a pilot

This repository includes PostgreSQL schema and claim/lease integration tests.
It does not provision an alerting vendor, managed-database backups, a process
supervisor, or production email domain. Those are deployment responsibilities
that must be exercised in the target environment before inviting pilot users.
