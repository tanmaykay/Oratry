from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.analysis_worker import (CostEstimator, DurableAnalysisWorker,
                                 _failure_classification, claim_next_job,
                                 build_worker, enqueue_analysis, requeue_failed_job,
                                 renew_lease)
from oratry.evaluation import EvaluationProviderError
from oratry.speech.providers import SpeechToTextProviderError
from app.db import Base
from app.models import (AnalysisJob, AnalysisResult, AnalysisRun, Assignment, Attempt,
                        Challenge, Recording, User, VocabularyItem, VocabularyObservation)
from oratry.speech.models import Transcript, TranscriptSegment, TranscriptionUsage, WordTimestamp


class FakeStorage:
    provider_name = "fake-private"
    def download(self, object_key: str, destination: Path) -> None:
        destination.write_bytes(b"not real audio")


class FakeStt:
    provider_name = "fake-stt"
    def transcribe(self, path: Path, *, language_hint=None):
        words = (WordTimestamp("Clear", "clear", 0, .3, .99), WordTimestamp("thinking", "thinking", .31, .7, .99))
        return Transcript("Clear thinking", "en", (TranscriptSegment("Clear thinking", 0, .7, words),),
                          "deepgram", "nova-3", "test", .99, TranscriptionUsage("req-1", .7))


class FakeEvaluator:
    def evaluate(self, input_):
        dimensions = {name: {"score": 70, "confidence": .8, "observation": "Observed evidence.",
                    "interpretation": "Coaching interpretation.",
                    "evidence": [{"source": "transcript", "quote": "Clear", "start_char": 0, "end_char": 5}]}
                    for name in ("structure", "clarity", "fluency", "language", "delivery")}
        evaluation = {"overall_score": 70, "overall_confidence": .8, "dimensions": dimensions,
                      "primary_weakness": {"dimension": "clarity", "observation": "Be specific.", "explanation": "Evidence is brief.",
                                           "evidence": [{"source": "transcript", "quote": "Clear", "start_char": 0, "end_char": 5}]},
                      "recommendation": {"action": "Add one concrete example.", "success_criterion": "State one example."},
                      "next_exercise": {"title": "Example", "instructions": "Explain one example.", "duration_seconds": 60}, "limitations": []}
        return SimpleNamespace(evaluation=evaluation, provider="openai", model="fake", schema_version="1", evaluation_version="1",
            rubric_version="1", prompt_version="1", prompt_sha256="a" * 64,
            usage=SimpleNamespace(input_tokens=20, output_tokens=30, latency_ms=4, request_id="llm-1"))


class CountingStt(FakeStt):
    def __init__(self): self.calls = 0
    def transcribe(self, *args, **kwargs):
        self.calls += 1
        return super().transcribe(*args, **kwargs)


class FailsOnceEvaluator(FakeEvaluator):
    def __init__(self): self.calls = 0
    def evaluate(self, input_):
        self.calls += 1
        if self.calls == 1:
            raise EvaluationProviderError("evaluation provider request failed")
        return super().evaluate(input_)


