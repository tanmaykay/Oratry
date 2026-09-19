# Oratry V1 Architecture

## Scope and implementation boundary

This document defines the target technical architecture. Implementation status is deliberately kept out of this document and lives in `project/CURRENT_STATE.md`. The active codebase is a modular-monolith prototype with a mock browser flow and a separate FastAPI demo API; do not infer that every target component below is already implemented.

## Target state

Oratry is a web-first training system whose unit of work is a **practice attempt**. The V1 loop is:

`baseline -> assigned challenge -> preparation -> recorded attempt -> analysis -> coaching -> retry -> comparison`

The deployed system consists of:

| Component | Responsibility | Technology |
| --- | --- | --- |
| Web app | Authenticated product UI, recording, upload, result and progress views | Next.js / React / TypeScript |
| API | Product commands, reads, authorization, signed uploads, orchestration | FastAPI / Python |
| Worker | Long-running and retryable analysis pipeline | Python worker consuming Redis jobs |
| Relational store | User, curriculum, attempt, score, and progress records | PostgreSQL |
| Queue | Analysis job delivery and retry scheduling | Redis |
| Object store | Immutable raw recordings and generated analysis artifacts | S3-compatible storage |
| Media tools | Audio normalization and objective signal extraction | FFmpeg plus Python audio-analysis code |
| Providers | Transcription and rubric evaluation behind replaceable adapters | STT and LLM provider interfaces |

The API is the only component permitted to issue uploads and read product data. Workers receive identifiers, read media through a short-lived internal object-store credential or signed URL, and write results through service-layer commands. Browser clients never call STT or LLM providers.

## Logical module boundaries

Target backend module boundaries:

```
backend/
  app/
    api/                 # FastAPI routing, request/response models, auth dependency
    application/         # use cases and transactions; orchestration only
    domain/              # entities, value objects, scoring rules, domain events
    persistence/         # SQLAlchemy repositories and migrations
    media/               # object-store gateway, FFmpeg normalization, signal metrics
    transcription/       # STT port and provider adapters
    evaluation/          # LLM port, prompts, structured-result validation
    coaching/            # recommendation selection from completed evaluations
    personalization/     # skill-state update and challenge selection
    workers/             # queue consumers and idempotent job handlers
    observability/       # structured logs, tracing, metrics, audit helpers
```

Frontend feature modules should mirror product surfaces: `home`, `practice`, `progress`, `vocabulary`, and `profile`, with a small shared API client, design system, auth/session support, and recorder/upload component. Product decisions remain on the server; the client may calculate transient recording duration or waveform display but must not produce authoritative metrics or scores.

### Dependency direction

`api -> application -> domain` and `workers -> application -> domain`. Persistence and all external providers implement ports declared by application/domain-facing code; they must not leak their SDK types upward. `coaching` consumes validated scores and evaluation findings; it does not call an LLM directly. `personalization` consumes longitudinal skill evidence and publishes the next challenge assignment.

## Analysis pipeline

1. API creates an `attempt` in `uploading` state and returns a constrained, short-lived upload URL.
2. Client uploads one audio recording and calls completion with its object key, checksum, duration, and MIME type.
3. API validates ownership and object metadata, seals the attempt, and enqueues `analyze_attempt(attempt_id)`.
4. Worker normalizes the recording with FFmpeg, stores the derived audio artifact, calls the configured STT adapter, and persists a versioned transcript.
5. Worker derives objective audio/transcript metrics (for example duration, words per minute, voiced/silent time, filler counts, and pauses) with their calculation/version metadata.
6. Worker asks the LLM adapter for a schema-constrained rubric evaluation based on the prompt, transcript, challenge rubric, and permitted objective context. It validates and stores the result.
7. Scoring calculates the five weighted dimension scores: Structure 25%, Clarity 20%, Fluency 20%, Language 20%, Delivery 15%. It stores score inputs and scorer version.
8. Coaching selects exactly one actionable recommendation from the evaluation and score gaps. Personalization updates skill evidence and assigns the next appropriate challenge. The attempt becomes `completed`.

Failures are retryable at a stage boundary and leave the attempt in `analysis_failed` with a safe user-facing message. Jobs must be idempotent by attempt ID and stage/version; repeating a job must not duplicate transcripts, scores, skill evidence, or coaching recommendations.

## Provider ports

Provider selection is configuration, not product logic. Adapters return canonical data structures and record provider/model/version on every result.

```
TranscriptionPort.transcribe(audio, language_hint) -> Transcript
AudioAnalyzer.analyze(audio, transcript) -> ObjectiveMetrics
EvaluationPort.evaluate(EvaluationInput) -> RubricEvaluation
ObjectStoragePort.create_upload(...) / get(...) / put(...)
JobQueuePort.enqueue_attempt_analysis(attempt_id)
```

`Transcript` contains timestamped segments/words when available, text, language, and confidence. `ObjectiveMetrics` contains values, units, provenance, and calculation version. `RubricEvaluation` contains dimension observations, bounded numeric judgments, evidence references into the transcript, and an optional uncertainty indicator. A provider outage must never cause a fallback adapter to silently mix incompatible results in one analysis revision.

## Scoring, coaching, and personalization

Objective measurements are facts and should be rendered separately from AI interpretation. A score is a product calculation with versioned weights and inputs; it is neither a raw provider score nor an undisclosed LLM opinion. The LLM may evaluate structure, clarity, language, and delivery evidence, but its output is stored as interpretation. The deterministic scorer combines validated inputs according to a published server-side rubric.

Coaching produces one behavior-focused recommendation for the current attempt, including: observed issue, one concrete action for the retry, and a success criterion. It must not generate a response, thesis, evidence, or argument for the user. Challenge prompts encourage independent research and preparation; they need not require the system to browse or supply sources in V1.

Personalization maintains per-skill evidence and selects challenge difficulty/skill emphasis from it. It should initially be rules-based and explainable. Do not build a trained learner model or fine-tune an audio model for V1.

## Security and operations

- Audio is sensitive user content. Use private object storage, signed uploads with size/content-type/key constraints, encryption at rest, and least-privilege service credentials.
- Verify upload ownership, checksum, media size/duration limits, and allowed content types before queuing work. Run FFmpeg in resource-limited workers.
- Enforce user authorization in every query; IDs alone are not authorization.
- Keep provider keys server-side; redact transcript/audio URLs and secrets from logs.
- Record analysis, provider, rubric, prompt, scorer, and metric-calculation versions for reproducibility.
- Define retention and user deletion behavior before collecting production recordings. Deletion must cover derived media, transcripts, evaluations, and object-store artifacts.
- Add structured logs, job-stage metrics, dead-letter visibility, and alerts for provider failure and queue age.

## Explicit V1 non-goals

No audio-model fine-tuning, real-time coaching, public sharing, collaborative practice, generic chatbot, autonomous web research, or ML-based curriculum optimization is required. Provider adapters keep those future options open without adding their complexity now.
