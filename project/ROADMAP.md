# V1 roadmap

## Milestone 1 — Durable foundation (complete)

Migration-owned PostgreSQL runtime, provider configuration guards, Compose/CI PostgreSQL verification, authenticated onboarding/baseline assignment, activation links, and server-backed profile/vocabulary foundations are integrated.

## Milestone 2 — Recording and analysis path (complete)

Private R2 signed uploads, durable job delivery, Deepgram transcription, deterministic metrics/scoring, configuration-selected structured evaluation, usage accounting, and retention deletion are implemented and verified with fixtures. R2 upload/delete canaries passed; the live R2/Deepgram/Gemini functional canary also passed.

The browser-to-R2/Deepgram/Gemini functional canary passed with a continuous worker. Provider cost accounting is intentionally deferred to V1-011; usage and latency continue to be persisted.

## Milestone 3 — Learning-loop completion (complete)

The evidence-first review is implemented: owner-authorized short-lived playback, a timestamp/confidence-aware transcript, deterministic filler/repetition/self-correction labels, challenge-linked feedback, same-challenge retries, and before/after comparisons from persisted evidence. The active curated catalog now persists challenge-owned vocabulary targets, which flow to deterministic coverage and evaluator context.

## Milestone 4 — Review quality and interaction (next)

Create a challenge-specific rubric and calibration set before retuning scores or coaching language. Then add an accessible custom waveform review: word selection seeks/highlights the recording, transcript findings have visible time spans, and visual encoding distinguishes deterministic local evidence from whole-attempt scores. Decide whether waveform peak data expires with the raw recording or is retained as derived learner data before implementation.

## Pilot hardening (after Milestone 3)

The PostgreSQL claim/lease integration coverage and deployment/backup/retention runbook are in place. Finish deployment-specific alerts, backup restore drill, supervised worker deployment, retention canary, production Resend/domain configuration, cost-budget monitoring, and controlled-pilot security review.
