# Pilot deployment checklist

This is the target-environment portion of V1-016. The repository provides the
container template, health endpoints, structured process output, and worker
health command; a specific hosting and monitoring account is still required
before this checklist can be executed.

## Deploy

1. Select a managed PostgreSQL provider and create a least-privileged runtime
   role plus a separate migration role. Run `alembic upgrade head` once per
   release before starting application processes.
2. Put production-only values in `/etc/oratry/production.env` (or equivalent
   secret manager), set `APP_ENVIRONMENT=production`, and run the services in
   `deploy/compose.pilot.yaml` under a supervisor with restart-on-failure.
3. Route the web application and API through HTTPS. Set `WEB_APP_URL`,
   `NEXT_PUBLIC_API_ORIGIN`, `ACTIVATION_URL_BASE`, and
   `GOOGLE_OAUTH_REDIRECT_URI` to their final HTTPS URLs.
4. Check `GET /health/live`, `GET /health/ready`, and
   `python -m app.worker --health`. These endpoints must not expose provider
   credentials, transcript text, recordings, or signed URLs.

## Required evidence before inviting pilot users

- Configure alert routes for API/worker restart loops, database failures,
  failed analysis jobs, queued jobs older than ten minutes, and overdue or
  failed recording deletion.
- Perform and record a managed PostgreSQL point-in-time restore into an empty
  non-production database. Do not use a production restore as a test.
- Run an R2 retention canary with deployed credentials: create a disposable
  object, schedule/delete it through the retention worker identity, and verify
  it cannot be read afterwards.
- Run a consented short recording through the live pipeline and confirm it
  reaches completed, schedules retention, and emits no raw content to logs.
- Record the date, release SHA, operator, and pass/fail result in the deployment
  system—not in learner data or application logs.

## Google sign-in deployment

Create a Google Cloud OAuth **Web application** client. Register exactly:

```text
https://<api-host>/v1/auth/google/callback
```

Set `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`,
`GOOGLE_OAUTH_REDIRECT_URI`, `WEB_APP_URL`, and `NEXT_PUBLIC_API_ORIGIN`. The
browser starts the flow against the API origin so the API-only signed OAuth
state cookie returns to the callback correctly. The redirect to the web app
contains a short-lived, one-time handoff code rather than a session token.
