# Current state

Last audited: 2026-09-18

## What works now

- A Next.js 15 / React 19 interface provides a complete, clickable local product walkthrough: landing, signup, onboarding, baseline, preparation, simulated recording/processing, results, retry, comparison, progress, vocabulary, and profile.
- A FastAPI application provides password-based signup/signin, JWT bearer authorization, challenge assignment, attempt lifecycle endpoints, vocabulary endpoints, result retrieval, and a basic progress/skill endpoint.
- The API has SQLAlchemy models and explicit Alembic migrations. SQLite is the default local database. A PostgreSQL 17 Compose service, gated live-Alembic integration suite, and GitHub Actions PostgreSQL verification job are present. The full active migration chain passed on an isolated non-superuser local PostgreSQL 17 database, including empty-database upgrade, schema/integrity checks, and downgrade cleanup. Python tests cover authorization, the demo recording-to-feedback flow, scoring, evaluation validation, personalization, deterministic speech-analysis modules, configuration, storage port contract, and ORM/migration index parity.
- A provider-neutral boundary exists for demo transcription and evaluation. An S3-compatible private-storage port and Cloudflare R2 adapter are present; recording retention has a migration-backed metadata lifecycle. The `oratry.speech` package separately provides deterministic transcript and PCM WAV analysis with tests.
- Skill evidence is persisted and current skill state is derived from recent evidence.

## What is demo or mocked

- The browser still uses `features/shared/mock-data.ts` for most preview screens. Its auth, baseline/onboarding, home, preparation, and recording-upload path now uses the FastAPI API through a typed same-origin client and a session-scoped bearer token. The recorder hashes the finalized browser `MediaRecorder` blob, uses only server-issued private upload headers, and preserves retry-safe completion confirmation. Live upload remains unavailable until private R2 configuration and a checksum canary are complete.
- API transcription always returns a fixed local transcript and its evaluator returns rule-based demo scores. The API service does not use the richer `oratry.speech` deterministic audio pipeline.
- `JobQueue` is an in-memory list. Upload completion only validates a caller-supplied object key; no object is stored, verified, or processed. The worker is manually invoked by tests or a legacy background endpoint.
- Runtime persistence defaults to SQLite. The runtime schema is migration-owned and supports PostgreSQL, though the legacy PostgreSQL SQL artifacts still describe a more complete future model than the active SQLAlchemy schema.
- Baseline/onboarding/home/comparison/status/idempotency/delete contracts described in docs are absent or only simulated.

## Architecture actually present

```text
Next.js mock UI ── no runtime connection ──> FastAPI demo API
                                             ├─ SQLAlchemy / SQLite runtime models
                                             ├─ in-memory queue + demo STT/evaluator
                                             └─ result JSON + skill projection

oratry.speech (independent deterministic analysis library)
PostgreSQL SQL artifacts (target model; not integrated)
```

This is a useful prototype foundation, but not yet a functioning end-to-end V1 vertical slice.

## Documentation accuracy

- `README.md` accurately labels the browser flow and backend providers as a local preview/demo, but it understates the implementation that now exists.
- `docs/architecture.md`, `docs/domain-model.md`, and `docs/api-contracts.md` are target technical design/contract documents and explicitly defer implementation status to this file.
- Several target API endpoints and guarantees documented in `docs/api-contracts.md` do not yet exist.
- The PostgreSQL SQL artifacts are a target data model, not runtime migrations.

## Verification at audit time

- Python: `43 passed, 2 skipped` using `python -m pytest`. Skipped tests require explicit disposable PostgreSQL test configuration.
- Frontend: `npm run lint` and `npm run typecheck` pass.
- `npm test` and `npm run build` cannot spawn child processes in this restricted Windows execution environment (`spawn EPERM`). This is an environment limitation; rerun in a normal developer shell/CI.

## Primary workstream

W2 Speech, W3 Evaluation, W4 Learning, W5 Backend, W6 Frontend, W7 upload implementation, and W8 Frontend Recorder are integrated following cross-workstream review. They provide a fixture-backed Deepgram adapter with canonical usage evidence, a settings-driven strict OpenAI evaluator contract, a stable baseline/recommendation policy, a concurrency-safe durable baseline/home/current-assignment API, an authenticated browser path, and a private signed-upload implementation. W7 is blocked only on private R2 configuration and a real checksum canary; W9 cannot begin real provider pipeline integration until that evidence exists. Current ownership and dependencies are in `project/WORKSTREAMS.md`.

Application startup and the development seed command no longer create database tables. Alembic uses the configured database URL, and the active migrations have explicit table operations rather than `metadata.create_all`. Non-local/test settings reject SQLite and the checked-in JWT default. `compose.yaml`, `docs/postgresql-development.md`, and `.github/workflows/postgres.yml` provide the local/CI verification path. PostgreSQL 17 verification passed locally without persisting credentials.

Provider and retention decisions are recorded in ADR 0003. Configuration names are present in `.env.example`; existing secrets in `.env` were not read or modified. The currently configured Cloudflare variables use legacy names and omit the explicit R2 bucket required by the application; no R2 object was created during the blocked canary attempt.

Milestone 2 has begun with `ObjectStorageProvider`, `R2ObjectStorageProvider`, and a `recordings` retention lifecycle table. The adapter is intentionally not wired to the demo upload endpoint yet: that requires the authenticated browser upload flow and server-side object metadata verification.

## Workstream coordination

Direct feature implementation is paused while the multi-agent workstream model is established. `project/WORKSTREAMS.md` defines specialist ownership, cross-workstream contracts, and the dependency DAG. The lead owns architecture, integration, ADRs, project state, and cross-workstream review.
