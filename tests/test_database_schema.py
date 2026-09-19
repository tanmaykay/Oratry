"""Integration checks for the active Alembic runtime schema on PostgreSQL.

These tests deliberately require a fresh, disposable database. They never use
the legacy ``db/migrations/*.sql`` reference artifacts. Set both
``ORATRY_POSTGRES_TEST_DATABASE_URL`` and ``ORATRY_POSTGRES_TEST=1`` to run
them; the second variable prevents accidental use of a developer database.
"""
from __future__ import annotations

import os
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError


ROOT = Path(__file__).resolve().parents[1]
DATABASE_URL = os.environ.get("ORATRY_POSTGRES_TEST_DATABASE_URL")
ENABLED = os.environ.get("ORATRY_POSTGRES_TEST") == "1"
pytestmark = pytest.mark.skipif(
    not (DATABASE_URL and ENABLED),
    reason="set ORATRY_POSTGRES_TEST=1 and ORATRY_POSTGRES_TEST_DATABASE_URL for PostgreSQL integration tests",
)


def _alembic(*args: str) -> None:
    environment = os.environ.copy()
    environment["DATABASE_URL"] = DATABASE_URL or ""
    subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        check=True,
        cwd=ROOT,
        env=environment,
    )


@pytest.fixture(scope="module", autouse=True)
def migrated_postgres_database():
    assert DATABASE_URL is not None
    assert DATABASE_URL.startswith(("postgresql://", "postgresql+psycopg://"))
    engine = create_engine(DATABASE_URL)
    with engine.connect() as connection:
        assert inspect(connection).get_table_names(schema="public") == [], (
            "PostgreSQL integration database must be empty before migration"
        )
    _alembic("upgrade", "head")
    yield engine
    _alembic("downgrade", "base")
    # Alembic deliberately retains its empty version table at base. This test
    # promises a reusable empty disposable database, so remove that test-owned
    # bookkeeping table explicitly after exercising the downgrade chain.
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE alembic_version"))
    with engine.connect() as connection:
        assert inspect(connection).get_table_names(schema="public") == []
    engine.dispose()


