# Current state

Last audited: 2026-09-21

## Working V1 slice

- The authenticated web application supports signup/activation, sign-in, onboarding, baseline assignment, challenge preparation, browser recording, private direct upload, analysis polling, profile, vocabulary, and progress surfaces. Completed-attempt review loads persisted evidence rather than mock data: challenge context, private replay during retention, deterministic metrics, structured evaluation, timestamp/confidence-aware transcript annotations, same-challenge retries, and before/after comparison.
- Runtime persistence is migration-owned PostgreSQL. The production database is at Alembic revision `20260922_08`; the active schema has been verified from an empty PostgreSQL database to head.
- Private Cloudflare R2 signed-upload and server-side deletion canaries passed with the configured credentials. No permanent recording URL is issued.
- Upload completion verifies object checksum and metadata, persists a recording, and atomically creates a durable `analysis_jobs` delivery. The worker leases, fences, retries, and reclaims deliveries; it is not an in-memory queue.
- The analysis worker uses the configured Deepgram prerecorded provider, computes deterministic transcript metrics and a versioned deterministic scorecard, requests strict structured Gemini evaluation, persists usage/latency and retention state, then projects skill evidence. Evaluator retries reuse immutable persisted STT evidence rather than paying for STT again.
- Raw audio is scheduled for configurable post-success deletion (24 hours by default). The retention worker records leases, attempts, backoff, and terminal deletion state while retaining non-audio learning evidence in PostgreSQL.
- Email activation uses a provider port: development outbox locally and Resend when production configuration is supplied. Vocabulary has a cached dictionary-provider boundary with a Datamuse fallback.
- Active curated challenges now persist versioned `target_vocabulary` JSON. Targets flow unchanged to deterministic transcript matching, scorecard coverage, and evaluator context. Pre-existing challenge versions retain an empty target list rather than receiving invented historical targets.

## Verification at this audit

- Python: `109 passed, 3 skipped` (`.venv\\Scripts\\python.exe -m pytest -q`). The skipped tests are intentionally gated external/provider tests.
- PostgreSQL schema integration: `3 passed` using the configured disposable PostgreSQL test database.
- Frontend: `npm run lint` and `npm run typecheck` pass.
- `git diff --check` passes; Windows line-ending notices are non-failing.
- R2 signed PUT/checksum and delete canaries passed. On 2026-09-21, a browser-originated recording completed end-to-end through R2, Deepgram, and Gemini; transcript, metrics, evaluation, scorecard, feedback, skill evidence, and scheduled retention were persisted.

## Configuration status and demo gate

The current runtime resolves PostgreSQL, R2, Deepgram, and Gemini provider selections and credentials. Provider unit-price configuration remains intentionally absent: `ANALYSIS_COST_VERSION` is `unconfigured` and all three rate settings are blank. The completed local Gemini run persisted input/output tokens and latency but correctly recorded `estimatedCostUsd: null`. Configure a price version and rates before a cost-accounted production release. Non-local/test worker startup rejects missing rates. OpenAI remains optional and is not required for the working V1 path.

Start the API, analysis worker, and retention worker separately using the documented commands in `README.md`, `docs/analysis-worker-operations.md`, and `docs/retention-operations.md`.

## Known limits

- Cost-rate configuration and continuous-worker deployment verification remain before a cost-accounted Stage 1 release. The browser-to-R2/Deepgram/Gemini functional canary passed.
- PostgreSQL job-claim semantics have schema coverage; add a multi-process PostgreSQL worker race test before a production pilot.
- Deployment-specific operational alerts, managed PostgreSQL restore drill, process supervision, and retention canary remain before a pilot. The runbook is in `docs/production-operations.md`.
- Comparison exposes only persisted score and deterministic metrics for a completed source/retry pair; unavailable comparisons are stated plainly rather than synthesizing improvements.
- Score calibration and the interactive waveform review are planned as V1-012 and V1-013. A gradient must not imply unvalidated moment-by-moment fluency or delivery scoring; waveform persistence versus the 24-hour raw-audio retention boundary remains a product/privacy decision.
- Deterministic WAV analysis no longer depends on deprecated `audioop`; it supports 8/16/24/32-bit PCM WAV directly.

## Architecture

```text
Next.js web client -> FastAPI modular monolith -> PostgreSQL
     |                     |\
     |                     | -> durable analysis_jobs -> analysis worker
     |                     |      -> private R2 -> Deepgram -> deterministic metrics
     |                     |      -> Gemini structured evaluation -> score/coaching/evidence
     +-> short-lived R2 signed PUT

retention worker -> private R2 delete -> PostgreSQL deletion audit
```

Provider SDKs remain behind storage, speech-to-text, and LLM ports. Deterministic measurement and scoring remain separate from model-assisted interpretation.
