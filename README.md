# Oratry

Oratry is a web-first personal practice system for clearer thinking and speaking.
Its V1 learning loop is:

`Think → Speak → Analyze → Correct → Retry → Progress`

The application is a modular monolith: a Next.js client, FastAPI API and worker
processes, PostgreSQL, private Cloudflare R2 storage, Deepgram prerecorded
transcription, deterministic scoring, and a provider-configured LLM evaluator.

## What works today

- Account signup, email activation, sign-in, profile, onboarding, and baseline assignment.
- Browser recording and direct signed upload to a private R2 bucket.
- Durable PostgreSQL-backed analysis jobs, Deepgram word timestamps, deterministic
  transcript metrics, Gemini structured evaluation, scoring, coaching, and skill evidence.
- Short-lived owner-authorized recording playback during the configurable raw-audio
  retention window; transcript and learning evidence remain after deletion.
- Challenge-specific review, same-challenge retry, evidence-only comparison,
  vocabulary lookup/cache, and progress history.

See [project/CURRENT_STATE.md](project/CURRENT_STATE.md) for the audited runtime
state and [project/BACKLOG.md](project/BACKLOG.md) for planned work.

## Architecture

```text
Next.js web client → FastAPI API → PostgreSQL
       │                    │
       │                    ├→ private R2 signed upload/download
       │                    └→ analysis_jobs → analysis worker
       │                                      ├→ Deepgram STT
       │                                      ├→ deterministic metrics/scoring
       │                                      └→ Gemini evaluation/coaching
       └→ browser recording

retention worker → private R2 deletion → PostgreSQL deletion audit
```

Provider SDKs are isolated behind storage, speech-to-text, and LLM interfaces.
LLMs do not calculate duration, WPM, filler counts, repetitions, or vocabulary
coverage. The application does not make psychological claims from audio.

## Prerequisites

- Python 3.12
- Current Node.js LTS
- PostgreSQL 17 or compatible managed PostgreSQL
- Docker Desktop only if using the included local PostgreSQL Compose service

Copy `.env.example` to an untracked `.env`. At minimum configure a PostgreSQL
`DATABASE_URL`. To run the live audio path, configure R2, Deepgram, and Gemini.
Never commit `.env` or provider credentials.

## Local setup

```powershell
npm install --include=dev
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
alembic upgrade head
python -m app.seed
```

For a Docker-backed local database:

```powershell
docker compose up -d postgres
$env:DATABASE_URL = "postgresql+psycopg://oratry:oratry-local-only@localhost:5433/oratry"
alembic upgrade head
python -m app.seed
```

Detailed PostgreSQL setup and destructive migration-test instructions are in
[docs/postgresql-development.md](docs/postgresql-development.md).

## Run the application

Start each process in a separate PowerShell terminal from the repository root:

```powershell
npm run dev
```

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

```powershell
.\.venv\Scripts\python.exe -m app.worker --worker-id analysis-local-1
```

```powershell
.\.venv\Scripts\python.exe -m app.retention_worker --poll-seconds 60
```

Open `http://127.0.0.1:3000`.

For local activation links, use `EMAIL_PROVIDER=development_outbox` and retrieve
the current link from `http://127.0.0.1:8000/v1/auth/development-outbox`.
Production email delivery requires Resend plus a verified sender domain.

## Challenge catalog and vocabulary targets

The active catalog is curated in `app/personalization/catalog.py`. Every active
challenge carries versioned, challenge-owned vocabulary targets. The worker sends
them to deterministic transcript matching and to the evaluator as challenge
context; a target match is never fabricated when no target exists.

## Verification

```powershell
npm run lint
npm run typecheck
npm run build
.\.venv\Scripts\python.exe -m pytest -q
```

Run `npm run build` only after stopping `npm run dev`: both commands write the
same generated `.next` directory.

Run the PostgreSQL integration suite only against an empty disposable database:

```powershell
$env:ORATRY_POSTGRES_TEST = "1"
$env:ORATRY_POSTGRES_TEST_DATABASE_URL = $env:TEST_DATABASE_URL
.\.venv\Scripts\python.exe -m pytest -q tests/test_database_schema.py
```

## Operations and project documentation

- [Analysis worker operations](docs/analysis-worker-operations.md)
- [Retention worker operations](docs/retention-operations.md)
- [Production operations runbook](docs/production-operations.md)
- [Architecture](docs/architecture.md)
- [API contracts](docs/api-contracts.md)
- [Architecture decisions](docs/adr/)
- [Roadmap](project/ROADMAP.md)
- [Workstreams](project/WORKSTREAMS.md)

Provider cost estimates are deliberately deferred until versioned provider rates
are configured. Usage and latency are still persisted. The interactive waveform
and score-calibration work is tracked separately so visual polish never obscures
the evidence behind a learner-facing review.
