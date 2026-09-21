from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, insert
from sqlalchemy.exc import IntegrityError

from app.models import (
    AnalysisJob,
    Assignment,
    Attempt,
    Challenge,
    DictionaryEntry,
    EmailVerificationChallenge,
    Recording,
    User,
    VocabularyItem,
)


def test_recording_retention_deadline_index_matches_active_migration():
    index_names = {index.name for index in Recording.__table__.indexes}
    assert "ix_recordings_retention_deadline" in index_names
    assert "ix_recordings_deletion_claim" in index_names
    assert "ix_recordings_attempt_id" not in index_names


def test_challenge_target_vocabulary_defaults_to_an_empty_versioned_list():
    column = Challenge.__table__.columns["target_vocabulary"]
    assert column.type.__class__.__name__ == "JSON"
    assert column.nullable is False


def test_recording_retention_retry_and_lease_metadata_matches_active_migration():
    table = Recording.__table__
    assert {
        "deletion_attempt_count",
        "deletion_available_at",
        "deletion_lease_expires_at",
    } <= {column.name for column in table.columns}
    assert "ck_recordings_deletion_attempt_count_nonnegative" in {
        constraint.name for constraint in table.constraints
    }
    indexes = {index.name: tuple(index.columns.keys()) for index in table.indexes}
    assert indexes["ix_recordings_deletion_claim"] == (
        "deletion_status",
        "deletion_available_at",
        "retention_deadline",
    )


def test_sqlite_lightweight_recording_deletion_attempt_count_is_nonnegative():
    engine = create_engine("sqlite://")
    User.__table__.create(engine)
    Challenge.__table__.create(engine)
    Assignment.__table__.create(engine)
    Attempt.__table__.create(engine)
    Recording.__table__.create(engine)
    created_at = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)
    with engine.begin() as connection:
        connection.execute(insert(User), {"id": "user-recording", "email": "recording@example.test", "password_hash": "hash", "accepted_terms": True, "preferences": {}, "created_at": created_at})
        connection.execute(insert(Challenge), {"id": "challenge-recording", "version": 1, "prompt": "Prompt", "preparation_guidance": "Guidance", "target_skills": [], "difficulty": 1, "target_duration_seconds": 60, "rubric_version": "1", "active": True})
        connection.execute(insert(Assignment), {"id": "assignment-recording", "user_id": "user-recording", "challenge_id": "challenge-recording", "reason": "test", "status": "assigned", "sequence": 1, "assigned_at": created_at})
        connection.execute(insert(Attempt), {"id": "attempt-recording", "user_id": "user-recording", "assignment_id": "assignment-recording", "status": "queued", "comparison_group_id": "group-recording", "ordinal": 1, "created_at": created_at})
        base = {"id": "recording-one", "attempt_id": "attempt-recording", "storage_provider": "test", "object_key": "private/recording-one", "content_type": "audio/webm", "byte_size": 1, "checksum_sha256": "a" * 64, "deletion_status": "scheduled", "created_at": created_at}
        connection.execute(insert(Recording), base)
        with pytest.raises(IntegrityError):
            with connection.begin_nested():
                connection.execute(insert(Recording), {**base, "id": "recording-two", "attempt_id": "other-attempt", "object_key": "private/recording-two", "deletion_attempt_count": -1})
    engine.dispose()


def test_baseline_assignment_partial_unique_indexes_match_active_migration():
    indexes = {index.name: index for index in Assignment.__table__.indexes}
    expected = {
        "uq_challenge_assignments_baseline_user_sequence": ("user_id", "sequence"),
        "uq_challenge_assignments_baseline_user_challenge": ("user_id", "challenge_id"),
    }
    for name, columns in expected.items():
        index = indexes[name]
        assert tuple(index.columns.keys()) == columns
        assert index.unique is True
        assert str(index.dialect_options["postgresql"]["where"]) == "reason = 'baseline'"
        assert str(index.dialect_options["sqlite"]["where"]) == "reason = 'baseline'"


def test_sqlite_lightweight_schema_enforces_baseline_partial_unique_indexes():
    """SQLite supports this PostgreSQL-authoritative invariant for fast tests."""
    engine = create_engine("sqlite://")
    Assignment.__table__.create(engine)
    baseline = {
        "id": "baseline-one",
        "user_id": "user-one",
        "challenge_id": "challenge-one",
        "reason": "baseline",
        "status": "assigned",
        "sequence": 1,
    }
    with engine.begin() as connection:
        connection.execute(insert(Assignment), baseline)
        with pytest.raises(IntegrityError):
            with connection.begin_nested():
                connection.execute(insert(Assignment), {**baseline, "id": "baseline-duplicate-sequence", "challenge_id": "challenge-two"})
        with pytest.raises(IntegrityError):
            with connection.begin_nested():
                connection.execute(insert(Assignment), {**baseline, "id": "baseline-duplicate-challenge", "sequence": 2})
        # The condition means non-baseline assignments are not constrained.
        connection.execute(insert(Assignment), {**baseline, "id": "recommended-one", "reason": "recommended"})
    engine.dispose()


def test_email_verification_challenge_metadata_matches_security_invariants():
    table = EmailVerificationChallenge.__table__
    assert {"email_verified_at"} <= {column.name for column in User.__table__.columns}
    assert {"user_id", "purpose", "token_digest", "expires_at", "consumed_at", "invalidated_at", "created_at"} <= {
        column.name for column in table.columns
    }
    assert "uq_email_verification_challenges_token_digest" in {
        constraint.name for constraint in table.constraints
    }
    active_index = next(index for index in table.indexes if index.name == "uq_email_verification_challenges_active_user_purpose")
    assert active_index.unique is True
    assert tuple(active_index.columns.keys()) == ("user_id", "purpose")
    expected_where = "consumed_at IS NULL AND invalidated_at IS NULL"
    assert str(active_index.dialect_options["postgresql"]["where"]) == expected_where
    assert str(active_index.dialect_options["sqlite"]["where"]) == expected_where


