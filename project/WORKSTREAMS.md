# Oratry V1 workstreams

Last updated: 2026-09-21

## Dependency DAG

```text
PostgreSQL + auth/baseline (DONE) -> private R2 upload (DONE) -> durable analysis (DONE)
                                                           |                 |
                                                           v                 v
                                                retention worker (DONE)  configured-provider canary
                                                                               -> evidence-first review (DONE)
                                                                               -> catalog/vocabulary targets
                                                                               -> pilot hardening
```

## Ownership and status

| ID | Specialist | Status | Deliverable |
| --- | --- | --- | --- |
| W5/W6 | Backend + Frontend | DONE | Authenticated onboarding, baseline, assignment, home, and preparation contracts. |
| W7/W8 | Backend + Frontend | DONE | Private R2 signed upload and browser recorder; upload and deletion provider canaries passed. |
| W9/W20/W21 | Integration, Speech, Evaluation | DONE | Durable leased pipeline, Deepgram normalization, deterministic scoring, strict configuration-selected evaluation, usage and cost instrumentation. |
| W10 | Integration | DONE | Configurable retention scheduler/worker, retry/lease audit lifecycle, and operations documentation. |
| W14/W15/W16 | Database, Backend, Frontend | DONE | Activation links, account surfaces, dictionary-backed vocabulary, and hardening tests. |
| W18 | Learning | DONE | Future curriculum taxonomy and catalog direction. |
| W12 | Code review | DONE | Cross-workstream review; configured-provider functional canary and repository operational verification passed. |

## Active work

`V1-012` is the next primary implementation task: build a consented, challenge-specific calibration set and versioned rubrics before changing scoring or coaching behavior. Target-environment pilot verification is V1-016 and depends on a hosting/monitoring selection. Cost accounting is explicitly deferred to V1-011; it is not a blocker for the learning-loop work. The Architect owns global documentation, integration, ADRs, and release decisions.
