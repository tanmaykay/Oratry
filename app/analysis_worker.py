"""Durable recording-analysis worker composition.

This module deliberately owns orchestration only.  Provider adapters normalize
at their own boundaries, while this worker persists Oratry's versioned evidence
and never logs raw audio, transcript text, credentials, or provider responses.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from typing import Any, Protocol
from uuid import uuid4

from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session

from app.models import (AnalysisJob, AnalysisResult, AnalysisRun, Assignment,
                        Attempt, Challenge, Recording, SkillEvidence, SkillState)
from app.personalization.skill_engine import SkillEvidence as ProjectionEvidence
from app.personalization.skill_engine import SkillStateProjection, update_skill_state
from app.scoring import build_deterministic_scorecard
from oratry.evaluation import EvaluationProviderError
from oratry.speech import DeepgramPrerecordedSpeechToTextProvider
from oratry.speech.providers import SpeechToTextProvider, SpeechToTextProviderError
from oratry.speech.transcript import analyze_transcript
from schemas.evaluation import EvaluationInput

ANALYSIS_STAGE = "recording_analysis"
ANALYSIS_STAGE_VERSION = "v1"
LEASE_SECONDS = 120
MAX_ATTEMPTS = 4


class LeaseLostError(RuntimeError):
    """Another worker owns the job, or its lease has safely expired."""


class AnalysisWorkerSettings(Protocol):
    app_environment: str
    stt_provider: str
    deepgram_api_key: str | None
    deepgram_model: str
    openai_api_key: str | None
    gemini_api_key: str | None
    gemini_evaluator_model: str
    llm_provider: str
    recording_retention_hours: int
    analysis_job_lease_seconds: int
    analysis_llm_timeout_seconds: float
    analysis_cost_version: str
    stt_cost_usd_per_audio_minute: float | None
    llm_input_cost_usd_per_million_tokens: float | None
    llm_output_cost_usd_per_million_tokens: float | None


class CostEstimator:
    """Configuration-versioned accounting, without embedding vendor pricing."""

    def __init__(self, *, version: str, stt_per_minute: float | None,
                 llm_input_per_million: float | None, llm_output_per_million: float | None) -> None:
        self.version = version
        self.stt_per_minute = stt_per_minute
        self.llm_input_per_million = llm_input_per_million
        self.llm_output_per_million = llm_output_per_million

    def stt(self, duration_seconds: float | None) -> float | None:
        if duration_seconds is None or self.stt_per_minute is None:
            return None
        return round(duration_seconds / 60 * self.stt_per_minute, 8)

    def llm(self, input_tokens: int | None, output_tokens: int | None) -> float | None:
        if (input_tokens is None or output_tokens is None or
                self.llm_input_per_million is None or self.llm_output_per_million is None):
            return None
        return round(input_tokens / 1_000_000 * self.llm_input_per_million +
                     output_tokens / 1_000_000 * self.llm_output_per_million, 8)


class PrivateStorage(Protocol):
    provider_name: str
    def download(self, object_key: str, destination: Path) -> None: ...


class Evaluator(Protocol):
    def evaluate(self, input_: EvaluationInput): ...


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _comparison_time(db: Session, now: datetime) -> datetime:
    """SQLite does not round-trip timezone-aware values from DATETIME columns.

    PostgreSQL remains authoritative and receives UTC-aware timestamps. The
    lightweight SQLite suite uses a naive UTC bind only for lease comparisons.
    """
    if db.get_bind().dialect.name == "sqlite":
        return now.replace(tzinfo=None)
    return now


def enqueue_analysis(db: Session, attempt_id: str) -> AnalysisJob:
    """Create the single immutable delivery record for an uploaded attempt."""
    job = AnalysisJob(
        attempt_id=attempt_id,
        event_key=f"attempt:{attempt_id}:{ANALYSIS_STAGE}:{ANALYSIS_STAGE_VERSION}",
        stage=ANALYSIS_STAGE,
        stage_version=ANALYSIS_STAGE_VERSION,
        payload={"attempt_id": attempt_id},
    )
    db.add(job)
    return job


def claim_next_job(db: Session, worker_id: str, *, now: datetime | None = None,
                   lease_seconds: int = LEASE_SECONDS) -> AnalysisJob | None:
    now = now or _utcnow()
    compare_now = _comparison_time(db, now)
    ready = or_(
        AnalysisJob.status == "queued",
        (AnalysisJob.status == "leased") & (AnalysisJob.lease_expires_at <= compare_now),
    )
    job = db.scalar(select(AnalysisJob).where(
        ready, AnalysisJob.available_at <= compare_now,
    ).order_by(AnalysisJob.created_at).with_for_update(skip_locked=True).limit(1))
    if job is None:
        return None
    job.status = "leased"
    job.lease_owner = worker_id
    job.lease_expires_at = now + timedelta(seconds=lease_seconds)
    job.attempt_count += 1
    job.updated_at = now
    db.commit()
    return job


def renew_lease(db: Session, job_id: str, worker_id: str, *, lease_seconds: int,
                now: datetime | None = None) -> bool:
    """Extend only a currently-owned, unexpired lease.

    ``worker_id`` is a unique lease token for each ``run_once`` invocation.
    Conditional updates provide fencing without adding an unversioned mutable
    claim to the evidence records.
    """
    now = now or _utcnow()
    compare_now = _comparison_time(db, now)
    result = db.execute(update(AnalysisJob).where(and_(
        AnalysisJob.id == job_id,
        AnalysisJob.status == "leased",
        AnalysisJob.lease_owner == worker_id,
        AnalysisJob.lease_expires_at > compare_now,
    )).values(lease_expires_at=now + timedelta(seconds=lease_seconds), updated_at=now)
        .execution_options(synchronize_session=False))
    db.flush()
    return result.rowcount == 1


def requeue_failed_job(db: Session, job_id: str, *, authorized: bool, now: datetime | None = None) -> bool:
    """Explicit operator-only recovery; never requeues a leased/completed job."""
    if not authorized:
        raise PermissionError("analysis job requeue requires an authorized operator")
    now = now or _utcnow()
    result = db.execute(update(AnalysisJob).where(and_(
        AnalysisJob.id == job_id, AnalysisJob.status == "failed",
    )).values(status="queued", available_at=now, completed_at=None,
              lease_owner=None, lease_expires_at=None, last_error_code=None, updated_at=now)
        .execution_options(synchronize_session=False))
    db.commit()
    return result.rowcount == 1


def _json(value: Any) -> Any:
    """Turn dataclasses/enums into JSON-compatible evidence without vendor data."""
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, dict):
        return {str(key): _json(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json(item) for item in value]
    return value


def _put(db: Session, run: AnalysisRun, result_type: str, payload: dict[str, Any]) -> None:
    result = db.scalar(select(AnalysisResult).where(
        AnalysisResult.analysis_run_id == run.id, AnalysisResult.result_type == result_type,
    ))
    if result is None:
        db.add(AnalysisResult(analysis_run_id=run.id, result_type=result_type, payload=payload))


def _result_payload(db: Session, run: AnalysisRun, result_type: str) -> dict[str, Any] | None:
    result = db.scalar(select(AnalysisResult).where(
        AnalysisResult.analysis_run_id == run.id, AnalysisResult.result_type == result_type,
    ))
    return result.payload if result and isinstance(result.payload, dict) else None


def _resume_transcription_evidence(db: Session, run: AnalysisRun) -> tuple[str, dict[str, Any], dict[str, Any]] | None:
    """Reuse the immutable successful STT stage after an evaluator retry."""
    transcript = _result_payload(db, run, "transcript")
    metrics = _result_payload(db, run, "metrics")
    if not transcript or not metrics or not isinstance(transcript.get("text"), str):
        return None
    items = metrics.get("items")
    if not isinstance(items, list):
        return None
    values: dict[str, Any] = {}
    findings: dict[str, Any] = {}
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            continue
        if "value" not in item:
            continue
        if item["name"] in {"immediate_repetitions", "target_vocabulary_used"}:
            findings[item["name"]] = item["value"]
        else:
            values[item["name"]] = item["value"]
    return transcript["text"], values, findings


def _failure_classification(exc: Exception) -> tuple[bool, str]:
    """Classify retryability at the orchestration boundary.

    Invalid strict-schema evaluator output is a permanent configuration/model
    quality incident, not a transient provider outage.  Transport failures are
    retryable. STT adapters already expose that distinction explicitly.
    """
    if isinstance(exc, SpeechToTextProviderError):
        return exc.retryable, "stt_retryable" if exc.retryable else "stt_invalid"
    if isinstance(exc, EvaluationProviderError):
        transient = str(exc) == "evaluation provider request failed"
        return transient, "evaluator_retryable" if transient else "evaluator_invalid"
    if isinstance(exc, FileNotFoundError):
        return False, "recording_missing"
    status_code = getattr(exc, "status_code", None) or getattr(getattr(exc, "response", None), "status_code", None)
    if status_code in {400, 401, 403, 404, 422}:
        return False, "storage_invalid"
    if isinstance(exc, (OSError, TimeoutError, ConnectionError)):
        return True, "storage_retryable"
    return False, "analysis_invalid"


def _metrics(transcript, duration_seconds: float | None, *, target_vocabulary: tuple[str, ...] = ()) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    artifacts = analyze_transcript(transcript, target_vocabulary)
    metrics = [asdict(item) for item in artifacts if item.__class__.__name__ == "Metric"]
    findings = [asdict(item) for item in artifacts if item.__class__.__name__ == "Finding"]
    words = next((item["value"] for item in metrics if item["name"] == "word_count"), 0)
    duration = transcript.usage.audio_duration_seconds or duration_seconds
    if duration and duration > 0:
        metrics.append({"name": "duration_seconds", "value": duration, "unit": "seconds", "source": "stt_metadata",
                        "measurement_kind": "deterministic", "reliability": "medium", "algorithm_version": "duration-v1"})
        metrics.append({"name": "words_per_minute", "value": round(float(words) / duration * 60, 1), "unit": "words_per_minute", "source": "derived",
                        "measurement_kind": "deterministic", "reliability": "medium", "algorithm_version": "duration-v1"})
    return ({item["name"]: item["value"] for item in metrics}, _json(metrics + findings),
            {item["name"]: item["value"] for item in findings})


def _project_skills(db: Session, attempt: Attempt, run: AnalysisRun, scorecard: dict[str, Any]) -> None:
    """Project only deterministic, measured scorecard dimensions into skills."""
    mapping = {
        "fluency": ("pace", "filler_use", "immediate_repetition"),
        "delivery": ("timing",),
        "language": ("target_vocabulary",),
    }
    for skill, dimensions in mapping.items():
        measured = [scorecard["dimensions"][dimension]["score"] for dimension in dimensions
                    if scorecard["dimensions"][dimension]["score"] is not None]
        if not measured:
            continue
        existing = db.scalar(select(SkillEvidence).where(
            SkillEvidence.analysis_run_id == run.id, SkillEvidence.skill == skill,
        ))
        if existing is None:
            value = sum(measured) / len(measured)
            confidence = min(1.0, len(measured) / len(dimensions))
            db.add(SkillEvidence(user_id=attempt.user_id, skill=skill, observed_level=value,
                                 confidence=confidence, evidence_type="deterministic_scorecard", analysis_run_id=run.id))
            db.flush()
        rows = list(db.scalars(select(SkillEvidence).where(
            SkillEvidence.user_id == attempt.user_id, SkillEvidence.skill == skill,
        ).order_by(SkillEvidence.recorded_at.desc()).limit(5)))
        evidence = [ProjectionEvidence(row.skill, row.observed_level, row.confidence, row.recorded_at,
                                       row.evidence_type, row.analysis_run_id) for row in rows]
        state = db.scalar(select(SkillState).where(SkillState.user_id == attempt.user_id, SkillState.skill == skill))
        current = SkillStateProjection(skill, state.estimated_level, state.confidence, state.updated_at, state.model_version) if state else None
        projected = update_skill_state(current, evidence)
        if state:
            state.estimated_level, state.confidence, state.model_version = projected.estimated_level, projected.confidence, projected.model_version
        else:
            db.add(SkillState(user_id=attempt.user_id, skill=skill, estimated_level=projected.estimated_level,
                              confidence=projected.confidence, model_version=projected.model_version))


class DurableAnalysisWorker:
    def __init__(self, db: Session, storage: PrivateStorage, stt: SpeechToTextProvider, evaluator: Evaluator,
                 *, retention_hours: int, lease_seconds: int = LEASE_SECONDS,
                 costs: CostEstimator | None = None) -> None:
        self.db, self.storage, self.stt, self.evaluator = db, storage, stt, evaluator
        self.retention_hours = retention_hours
        self.lease_seconds = lease_seconds
        self.costs = costs or CostEstimator(version="unconfigured", stt_per_minute=None,
                                             llm_input_per_million=None, llm_output_per_million=None)

    def run_once(self, worker_id: str | None = None) -> bool:
        # The process label is optional observability context. The persisted
        # owner is deliberately unique per delivery, making it an opaque lease
        # token rather than a reusable process identity.
        lease_token = f"{(worker_id or 'worker')[:90]}:{uuid4()}"
        job = claim_next_job(self.db, lease_token, lease_seconds=self.lease_seconds)
        if job is None:
            return False
        try:
            self._process(job, lease_token)
        except Exception as exc:
            self._fail(job, lease_token, exc)
        return True

    def _renew_or_raise(self, job: AnalysisJob, lease_token: str) -> None:
        if not renew_lease(self.db, job.id, lease_token, lease_seconds=self.lease_seconds):
            self.db.rollback()
            raise LeaseLostError("analysis job lease is no longer owned by this worker")

    def _process(self, job: AnalysisJob, lease_token: str) -> None:
        attempt = self.db.get(Attempt, job.attempt_id)
        recording = self.db.scalar(select(Recording).where(Recording.attempt_id == job.attempt_id))
        run = self.db.scalar(select(AnalysisRun).where(AnalysisRun.attempt_id == job.attempt_id, AnalysisRun.version == 1))
        if not attempt or not recording or not run:
            raise ValueError("analysis prerequisites unavailable")
        if run.status == "completed":
            self._complete(job, lease_token)
            return
        attempt.status, run.status, run.current_stage = "analyzing", "analyzing", "transcription"
        self.db.commit()
        resumed = _resume_transcription_evidence(self.db, run)
        if resumed is None:
            with TemporaryDirectory(prefix="oratry-analysis-") as directory:
                extension = {"audio/webm": ".webm", "audio/wav": ".wav", "audio/mpeg": ".mp3", "audio/mp4": ".m4a"}.get(recording.content_type, ".bin")
                audio_path = Path(directory) / f"recording{extension}"
                self.storage.download(recording.object_key, audio_path)
                self._renew_or_raise(job, lease_token)
                started = perf_counter()
                transcript = self.stt.transcribe(audio_path)
                stt_latency = round((perf_counter() - started) * 1000)
                self._renew_or_raise(job, lease_token)
            transcript_text = transcript.text
            _put(self.db, run, "transcript", _json(asdict(transcript)))
            _put(self.db, run, "provider_usage", {"stt": {"provider": transcript.provider, "model": transcript.provider_model,
                "requestId": transcript.usage.provider_request_id, "audioDurationSeconds": transcript.usage.audio_duration_seconds,
                "latencyMs": stt_latency, "estimatedCostUsd": self.costs.stt(transcript.usage.audio_duration_seconds),
                "costEstimateVersion": self.costs.version}})
            target_vocabulary: tuple[str, ...] = ()
            assignment = self.db.get(Assignment, attempt.assignment_id)
            challenge = self.db.get(Challenge, assignment.challenge_id) if assignment else None
            if challenge is None:
                raise ValueError("challenge unavailable")
            target_vocabulary = tuple(challenge.target_vocabulary or ())
            metrics_map, metrics_payload, findings = _metrics(transcript, attempt.duration_seconds, target_vocabulary=target_vocabulary)
            run.current_stage = "metrics"
            _put(self.db, run, "metrics", {"items": metrics_payload, "calculationVersion": "transcript-rules-v1"})
        else:
            transcript_text, metrics_map, findings = resumed
            assignment = self.db.get(Assignment, attempt.assignment_id)
            challenge = self.db.get(Challenge, assignment.challenge_id) if assignment else None
            if challenge is None:
                raise ValueError("challenge unavailable")
            target_vocabulary = tuple(challenge.target_vocabulary or ())
        run.current_stage = "evaluation"
        # Persist/reuse immutable STT evidence before a paid evaluator call.
        self.db.commit()
        evaluation = self.evaluator.evaluate(EvaluationInput(challenge=challenge.prompt, prompt=challenge.preparation_guidance,
            target_skill=(challenge.target_skills or ["clarity"])[0], transcript=transcript_text, speech_metrics=metrics_map,
            target_vocabulary=target_vocabulary))
        self._renew_or_raise(job, lease_token)
        evaluation_payload = {"result": evaluation.evaluation, "provenance": {"provider": evaluation.provider, "model": evaluation.model,
            "schemaVersion": evaluation.schema_version, "evaluationVersion": evaluation.evaluation_version, "rubricVersion": evaluation.rubric_version,
            "promptVersion": evaluation.prompt_version, "promptSha256": evaluation.prompt_sha256}, "usage": {
            "inputTokens": evaluation.usage.input_tokens, "outputTokens": evaluation.usage.output_tokens,
            "latencyMs": evaluation.usage.latency_ms, "requestId": evaluation.usage.request_id,
            "estimatedCostUsd": self.costs.llm(evaluation.usage.input_tokens, evaluation.usage.output_tokens),
            "costEstimateVersion": self.costs.version}}
        _put(self.db, run, "evaluation", evaluation_payload)
        self.db.flush()
        usage = _result_payload(self.db, run, "provider_usage")
        usage_row = self.db.scalar(select(AnalysisResult).where(AnalysisResult.analysis_run_id == run.id, AnalysisResult.result_type == "provider_usage"))
        if usage_row and usage:
            usage_row.payload = {**usage, "llm": evaluation_payload["usage"]}
        run.current_stage = "scoring"
        scorecard = build_deterministic_scorecard(metrics_map, immediate_repetitions=findings.get("immediate_repetitions", ()),
            target_duration_seconds=challenge.target_duration_seconds, target_vocabulary=target_vocabulary,
            used_target_vocabulary=findings.get("target_vocabulary_used", ()))
        _put(self.db, run, "scorecard", scorecard)
        run.current_stage = "feedback"
        _put(self.db, run, "feedback", {"primaryWeakness": evaluation.evaluation["primary_weakness"],
                                           "recommendation": evaluation.evaluation["recommendation"],
                                           "nextExercise": evaluation.evaluation["next_exercise"]})
        _project_skills(self.db, attempt, run, scorecard)
        run.status, run.current_stage = "completed", "completed"
        attempt.status, attempt.completed_at = "completed", _utcnow()
        assignment.status = "completed"
        retention_deadline = _utcnow() + timedelta(hours=self.retention_hours)
        recording.retention_deadline, recording.deletion_status = retention_deadline, "scheduled"
        recording.deletion_available_at = retention_deadline
        self._complete(job, lease_token, commit=False)
        self.db.commit()

    def _complete(self, job: AnalysisJob, lease_token: str, *, commit: bool = True) -> None:
        now = _utcnow()
        compare_now = _comparison_time(self.db, now)
        result = self.db.execute(update(AnalysisJob).where(and_(
            AnalysisJob.id == job.id, AnalysisJob.status == "leased",
            AnalysisJob.lease_owner == lease_token, AnalysisJob.lease_expires_at > compare_now,
        )).values(status="completed", completed_at=now, lease_owner=None,
                  lease_expires_at=None, last_error_code=None, updated_at=now)
            .execution_options(synchronize_session=False))
        if result.rowcount != 1:
            raise LeaseLostError("analysis job completion rejected by lease fence")
        if commit:
            self.db.commit()

    def _fail(self, job: AnalysisJob, lease_token: str, exc: Exception) -> None:
        self.db.rollback()
        # A stale delivery must never overwrite the current owner's outcome.
        if isinstance(exc, LeaseLostError):
            return
        job = self.db.get(AnalysisJob, job.id)
        if not job or job.status != "leased" or job.lease_owner != lease_token:
            return
        attempt = self.db.get(Attempt, job.attempt_id) if job else None
        run = self.db.scalar(select(AnalysisRun).where(AnalysisRun.attempt_id == job.attempt_id, AnalysisRun.version == 1)) if job else None
        retryable, code = _failure_classification(exc)
        if job and retryable and job.attempt_count < MAX_ATTEMPTS:
            job.status, job.available_at = "queued", _utcnow() + timedelta(seconds=2 ** job.attempt_count)
            job.lease_owner, job.lease_expires_at, job.last_error_code = None, None, code
        elif job:
            job.status, job.completed_at, job.lease_owner, job.lease_expires_at, job.last_error_code = "failed", _utcnow(), None, None, code
        if attempt:
            attempt.status = "analysis_failed"
        if run:
            run.status, run.current_stage, run.failure_code = "failed", "failed", code
        self.db.commit()


def build_worker(db: Session, storage, settings: AnalysisWorkerSettings) -> DurableAnalysisWorker:
    """Production composition point used by the standalone worker command."""
    from oratry.evaluation import GeminiGenerateContentTransport, OpenAIResponsesTransport, build_evaluator
    if settings.stt_provider.casefold() != "deepgram" or not settings.deepgram_api_key:
        raise RuntimeError("STT_PROVIDER=deepgram and DEEPGRAM_API_KEY are required for analysis worker")
    is_non_local = settings.app_environment.casefold() not in {"local", "test"}
    rates = (settings.stt_cost_usd_per_audio_minute, settings.llm_input_cost_usd_per_million_tokens,
             settings.llm_output_cost_usd_per_million_tokens)
    if is_non_local and (settings.analysis_cost_version == "unconfigured" or any(rate is None for rate in rates)):
        raise RuntimeError("ANALYSIS_COST_VERSION and all provider cost rates are required outside local/test")
    llm_provider = settings.llm_provider.casefold()
    if llm_provider == "openai":
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
        # Durable job retry owns retries. SDK retries would multiply a bounded
        # per-request timeout and could outlive this job's lease.
        evaluator_transport = OpenAIResponsesTransport(
            settings.openai_api_key, timeout_seconds=settings.analysis_llm_timeout_seconds, max_retries=0,
        )
    elif llm_provider == "gemini":
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is required when LLM_PROVIDER=gemini")
        evaluator_transport = GeminiGenerateContentTransport(
            settings.gemini_api_key, timeout_seconds=settings.analysis_llm_timeout_seconds,
        )
    else:
        raise RuntimeError("LLM_PROVIDER must be one of: openai, gemini")
    return DurableAnalysisWorker(db, storage,
        DeepgramPrerecordedSpeechToTextProvider(settings.deepgram_api_key, model=settings.deepgram_model),
        build_evaluator(settings, evaluator_transport), retention_hours=settings.recording_retention_hours,
        lease_seconds=settings.analysis_job_lease_seconds,
        costs=CostEstimator(
            version=settings.analysis_cost_version,
            stt_per_minute=settings.stt_cost_usd_per_audio_minute,
            llm_input_per_million=settings.llm_input_cost_usd_per_million_tokens,
            llm_output_per_million=settings.llm_output_cost_usd_per_million_tokens,
        ))
