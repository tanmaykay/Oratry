from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base
def now(): return datetime.now(timezone.utc)
def uid(): return str(uuid4())

class User(Base):
    __tablename__="users"
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid); email: Mapped[str]=mapped_column(String(320),unique=True,index=True); password_hash: Mapped[str]=mapped_column(String(255)); accepted_terms: Mapped[bool]=mapped_column(Boolean); preferences: Mapped[dict]=mapped_column(JSON,default=dict); email_verified_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True); created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)


class EmailVerificationChallenge(Base):
    """One-time email activation evidence; the plaintext token is never persisted."""

    __tablename__ = "email_verification_challenges"
    __table_args__ = (
        CheckConstraint("purpose = 'signup_activation'", name="ck_email_verification_challenges_purpose"),
        CheckConstraint("length(token_digest) = 64", name="ck_email_verification_challenges_token_digest_length"),
        CheckConstraint("expires_at > created_at", name="ck_email_verification_challenges_expiry_after_creation"),
        UniqueConstraint("token_digest", name="uq_email_verification_challenges_token_digest"),
        Index("ix_email_verification_challenges_user_id", "user_id"),
        Index("ix_email_verification_challenges_expires_at", "expires_at"),
        Index(
            "uq_email_verification_challenges_active_user_purpose",
            "user_id",
            "purpose",
            unique=True,
            postgresql_where=text("consumed_at IS NULL AND invalidated_at IS NULL"),
            sqlite_where=text("consumed_at IS NULL AND invalidated_at IS NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    purpose: Mapped[str] = mapped_column(String(40), nullable=False, default="signup_activation")
    token_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
class Challenge(Base):
    __tablename__="challenges"
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid); version: Mapped[int]=mapped_column(Integer,default=1); prompt: Mapped[str]=mapped_column(Text); preparation_guidance: Mapped[str]=mapped_column(Text); target_skills: Mapped[list]=mapped_column(JSON); target_vocabulary: Mapped[list]=mapped_column(JSON,default=list,server_default=text("'[]'")); difficulty: Mapped[int]=mapped_column(Integer); target_duration_seconds: Mapped[int]=mapped_column(Integer); rubric_version: Mapped[str]=mapped_column(String(32),default="1"); active: Mapped[bool]=mapped_column(Boolean,default=True)
class Assignment(Base):
    __tablename__="challenge_assignments"
    __table_args__ = (
        # The baseline policy assigns each fixed sequence and challenge once.
        # Partial uniqueness leaves ordinary/recommended assignments unconstrained.
        Index(
            "uq_challenge_assignments_baseline_user_sequence",
            "user_id",
            "sequence",
            unique=True,
            postgresql_where=text("reason = 'baseline'"),
            sqlite_where=text("reason = 'baseline'"),
        ),
        Index(
            "uq_challenge_assignments_baseline_user_challenge",
            "user_id",
            "challenge_id",
            unique=True,
            postgresql_where=text("reason = 'baseline'"),
            sqlite_where=text("reason = 'baseline'"),
        ),
    )
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid); user_id: Mapped[str]=mapped_column(ForeignKey("users.id"),index=True); challenge_id: Mapped[str]=mapped_column(ForeignKey("challenges.id")); reason: Mapped[str]=mapped_column(String(80),default="recommended"); status: Mapped[str]=mapped_column(String(30),default="assigned"); sequence: Mapped[int]=mapped_column(Integer,default=1); assigned_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
class Attempt(Base):
    __tablename__="attempts"
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid); user_id: Mapped[str]=mapped_column(ForeignKey("users.id"),index=True); assignment_id: Mapped[str]=mapped_column(ForeignKey("challenge_assignments.id")); status: Mapped[str]=mapped_column(String(30),default="uploading"); comparison_group_id: Mapped[str]=mapped_column(String(36),default=uid); retry_of_attempt_id: Mapped[str|None]=mapped_column(ForeignKey("attempts.id"),nullable=True); ordinal: Mapped[int]=mapped_column(Integer,default=1); object_key: Mapped[str|None]=mapped_column(String(512),nullable=True); checksum: Mapped[str|None]=mapped_column(String(128),nullable=True); duration_seconds: Mapped[float|None]=mapped_column(Float,nullable=True); content_type: Mapped[str|None]=mapped_column(String(100),nullable=True); created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now); sealed_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True); completed_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
class Recording(Base):
    """Raw-media metadata and its independently retryable retention lifecycle."""
    __tablename__ = "recordings"
    __table_args__ = (
        CheckConstraint(
            "deletion_attempt_count >= 0",
            name="ck_recordings_deletion_attempt_count_nonnegative",
        ),
        Index(
            "ix_recordings_deletion_claim",
            "deletion_status",
            "deletion_available_at",
            "retention_deadline",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    attempt_id: Mapped[str] = mapped_column(ForeignKey("attempts.id"), unique=True)
    storage_provider: Mapped[str] = mapped_column(String(40))
    object_key: Mapped[str] = mapped_column(String(512), unique=True)
    content_type: Mapped[str] = mapped_column(String(100))
    byte_size: Mapped[int] = mapped_column(Integer)
    checksum_sha256: Mapped[str] = mapped_column(String(64))
    retention_deadline: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    deletion_status: Mapped[str] = mapped_column(String(30), default="not_scheduled")
    deletion_attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    deletion_available_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deletion_lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deletion_error: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
class AnalysisRun(Base):
    __tablename__="analysis_runs"; __table_args__=(UniqueConstraint("attempt_id","version"),)
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid); attempt_id: Mapped[str]=mapped_column(ForeignKey("attempts.id"),index=True); version: Mapped[int]=mapped_column(Integer,default=1); status: Mapped[str]=mapped_column(String(30),default="queued"); current_stage: Mapped[str]=mapped_column(String(40),default="queued"); failure_code: Mapped[str|None]=mapped_column(String(80),nullable=True); updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now,onupdate=now)


