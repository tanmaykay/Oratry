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
        "skill_states", "users", "vocabulary_items",
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
