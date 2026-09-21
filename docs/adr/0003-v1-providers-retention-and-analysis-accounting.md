# ADR 0003: V1 providers, audio retention, and analysis accounting

Date: 2026-09-18

## Status

Accepted

## Decision

- PostgreSQL is the production source of truth. Local PostgreSQL is supported; Supabase is the preferred managed PostgreSQL option.
- Raw recordings are stored in a private Cloudflare R2 Standard bucket through an S3-compatible `ObjectStorageProvider`. The application issues only short-lived signed URLs; permanent public URLs are forbidden.
- After successful analysis, raw audio is retained for a configurable period, defaulting to 24 hours, then automatically deleted. PostgreSQL retains the retention deadline and deletion outcome plus all non-audio learning evidence: transcript, word timestamps, deterministic metrics, evaluations, scores, feedback, challenge/attempt history, and skill observations.
- V1 uses Deepgram Nova-3 prerecorded transcription. Provider adapters must normalize word-level timestamps and confidence into the canonical transcript contract.
- Superseded for evaluator choice by ADR 0004. The original OpenAI evaluator remains available behind `LLMProvider` for configuration-selected comparisons.
- Every completed analysis records STT audio duration, LLM input/output tokens, estimated provider cost, and latency. The initial operating target is less than approximately USD 0.01 variable cost for a two-minute session.

## Consequences

Raw audio deletion is a separate, retryable lifecycle from successful analysis. A failed deletion is recorded and retried; it does not erase the analysis evidence. No provider may be selected by business logic, and no LLM may generate deterministic speech measurements.

The cost target is an operational budget rather than a guarantee: provider pricing, prompt length, retry volume, and storage operations must be measured before a production commitment.