class AnalysisJob(Base):
    """Durable, idempotent work delivery for the analysis pipeline.

    This is deliberately separate from ``AnalysisRun``.  A job is the delivery
    record for one immutable pipeline stage/version request; an analysis run is
    the persisted analysis evidence produced by that work.  Workers lease jobs
    using ``status``, ``available_at`` and ``lease_expires_at`` and must not put
    transcripts, provider credentials, or raw recording bytes in ``payload``.
    """

    __tablename__ = "analysis_jobs"
    __table_args__ = (
        UniqueConstraint("event_key", name="uq_analysis_jobs_event_key"),
        UniqueConstraint(
            "attempt_id", "stage", "stage_version",
            name="uq_analysis_jobs_attempt_stage_version",
        ),
        CheckConstraint("attempt_count >= 0", name="ck_analysis_jobs_attempt_count_nonnegative"),
        CheckConstraint(
            "status IN ('queued', 'leased', 'completed', 'failed')",
            name="ck_analysis_jobs_status",
        ),
        CheckConstraint(
            "lease_expires_at IS NULL OR lease_owner IS NOT NULL",
            name="ck_analysis_jobs_lease_owner_required",
        ),
        CheckConstraint(
            "completed_at IS NULL OR status IN ('completed', 'failed')",
            name="ck_analysis_jobs_terminal_status_for_completion",
        ),
        # Workers find ready work through this composite index.  Expired leases
        # are also indexed independently below for the reclaim branch.
        Index("ix_analysis_jobs_claim", "status", "available_at", "created_at"),
        Index("ix_analysis_jobs_lease_expires_at", "lease_expires_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    attempt_id: Mapped[str] = mapped_column(ForeignKey("attempts.id"), nullable=False, index=True)
    event_key: Mapped[str] = mapped_column(String(128), nullable=False)
    stage: Mapped[str] = mapped_column(String(40), nullable=False)
    stage_version: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now)
    lease_owner: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now, onupdate=now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
class AnalysisResult(Base):
    __tablename__="analysis_results"; __table_args__=(UniqueConstraint("analysis_run_id","result_type"),)
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid); analysis_run_id: Mapped[str]=mapped_column(ForeignKey("analysis_runs.id")); result_type: Mapped[str]=mapped_column(String(40)); payload: Mapped[dict]=mapped_column(JSON)
class SkillState(Base):
    __tablename__="skill_states"; __table_args__=(UniqueConstraint("user_id","skill"),)
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid); user_id: Mapped[str]=mapped_column(ForeignKey("users.id"),index=True); skill: Mapped[str]=mapped_column(String(30)); estimated_level: Mapped[float]=mapped_column(Float); confidence: Mapped[float]=mapped_column(Float); model_version: Mapped[str]=mapped_column(String(30),default="rules-1"); updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
class SkillEvidence(Base):
    """Immutable input for the replaceable SkillState projection."""
    __tablename__="skill_evidence"
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid); user_id: Mapped[str]=mapped_column(ForeignKey("users.id"),index=True); skill: Mapped[str]=mapped_column(String(30),index=True); observed_level: Mapped[float]=mapped_column(Float); confidence: Mapped[float]=mapped_column(Float); evidence_type: Mapped[str]=mapped_column(String(40)); analysis_run_id: Mapped[str|None]=mapped_column(ForeignKey("analysis_runs.id"),nullable=True); recorded_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
class VocabularyItem(Base):
    __tablename__="vocabulary_items"
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid); user_id: Mapped[str]=mapped_column(ForeignKey("users.id"),index=True); word: Mapped[str]=mapped_column(String(200)); practice_status: Mapped[str]=mapped_column(String(30),default="new")
    # A vocabulary item is always user-owned.  Its optional lookup reference is
    # a shared, replaceable cache and must never be treated as learning state.
    dictionary_entry_id: Mapped[str | None] = mapped_column(
        ForeignKey("dictionary_entries.id", ondelete="SET NULL"), nullable=True, index=True
    )


class DictionaryEntry(Base):
    """Provider-cached reference facts, keyed by language and normalized term.

    ``payload`` is deliberately versioned rather than spread across columns so
    providers can supply multiple definitions, pronunciations, examples and
    lexical relations without making vendor response shapes part of the schema.
    """

    __tablename__ = "dictionary_entries"
    __table_args__ = (
        UniqueConstraint("language", "normalized_term", name="uq_dictionary_entries_language_normalized_term"),
        CheckConstraint("length(trim(language)) > 0", name="ck_dictionary_entries_language_not_blank"),
        CheckConstraint("length(trim(normalized_term)) > 0", name="ck_dictionary_entries_normalized_term_not_blank"),
        CheckConstraint("length(trim(source)) > 0", name="ck_dictionary_entries_source_not_blank"),
        CheckConstraint("expires_at IS NULL OR expires_at >= fetched_at", name="ck_dictionary_entries_expiry_after_fetch"),
        Index("ix_dictionary_entries_expires_at", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    language: Mapped[str] = mapped_column(String(16), nullable=False)
    normalized_term: Mapped[str] = mapped_column(String(200), nullable=False)
    payload_version: Mapped[str] = mapped_column(String(32), nullable=False, default="dictionary-entry-1")
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    source_metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now, onupdate=now)
