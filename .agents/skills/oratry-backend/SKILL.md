---
name: oratry-backend
description: Implement Oratry FastAPI application contracts, authorization, lifecycle orchestration, and service-layer behavior for an assigned backend workstream.
---

# Oratry Backend

Read `project/WORKSTREAMS.md`, current API contracts, and assigned ADRs first. Own `app/main.py`, `app/schemas.py`, `app/services.py`, `app/core.py`, `app/workers.py`, and backend tests except files explicitly owned by another specialist. Do not modify migrations/models, provider adapters, frontend code, or global docs.

Preserve authenticated ownership checks, opaque-resource 404 behavior, structured errors, explicit state transitions, and idempotency. Business services depend on ports, never provider SDKs. Do not make the queue or storage behavior appear durable when it is not. Handoff any schema need as a migration request with fields, constraints, and backfill implications.

Run focused API tests and report contract changes, failure behavior, and integration dependencies.