def test_durable_worker_persists_versioned_evidence_and_schedules_retention(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'analysis.db'}")
    Base.metadata.create_all(engine)
    Local = sessionmaker(bind=engine, autoflush=False)
    with Local() as db:
        user = User(email="worker@example.test", password_hash="x", accepted_terms=True)
        challenge = Challenge(prompt="Explain a decision.", preparation_guidance="Use an example.", target_skills=["clarity"], target_vocabulary=["clear"], difficulty=1, target_duration_seconds=60)
        db.add_all([user, challenge]); db.flush()
        assignment = Assignment(user_id=user.id, challenge_id=challenge.id)
        db.add(assignment); db.flush()
        attempt = Attempt(user_id=user.id, assignment_id=assignment.id, status="queued", object_key="private/test/raw", duration_seconds=1, content_type="audio/webm")
        db.add(attempt); db.flush()
        db.add(Recording(attempt_id=attempt.id, storage_provider="fake-private", object_key=attempt.object_key, content_type="audio/webm", byte_size=1, checksum_sha256="a" * 64))
        db.add(AnalysisRun(attempt_id=attempt.id, version=1, status="queued", current_stage="queued"))
        enqueue_analysis(db, attempt.id)
        db.commit()
        worker = DurableAnalysisWorker(
            db, FakeStorage(), FakeStt(), FakeEvaluator(), retention_hours=24,
            costs=CostEstimator(version="test-price-v1", stt_per_minute=.12,
                                llm_input_per_million=1, llm_output_per_million=2),
        )
        assert worker.run_once("test-worker")
        db.expire_all()
        assert db.get(Attempt, attempt.id).status == "completed"
        assert db.scalar(select(AnalysisJob)).status == "completed"
        recording = db.scalar(select(Recording))
        assert recording.deletion_status == "scheduled" and recording.retention_deadline is not None
        assert recording.deletion_available_at == recording.retention_deadline
        types = {row.result_type for row in db.scalars(select(AnalysisResult))}
        assert {"transcript", "metrics", "evaluation", "scorecard", "feedback", "provider_usage"} <= types
        # Provider accounting records metadata only, never request payloads/audio bytes.
        usage = db.scalar(select(AnalysisResult).where(AnalysisResult.result_type == "provider_usage")).payload
        assert usage["stt"]["audioDurationSeconds"] == .7
        assert usage["llm"]["inputTokens"] == 20
        assert usage["stt"]["costEstimateVersion"] == "test-price-v1"
        assert usage["stt"]["estimatedCostUsd"] == .0014
        assert usage["llm"]["estimatedCostUsd"] == .00008
        scorecard = db.scalar(select(AnalysisResult).where(AnalysisResult.result_type == "scorecard")).payload
        assert scorecard["dimensions"]["target_vocabulary"]["input"] == {"target_count": 1, "used_count": 1}
        item = db.scalar(select(VocabularyItem).where(VocabularyItem.user_id == user.id))
        observation = db.scalar(select(VocabularyObservation).where(VocabularyObservation.analysis_run_id == db.scalar(select(AnalysisRun)).id))
        assert item.word == "clear" and item.practice_status == "practicing"
        assert observation.vocabulary_item_id == item.id and observation.normalized_word == "clear"
        # SQLite lightweight tests do not enable foreign-key enforcement. The
        # real PostgreSQL schema suite asserts the ON DELETE SET NULL contract.
        db.delete(item); db.commit()


def test_lease_fencing_and_operator_requeue_are_conditional(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'leases.db'}")
    Base.metadata.create_all(engine)
    Local = sessionmaker(bind=engine, autoflush=False)
    with Local() as db:
        user = User(email="lease@example.test", password_hash="x", accepted_terms=True)
        challenge = Challenge(prompt="Prompt", preparation_guidance="Guide", target_skills=[], difficulty=1, target_duration_seconds=60)
        db.add_all([user, challenge]); db.flush()
        assignment = Assignment(user_id=user.id, challenge_id=challenge.id); db.add(assignment); db.flush()
        attempt = Attempt(user_id=user.id, assignment_id=assignment.id, comparison_group_id="group")
        db.add(attempt); db.flush(); job = enqueue_analysis(db, attempt.id); db.commit()
        claimed = claim_next_job(db, "owner-one")
        assert claimed and renew_lease(db, claimed.id, "owner-one", lease_seconds=60)
        assert not renew_lease(db, claimed.id, "owner-two", lease_seconds=60)
        db.rollback()
        claimed.status, claimed.lease_owner, claimed.lease_expires_at = "failed", None, None
        db.commit()
        with pytest.raises(PermissionError):
            requeue_failed_job(db, claimed.id, authorized=False)
        assert requeue_failed_job(db, claimed.id, authorized=True)
        assert db.get(AnalysisJob, claimed.id).status == "queued"


def test_expired_lease_can_be_reclaimed_only_after_the_bounded_lease_window(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'expiry.db'}")
    Base.metadata.create_all(engine)
    Local = sessionmaker(bind=engine, autoflush=False)
    at = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)
    with Local() as db:
        user = User(email="expiry@example.test", password_hash="x", accepted_terms=True)
        challenge = Challenge(prompt="Prompt", preparation_guidance="Guide", target_skills=[], difficulty=1, target_duration_seconds=60)
        db.add_all([user, challenge]); db.flush(); assignment = Assignment(user_id=user.id, challenge_id=challenge.id)
        db.add(assignment); db.flush(); attempt = Attempt(user_id=user.id, assignment_id=assignment.id, comparison_group_id="expiry")
        db.add(attempt); db.flush(); job = enqueue_analysis(db, attempt.id); job.available_at = at; db.commit()
        assert claim_next_job(db, "first", now=at, lease_seconds=75)
        before_expiry = at + timedelta(seconds=74)
        assert renew_lease(db, job.id, "first", lease_seconds=75, now=before_expiry)
        db.commit()
        # A stopped worker cannot renew after expiry; a later worker can claim.
        after_expiry = before_expiry + timedelta(seconds=76)
        assert not renew_lease(db, job.id, "first", lease_seconds=75, now=after_expiry)
        db.rollback()
        reclaimed = claim_next_job(db, "second", now=after_expiry, lease_seconds=75)
        assert reclaimed is not None and reclaimed.lease_owner == "second"


