# Current state

Last audited: 2026-09-24

## Working V1 slice

- The authenticated web application supports signup/activation, sign-in, onboarding, baseline assignment, challenge preparation, browser recording, private direct upload, analysis polling, profile, vocabulary, and progress surfaces. Completed-attempt review loads persisted evidence rather than mock data: challenge context, private replay during retention, decoded recording-amplitude waveform, timestamp/confidence-aware transcript annotations that seek the recording, deterministic metrics, structured evaluation, same-challenge retries, and before/after comparison.
- Runtime persistence is migration-owned PostgreSQL. The production database is at Alembic revision `20260924_12`; the active schema has been verified from an empty PostgreSQL database to head.
- Private Cloudflare R2 signed-upload and server-side deletion canaries passed with the configured credentials. No permanent recording URL is issued.
- Upload completion verifies object checksum and metadata, persists a recording, and atomically creates a durable `analysis_jobs` delivery. The worker leases, fences, retries, and reclaims deliveries; it is not an in-memory queue.
- The analysis worker uses the configured Deepgram prerecorded provider, computes deterministic transcript metrics and a versioned deterministic scorecard, requests strict structured Gemini evaluation, persists usage/latency and retention state, then projects skill evidence. Evaluator retries reuse immutable persisted STT evidence rather than paying for STT again.
- Raw audio is scheduled for configurable post-success deletion (24 hours by default). The retention worker records leases, attempts, backoff, and terminal deletion state while retaining non-audio learning evidence in PostgreSQL.
- Email activation uses a provider port: development outbox locally and Resend when production configuration is supplied. Vocabulary has a cached dictionary-provider boundary with a Datamuse fallback.
- Google OIDC is implemented behind an identity-provider boundary with PKCE, signed callback state, verified provider subject binding, and an opaque one-time browser handoff. It remains disabled until Google OAuth client configuration is supplied.
- V1-016 now includes API liveness/readiness endpoints, a pilot Compose template with supervised process restart policy, worker health checks, and a target-environment checklist. Target hosting, monitoring, managed-PostgreSQL restore proof, and retention canary execution remain environment work.
- Active curated challenges now persist versioned `target_vocabulary` JSON. Targets flow unchanged to deterministic transcript matching, scorecard coverage, and evaluator context. Pre-existing challenge versions retain an empty target list rather than receiving invented historical targets.
- Home and challenge briefing now connect a learner to the current challenge’s vocabulary targets and practice history, so target-word preparation, recording review, and progress are navigable as one loop. The canonical active and future challenge taxonomy is documented in `docs/challenge-catalog.md`; future modes remain inactive until their mode-specific experience and rubric are validated.
- Completed analyses now project exact deterministic challenge-target matches into immutable vocabulary observations. The Word Bank shows occurrence count and last observed date; deleting a Word Bank item preserves the historical observation while clearing only its optional item link. Home exposes the latest visible, persisted primary coaching focus and never counts or focuses a hidden review.
- Client API requests have a bounded 15-second timeout. A failed bootstrap therefore reaches the retryable loading-error screen instead of leaving a refreshed practice session on an indefinite spinner.
- A new recording with a different checksum supersedes an unsealed `uploading` attempt, allowing recovery from an interrupted browser upload without modifying queued or completed attempts.
- The direct-upload deadline is one minute. R2 worker reads are bounded to a 5-second connect and 10-second read timeout, with one storage retry; the learner-facing processing state exposes private-storage retrieval failure distinctly from transcription/evaluation failure. A current authenticated R2 head/download diagnostic passed after the earlier transient storage failures.
- Preparation notes are browser-session-only and never submitted for analysis. Profile preferences now select hidden notes, always-visible notes, or five-second quick glances followed by a twenty-second cooldown during speaking.
- Learners can reversibly hide completed or failed reviews from Progress. Hiding preserves immutable evidence, baseline completion, and existing skill projections, but removes the review, its playback, and direct result routes from the learner-facing surfaces. Irreversible practice-data deletion remains a separate, unimplemented privacy action.
- New analyses use deterministic scorecard `deterministic-metrics-v3`: zero transcribed words yields an overall score of zero, a short transcript caps the overall score until it reaches `max(10 words, 0.5 words per challenge-target second)`, and timestamp-evidenced long internal pauses contribute to fluency. This gate also prevents incomplete responses from creating skill-profile evidence. Deepgram prerecorded requests opt into `filler_words=true`; deterministic word-confidence metrics warn the evaluator not to treat uncertain transcription as incoherence. Evaluator rubric/prompt `1.2.0` instructs the model to score an absent transcript as zero. Prior persisted scorecards/evaluations remain immutable under their recorded versions.

## Verification at this audit

- Python: `117 passed, 4 skipped` (`.venv\\Scripts\\python.exe -m pytest -q`). The skipped tests are intentionally gated external/provider tests.
- PostgreSQL schema integration: `4 passed` using the configured disposable PostgreSQL test database, including an independent-session concurrent `SKIP LOCKED` claim race.
- Frontend: `npm run lint` and `npm run typecheck` pass.
- `git diff --check` passes; Windows line-ending notices are non-failing.
- R2 signed PUT/checksum and delete canaries passed. On 2026-09-21, a browser-originated recording completed end-to-end through R2, Deepgram, and Gemini; transcript, metrics, evaluation, scorecard, feedback, skill evidence, and scheduled retention were persisted. On 2026-09-24, the owner-authorized signed R2 `GET` was verified in the browser: private playback and decoded waveform peaks both completed after the CORS update.

## Configuration status and demo gate

The current runtime resolves PostgreSQL, R2, Deepgram, and Gemini provider selections and credentials. Provider unit-price configuration remains intentionally absent: `ANALYSIS_COST_VERSION` is `unconfigured` and all three rate settings are blank. The completed local Gemini run persisted input/output tokens and latency but correctly recorded `estimatedCostUsd: null`. Configure a price version and rates before a cost-accounted production release. Non-local/test worker startup rejects missing rates. OpenAI remains optional and is not required for the working V1 path.

Start the API, analysis worker, and retention worker separately using the documented commands in `README.md`, `docs/analysis-worker-operations.md`, and `docs/retention-operations.md`.

## Known limits

- Cost-rate configuration and continuous-worker deployment verification remain before a cost-accounted Stage 1 release. The browser-to-R2/Deepgram/Gemini functional canary passed.
- Deployment-specific alert routing, managed PostgreSQL restore drill, deployed process supervision verification, and retention canary remain before a pilot. The template and checklist are in `docs/pilot-deployment.md`.
- Google sign-in awaits a client ID, client secret, and final HTTPS callback/origin values. Production Resend/domain configuration remains separate.
- Comparison exposes only persisted score and deterministic metrics for a completed source/retry pair; unavailable comparisons are stated plainly rather than synthesizing improvements.
- Score calibration remains V1-012. V1-013 is complete: waveform peaks are decoded locally from the owner-authorized short-lived recording URL and are not persisted, so they disappear with raw-audio access. The R2 signed-`GET` CORS configuration is now browser-verified for the local web origin. Colored waveform marks represent transcript-derived lexical evidence only, never unvalidated moment-level skill scoring.
- Deterministic WAV analysis no longer depends on deprecated `audioop`; it supports 8/16/24/32-bit PCM WAV directly.
- The response-coverage guard is a safety floor, not final calibration. Challenge-specific score calibration still requires a consented, labelled evaluation set.

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
