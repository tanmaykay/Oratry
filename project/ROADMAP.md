# V1 roadmap

## Milestone 1 — Durable foundation (complete)

Migration-owned PostgreSQL runtime, provider configuration guards, Compose/CI PostgreSQL verification, authenticated onboarding/baseline assignment, activation links, and server-backed profile/vocabulary foundations are integrated.

## Milestone 2 — Recording and analysis path (complete)

Private R2 signed uploads, durable job delivery, Deepgram transcription, deterministic metrics/scoring, configuration-selected structured evaluation, usage accounting, and retention deletion are implemented and verified with fixtures. R2 upload/delete canaries passed; the live R2/Deepgram/Gemini functional canary also passed.

The browser-to-R2/Deepgram/Gemini functional canary passed with a continuous worker. Provider cost accounting is intentionally deferred to V1-011; usage and latency continue to be persisted.

## Milestone 3 — Learning-loop completion (complete)

The evidence-first review is implemented: owner-authorized short-lived playback, a timestamp/confidence-aware transcript, deterministic filler/repetition/self-correction labels, challenge-linked feedback, same-challenge retries, and before/after comparisons from persisted evidence. The active curated catalog now persists challenge-owned vocabulary targets, which flow to deterministic coverage and evaluator context.

## Milestone 4 — Review quality and interaction (in progress)

The accessible custom waveform review is implemented: browser-decoded amplitude peaks, word selection seeking/highlighting, and transcript-derived local markers are visually separate from whole-attempt scores. Peaks are deliberately not persisted and therefore expire with the raw recording; signed recording `GET` CORS is required for waveform decoding. Initial score safety guardrails now prevent silent/fragmentary transcripts from earning delivery credit. Next, create a challenge-specific rubric and consented calibration set before retuning weights or coaching language.

## Pilot hardening (after Milestone 3)

Repository operational hardening is complete: CI migrates PostgreSQL and races two independent job claimers, while the runbook documents deployment, backup, retention, and recovery procedures. Finish target-environment alerts, backup restore drill, supervised worker deployment, retention canary, production Resend/domain configuration, cost-budget monitoring, calibration, and controlled-pilot security review.