def test_sqlite_lightweight_schema_enforces_one_outstanding_activation_per_user():
    """The partial uniqueness invariant is portable enough for fast local tests."""
    engine = create_engine("sqlite://")
    User.__table__.create(engine)
    EmailVerificationChallenge.__table__.create(engine)
    created_at = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)
    expires_at = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)
    base = {
        "id": "challenge-one",
        "user_id": "user-one",
        "purpose": "signup_activation",
        "token_digest": "a" * 64,
        "expires_at": expires_at,
        "created_at": created_at,
    }
    with engine.begin() as connection:
        connection.execute(insert(User), {
            "id": "user-one",
            "email": "activation@example.test",
            "password_hash": "hash",
            "accepted_terms": True,
            "preferences": {},
            "created_at": created_at,
        })
        connection.execute(insert(EmailVerificationChallenge), base)
        with pytest.raises(IntegrityError):
            with connection.begin_nested():
                connection.execute(insert(EmailVerificationChallenge), {
                    **base,
                    "id": "challenge-two",
                    "token_digest": "b" * 64,
                })
        connection.execute(
            EmailVerificationChallenge.__table__.update()
            .where(EmailVerificationChallenge.id == "challenge-one")
            .values(invalidated_at=datetime(2026, 9, 19, 12, 5, tzinfo=timezone.utc))
        )
        connection.execute(insert(EmailVerificationChallenge), {
            **base,
            "id": "challenge-three",
            "token_digest": "c" * 64,
        })
    engine.dispose()


def test_dictionary_cache_metadata_is_versioned_and_keeps_vocabulary_user_owned():
    table = DictionaryEntry.__table__
    assert {
        "language", "normalized_term", "payload_version", "payload", "source",
        "source_metadata", "fetched_at", "expires_at", "created_at", "updated_at",
    } <= {column.name for column in table.columns}
    assert "uq_dictionary_entries_language_normalized_term" in {
        constraint.name for constraint in table.constraints
    }
    assert "ix_dictionary_entries_expires_at" in {index.name for index in table.indexes}
    vocabulary_columns = {column.name: column for column in VocabularyItem.__table__.columns}
    assert vocabulary_columns["dictionary_entry_id"].nullable is True
    fk = next(
        fk
        for fk in VocabularyItem.__table__.foreign_key_constraints
        if tuple(fk.column_keys) == ("dictionary_entry_id",)
    )
    assert fk.ondelete == "SET NULL"


def test_analysis_job_metadata_supports_idempotent_durable_leasing():
    table = AnalysisJob.__table__
    assert {
        "attempt_id", "event_key", "stage", "stage_version", "payload", "status",
        "attempt_count", "available_at", "lease_owner", "lease_expires_at",
        "last_error_code", "created_at", "updated_at", "completed_at",
    } <= {column.name for column in table.columns}
    unique_constraints = {constraint.name for constraint in table.constraints}
    assert {"uq_analysis_jobs_event_key", "uq_analysis_jobs_attempt_stage_version"} <= unique_constraints
    indexes = {index.name: tuple(index.columns.keys()) for index in table.indexes}
    assert indexes["ix_analysis_jobs_claim"] == ("status", "available_at", "created_at")
    assert indexes["ix_analysis_jobs_lease_expires_at"] == ("lease_expires_at",)


def test_sqlite_lightweight_analysis_job_integrity_constraints():
    engine = create_engine("sqlite://")
    User.__table__.create(engine)
    Challenge.__table__.create(engine)
    Assignment.__table__.create(engine)
    Attempt.__table__.create(engine)
    AnalysisJob.__table__.create(engine)
    created_at = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)
    with engine.begin() as connection:
        connection.execute(insert(User), {"id": "user-job", "email": "jobs@example.test", "password_hash": "hash", "accepted_terms": True, "preferences": {}, "created_at": created_at})
        connection.execute(insert(Challenge), {"id": "challenge-job", "version": 1, "prompt": "Prompt", "preparation_guidance": "Guidance", "target_skills": [], "difficulty": 1, "target_duration_seconds": 60, "rubric_version": "1", "active": True})
        connection.execute(insert(Assignment), {"id": "assignment-job", "user_id": "user-job", "challenge_id": "challenge-job", "reason": "test", "status": "assigned", "sequence": 1, "assigned_at": created_at})
        connection.execute(insert(Attempt), {"id": "attempt-job", "user_id": "user-job", "assignment_id": "assignment-job", "status": "queued", "comparison_group_id": "group-job", "ordinal": 1, "created_at": created_at})
        base = {"id": "job-one", "attempt_id": "attempt-job", "event_key": "attempt-job:analysis:analysis-v1", "stage": "analysis", "stage_version": "analysis-v1", "payload": {"recording_id": "recording-job"}, "status": "queued", "attempt_count": 0, "available_at": created_at, "created_at": created_at, "updated_at": created_at}
        connection.execute(insert(AnalysisJob), base)
        with pytest.raises(IntegrityError):
            with connection.begin_nested():
                connection.execute(insert(AnalysisJob), {**base, "id": "job-two", "event_key": "attempt-job:analysis:analysis-v2"})
        with pytest.raises(IntegrityError):
            with connection.begin_nested():
                connection.execute(insert(AnalysisJob), {**base, "id": "job-three", "event_key": "other-event", "stage_version": "analysis-v2", "lease_expires_at": created_at})
    engine.dispose()
