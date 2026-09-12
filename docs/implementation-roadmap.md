# Oratry V1 Implementation Roadmap

The repository has no implemented product features, so the first milestone establishes an executable vertical foundation before feature breadth. Each phase should end with a demonstrable, tested slice; avoid building a generic platform in advance.

## 0. Decisions and foundations

- Select deployment, identity, S3-compatible storage, Redis, PostgreSQL, one STT provider, and one LLM provider based on privacy, regional, cost, and latency requirements.
- Turn the existing Python package into a FastAPI service with configuration, health checks, structured logging, linting/formatting, tests, migrations, and local development containers or documented service setup.
- Create the Next.js application and shared API schema/client generation approach.
- Define recording constraints (browser support, accepted format, maximum file size, and duration tolerance) and data-retention/deletion policy.

Exit condition: authenticated API skeleton, web shell with Home/Practice/Progress/Vocabulary/Profile navigation, PostgreSQL migration workflow, and CI checks run locally and in the chosen host.

## 1. Curriculum, baseline, and assignment slice

- Implement the versioned challenge catalog, core taxonomy, assignment records, and a small curated baseline set.
- Implement signup/onboarding/profile, baseline start/status, current assignment, and Home/Practice preparation UI.
- Use an explainable initial assignment policy: baseline sequence first, then a challenge targeting the least-supported/lowest recent skill area.

Exit condition: a signed-in user can start baseline, view a durable assigned challenge with preparation guidance, and resume it on another device.

## 2. Recording and durable media slice

- Build browser recording with clear consent, timer, playback, retry-before-submit, and upload recovery UX.
- Implement attempt creation, short-lived constrained upload URLs, completion verification, private object keys, and attempt lifecycle APIs.
- Add media validation and safe worker-side FFmpeg normalization.

Exit condition: a user can submit one approximately two-minute recording, reload the page, and observe a durable queued/analyzing status without exposing the recording publicly.

## 3. Asynchronous analysis slice

- Add Redis worker, idempotent job processing, stage state, retries, dead-letter/operational visibility, and analysis-run versioning.
- Implement one STT adapter and canonical timestamped transcript persistence.
- Implement objective metrics with tests and explicit unavailable states. Validate metrics against a small consented fixture set.

Exit condition: uploaded audio reliably yields a stored transcript and separately displayed objective metrics, including safe failure behavior and retries.

## 4. Evaluation, scoring, and coaching slice

- Define the evaluation JSON schema, rubric/prompt versions, validator, and one LLM adapter.
- Implement deterministic weighted scorecards (Structure 25%, Clarity 20%, Fluency 20%, Language 20%, Delivery 15%) with unit tests for calculation and version persistence.
- Implement the one-recommendation coaching policy and result UI that visibly distinguishes measurements from AI interpretation.

Exit condition: a completed attempt presents transcript, factual metrics, rubric scorecard, AI evaluation evidence, and one actionable retry recommendation.

## 5. Retry, comparison, and progress slice

- Gate retry creation on a completed original attempt and preserve the same challenge version and comparison group.
- Build result comparison for score dimensions and objective metrics, with appropriate labels where values are not comparable.
- Persist skill evidence/state, provide progress trends, and create the user-managed Vocabulary surface.

Exit condition: a user can retry the same challenge and see an honest original-versus-retry comparison plus a longitudinal skill view.

## 6. Hardening and controlled launch

- Test authorization boundaries, uploads, idempotency, provider failures, corrupted media, duplicate jobs, deletion, and concurrency.
- Instrument analysis latency/cost/error rate, queue age, completion rate, retry rate, and outcome quality signals.
- Run an internal pilot, audit coaching recommendations for non-authorship, validate score stability, then tune challenge/rubric versions through explicit migrations.

Exit condition: production readiness review covers privacy/retention, backup/restore, monitoring, incident response, provider limits/cost controls, and documented rollout criteria.

## Key sequencing rules

Do not add real-time features before the asynchronous pipeline is reliable. Do not build adaptive ML before there is sufficient trustworthy longitudinal evidence. Do not couple UI directly to a provider SDK. Do not treat LLM evaluation as a substitute for objective metrics or the versioned scoring policy. No audio model fine-tuning belongs in V1.
