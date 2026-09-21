"""Durable server-side raw-recording retention worker."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from time import sleep
from uuid import uuid4

from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Recording
from app.storage import ObjectStorageProvider

MAX_DELETE_ATTEMPTS = 5
DELETE_LEASE_SECONDS = 120
DELETE_RETRY_BASE_SECONDS = 60
DELETE_RETRY_MAX_SECONDS = 60 * 60


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _failure_code(error: Exception) -> tuple[str, bool]:
    """Normalize provider failures without storing provider error text."""
    if isinstance(error, (ConnectionError, TimeoutError)):
        return "storage_unavailable", True
    if getattr(error, "retryable", False):
        return "storage_retryable", True
    return "storage_delete_failed", False


def _retry_delay_seconds(attempt_count: int) -> int:
    return min(DELETE_RETRY_BASE_SECONDS * (2 ** max(0, attempt_count - 1)), DELETE_RETRY_MAX_SECONDS)


def _lease_expiry(now: datetime) -> datetime:
    """Use the persisted expiry as a fencing value until a lease-token column exists.

    PostgreSQL preserves microseconds. The nonce avoids two reclaimers created
    in the same clock tick receiving the same fencing value.
    """
    return now + timedelta(seconds=DELETE_LEASE_SECONDS, microseconds=(uuid4().int % 1_000_000) + 1)


@dataclass(frozen=True)
class ClaimedDeletion:
    recording_id: str
    storage_provider: str
    object_key: str
    lease_expires_at: datetime


class RecordingRetentionWorker:
    """Claim one due private recording and delete it through the storage port."""

    def __init__(self, db: Session, storage: ObjectStorageProvider, *, now=_utcnow) -> None:
        self.db, self.storage, self.now = db, storage, now

    def run_once(self) -> bool:
        claim = self._claim_due_recording()
        if claim is None:
            return False
        if claim.storage_provider != self.storage.provider_name:
            self._fail(claim, "storage_provider_mismatch", retryable=False, attempt_count=0)
            return True
        # Increment once, directly before one external delete. A stale lease
        # cannot increment a newer worker's counter.
        attempt_count = self._begin_external_delete(claim)
        if attempt_count is None:
            return True
        try:
            self.storage.delete(claim.object_key)
        except Exception as error:  # provider details never leave this boundary
            code, retryable = _failure_code(error)
            self._fail(claim, code, retryable=retryable, attempt_count=attempt_count)
        else:
            self._mark_deleted(claim)
        return True

    def _claim_due_recording(self) -> ClaimedDeletion | None:
        now = self.now()
        # Null availability handles rows scheduled before the retry migration.
        ready_scheduled = and_(
            Recording.deletion_status == "scheduled",
            or_(
                and_(Recording.deletion_available_at.is_not(None), Recording.deletion_available_at <= now),
                and_(Recording.deletion_available_at.is_(None), Recording.retention_deadline <= now),
            ),
        )
        expired_lease = and_(
            Recording.deletion_status == "deleting",
            Recording.deletion_lease_expires_at.is_not(None),
            Recording.deletion_lease_expires_at <= now,
        )
        recording = self.db.scalar(
            select(Recording).where(or_(ready_scheduled, expired_lease))
            .order_by(Recording.deletion_available_at, Recording.retention_deadline, Recording.id)
            .with_for_update(skip_locked=True).limit(1)
        )
        if recording is None:
            return None
        lease_expires_at = _lease_expiry(now)
        recording.deletion_status = "deleting"
        recording.deletion_available_at = None
        recording.deletion_lease_expires_at = lease_expires_at
        recording.deletion_error = None
        self.db.commit()
        return ClaimedDeletion(recording.id, recording.storage_provider, recording.object_key, lease_expires_at)

    def _begin_external_delete(self, claim: ClaimedDeletion) -> int | None:
        result = self.db.execute(update(Recording).where(
            Recording.id == claim.recording_id,
            Recording.deletion_status == "deleting",
            Recording.deletion_lease_expires_at == claim.lease_expires_at,
        ).values(deletion_attempt_count=Recording.deletion_attempt_count + 1).execution_options(synchronize_session=False))
        if result.rowcount != 1:
            self.db.rollback()
            return None
        self.db.commit()
        return self.db.scalar(select(Recording.deletion_attempt_count).where(Recording.id == claim.recording_id))

    def _mark_deleted(self, claim: ClaimedDeletion) -> None:
        self._finish(claim, deletion_status="deleted", deleted_at=self.now(), deletion_error=None,
                     deletion_available_at=None, deletion_lease_expires_at=None)

    def _fail(self, claim: ClaimedDeletion, code: str, *, retryable: bool, attempt_count: int) -> None:
        is_retry = retryable and attempt_count < MAX_DELETE_ATTEMPTS
        self._finish(
            claim,
            deletion_status="scheduled" if is_retry else "delete_failed",
            deletion_error=code,
            deletion_available_at=(self.now() + timedelta(seconds=_retry_delay_seconds(attempt_count))) if is_retry else None,
            deletion_lease_expires_at=None,
        )

    def _finish(self, claim: ClaimedDeletion, **values) -> None:
        result = self.db.execute(update(Recording).where(
            Recording.id == claim.recording_id,
            Recording.deletion_status == "deleting",
            Recording.deletion_lease_expires_at == claim.lease_expires_at,
        ).values(**values).execution_options(synchronize_session=False))
        if result.rowcount:
            self.db.commit()
        else:
            self.db.rollback()


def main() -> int:
    parser = argparse.ArgumentParser(description="Delete expired private Oratry recordings")
    parser.add_argument("--once", action="store_true", help="process at most one due recording and exit")
    parser.add_argument("--poll-seconds", type=int, default=60, help="continuous-mode polling interval")
    args = parser.parse_args()
    if args.poll_seconds <= 0:
        parser.error("--poll-seconds must be greater than zero")
    from app.main import get_object_storage
    while True:
        with SessionLocal() as db:
            processed = RecordingRetentionWorker(db, get_object_storage()).run_once()
        if args.once:
            return 0
        if not processed:
            sleep(args.poll_seconds)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
