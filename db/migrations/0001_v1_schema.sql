-- Oratry V1 PostgreSQL schema. Apply with psql -v ON_ERROR_STOP=1 -f this_file.
-- All timestamps are timestamptz (UTC is enforced by application connections).

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;

CREATE TYPE skill_code AS ENUM ('thinking', 'structure', 'language', 'fluency', 'delivery');
CREATE TYPE assignment_status AS ENUM ('assigned', 'in_progress', 'completed', 'cancelled');
CREATE TYPE attempt_status AS ENUM ('uploading', 'queued', 'analyzing', 'completed', 'analysis_failed');
CREATE TYPE analysis_status AS ENUM ('queued', 'running', 'completed', 'failed');
CREATE TYPE recording_kind AS ENUM ('raw', 'normalized');
CREATE TYPE transcript_status AS ENUM ('completed', 'failed');
CREATE TYPE metric_source AS ENUM ('audio', 'transcript', 'derived');
CREATE TYPE evaluation_status AS ENUM ('validated', 'rejected');
CREATE TYPE vocabulary_status AS ENUM ('saved', 'learning', 'mastered', 'archived');

CREATE TABLE users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email citext NOT NULL UNIQUE,
    display_name text NOT NULL CHECK (char_length(btrim(display_name)) BETWEEN 1 AND 120),
    accepted_terms_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz,
    CHECK (position('@' IN email::text) > 1)
);

CREATE TABLE user_preferences (
    user_id uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    preferred_language varchar(16) NOT NULL DEFAULT 'en',
    analysis_consent_at timestamptz,
    timezone text NOT NULL DEFAULT 'UTC',
    notifications_enabled boolean NOT NULL DEFAULT true,
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- Current, replaceable projection. The evidence that produced it remains below.
CREATE TABLE skill_profiles (
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    skill skill_code NOT NULL,
    estimated_level numeric(5,2) NOT NULL CHECK (estimated_level BETWEEN 0 AND 100),
    confidence numeric(4,3) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    model_version text NOT NULL CHECK (char_length(btrim(model_version)) > 0),
    last_evidence_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, skill)
);

CREATE TABLE challenges (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    challenge_family_id uuid NOT NULL,
    version integer NOT NULL CHECK (version > 0),
    title text NOT NULL CHECK (char_length(btrim(title)) BETWEEN 1 AND 200),
    prompt text NOT NULL CHECK (char_length(btrim(prompt)) > 0),
    preparation_guidance text NOT NULL DEFAULT '',
    target_skills skill_code[] NOT NULL CHECK (cardinality(target_skills) > 0),
    difficulty smallint NOT NULL CHECK (difficulty BETWEEN 1 AND 5),
    target_duration_seconds integer NOT NULL CHECK (target_duration_seconds BETWEEN 15 AND 1800),
    rubric_version text NOT NULL CHECK (char_length(btrim(rubric_version)) > 0),
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (challenge_family_id, version)
);

CREATE TABLE challenge_vocabulary (
    challenge_id uuid NOT NULL REFERENCES challenges(id) ON DELETE CASCADE,
    vocabulary_id uuid NOT NULL,
    is_required boolean NOT NULL DEFAULT false,
    PRIMARY KEY (challenge_id, vocabulary_id)
);

CREATE TABLE sessions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    started_at timestamptz NOT NULL DEFAULT now(),
    ended_at timestamptz,
    client_platform text,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (ended_at IS NULL OR ended_at >= started_at)
);

CREATE TABLE challenge_assignments (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    challenge_id uuid NOT NULL REFERENCES challenges(id) ON DELETE RESTRICT,
    reason text NOT NULL CHECK (char_length(btrim(reason)) > 0),
    sequence integer NOT NULL CHECK (sequence > 0),
    status assignment_status NOT NULL DEFAULT 'assigned',
    assigned_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    UNIQUE (user_id, sequence),
    CHECK ((status = 'completed') = (completed_at IS NOT NULL))
);

