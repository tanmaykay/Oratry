from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Assignment, Attempt, Challenge, Recording, User
from app.retention_worker import (DELETE_LEASE_SECONDS, DELETE_RETRY_BASE_SECONDS,
                                  RecordingRetentionWorker)


class FakePrivateStorage:
    provider_name = "fake-private"

    def __init__(self, failures: list[Exception] | None = None):
        self.failures = failures or []
        self.deleted: list[str] = []

    def delete(self, object_key: str) -> None:
        self.deleted.append(object_key)
        if self.failures:
            raise self.failures.pop(0)


def _recording(db, *, deadline, status="scheduled", provider="fake-private", available_at=None, lease_expires_at=None):
    user = User(email=f"retention-{deadline.timestamp()}@example.test", password_hash="x", accepted_terms=True)
    challenge = Challenge(prompt="Prompt", preparation_guidance="Guide", target_skills=["clarity"], difficulty=1, target_duration_seconds=60)
    db.add_all([user, challenge]); db.flush()
    assignment = Assignment(user_id=user.id, challenge_id=challenge.id)
    db.add(assignment); db.flush()
    attempt = Attempt(user_id=user.id, assignment_id=assignment.id, object_key=f"private/{user.id}")
    db.add(attempt); db.flush()
    recording = Recording(attempt_id=attempt.id, storage_provider=provider, object_key=attempt.object_key,
                          content_type="audio/webm", byte_size=1, checksum_sha256="a" * 64,
                          retention_deadline=deadline, deletion_status=status,
                          deletion_available_at=available_at, deletion_lease_expires_at=lease_expires_at)
    db.add(recording); db.commit()
    return recording


def _database(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'retention.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False)


def test_due_private_recording_is_deleted_and_audited(tmp_path):
    now = datetime(2026, 9, 20, tzinfo=timezone.utc)
    Local = _database(tmp_path)
    with Local() as db:
        due = _recording(db, deadline=now - timedelta(seconds=1))
        future = _recording(db, deadline=now + timedelta(hours=1))
        storage = FakePrivateStorage()
        worker = RecordingRetentionWorker(db, storage, now=lambda: now)

        assert worker.run_once() is True
        db.expire_all()
        deleted = db.get(Recording, due.id)
        assert deleted.deletion_status == "deleted"
        # SQLite does not round-trip timezone offsets despite timezone=True;
        # PostgreSQL does. Compare the instant in the lightweight test.
        assert deleted.deleted_at.replace(tzinfo=timezone.utc) == now and deleted.deletion_error is None
        assert deleted.deletion_attempt_count == 1
        assert deleted.deletion_available_at is None and deleted.deletion_lease_expires_at is None
        assert db.get(Recording, future.id).deletion_status == "scheduled"
        assert storage.deleted == [due.object_key]
        assert worker.run_once() is False


def test_transient_delete_failure_persists_backoff_for_a_later_worker(tmp_path):
    now = datetime(2026, 9, 20, tzinfo=timezone.utc)
    Local = _database(tmp_path)
    with Local() as db:
        due = _recording(db, deadline=now - timedelta(seconds=1))
        storage = FakePrivateStorage([TimeoutError()])
        worker = RecordingRetentionWorker(db, storage, now=lambda: now)

        assert worker.run_once() is True
        db.expire_all()
        pending = db.get(Recording, due.id)
        assert pending.deletion_status == "scheduled"
        assert pending.deletion_attempt_count == 1
        assert pending.deletion_available_at.replace(tzinfo=timezone.utc) == now + timedelta(seconds=DELETE_RETRY_BASE_SECONDS)
        assert pending.deletion_lease_expires_at is None
        assert worker.run_once() is False
        assert RecordingRetentionWorker(db, storage, now=lambda: now + timedelta(seconds=DELETE_RETRY_BASE_SECONDS)).run_once()
        db.expire_all()
        assert db.get(Recording, due.id).deletion_status == "deleted"
        assert db.get(Recording, due.id).deletion_attempt_count == 2


def test_terminal_failure_records_safe_code_without_provider_detail(tmp_path):
    now = datetime(2026, 9, 20, tzinfo=timezone.utc)
    Local = _database(tmp_path)
    with Local() as db:
        due = _recording(db, deadline=now - timedelta(seconds=1))
        worker = RecordingRetentionWorker(db, FakePrivateStorage([ValueError("private/object-key")]), now=lambda: now)

        assert worker.run_once() is True
        db.expire_all()
        failed = db.get(Recording, due.id)
        assert failed.deletion_status == "delete_failed"
        assert failed.deletion_error == "storage_delete_failed"
        assert failed.deletion_attempt_count == 1
        assert "private" not in failed.deletion_error


def test_provider_mismatch_never_deletes_the_object(tmp_path):
    now = datetime(2026, 9, 20, tzinfo=timezone.utc)
    Local = _database(tmp_path)
    with Local() as db:
        due = _recording(db, deadline=now - timedelta(seconds=1), provider="another-private-provider")
        storage = FakePrivateStorage()

        assert RecordingRetentionWorker(db, storage, now=lambda: now).run_once() is True
        db.expire_all()
        assert db.get(Recording, due.id).deletion_status == "delete_failed"
        assert db.get(Recording, due.id).deletion_error == "storage_provider_mismatch"
        assert storage.deleted == []


def test_expired_lease_is_reclaimed_and_only_new_lease_can_delete(tmp_path):
    now = datetime(2026, 9, 20, tzinfo=timezone.utc)
    Local = _database(tmp_path)
    with Local() as db:
        due = _recording(db, deadline=now - timedelta(hours=1), status="deleting",
                         lease_expires_at=now - timedelta(seconds=1))
        storage = FakePrivateStorage()
        assert RecordingRetentionWorker(db, storage, now=lambda: now).run_once()
        db.expire_all()
        row = db.get(Recording, due.id)
        assert row.deletion_status == "deleted"
        assert row.deletion_attempt_count == 1
        assert storage.deleted == [due.object_key]


def test_stale_claim_cannot_increment_or_finish_reclaimed_lease(tmp_path):
    now = datetime(2026, 9, 20, tzinfo=timezone.utc)
    Local = _database(tmp_path)
    with Local() as db:
        due = _recording(db, deadline=now - timedelta(hours=1))
        worker = RecordingRetentionWorker(db, FakePrivateStorage(), now=lambda: now)
        stale = worker._claim_due_recording()
        assert stale is not None
        db.get(Recording, due.id).deletion_lease_expires_at = now - timedelta(seconds=1)
        db.commit()
        fresh_worker = RecordingRetentionWorker(db, FakePrivateStorage(), now=lambda: now)
        fresh = fresh_worker._claim_due_recording()
        assert fresh is not None and fresh.lease_expires_at != stale.lease_expires_at
        assert worker._begin_external_delete(stale) is None
        assert fresh_worker._begin_external_delete(fresh) == 1
