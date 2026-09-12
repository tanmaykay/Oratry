# Oratry V1 Domain Model

## Ownership and aggregate boundaries

PostgreSQL is authoritative for product state. Object storage owns audio bytes and derived media only; Redis owns no durable business state. Provider outputs become durable only after validation and persistence in PostgreSQL.

| Aggregate / record | Owner | Purpose |
| --- | --- | --- |
| User, Profile | Identity/Profile | Account and user preferences, including language/consent settings needed for analysis |
| Challenge | Curriculum | Versioned speaking prompt, expected duration, target skills, difficulty, preparation guidance, and evaluation rubric reference |
| BaselineAssessment | Assessment | A bounded initial set of assigned baseline challenges and its completion state |
| ChallengeAssignment | Personalization | A user-specific assignment; records why, source (baseline or adaptive), and ordering |
| Attempt | Practice | User response to one assignment; owns lifecycle and retry relationship |
| MediaAsset | Media | Metadata and private object key for immutable raw/normalized audio |
| AnalysisRun | Analysis | One versioned execution of pipeline stages for an attempt |
| Transcript | Transcription | Canonical text and timestamp segments produced by a particular STT provider/version |
| ObjectiveMetricSet | Audio analysis | Measured values, units, calculation version, and provenance |
| Evaluation | Evaluation | Validated AI observations and dimension judgments with evidence references |
| Scorecard | Scoring | Dimension scores, weighted total, input references, weight/scorer version |
| CoachingRecommendation | Coaching | Exactly one active recommendation for an attempt's analysis run |
| SkillEvidence, SkillState | Personalization | Append-only evidence and derived current estimate per user/skill |
| VocabularyItem | Vocabulary | User-owned saved word/phrase and optional practice status; not inferred automatically in V1 |

The `Attempt` is the principal transactional aggregate. Its creation/sealing transitions occur in short database transactions. Analysis stages use separate, idempotent transactions keyed by `(attempt_id, analysis_version, stage)`.

## Relationships

```
User --< ChallengeAssignment >-- Challenge
User --< BaselineAssessment --< ChallengeAssignment
ChallengeAssignment --< Attempt (one original plus optional retries)
Attempt --< MediaAsset
Attempt --< AnalysisRun --1 Transcript
                       --1 ObjectiveMetricSet
                       --1 Evaluation --1 Scorecard --1 CoachingRecommendation
User --< SkillEvidence >-- AnalysisRun
User --1 SkillState (per core skill)
```

A retry is another `Attempt` attached to the same `ChallengeAssignment` and comparison group. It is not a replacement or mutation of the original attempt. The client can compare the completed original and retry using their independent scorecards and metric sets.

## Key fields and invariants

### Challenge and assignment

`Challenge`: `id`, `version`, `prompt`, `preparation_guidance`, `target_skills`, `difficulty`, `target_duration_seconds`, `rubric_version`, `active`.

`ChallengeAssignment`: `id`, `user_id`, `challenge_id`, `challenge_version`, `reason`, `sequence`, `status`, `assigned_at`. Preserve the challenge version so later curriculum edits cannot alter historical evaluation.

### Attempt and analysis

`Attempt`: `id`, `user_id`, `assignment_id`, `comparison_group_id`, `retry_of_attempt_id?`, `ordinal`, `status`, `created_at`, `sealed_at`, `completed_at`.

Allowed attempt states: `uploading -> queued -> analyzing -> completed`; `uploading|queued|analyzing -> analysis_failed`. A retry cannot be created until its source attempt has a completed analysis and active coaching recommendation. Only one raw recording is attached to an attempt in V1.

`AnalysisRun`: `id`, `attempt_id`, `version`, `status`, `current_stage`, `started_at`, `completed_at`, `failure_code?`. Each output references its analysis run. Re-analysis creates a new run/version rather than overwriting historical results.

### Result data

`ObjectiveMetricSet` stores a typed map of values, units, source (`audio`, `transcript`, or `derived`), validity flags, and algorithm version. Initial metric names may include `duration_seconds`, `word_count`, `words_per_minute`, `filler_count`, `filler_rate`, `pause_count`, `pause_seconds`, and `speaking_ratio`. Metrics unavailable from a provider remain explicitly unavailable; do not fabricate zeroes.

`Evaluation` stores `rubric_version`, `prompt_version`, `model_provider`, `model_name`, structured observations by dimension, transcript evidence spans, and validation status. It is interpretation, not measurement.

`Scorecard` stores integers or decimals on a documented 0–100 scale for `structure`, `clarity`, `fluency`, `language`, `delivery`, plus `overall`. `overall` is calculated as:

`0.25 structure + 0.20 clarity + 0.20 fluency + 0.20 language + 0.15 delivery`

Persist the exact dimension values, weights, scorer version, and source result IDs. Do not recalculate historical scorecards under new weights.

### Longitudinal model

The core skill taxonomy is fixed in V1: Thinking (reasoning, synthesis, argumentation, improvisation), Structure (organization, transitions, conclusions), Language (vocabulary, retrieval, precision), Fluency (fillers, hesitation, pace), and Delivery (clarity, intonation, energy).

`SkillEvidence` is append-only and references the attempt/analysis input that created it, a skill, observed level, confidence, and evidence type. `SkillState` is a replaceable derived projection with `estimated_level`, `confidence`, `last_evidence_at`, and model version. The initial personalization policy can use recent evidence, baseline completion, and challenge difficulty; it must never infer ability from missing analysis.

## Database constraints and indexes

- Foreign keys enforce user and ownership chains. All primary IDs are opaque UUIDs.
- Unique `(attempt_id, version)` for analysis runs and `(analysis_run_id, result_type)` for singleton completed outputs.
- Unique `(assignment_id, ordinal)` to order retries; constraint `retry_of_attempt_id IS NULL` only for ordinal 1.
- Index `challenge_assignments(user_id, status, sequence)`, `attempts(user_id, created_at DESC)`, `analysis_runs(status, updated_at)`, and `skill_evidence(user_id, skill, recorded_at DESC)`.
- Store timestamps in UTC. Store provider payloads only when needed for audit/debug and with a defined retention policy; canonical fields remain queryable columns/JSONB.
