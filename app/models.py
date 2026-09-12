from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base
def now(): return datetime.now(timezone.utc)
def uid(): return str(uuid4())

class User(Base):
    __tablename__="users"
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid); email: Mapped[str]=mapped_column(String(320),unique=True,index=True); password_hash: Mapped[str]=mapped_column(String(255)); accepted_terms: Mapped[bool]=mapped_column(Boolean); preferences: Mapped[dict]=mapped_column(JSON,default=dict); created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
class Challenge(Base):
    __tablename__="challenges"
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid); version: Mapped[int]=mapped_column(Integer,default=1); prompt: Mapped[str]=mapped_column(Text); preparation_guidance: Mapped[str]=mapped_column(Text); target_skills: Mapped[list]=mapped_column(JSON); difficulty: Mapped[int]=mapped_column(Integer); target_duration_seconds: Mapped[int]=mapped_column(Integer); rubric_version: Mapped[str]=mapped_column(String(32),default="1"); active: Mapped[bool]=mapped_column(Boolean,default=True)
class Assignment(Base):
    __tablename__="challenge_assignments"
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid); user_id: Mapped[str]=mapped_column(ForeignKey("users.id"),index=True); challenge_id: Mapped[str]=mapped_column(ForeignKey("challenges.id")); reason: Mapped[str]=mapped_column(String(80),default="recommended"); status: Mapped[str]=mapped_column(String(30),default="assigned"); sequence: Mapped[int]=mapped_column(Integer,default=1); assigned_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
class Attempt(Base):
    __tablename__="attempts"
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid); user_id: Mapped[str]=mapped_column(ForeignKey("users.id"),index=True); assignment_id: Mapped[str]=mapped_column(ForeignKey("challenge_assignments.id")); status: Mapped[str]=mapped_column(String(30),default="uploading"); comparison_group_id: Mapped[str]=mapped_column(String(36),default=uid); retry_of_attempt_id: Mapped[str|None]=mapped_column(ForeignKey("attempts.id"),nullable=True); ordinal: Mapped[int]=mapped_column(Integer,default=1); object_key: Mapped[str|None]=mapped_column(String(512),nullable=True); checksum: Mapped[str|None]=mapped_column(String(128),nullable=True); duration_seconds: Mapped[float|None]=mapped_column(Float,nullable=True); content_type: Mapped[str|None]=mapped_column(String(100),nullable=True); created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now); sealed_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True); completed_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
class AnalysisRun(Base):
    __tablename__="analysis_runs"; __table_args__=(UniqueConstraint("attempt_id","version"),)
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid); attempt_id: Mapped[str]=mapped_column(ForeignKey("attempts.id"),index=True); version: Mapped[int]=mapped_column(Integer,default=1); status: Mapped[str]=mapped_column(String(30),default="queued"); current_stage: Mapped[str]=mapped_column(String(40),default="queued"); failure_code: Mapped[str|None]=mapped_column(String(80),nullable=True); updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now,onupdate=now)
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
