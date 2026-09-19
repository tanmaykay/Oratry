import pytest
from sqlalchemy import create_engine, insert
from sqlalchemy.exc import IntegrityError

from app.models import Assignment, Recording


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
