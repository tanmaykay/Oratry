# PostgreSQL target-schema reference

These SQL files are reference artifacts for the fuller target schema. The active runtime migration path is Alembic under `migrations/`; do not apply both systems to one database. Current implementation status is in `project/CURRENT_STATE.md`.

Do not execute these files against an Oratry runtime database. Use the active
Alembic workflow in [docs/postgresql-development.md](../docs/postgresql-development.md)
for local or managed PostgreSQL. These files are retained to communicate the
future target model only.

## Design notes and invariants

- UUIDs are opaque primary keys. `challenges` is append-only by intent: a new curriculum revision has a new `id`, with `challenge_family_id` and `version` identifying its lineage. Assignments point at that immutable revision.
- `challenge_attempts` preserves every original and retry. `(assignment_id, ordinal)` is unique; ordinal one cannot have a retry parent and every later ordinal must have one. The second migration enforces that an attempt owns its assignment/session and that a retry directly follows a completed attempt in the same user, assignment, and comparison group.
- Audio bytes never enter PostgreSQL. `recordings` stores only private object-storage metadata; at most one raw and one normalized asset can attach to an attempt.
- An analysis run is versioned per attempt. Transcript, metric, and evaluation records attach to a run, so re-analysis never overwrites historical output. Evaluations require provider, model, model version, rubric version, prompt version, and confidence.
- `skill_observations` and `user_vocabulary_observations` are append-only evidence. `skill_profiles` and `user_vocabulary.current_proficiency` are current projections, not the sole historical record.
- A metric is unique per run/name/calculation version, includes provenance and confidence, and unavailable values are never represented as a fabricated zero.
- `feedback_one_active_per_evaluation` guarantees one active coaching recommendation per evaluation. Application services enforce lifecycle transitions, cross-user ownership chains, retry eligibility, and immutable object-store keys; those require transactional business context beyond a simple row constraint.

The indexes target the documented workload: a user's assignment queue, recent attempts, worker queue polling, transcript playback, progress evidence, vocabulary history, and aggregate/user event timelines.