def test_active_alembic_chain_creates_expected_postgresql_schema(migrated_postgres_database) -> None:
    inspector = inspect(migrated_postgres_database)
    expected_tables = {
        "alembic_version", "analysis_results", "analysis_runs", "attempts",
        "challenge_assignments", "challenges", "recordings", "skill_evidence",
        "skill_states", "users", "vocabulary_items", "email_verification_challenges",
        "dictionary_entries",
    }
    assert set(inspector.get_table_names(schema="public")) == expected_tables

    recording_columns = {column["name"]: column for column in inspector.get_columns("recordings")}
    assert {"retention_deadline", "deletion_status", "deleted_at", "deletion_error"} <= recording_columns.keys()
    assert recording_columns["retention_deadline"]["type"].timezone is True
    assert recording_columns["deleted_at"]["type"].timezone is True
    assert recording_columns["deletion_status"]["nullable"] is False

    user_columns = {column["name"]: column for column in inspector.get_columns("users")}
    assert user_columns["preferences"]["type"].__class__.__name__ == "JSON"
    assert user_columns["created_at"]["type"].timezone is True
    assert user_columns["email_verified_at"]["type"].timezone is True
    assert user_columns["email_verified_at"]["nullable"] is True

    verification_columns = {
        column["name"]: column
        for column in inspector.get_columns("email_verification_challenges")
    }
    assert {"purpose", "token_digest", "expires_at", "consumed_at", "invalidated_at", "created_at"} <= verification_columns.keys()
    assert verification_columns["expires_at"]["type"].timezone is True
    assert verification_columns["consumed_at"]["type"].timezone is True
    verification_fks = inspector.get_foreign_keys("email_verification_challenges")
    assert {(foreign_key["constrained_columns"][0], foreign_key["referred_table"]) for foreign_key in verification_fks} == {
        ("user_id", "users")
    }
    verification_indexes = {index["name"]: index for index in inspector.get_indexes("email_verification_challenges")}
    assert verification_indexes["uq_email_verification_challenges_active_user_purpose"]["unique"] is True
    assert verification_indexes["ix_email_verification_challenges_expires_at"]["unique"] is False

    recording_foreign_keys = inspector.get_foreign_keys("recordings")
    assert {(foreign_key["constrained_columns"][0], foreign_key["referred_table"]) for foreign_key in recording_foreign_keys} == {
        ("attempt_id", "attempts")
    }
    attempt_foreign_keys = inspector.get_foreign_keys("attempts")
    assert {(foreign_key["constrained_columns"][0], foreign_key["referred_table"]) for foreign_key in attempt_foreign_keys} == {
        ("assignment_id", "challenge_assignments"), ("retry_of_attempt_id", "attempts"), ("user_id", "users")
    }

    assert any(index["name"] == "ix_users_email" and index["unique"] for index in inspector.get_indexes("users"))
    assert any(index["name"] == "ix_recordings_retention_deadline" for index in inspector.get_indexes("recordings"))
    assignment_indexes = {index["name"]: index for index in inspector.get_indexes("challenge_assignments")}
    assert assignment_indexes["uq_challenge_assignments_baseline_user_sequence"]["unique"] is True
    assert assignment_indexes["uq_challenge_assignments_baseline_user_challenge"]["unique"] is True
    assert {tuple(constraint["column_names"]) for constraint in inspector.get_unique_constraints("recordings")} >= {
        ("attempt_id",), ("object_key",)
    }

    dictionary_columns = {column["name"]: column for column in inspector.get_columns("dictionary_entries")}
    assert {
        "language", "normalized_term", "payload_version", "payload", "source",
        "source_metadata", "fetched_at", "expires_at", "created_at", "updated_at",
    } <= dictionary_columns.keys()
    assert dictionary_columns["fetched_at"]["type"].timezone is True
    assert dictionary_columns["expires_at"]["type"].timezone is True
    dictionary_indexes = {index["name"]: index for index in inspector.get_indexes("dictionary_entries")}
    assert dictionary_indexes["ix_dictionary_entries_expires_at"]["unique"] is False
    assert ("language", "normalized_term") in {
        tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("dictionary_entries")
    }
    vocabulary_foreign_keys = inspector.get_foreign_keys("vocabulary_items")
    assert ("dictionary_entry_id", "dictionary_entries") in {
        (foreign_key["constrained_columns"][0], foreign_key["referred_table"])
        for foreign_key in vocabulary_foreign_keys
    }


