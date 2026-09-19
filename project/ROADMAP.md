# V1 roadmap

## Milestone 1 — Durable backend foundation (in progress)

Replace the split SQLite/runtime and PostgreSQL/target schema story with one migration-owned PostgreSQL runtime model. Add configuration validation, health/readiness behavior, and durable attempt/analysis state contracts while retaining an isolated local-test strategy.

Status: migration ownership, production configuration guards, Compose setup, PostgreSQL CI, and a clean PostgreSQL 17 migration verification are complete. Lifecycle/status contracts remain.

## Milestone 2 — Real recording and durable analysis path (foundation started)

An S3-compatible R2 adapter and recording-retention metadata are present, but the user-facing path has not started. Implement browser authentication and API integration, `MediaRecorder`, private constrained object-storage uploads, metadata verification, and a retryable asynchronous worker. Connect canonical STT and deterministic metrics to persisted analysis runs.

Exit: a signed-in user can record, upload, reload, and see a real queued/completed result based on their recording.

## Milestone 3 — Evaluation, retry, and progress completion (not started)

Add schema-validated LLM evaluation behind a provider adapter, versioned score/coaching persistence, baseline/onboarding assignment policy, retry/comparison endpoints and UI, and a real progress view.

Exit: the full V1 loop works with one production STT provider and one LLM provider, including failure/retry behavior.

## Launch hardening (not started)

Define retention/deletion policy, enforce idempotency, complete authorization and media-failure coverage, add observability, provider cost controls, backups, and controlled pilot readiness checks.