CREATE TABLE challenge_attempts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    assignment_id uuid NOT NULL REFERENCES challenge_assignments(id) ON DELETE RESTRICT,
    session_id uuid REFERENCES sessions(id) ON DELETE SET NULL,
    comparison_group_id uuid NOT NULL,
    retry_of_attempt_id uuid REFERENCES challenge_attempts(id) ON DELETE RESTRICT,
    ordinal integer NOT NULL CHECK (ordinal > 0),
    status attempt_status NOT NULL DEFAULT 'uploading',
    created_at timestamptz NOT NULL DEFAULT now(),
    sealed_at timestamptz,
    completed_at timestamptz,
    failure_code text,
    UNIQUE (assignment_id, ordinal),
    CHECK ((ordinal = 1) = (retry_of_attempt_id IS NULL)),
    CHECK (completed_at IS NULL OR status = 'completed'),
    CHECK (sealed_at IS NULL OR sealed_at >= created_at)
);

CREATE TABLE recordings (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    attempt_id uuid NOT NULL REFERENCES challenge_attempts(id) ON DELETE CASCADE,
    kind recording_kind NOT NULL DEFAULT 'raw',
    storage_provider text NOT NULL CHECK (char_length(btrim(storage_provider)) > 0),
    object_key text NOT NULL CHECK (char_length(btrim(object_key)) > 0),
    checksum_sha256 char(64) NOT NULL CHECK (checksum_sha256 ~ '^[0-9A-Fa-f]{64}$'),
    content_type text NOT NULL CHECK (char_length(btrim(content_type)) > 0),
    byte_size bigint NOT NULL CHECK (byte_size > 0),
    duration_ms integer NOT NULL CHECK (duration_ms > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (attempt_id, kind),
    UNIQUE (storage_provider, object_key)
);

CREATE TABLE analysis_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    attempt_id uuid NOT NULL REFERENCES challenge_attempts(id) ON DELETE CASCADE,
    version integer NOT NULL CHECK (version > 0),
    status analysis_status NOT NULL DEFAULT 'queued',
    current_stage text NOT NULL DEFAULT 'queued',
    started_at timestamptz,
    completed_at timestamptz,
    failure_code text,
    updated_at timestamptz NOT NULL DEFAULT now(),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (attempt_id, version),
    CHECK (completed_at IS NULL OR status IN ('completed', 'failed'))
);

CREATE TABLE transcripts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_run_id uuid NOT NULL UNIQUE REFERENCES analysis_runs(id) ON DELETE CASCADE,
    provider text NOT NULL,
    model_version text NOT NULL,
    language_code varchar(16),
    text text NOT NULL DEFAULT '',
    confidence numeric(4,3) CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
    status transcript_status NOT NULL DEFAULT 'completed',
    provider_payload jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE transcript_words (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    transcript_id uuid NOT NULL REFERENCES transcripts(id) ON DELETE CASCADE,
    position integer NOT NULL CHECK (position >= 0),
    word text NOT NULL CHECK (char_length(btrim(word)) > 0),
    start_ms integer NOT NULL CHECK (start_ms >= 0),
    end_ms integer NOT NULL CHECK (end_ms >= start_ms),
    confidence numeric(4,3) CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
    UNIQUE (transcript_id, position)
);

CREATE TABLE speech_metrics (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_run_id uuid NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
    metric_name text NOT NULL CHECK (char_length(btrim(metric_name)) > 0),
    value numeric,
    unit text NOT NULL CHECK (char_length(btrim(unit)) > 0),
    source metric_source NOT NULL,
    calculation_version text NOT NULL,
    confidence numeric(4,3) CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
    is_available boolean NOT NULL DEFAULT true,
    provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (analysis_run_id, metric_name, calculation_version),
    CHECK ((is_available AND value IS NOT NULL) OR (NOT is_available AND value IS NULL))
);

CREATE TABLE evaluations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_run_id uuid NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
    rubric_version text NOT NULL,
    prompt_version text NOT NULL,
    model_provider text NOT NULL,
    model_name text NOT NULL,
    model_version text NOT NULL,
    status evaluation_status NOT NULL DEFAULT 'validated',
    confidence numeric(4,3) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    dimension_observations jsonb NOT NULL,
    evidence_spans jsonb NOT NULL DEFAULT '[]'::jsonb,
    provider_payload jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (analysis_run_id, rubric_version, prompt_version, model_provider, model_version)
);

