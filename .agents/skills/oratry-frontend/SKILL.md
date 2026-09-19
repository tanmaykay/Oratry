---
name: oratry-frontend
description: Implement Oratry Next.js product surfaces, browser recording UX, and typed API consumption when assigned a frontend workstream.
---

# Oratry Frontend

Read `project/WORKSTREAMS.md`, `project/CURRENT_STATE.md`, and the assigned API contract before editing. Own `app/*.tsx`, `features/**`, frontend tests, and presentation styles. Do not modify backend routes, database models/migrations, provider adapters, or global project-state documents.

Use typed client boundaries; never embed provider keys or call R2, Deepgram, or OpenAI from the browser. Treat server measurements and scores as authoritative. Browser recording is `MediaRecorder` plus short-lived server-issued upload instructions; show consent, permission, error, retry-before-submit, upload recovery, and polling states. Preserve the distinction between objective metrics and AI interpretation.

Run focused frontend tests, lint, and typecheck. If an API contract is missing or incompatible, document the exact required request/response change in the handoff instead of changing another workstream's files.
