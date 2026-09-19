---
name: oratry-database
description: Design and implement Oratry PostgreSQL/SQLAlchemy persistence changes and Alembic migrations for an assigned database workstream.
---

# Oratry Database

Read `project/WORKSTREAMS.md`, relevant ADRs, runtime models, and existing migrations. Own `app/models.py`, `migrations/**`, `db/migrations/**`, `db/seeds/**`, schema tests, and database documentation. Do not change API handlers, provider implementations, or frontend code.

PostgreSQL is authoritative. Use additive, migration-owned, reversible changes where feasible; never reintroduce `create_all` for runtime or seed behavior. Preserve immutable/versioned analysis evidence, retention/deletion state, and tenant ownership integrity. Model raw audio as metadata only; object bytes stay in private object storage. Identify SQLite-test compatibility explicitly when it differs from PostgreSQL.

Verify clean migration upgrade and focused schema/integrity tests. Handoff exact ORM field and query expectations to backend/integration owners.