CREATE TABLE feedback (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    evaluation_id uuid NOT NULL REFERENCES evaluations(id) ON DELETE CASCADE,
    focus_skill skill_code NOT NULL,
    observation text NOT NULL CHECK (char_length(btrim(observation)) > 0),
    action text NOT NULL CHECK (char_length(btrim(action)) > 0),
    success_criterion text NOT NULL CHECK (char_length(btrim(success_criterion)) > 0),
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX feedback_one_active_per_evaluation ON feedback (evaluation_id) WHERE is_active;

CREATE TABLE vocabulary (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    term text NOT NULL CHECK (char_length(btrim(term)) BETWEEN 1 AND 160),
    normalized_term text NOT NULL CHECK (char_length(btrim(normalized_term)) BETWEEN 1 AND 160),
    language_code varchar(16) NOT NULL DEFAULT 'en',
    definition text,
    example_usage text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (language_code, normalized_term)
);

ALTER TABLE challenge_vocabulary
    ADD CONSTRAINT challenge_vocabulary_vocabulary_id_fkey
    FOREIGN KEY (vocabulary_id) REFERENCES vocabulary(id) ON DELETE RESTRICT;

CREATE TABLE user_vocabulary (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    vocabulary_id uuid NOT NULL REFERENCES vocabulary(id) ON DELETE RESTRICT,
    status vocabulary_status NOT NULL DEFAULT 'saved',
    current_proficiency numeric(5,2) NOT NULL DEFAULT 0 CHECK (current_proficiency BETWEEN 0 AND 100),
    last_practiced_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, vocabulary_id)
);

CREATE TABLE user_vocabulary_observations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_vocabulary_id uuid NOT NULL REFERENCES user_vocabulary(id) ON DELETE CASCADE,
    proficiency numeric(5,2) NOT NULL CHECK (proficiency BETWEEN 0 AND 100),
    confidence numeric(4,3) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    source text NOT NULL CHECK (char_length(btrim(source)) > 0),
    attempt_id uuid REFERENCES challenge_attempts(id) ON DELETE SET NULL,
    observed_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE skill_observations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    skill skill_code NOT NULL,
    observed_level numeric(5,2) NOT NULL CHECK (observed_level BETWEEN 0 AND 100),
    confidence numeric(4,3) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    evidence_type text NOT NULL CHECK (char_length(btrim(evidence_type)) > 0),
    analysis_run_id uuid REFERENCES analysis_runs(id) ON DELETE SET NULL,
    evaluation_id uuid REFERENCES evaluations(id) ON DELETE SET NULL,
    model_version text NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    CHECK (analysis_run_id IS NOT NULL OR evaluation_id IS NOT NULL)
);

CREATE TABLE events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid REFERENCES users(id) ON DELETE SET NULL,
    aggregate_type text NOT NULL,
    aggregate_id uuid NOT NULL,
    event_type text NOT NULL,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX challenge_assignments_user_status_sequence_idx ON challenge_assignments (user_id, status, sequence);
CREATE INDEX challenge_attempts_user_created_at_idx ON challenge_attempts (user_id, created_at DESC);
CREATE INDEX challenge_attempts_assignment_idx ON challenge_attempts (assignment_id, ordinal);
CREATE INDEX sessions_user_started_at_idx ON sessions (user_id, started_at DESC);
CREATE INDEX analysis_runs_status_updated_at_idx ON analysis_runs (status, updated_at);
CREATE INDEX transcript_words_transcript_timing_idx ON transcript_words (transcript_id, start_ms);
CREATE INDEX speech_metrics_run_metric_idx ON speech_metrics (analysis_run_id, metric_name);
CREATE INDEX evaluations_analysis_run_idx ON evaluations (analysis_run_id);
CREATE INDEX skill_observations_user_skill_recorded_idx ON skill_observations (user_id, skill, recorded_at DESC);
CREATE INDEX user_vocabulary_observations_item_observed_idx ON user_vocabulary_observations (user_vocabulary_id, observed_at DESC);
CREATE INDEX events_aggregate_occurred_idx ON events (aggregate_type, aggregate_id, occurred_at DESC);
CREATE INDEX events_user_occurred_idx ON events (user_id, occurred_at DESC) WHERE user_id IS NOT NULL;

COMMIT;