def test_json_timestamps_retention_and_uniqueness_behave_on_postgresql(migrated_postgres_database) -> None:
    engine = migrated_postgres_database
    created_at = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)
    retention_deadline = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)
    with engine.begin() as connection:
        connection.execute(text("""
            INSERT INTO users (id, email, password_hash, accepted_terms, preferences, created_at)
            VALUES ('00000000-0000-0000-0000-000000000001', 'postgres@example.test', 'hash', true,
                    CAST(:preferences AS JSON), :created_at)
        """), {"created_at": created_at, "preferences": json.dumps({
            "timezone": "Asia/Kolkata", "notifications": True,
        })})
        connection.execute(text("""
            INSERT INTO challenges (id, version, prompt, preparation_guidance, target_skills, difficulty,
                                    target_duration_seconds, rubric_version, active)
            VALUES ('00000000-0000-0000-0000-000000000002', 1, 'Prompt', 'Guidance', '["fluency"]'::json,
                    1, 120, '1', true)
        """))
        connection.execute(text("""
            INSERT INTO dictionary_entries
                (id, language, normalized_term, payload_version, payload, source, source_metadata,
                 fetched_at, expires_at, created_at, updated_at)
            VALUES ('00000000-0000-0000-0000-000000000017', 'en', 'articulate', 'dictionary-entry-1',
                    CAST(:dictionary_payload AS JSON), 'fixture', CAST(:source_metadata AS JSON),
                    :created_at, :retention_deadline, :created_at, :created_at)
        """), {
            "created_at": created_at,
            "retention_deadline": retention_deadline,
            "dictionary_payload": json.dumps({"definitions": ["express ideas clearly"]}),
            "source_metadata": json.dumps({"license": "fixture"}),
        })
        connection.execute(text("""
            INSERT INTO vocabulary_items (id, user_id, word, practice_status, dictionary_entry_id)
            VALUES ('00000000-0000-0000-0000-000000000018',
                    '00000000-0000-0000-0000-000000000001', 'Articulate', 'new',
                    '00000000-0000-0000-0000-000000000017')
        """))
        dictionary_row = connection.execute(text("""
            SELECT normalized_term, payload, source_metadata, expires_at
            FROM dictionary_entries
            WHERE id = '00000000-0000-0000-0000-000000000017'
        """)).one()
        assert dictionary_row.normalized_term == "articulate"
        assert dictionary_row.payload == {"definitions": ["express ideas clearly"]}
        assert dictionary_row.source_metadata == {"license": "fixture"}
        assert dictionary_row.expires_at == retention_deadline
        with pytest.raises(IntegrityError):
            with connection.begin_nested():
                connection.execute(text("""
                    INSERT INTO dictionary_entries
                        (id, language, normalized_term, payload_version, payload, source, source_metadata,
                         fetched_at, created_at, updated_at)
                    VALUES ('00000000-0000-0000-0000-000000000019', 'en', 'articulate', 'dictionary-entry-1',
                            '{}'::json, 'fixture', '{}'::json, :created_at, :created_at, :created_at)
                """), {"created_at": created_at})
        connection.execute(text("""
            INSERT INTO email_verification_challenges
                (id, user_id, purpose, token_digest, expires_at, created_at)
            VALUES ('00000000-0000-0000-0000-000000000014',
                    '00000000-0000-0000-0000-000000000001', 'signup_activation',
                    repeat('d', 64), :retention_deadline, :created_at)
        """), {"created_at": created_at, "retention_deadline": retention_deadline})
        with pytest.raises(IntegrityError):
            with connection.begin_nested():
                connection.execute(text("""
                    INSERT INTO email_verification_challenges
                        (id, user_id, purpose, token_digest, expires_at, created_at)
                    VALUES ('00000000-0000-0000-0000-000000000015',
                            '00000000-0000-0000-0000-000000000001', 'signup_activation',
                            repeat('e', 64), :retention_deadline, :created_at)
                """), {"created_at": created_at, "retention_deadline": retention_deadline})
        connection.execute(text("""
            UPDATE email_verification_challenges
            SET invalidated_at = :created_at
            WHERE id = '00000000-0000-0000-0000-000000000014'
        """), {"created_at": created_at})
        connection.execute(text("""
            INSERT INTO email_verification_challenges
                (id, user_id, purpose, token_digest, expires_at, created_at)
            VALUES ('00000000-0000-0000-0000-000000000016',
                    '00000000-0000-0000-0000-000000000001', 'signup_activation',
                    repeat('f', 64), :retention_deadline, :created_at)
        """), {"created_at": created_at, "retention_deadline": retention_deadline})
        connection.execute(text("""
            INSERT INTO challenge_assignments (id, user_id, challenge_id, reason, status, sequence, assigned_at)
            VALUES ('00000000-0000-0000-0000-000000000003', '00000000-0000-0000-0000-000000000001',
                    '00000000-0000-0000-0000-000000000002', 'test', 'assigned', 1, :created_at)
        """), {"created_at": created_at})
        connection.execute(text("""
            INSERT INTO attempts (id, user_id, assignment_id, status, comparison_group_id, ordinal, created_at)
            VALUES ('00000000-0000-0000-0000-000000000004', '00000000-0000-0000-0000-000000000001',
                    '00000000-0000-0000-0000-000000000003', 'uploading',
                    '00000000-0000-0000-0000-000000000005', 1, :created_at)
        """), {"created_at": created_at})
        connection.execute(text("""
            INSERT INTO recordings (id, attempt_id, storage_provider, object_key, content_type, byte_size,
                                    checksum_sha256, retention_deadline, deletion_status, created_at)
            VALUES ('00000000-0000-0000-0000-000000000006', '00000000-0000-0000-0000-000000000004',
                    'r2', 'private/test.webm', 'audio/webm', 42, repeat('a', 64), :retention_deadline,
                    'scheduled', :created_at)
        """), {"created_at": created_at, "retention_deadline": retention_deadline})

        row = connection.execute(text("""
                SELECT users.preferences, users.created_at, recordings.retention_deadline,
                       recordings.deletion_status
            FROM users JOIN challenge_assignments ON challenge_assignments.user_id = users.id
            JOIN attempts ON attempts.assignment_id = challenge_assignments.id
            JOIN recordings ON recordings.attempt_id = attempts.id
        """)).one()
        assert row.preferences == {"timezone": "Asia/Kolkata", "notifications": True}
        assert row.created_at == created_at
        assert row.retention_deadline == retention_deadline
        assert row.deletion_status == "scheduled"

        with pytest.raises(IntegrityError):
            with connection.begin_nested():
                connection.execute(text("""
                    INSERT INTO recordings (id, attempt_id, storage_provider, object_key, content_type, byte_size,
                                            checksum_sha256, deletion_status, created_at)
                    VALUES ('00000000-0000-0000-0000-000000000008', '00000000-0000-0000-0000-000000000099',
                            'r2', 'private/orphan.webm', 'audio/webm', 1, repeat('c', 64), 'not_scheduled', :created_at)
                """), {"created_at": created_at})

        connection.execute(text("""
            INSERT INTO challenges (id, version, prompt, preparation_guidance, target_skills, difficulty,
                                    target_duration_seconds, rubric_version, active)
            VALUES ('00000000-0000-0000-0000-000000000009', 1, 'Second prompt', 'Guidance',
                    '["fluency"]'::json, 1, 120, '1', true)
        """))
        connection.execute(text("""
            INSERT INTO challenge_assignments (id, user_id, challenge_id, reason, status, sequence, assigned_at)
            VALUES ('00000000-0000-0000-0000-000000000010', '00000000-0000-0000-0000-000000000001',
                    '00000000-0000-0000-0000-000000000002', 'baseline', 'assigned', 1, :created_at)
        """), {"created_at": created_at})

        # The fixed baseline has one row per sequence and one row per challenge
        # for a user; ordinary assignments remain outside both partial indexes.
        with pytest.raises(IntegrityError):
            with connection.begin_nested():
                connection.execute(text("""
                    INSERT INTO challenge_assignments (id, user_id, challenge_id, reason, status, sequence, assigned_at)
                    VALUES ('00000000-0000-0000-0000-000000000011', '00000000-0000-0000-0000-000000000001',
                            '00000000-0000-0000-0000-000000000009', 'baseline', 'assigned', 1, :created_at)
                """), {"created_at": created_at})
        with pytest.raises(IntegrityError):
            with connection.begin_nested():
                connection.execute(text("""
                    INSERT INTO challenge_assignments (id, user_id, challenge_id, reason, status, sequence, assigned_at)
                    VALUES ('00000000-0000-0000-0000-000000000012', '00000000-0000-0000-0000-000000000001',
                            '00000000-0000-0000-0000-000000000002', 'baseline', 'assigned', 2, :created_at)
                """), {"created_at": created_at})
        connection.execute(text("""
            INSERT INTO challenge_assignments (id, user_id, challenge_id, reason, status, sequence, assigned_at)
            VALUES ('00000000-0000-0000-0000-000000000013', '00000000-0000-0000-0000-000000000001',
                    '00000000-0000-0000-0000-000000000009', 'recommended', 'assigned', 1, :created_at)
        """), {"created_at": created_at})

        with pytest.raises(IntegrityError):
            with connection.begin_nested():
                connection.execute(text("""
                    INSERT INTO recordings (id, attempt_id, storage_provider, object_key, content_type, byte_size,
                                            checksum_sha256, deletion_status, created_at)
                    VALUES ('00000000-0000-0000-0000-000000000007', '00000000-0000-0000-0000-000000000004',
                            'r2', 'private/duplicate.webm', 'audio/webm', 1, repeat('b', 64), 'not_scheduled', :created_at)
                """), {"created_at": created_at})
