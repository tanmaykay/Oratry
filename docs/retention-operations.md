# Recording retention operations

Raw recording objects are private and are deleted server-side only. Analysis
completion sets a configurable `RECORDING_RETENTION_HOURS` deadline (24 hours
by default); transcripts, metrics, evaluations, scores, feedback, and skill
evidence remain in PostgreSQL after the raw object is removed.

## Run the worker

Use the same environment and database configuration as the API. Process one
due object in an operational job or health check:

```powershell
.\.venv\Scripts\python.exe -m app.retention_worker --once
```

For a local continuously running worker:

```powershell
.\.venv\Scripts\python.exe -m app.retention_worker --poll-seconds 60
```

Production should run this command under a process supervisor or scheduled
worker identity. It requires only server-side R2 credentials with permission to
delete objects in the configured private bucket. Browser credentials and public
object URLs are never used.

## Lifecycle and failures

Eligible rows move through `scheduled` → `deleting` → `deleted` or
`delete_failed`. The worker leases a row before an external delete, increments
the persisted attempt count immediately before that call, and writes a bounded
exponential `deletion_available_at` backoff after a transient failure. Expired
leases are reclaimed; a stale worker cannot overwrite the newer lease's
outcome. It stores only a normalized error code, never a provider message, URL,
or object key. A provider-name mismatch fails closed.

Before enabling the worker outside local development, run a disposable R2
delete canary with the deployed credentials: upload a non-audio canary object,
delete it using the worker's storage identity, verify it cannot be read, then
remove its database test record. Do not claim production deletion verification
until that canary passes.

The worker depends on migration `20260920_07`, which adds the persisted retry
and lease fields plus the composite claim index. Analysis completion must set
both `retention_deadline` and `deletion_available_at` to the configured due
time when it schedules deletion.
