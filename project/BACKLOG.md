# Engineering backlog

| ID | Description | Priority | Dependencies | Acceptance criteria | Status |
| --- | --- | --- | --- | --- | --- |
| V1-001 | PostgreSQL migration verification | P0 | None | Clean PostgreSQL upgrade to head, integrity checks, and downgrade cleanup pass. | DONE |
| V1-002 | Baseline, assignment, auth, profile, and vocabulary contracts | P0 | V1-001 | Verified users can complete onboarding and use persisted account surfaces. | DONE |
| V1-003 | Private recording upload lifecycle | P0 | V1-001, V1-002 | Browser receives a constrained signed upload and server verifies private object metadata/checksum. R2 canaries pass. | DONE |
| V1-004 | Durable analysis and evaluation pipeline | P0 | V1-003 | Durable leased job runs Deepgram, deterministic metrics/scoring, strict configuration-selected evaluation, and persists evidence/usage idempotently. | DONE |
| V1-005 | Configured-provider Stage 1 canary | P0 | V1-004 | A real browser recording reaches completed results; usage/latency and retention deadline are persisted. The R2/Deepgram/Gemini functional canary passed. | DONE |
| V1-006 | Evidence-first result review, retry, comparison, and progress | P0 | V1-005 | A completed attempt has an authenticated short-lived playback URL while raw audio exists; transcript words render with timestamp/confidence-aware annotations; deterministic fillers, adjacent repetitions, and possible self-corrections are clearly labelled; retry/comparison/progress use actual evidence and communicate unavailable data honestly. | DONE |
| V1-007 | Challenge catalog and target vocabulary | P1 | V1-006 | Curated initial challenge types/topics and versioned target vocabulary enable real coverage measurements. | DONE |
| V1-008 | Production operational hardening | P1 | V1-005 | PostgreSQL multi-worker claim test and deployment/backup/retention runbook are present. Deployment-specific alerts, managed backup restore drill, process supervision, and retention canary remain. | IN_PROGRESS |
| V1-009 | Production email delivery | P1 | Domain and Resend credentials | Resend delivery, verified sender domain, activation link UX, and production configuration verification pass. | BLOCKED |
| V1-010 | Replace deprecated audio dependency | P1 | None | Deterministic WAV analysis works without `audioop` on supported Python versions. | DONE |
| V1-011 | Provider cost accounting | P1 | V1-005, configured provider rates | Versioned Deepgram and evaluator rates produce per-session estimated costs and budget alerts. Deferred by product decision; usage and latency remain recorded. | TODO |
| V1-012 | Evaluation and scoring calibration | P1 | V1-007, representative consented recordings | Define challenge-specific scoring rubrics, build a labelled evaluation set, calibrate deterministic weights and evaluator prompts, version every rubric/model/scorer change, and present uncertainty or unavailable evidence honestly. | READY |
| V1-013 | Interactive recording-review waveform | P1 | V1-006, recording-retention decision | Replace the native audio control with an accessible waveform player synchronized with transcript word timestamps; select a word/filler/repetition to seek and highlight its audio span; make visual labels explain their evidence source. Never portray whole-attempt skill scores as moment-level acoustic facts without a validated deterministic measurement. | TODO |