def test_provider_failure_classification_keeps_invalid_evaluator_output_terminal():
    assert _failure_classification(SpeechToTextProviderError("quota", retryable=True)) == (True, "stt_retryable")
    assert _failure_classification(SpeechToTextProviderError("bad audio", retryable=False)) == (False, "stt_invalid")
    assert _failure_classification(EvaluationProviderError("evaluation provider request failed")) == (True, "evaluator_retryable")
    assert _failure_classification(EvaluationProviderError("evaluation provider returned invalid JSON")) == (False, "evaluator_invalid")


def test_evaluator_retry_reuses_immutable_transcription_and_metrics_evidence(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'retry.db'}")
    Base.metadata.create_all(engine)
    Local = sessionmaker(bind=engine, autoflush=False)
    with Local() as db:
        user = User(email="retry@example.test", password_hash="x", accepted_terms=True)
        challenge = Challenge(prompt="Prompt", preparation_guidance="Guide", target_skills=["clarity"], difficulty=1, target_duration_seconds=60)
        db.add_all([user, challenge]); db.flush()
        assignment = Assignment(user_id=user.id, challenge_id=challenge.id); db.add(assignment); db.flush()
        attempt = Attempt(user_id=user.id, assignment_id=assignment.id, status="queued", object_key="private/retry", duration_seconds=1, content_type="audio/webm")
        db.add(attempt); db.flush()
        db.add(Recording(attempt_id=attempt.id, storage_provider="fake-private", object_key=attempt.object_key, content_type="audio/webm", byte_size=1, checksum_sha256="b" * 64))
        db.add(AnalysisRun(attempt_id=attempt.id, version=1, status="queued", current_stage="queued")); enqueue_analysis(db, attempt.id); db.commit()
        stt, evaluator = CountingStt(), FailsOnceEvaluator()
        worker = DurableAnalysisWorker(db, FakeStorage(), stt, evaluator, retention_hours=24)
        assert worker.run_once("retry-worker")
        job = db.scalar(select(AnalysisJob)); assert job.status == "queued"
        before = {row.result_type: row.payload for row in db.scalars(select(AnalysisResult))}
        assert set(before) == {"transcript", "metrics", "provider_usage"}
        job.available_at = datetime.now(timezone.utc); db.commit()
        assert worker.run_once("retry-worker")
        db.expire_all()
        after = {row.result_type: row.payload for row in db.scalars(select(AnalysisResult))}
        assert stt.calls == 1 and evaluator.calls == 2
        assert after["transcript"] == before["transcript"]
        assert after["metrics"] == before["metrics"]
        assert after["provider_usage"]["stt"] == before["provider_usage"]["stt"]
        assert after["provider_usage"]["llm"]["requestId"] == "llm-1"


def test_non_local_worker_requires_versioned_provider_cost_configuration():
    settings = SimpleNamespace(
        app_environment="production", stt_provider="deepgram", deepgram_api_key="key", deepgram_model="nova-3",
        openai_api_key="key", recording_retention_hours=24, analysis_job_lease_seconds=120,
        analysis_llm_timeout_seconds=60, analysis_cost_version="unconfigured",
        stt_cost_usd_per_audio_minute=None, llm_input_cost_usd_per_million_tokens=None,
        llm_output_cost_usd_per_million_tokens=None,
    )
    with pytest.raises(RuntimeError, match="ANALYSIS_COST_VERSION"):
        build_worker(None, None, settings)


def test_worker_disables_sdk_retries_so_llm_timeout_is_a_total_call_bound():
    settings = SimpleNamespace(
        app_environment="production", stt_provider="deepgram", deepgram_api_key="key", deepgram_model="nova-3",
        openai_api_key="key", llm_provider="openai", evaluator_model="gpt-5.6-luna", evaluator_reasoning_effort="low",
        recording_retention_hours=24, analysis_job_lease_seconds=120, analysis_llm_timeout_seconds=60,
        analysis_cost_version="prices-v1", stt_cost_usd_per_audio_minute=.1,
        llm_input_cost_usd_per_million_tokens=1, llm_output_cost_usd_per_million_tokens=2,
    )
    worker = build_worker(None, None, settings)
    assert worker.evaluator._provider._timeout_seconds == 60
    assert worker.evaluator._provider._max_retries == 0
