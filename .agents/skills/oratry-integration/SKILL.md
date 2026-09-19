---
name: oratry-integration
description: Integrate approved Oratry ports into end-to-end recording, retention, job, and observability flows after specialist contracts are ready.
---

# Oratry Integration

Read `project/WORKSTREAMS.md` and all relevant ADRs before work. Own composition roots, provider selection/wiring, worker orchestration, integration tests, and operational instrumentation. Do not redefine domain contracts, alter frontend screens, write migrations, or change provider payload normalization without the owning workstream.

Wire only approved ports: private R2 storage, Deepgram prerecorded STT, OpenAI evaluator, and a durable queue. Enforce short-lived signed uploads, object metadata verification, idempotent stage boundaries, retention deletion retry, and per-session provider duration/tokens/cost/latency measurement. Never log secrets, permanent URLs, raw transcript content, or credentials.

Use fake ports for automated tests; paid/live integrations require explicit authorization. Report cross-workstream incompatibilities as integration blockers.
