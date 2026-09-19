from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, insert
from sqlalchemy.exc import IntegrityError

from app.models import Assignment, DictionaryEntry, EmailVerificationChallenge, Recording, User, VocabularyItem


def test_recording_retention_deadline_index_matches_active_migration():
    index_names = {index.name for index in Recording.__table__.indexes}
    assert "ix_recordings_retention_deadline" in index_names
    assert "ix_recordings_attempt_id" not in index_names


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
