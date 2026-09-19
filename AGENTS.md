# Oratry engineering guide

## Product focus

Work toward the authenticated, durable V1 learning loop:

`Think -> Speak -> Analyze -> Correct -> Retry -> Progress`

Prefer completing this vertical slice over expanding mock screens or adding adjacent features.

## Architecture guardrails

- Keep V1 a modular monolith: Next.js web client, FastAPI API/worker code, PostgreSQL source of truth, private object storage, and asynchronous analysis jobs.
- Keep external integrations behind ports. Business services must not import vendor SDKs.
- Persist immutable, versioned analysis evidence. Derive current skill state as a replaceable projection.
- Keep deterministic metrics separate from AI interpretation and scoring.
- Do not infer emotional or psychological state from audio.
- Add migrations for runtime schema changes; do not mutate a deployed schema manually.

## Working agreement

- Read `project/CURRENT_STATE.md` and `project/BACKLOG.md` before selecting the next task.
- Keep one primary implementation task `IN_PROGRESS` per workstream.
- Preserve unrelated uncommitted work.
- Run focused checks after every change and record known verification limits factually.
- Update project-state documentation when implementation reality changes.

## Documentation governance

The Architect/Orchestrator owns global project state: `project/PRODUCT.md`, `project/CURRENT_STATE.md`, `project/ROADMAP.md`, `project/BACKLOG.md`, `project/WORKSTREAMS.md`, `docs/architecture.md`, and cross-domain ADRs. Specialists read these documents but do not normally rewrite them.

Specialists own implementation, tests, fixtures, and domain-specific technical documentation. A specialist may update global documentation only when explicitly assigned. Every handoff reports task ID, status, implementation summary, tests/results, changed modules, contract/schema changes, migrations, new configuration, known limitations, blockers, and commit/branch when applicable. The Architect/Orchestrator integrates the handoff and updates global state.
