# Engineering backlog

| ID | Description | Priority | Dependencies | Acceptance criteria | Status |
| --- | --- | --- | --- | --- | --- |
| V1-001 | PostgreSQL migration verification | P0 | None | Owner: Architect. PostgreSQL 17 clean upgrade to Alembic head, schema/integrity checks, and downgrade cleanup passed on an isolated non-superuser database. | DONE |
| V1-002 | Baseline and assignment domain | P0 | V1-001 contract review | Owner: Learning + Backend. A new user can start and resume durable baseline assignments and retrieve the current assignment. | DONE |
| V1-003 | Authenticated web onboarding and preparation | P0 | V1-002 | Owner: Frontend. Browser uses server session and assignment data with loading/error states. | DONE |
| V1-004 | Recording upload lifecycle | P0 | V1-001, V1-003 | Owner: Frontend + Backend. Browser records audio, receives a short-lived upload instruction, uploads privately, and sees durable status after reload. Implementation is reviewed; live R2 checksum canary/configuration is pending. | BLOCKED |
| V1-005 | Async transcription and deterministic analysis | P0 | V1-004 | Owner: Speech + Integration. A real upload produces canonical Deepgram transcript and versioned deterministic metrics, or a retryable failure. | TODO |
| V1-006 | Evaluation, scoring, and coaching | P0 | V1-005 | Owner: Evaluation + Integration. Validated OpenAI interpretation, deterministic scorecard, provider usage, and one coaching insight are persisted and displayed. | TODO |
| V1-007 | Retry, comparison, and progress | P0 | V1-006 | Owner: Backend + Frontend. User can retry, compare attempts honestly, and view skill evidence/progress. | TODO |
| V1-008 | Retention, deletion, and observability | P0 | V1-004 | Owner: Integration. Configurable raw-audio deletion, deletion audit state, provider cost/latency, and operational failure signals are implemented. | READY |
| V1-009 | Replace deprecated audio dependency | P1 | V1-005 | Owner: Speech. Deterministic WAV analysis runs without `audioop` on supported Python versions. | TODO |
| V1-010 | Email activation and verified-account access | P0 | V1-001 | Owner: Database + Backend + Frontend. Signup creates a one-time expiring activation link; unverified accounts cannot authenticate; local development has a safe email outbox and production uses a configured provider abstraction. | IN_PROGRESS |
| V1-011 | Server-backed profile, vocabulary, and progress surfaces | P1 | V1-003 | Owner: Backend + Frontend. Profile preferences, vocabulary CRUD, and empty/real progress states are authenticated, persisted, and do not present mock learning results as real. | IN_PROGRESS |
