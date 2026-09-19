# Oratry V1 local preview

Oratry is a Next.js 15/React 19 browser preview alongside a FastAPI/Python 3.12 API. The browser flow is currently mock-driven; the API is a separate authenticated demo pipeline with SQLite as the default local database. See `project/CURRENT_STATE.md` for implementation reality and `project/ROADMAP.md` for the V1 path.

## Requirements

- Node.js 22 (or a compatible current Node LTS) and npm
- Python 3.12
- No Docker, PostgreSQL, Redis, STT, LLM, or FFmpeg is required for the local browser preview.

## Fresh setup

In PowerShell at the repository root:

```powershell
Copy-Item .env.example .env
npm install --include=dev
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
alembic upgrade head
python -m app.seed
```

`alembic upgrade head` applies the active SQLAlchemy migration series to the configured `DATABASE_URL` (SQLite by default). The checked-in `db/migrations/*.sql` artifacts describe a more complete PostgreSQL target model and are not part of the active Alembic upgrade path.

## Run the browser preview

```powershell
npm run dev
```

Open http://localhost:3000. Start at **Start practicing** and continue through onboarding, practice, speaking, processing, results, feedback, retry, comparison, and progress. No account, microphone, or API needs to be configured for this walkthrough.

## Run the API

In a second PowerShell after activating `.venv`:

```powershell
python main.py
```

The API is available at http://localhost:8000 and interactive docs at http://localhost:8000/docs. Its local seed user is `maya@example.test` with password `local-preview-password`.

The API currently uses SQLite plus in-process demo transcription/evaluation and an in-memory job list. An R2 adapter and recording-retention metadata exist but are not wired to uploads. Do not set `NEXT_PUBLIC_API_URL` for the current mock-driven UI; its browser API contract is not yet authenticated/wired to the backend's token flow.

## Checks

```powershell
npm run lint
npm run typecheck
npm test
npm run build
.\.venv\Scripts\python.exe -m pytest
```

## PostgreSQL development

The production runtime schema is standard PostgreSQL and is owned by Alembic.
For Docker Compose setup, clean-database migration verification, and managed
PostgreSQL guidance, see [docs/postgresql-development.md](docs/postgresql-development.md).
The checked-in `db/migrations/*.sql` files remain target-model reference
artifacts; do not apply them to an Alembic-managed database.
