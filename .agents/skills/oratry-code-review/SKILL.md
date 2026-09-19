---
name: oratry-code-review
description: Perform an evidence-backed architecture and code review of an Oratry workstream change without implementing it.
---

# Oratry Code Review

Read the assigned diff, `project/WORKSTREAMS.md`, current state, and relevant ADRs. Do not edit implementation files unless explicitly asked to apply a narrowly described fix. Review for ownership-boundary violations, contract drift, authorization/privacy risks, migration safety, idempotency/retry behavior, versioning, deterministic-versus-AI separation, tests, and operational observability.

Return findings ordered by severity with file/line references, followed by verification gaps and a concise approval/block recommendation. Do not report speculative stylistic preferences as defects.
