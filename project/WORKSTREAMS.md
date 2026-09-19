# Oratry V1 workstreams

Last updated: 2026-09-18

## Operating model

The lead agent owns architecture, shared contracts (documented in `docs/`), global project state, ADRs, merge/integration sequencing, and cross-workstream review. Specialists must stay within the file ownership below. Contract changes require a handoff note; the lead resolves conflicts before another workstream consumes them.

All specialist skills are explicit-only and live in `.agents/skills/`.

## Dependency DAG

```text
Database foundation (DONE) ────────┬─> W5 baseline/API lifecycle ─> W6 authenticated web shell
                                  ├─> W7 storage upload lifecycle ─┬─> W9 async pipeline integration ─> W11 results/retry/progress integration
                                  └─> W10 retention + usage ledger ┘

Speech foundation (DONE) ──────────────────────────────────────────┘
Evaluation foundation (DONE) ──────────────────────────────────────┘
W4 learning policy + baseline catalog ─────────────> W5 ───────────┘
Browser recorder foundation (DONE) ────────────────> W7

W12 cross-workstream review gates each merge and W9/W11.
```

## Ownership and status

| ID | Specialist | Status | Owned files/modules | Deliverable / acceptance |
| --- | --- | --- | --- | --- |
| W5 | Backend | DONE | `app/main.py`, `app/schemas.py`, `app/services.py`, backend API tests | Durable onboarding/baseline/home/assignment contracts and authorization; reviewed after migration-backed baseline uniqueness and ordered-attempt enforcement. |
| W6 | Frontend | DONE | `app/*.tsx`, `features/**`, frontend tests/styles | Authenticated onboarding, home, and preparation UI using typed server client. |
| W7 | Backend + Frontend | BLOCKED by R2 canary/configuration | backend upload endpoints/service tests; recorder upload glue | Private signed upload, metadata verification, and browser lifecycle are implemented and reviewed; live single-PUT checksum behavior requires a private R2 canary. |
| W9 | Integration | BLOCKED by W7 R2 canary | composition/wiring, workers, integration tests | Durable queue, storage/STT/evaluator pipeline, idempotent stages and provider usage instrumentation. |
| W10 | Integration | BLOCKED by W7 | retention worker, integration tests/ops docs | Configurable post-success deletion scheduling/retry and deletion audit state. |
| W11 | Integration + Frontend | BLOCKED by W5/W7/W9 | assigned integration glue and result/progress UI | Polling, result display, retry comparison, and progress flow. |
| W12 | Code review | ON_DEMAND | no implementation ownership | Architecture/security/contract review before merge and before W9/W11 integration. |
| W14 | Database | IN_PROGRESS | `app/models.py`, `migrations/**`, schema tests | Email activation persistence: verified user state and one-time token lifecycle. |
| W16 | Frontend | IN_PROGRESS | account surfaces, typed client, frontend tests/styles | Replace mock profile/vocabulary/progress surfaces with authenticated server data. |

## Parallel start set

W2 Speech, W3 Evaluation, W4 Learning, W5 Backend, W6 Frontend, W7 upload implementation, and W8 Frontend Recorder are integrated following W12 review. W7 remains conditionally blocked pending the private R2 canary; no workstream is actively editing its owned implementation files.

## Handoff format

Each specialist returns:

1. Files changed and files intentionally not changed.
2. Contract introduced or consumed, including example types/payloads where relevant.
3. Verification performed and result.
4. Open dependency, blocker, or requested decision.
