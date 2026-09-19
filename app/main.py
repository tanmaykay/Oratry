import logging
from datetime import datetime, timezone
from functools import lru_cache
from uuid import UUID
from fastapi import BackgroundTasks, Body, Depends, FastAPI, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core import DomainError, configure_logging, create_token, decode_token, domain_error_handler, http_error_handler, password_hash, settings
from app.db import get_db
from app.models import AnalysisResult, AnalysisRun, Assignment, Attempt, Challenge, DictionaryEntry, Recording, SkillState, User, VocabularyItem
from app.schemas import ActivationResend, ChallengeCreate, CreateAttempt, Preferences, SignIn, SignUp, UploadComplete, VocabularyCreate, VocabularyUpdate
from app.services import ActivationService, CurriculumService, DictionaryService, job_queue, owned_attempt, process_job
from app.email import DevelopmentOutboxEmailProvider, DisabledEmailProvider, EmailDeliveryError, EmailProvider, ResendEmailProvider
from app.dictionary import DatamuseDictionaryProvider, DictionaryProvider, DisabledDictionaryProvider, FreeDictionaryApiProvider, ResilientDictionaryProvider
from app.storage import ObjectStorageProvider, R2ObjectStorageProvider

configure_logging(); log=logging.getLogger("oratry.api")
app=FastAPI(title="Oratry API",version="1.0")
app.add_exception_handler(DomainError,domain_error_handler); from fastapi import HTTPException; app.add_exception_handler(HTTPException,http_error_handler)
bearer=HTTPBearer()
SUPPORTED_AUDIO_CONTENT_TYPES = {"audio/webm", "audio/mpeg", "audio/wav", "audio/mp4"}


@lru_cache
def get_email_provider() -> EmailProvider:
    """Compose email transport at the edge; unknown providers never downgrade."""
    provider = settings.email_provider.casefold()
    if provider == "development_outbox" and settings.app_environment.casefold() in {"local", "test"}:
        return DevelopmentOutboxEmailProvider()
    if provider == "resend":
        if not settings.resend_api_key or not settings.resend_from_address:
            raise DomainError("email_not_configured", "Account activation email is not configured", 503)
        return ResendEmailProvider(api_key=settings.resend_api_key, from_address=settings.resend_from_address)
    if provider == "disabled":
        return DisabledEmailProvider()
    raise DomainError("email_not_configured", "Account activation email is not configured", 503)


def activation_service(db: Session, provider: EmailProvider) -> ActivationService:
    return ActivationService(
        db, provider,
        activation_url_base=settings.activation_url_base,
        token_minutes=settings.activation_token_minutes,
        resend_min_seconds=settings.activation_resend_min_seconds,
        resend_max_per_hour=settings.activation_resend_max_per_hour,
    )


@lru_cache
def get_dictionary_provider() -> DictionaryProvider:
    provider = settings.dictionary_provider.casefold()
    if provider == "free_dictionary_api":
        return ResilientDictionaryProvider(FreeDictionaryApiProvider(), DatamuseDictionaryProvider())
    if provider == "disabled":
        return DisabledDictionaryProvider()
    raise DomainError("dictionary_not_configured", "Dictionary lookup is not configured", 503)


def dictionary_service(db: Session, provider: DictionaryProvider) -> DictionaryService:
    return DictionaryService(db, provider, cache_hours=settings.dictionary_cache_hours)


@lru_cache
def get_object_storage() -> ObjectStorageProvider:
    """Compose the configured private object-storage adapter at the API edge."""
    if settings.object_storage_provider != "r2":
        raise DomainError("storage_not_configured", "Private recording storage is not configured", 503)
    values = {
        "endpoint_url": settings.r2_endpoint_url,
        "bucket": settings.r2_bucket,
        "access_key_id": settings.r2_access_key_id,
        "secret_access_key": settings.r2_secret_access_key,
    }
    if not all(values.values()):
        raise DomainError("storage_not_configured", "Private recording storage is not configured", 503)
    return R2ObjectStorageProvider(**values) # type: ignore[arg-type]


def _validate_audio_content_type(content_type: str) -> str:
    normalized = content_type.lower().split(";", 1)[0].strip()
    if normalized not in SUPPORTED_AUDIO_CONTENT_TYPES:
        raise DomainError("unsupported_media", "Unsupported audio content type")
    return normalized


def _upload_view(instruction) -> dict:
    expires_at = datetime.now(timezone.utc) + instruction.expires_in
    return {
        "method": instruction.method,
        "url": instruction.url,
        "objectKey": instruction.object_key,
        "headers": instruction.headers,
        "expiresAt": expires_at,
    }


def _issued_object_key(user_id: str, attempt_id: str) -> str:
    return f"private/{user_id}/{attempt_id}/raw"


def _create_upload_instruction(storage: ObjectStorageProvider, *, object_key: str, content_type: str, checksum_sha256: str):
    try:
        return storage.create_upload(
            object_key=object_key, content_type=content_type,
            max_bytes=settings.upload_max_bytes, checksum_sha256=checksum_sha256,
        )
    except Exception as exc:
        log.warning("recording_upload_instruction_failed provider=%s", storage.provider_name)
        raise DomainError("upload_unavailable", "Recording upload is temporarily unavailable", 503) from exc


def _is_upload_completion_uniqueness_error(exc: IntegrityError) -> bool:
    """Only replay a race on the rows sealed by upload completion itself."""
    detail = str(exc.orig).lower()
    return any(marker in detail for marker in (
        "recordings.attempt_id", "recordings_attempt_id_key",
        "analysis_runs.attempt_id, analysis_runs.version",
        "analysis_runs_attempt_id_version_key",
    ))
def current_user(credentials:HTTPAuthorizationCredentials=Depends(bearer),db:Session=Depends(get_db)):
    user=db.get(User,str(decode_token(credentials.credentials)))
    if not user: raise DomainError("not_found","Resource not found",404)
    return user
def user_view(user): return {"id":user.id,"email":user.email,"preferences":user.preferences,"emailVerifiedAt":user.email_verified_at,"createdAt":user.created_at}
def challenge_view(challenge): return {"id":challenge.id,"version":challenge.version,"prompt":challenge.prompt,"preparationGuidance":challenge.preparation_guidance,"targetSkills":challenge.target_skills,"difficulty":challenge.difficulty,"targetDurationSeconds":challenge.target_duration_seconds}
def assignment_view(assignment, db):
    return {"assignmentId":assignment.id,"status":assignment.status,"reason":assignment.reason,
            "challenge":challenge_view(db.get(Challenge,assignment.challenge_id))}
def attempt_view(attempt,db):
    assignment=db.get(Assignment,attempt.assignment_id); return {"id":attempt.id,"status":attempt.status,"assignmentId":attempt.assignment_id,"createdAt":attempt.created_at,"challenge":challenge_view(db.get(Challenge,assignment.challenge_id))}
@app.post("/v1/auth/sign-up",status_code=201)
@app.post("/auth/signup",status_code=201,include_in_schema=False)
def signup(body:SignUp,db:Session=Depends(get_db),provider:EmailProvider=Depends(get_email_provider)):
    if not body.accepted_terms: raise DomainError("terms_required","Terms must be accepted")
    if db.scalar(select(User).where(User.email==str(body.email).lower())): raise DomainError("email_taken","An account already exists for this email",409)
    user=User(email=str(body.email).lower(),password_hash=password_hash.hash(body.password),accepted_terms=True)
    db.add(user)
    try:
        activation_service(db, provider).issue(user)
        db.commit()
    except EmailDeliveryError as exc:
        db.rollback()
        raise DomainError("activation_email_unavailable", "Account activation is temporarily unavailable", 503) from exc
    db.refresh(user)
    return {"user":user_view(user),"activationRequired":True,"delivery":"email"}
@app.post("/v1/auth/sign-in")
@app.post("/auth/login",include_in_schema=False)
def login(body:SignIn,db:Session=Depends(get_db)):
    user=db.scalar(select(User).where(User.email==str(body.email).lower()))
    if not user or not password_hash.verify(body.password,user.password_hash): raise DomainError("invalid_credentials","Invalid email or password",401)
    if user.email_verified_at is None:
        raise DomainError("email_verification_required", "Activate your account from the link sent to your email", 403)
    return {"user":user_view(user),"session":{"accessToken":create_token(UUID(user.id)),"tokenType":"bearer"}}


@app.get("/v1/auth/activate")
def activate_account(token: str, db: Session = Depends(get_db)):
    user = activation_service(db, get_email_provider()).consume(token)
    if user is None:
        raise DomainError("activation_link_invalid", "This activation link is invalid or expired", 400)
    return {"user": user_view(user), "session": {"accessToken": create_token(UUID(user.id)), "tokenType": "bearer"}}


@app.post("/v1/auth/resend-activation", status_code=202)
def resend_activation(body: ActivationResend, db: Session = Depends(get_db), provider: EmailProvider = Depends(get_email_provider)):
    """Non-enumerating resend endpoint; throttled and unknown emails look alike."""
    user = db.scalar(select(User).where(User.email == str(body.email).lower()))
    if user and user.email_verified_at is None:
        service = activation_service(db, provider)
        if service.may_resend(user.id):
            try:
                service.issue(user)
                db.commit()
            except EmailDeliveryError:
                db.rollback()
                # Retain the generic public response: callers cannot use this
                # route to distinguish an address or infer provider state.
    return {"accepted": True}


@app.get("/v1/auth/development-outbox", include_in_schema=False)
def development_outbox():
    """Local-preview only: activation links stay in volatile process memory."""
    if settings.app_environment.casefold() not in {"local", "test"}:
        raise DomainError("not_found", "Resource not found", 404)
    provider = get_email_provider()
    if not isinstance(provider, DevelopmentOutboxEmailProvider):
        raise DomainError("not_found", "Resource not found", 404)
    return {"messages": [{"recipient": item.recipient, "activationUrl": item.activation_url} for item in provider.messages]}
@app.get("/v1/me")
@app.get("/me",include_in_schema=False)
def me(user:User=Depends(current_user),db:Session=Depends(get_db)):
    curriculum=CurriculumService(db)
    baseline_status, _, _=curriculum.baseline_status(user.id)
    assignment=curriculum.current_assignment(user.id) if baseline_status != "not_started" else None
    return {**user_view(user),"onboardingState":baseline_status,
            "currentAssignment":assignment_view(assignment,db) if assignment else None}
@app.patch("/v1/me")
@app.patch("/me/preferences",include_in_schema=False)
def patch_me(body:Preferences,user:User=Depends(current_user),db:Session=Depends(get_db)): user.preferences=body.preferences; db.commit(); return user_view(user)

@app.post("/v1/baseline/start",status_code=201)
def start_baseline(user:User=Depends(current_user),db:Session=Depends(get_db)):
    """Idempotently persist the V1 baseline sequence for the authenticated user."""
    curriculum=CurriculumService(db)
    assignments=curriculum.start_baseline(user.id)
    status, _, current=curriculum.baseline_status(user.id)
    return {"status":status,"assignments":[assignment_view(item,db) for item in assignments],
            "currentAssignment":assignment_view(current,db) if current else None}

@app.get("/v1/baseline")
def get_baseline(user:User=Depends(current_user),db:Session=Depends(get_db)):
    curriculum=CurriculumService(db)
    status, assignments, current=curriculum.baseline_status(user.id)
    return {"status":status,"assignments":[assignment_view(item,db) for item in assignments],
            "currentAssignment":assignment_view(current,db) if current else None}

@app.get("/v1/assignments/current")
def current_assignment(user:User=Depends(current_user),db:Session=Depends(get_db)):
    curriculum=CurriculumService(db)
    status, _, _=curriculum.baseline_status(user.id)
    if status == "not_started":
        raise DomainError("baseline_not_started","Start the baseline before requesting an assignment",409)
    assignment=curriculum.current_assignment(user.id)
    if not assignment:
        raise DomainError("no_assignment","No practice assignment is available",404)
    return assignment_view(assignment,db)

@app.get("/v1/home")
def home(user:User=Depends(current_user),db:Session=Depends(get_db)):
    curriculum=CurriculumService(db)
    baseline_status, _, _=curriculum.baseline_status(user.id)
    assignment=curriculum.current_assignment(user.id) if baseline_status != "not_started" else None
    in_progress=db.scalar(select(Attempt).where(
        Attempt.user_id==user.id, Attempt.status.in_(("uploading","queued","analyzing","analysis_failed"))
    ).order_by(Attempt.created_at.desc()))
    completed_count=db.scalar(select(func.count(Attempt.id)).where(
        Attempt.user_id==user.id, Attempt.status=="completed"
    )) or 0
    return {"onboardingState":baseline_status,
            "currentAssignment":assignment_view(assignment,db) if assignment else None,
            "inProgressAttempt":attempt_view(in_progress,db) if in_progress else None,
            "coachingFocus":None,
            "recentProgress":{"completedAttemptCount":completed_count}}

@app.get("/v1/challenges/recommended")
@app.get("/challenges/recommended",include_in_schema=False)
def recommended(user:User=Depends(current_user),db:Session=Depends(get_db)):
    assignment=db.scalar(select(Assignment).where(Assignment.user_id==user.id,Assignment.status=="assigned").order_by(Assignment.sequence))
    if assignment: return {"assignmentId":assignment.id,"challenge":challenge_view(db.get(Challenge,assignment.challenge_id))}
    challenge=db.scalar(select(Challenge).where(Challenge.active==True))
    if not challenge: raise DomainError("no_challenge","No challenges are currently available",404)
    assignment=Assignment(user_id=user.id,challenge_id=challenge.id); db.add(assignment); db.commit(); return {"assignmentId":assignment.id,"challenge":challenge_view(challenge)}
@app.post("/v1/challenges/generate",status_code=201)
@app.post("/challenges/generate",status_code=201,include_in_schema=False)
def generate_challenge(body:ChallengeCreate,user:User=Depends(current_user),db:Session=Depends(get_db)):
    challenge=Challenge(**body.model_dump()); db.add(challenge); db.commit(); return challenge_view(challenge)
@app.get("/v1/challenges/{challenge_id}")
@app.get("/challenges/{challenge_id}",include_in_schema=False)
def get_challenge(challenge_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    assignment=db.scalar(select(Assignment).where(Assignment.user_id==user.id,Assignment.challenge_id==challenge_id))
    if not assignment: raise DomainError("not_found","Resource not found",404)
    return challenge_view(db.get(Challenge,challenge_id))

@app.post("/v1/assignments/{assignment_id}/attempts",status_code=201)
def create_attempt(assignment_id:str, body:CreateAttempt|None=Body(default=None), user:User=Depends(current_user), db:Session=Depends(get_db), storage:ObjectStorageProvider=Depends(get_object_storage)):
    assignment=db.scalar(select(Assignment).where(Assignment.id==assignment_id,Assignment.user_id==user.id))
    if not assignment: raise DomainError("not_found","Resource not found",404)
    if assignment.reason == "baseline":
        current = CurriculumService(db).current_assignment(user.id)
        if current is None or current.id != assignment.id:
            raise DomainError(
                "baseline_assignment_not_current",
                "Complete the current baseline step before starting another one",
                409,
            )
    if body is None:
        raise DomainError("checksum_required", "A recording SHA-256 checksum is required before upload", 422)
    request = body
    content_type = _validate_audio_content_type(request.content_type)
    if request.retry_of_attempt_id:
        source = owned_attempt(db, user.id, request.retry_of_attempt_id)
        if source.assignment_id != assignment.id or source.status != "completed":
            raise DomainError("retry_not_available", "This retry source is not available", 409)
    else:
        # Repeated create requests before an upload is sealed resume the same
        # attempt. This is intentionally narrower than header idempotency,
        # which needs durable key storage in a later schema change.
        attempt = db.scalar(select(Attempt).where(
            Attempt.user_id == user.id, Attempt.assignment_id == assignment.id,
            Attempt.status == "uploading", Attempt.retry_of_attempt_id.is_(None),
        ).order_by(Attempt.created_at.desc()))
        if attempt is not None:
            if attempt.content_type and attempt.content_type != content_type:
                raise DomainError("upload_media_type_locked", "This upload attempt was created for a different media type", 409)
            if attempt.checksum != request.checksum_sha256:
                raise DomainError("upload_checksum_locked", "This upload attempt was created for a different recording", 409)
            instruction = _create_upload_instruction(
                storage, object_key=_issued_object_key(user.id, attempt.id),
                content_type=content_type, checksum_sha256=attempt.checksum,
            )
            return {**attempt_view(attempt,db),"upload":_upload_view(instruction)}
    attempt=Attempt(user_id=user.id,assignment_id=assignment.id,content_type=content_type, checksum=request.checksum_sha256,
                    retry_of_attempt_id=request.retry_of_attempt_id)
    if request.retry_of_attempt_id:
        source = owned_attempt(db, user.id, request.retry_of_attempt_id)
        attempt.comparison_group_id = source.comparison_group_id
        attempt.ordinal = source.ordinal + 1
    db.add(attempt)
    db.flush()
    instruction = _create_upload_instruction(
        storage, object_key=_issued_object_key(user.id, attempt.id),
        content_type=content_type, checksum_sha256=request.checksum_sha256,
    )
    db.commit()
    return {**attempt_view(attempt,db),"upload":_upload_view(instruction)}
@app.post("/v1/sessions",status_code=201,include_in_schema=False)
def create_session(assignment_id:str,body:CreateAttempt,user:User=Depends(current_user),db:Session=Depends(get_db),storage:ObjectStorageProvider=Depends(get_object_storage)): return create_attempt(assignment_id,body,user,db,storage)
@app.post("/v1/attempts/{attempt_id}/upload-complete",status_code=202)
@app.post("/sessions/{attempt_id}/upload",status_code=202,include_in_schema=False)
def upload_complete(attempt_id:str,body:UploadComplete,user:User=Depends(current_user),db:Session=Depends(get_db),storage:ObjectStorageProvider=Depends(get_object_storage)):
    attempt=owned_attempt(db,user.id,attempt_id)
    expected = _issued_object_key(user.id, attempt.id)
    content_type = _validate_audio_content_type(body.content_type)
    if body.object_key != expected:
        raise DomainError("invalid_upload", "Upload key is not authorized", 403)
    if attempt.content_type != content_type:
        raise DomainError("invalid_upload", "Upload media type does not match the issued instruction", 409)
    if attempt.status != "uploading":
        recording = db.scalar(select(Recording).where(Recording.attempt_id == attempt.id))
        if attempt.status == "queued" and recording and (
            recording.object_key == body.object_key and recording.content_type == content_type
            and recording.byte_size == body.byte_size and recording.checksum_sha256 == attempt.checksum
        ):
            return {"id":attempt.id,"status":"queued","queue":{"durable":False,"delivery":"in_memory"}}
        raise DomainError("invalid_state", "This attempt cannot accept an upload", 409)
    try:
        metadata = storage.head(body.object_key)
    except Exception as exc:
        log.info("recording_upload_verification_failed provider=%s", storage.provider_name)
        raise DomainError("upload_verification_failed", "Uploaded recording could not be verified", 409) from exc
    if metadata.object_key != expected or metadata.content_type.lower().split(";", 1)[0].strip() != content_type:
        raise DomainError("upload_verification_failed", "Uploaded object metadata does not match the issued instruction", 409)
    if metadata.byte_size != body.byte_size or metadata.byte_size > settings.upload_max_bytes:
        raise DomainError("upload_verification_failed", "Uploaded object size could not be verified", 409)
    if metadata.checksum_sha256 is None or metadata.checksum_sha256 != attempt.checksum:
        raise DomainError("upload_verification_failed", "Uploaded object checksum could not be verified", 409)
    attempt.object_key,attempt.duration_seconds,attempt.content_type=body.object_key,body.duration_seconds,content_type
    attempt.status="queued"; attempt.sealed_at=datetime.now(timezone.utc)
    db.add(Recording(attempt_id=attempt.id, storage_provider=storage.provider_name, object_key=body.object_key,
                     content_type=content_type, byte_size=body.byte_size, checksum_sha256=attempt.checksum,
                     retention_deadline=None, deletion_status="not_scheduled"))
    db.add(AnalysisRun(attempt_id=attempt.id,version=1,status="queued",current_stage="queued"))
    try:
        db.commit()
    except IntegrityError as exc:
        # Another request can seal the same upload while this transaction is
        # verifying R2 metadata. Recover only the unique Recording/AnalysisRun
        # completion race; all non-equivalent or unrelated integrity failures
        # remain errors.
        if not _is_upload_completion_uniqueness_error(exc):
            raise
        db.rollback()
        sealed = owned_attempt(db, user.id, attempt_id)
        recording = db.scalar(select(Recording).where(Recording.attempt_id == sealed.id))
        run = db.scalar(select(AnalysisRun).where(AnalysisRun.attempt_id == sealed.id, AnalysisRun.version == 1))
        if sealed.status == "queued" and recording and run and (
            recording.object_key == body.object_key
            and recording.content_type == content_type
            and recording.byte_size == body.byte_size
            and recording.checksum_sha256 == sealed.checksum
        ):
            return {"id": sealed.id, "status": "queued", "queue": {"durable": False, "delivery": "in_memory"}}
        raise exc
    job_queue.enqueue_attempt_analysis(attempt.id)
    return {"id":attempt.id,"status":"queued","queue":{"durable":False,"delivery":"in_memory"}}
def _run_job(attempt_id):
    from app.db import SessionLocal
    with SessionLocal() as db: process_job(db,attempt_id)
@app.post("/sessions/{attempt_id}/analyze",status_code=202,include_in_schema=False)
def analyze(attempt_id:str,background:BackgroundTasks,user:User=Depends(current_user),db:Session=Depends(get_db)):
    attempt=owned_attempt(db,user.id,attempt_id)
    if attempt.status not in {"queued","analysis_failed"}: raise DomainError("invalid_state","Analysis cannot be queued",409)
    background.add_task(_run_job,attempt.id); return {"id":attempt.id,"status":attempt.status}
@app.get("/v1/attempts/{attempt_id}")
@app.get("/sessions/{attempt_id}",include_in_schema=False)
def get_attempt(attempt_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)): return attempt_view(owned_attempt(db,user.id,attempt_id),db)
@app.get("/v1/attempts/{attempt_id}/result")
@app.get("/sessions/{attempt_id}/feedback",include_in_schema=False)
def result(attempt_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    attempt=owned_attempt(db,user.id,attempt_id)
    if attempt.status!="completed": raise DomainError("analysis_not_complete","Analysis is not complete",409)
    run=db.scalar(select(AnalysisRun).where(AnalysisRun.attempt_id==attempt.id).order_by(AnalysisRun.version.desc())); data={row.result_type:row.payload for row in db.scalars(select(AnalysisResult).where(AnalysisResult.analysis_run_id==run.id))}
    return {"attemptId":attempt.id,"analysisVersion":run.version,"transcript":data["transcript"],"objectiveMetrics":data["metrics"],"evaluation":data["evaluation"],"scorecard":data["scorecard"],"coachingRecommendation":data["feedback"]}
@app.post("/sessions/{attempt_id}/retry",status_code=201,include_in_schema=False)
def retry(attempt_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    source=owned_attempt(db,user.id,attempt_id)
    if source.status!="completed": raise DomainError("retry_not_available","Complete analysis before retrying",409)
    attempt=Attempt(user_id=user.id,assignment_id=source.assignment_id,retry_of_attempt_id=source.id,comparison_group_id=source.comparison_group_id,ordinal=source.ordinal+1); db.add(attempt); db.commit(); return attempt_view(attempt,db)

@app.get("/v1/progress")
@app.get("/progress",include_in_schema=False)
def progress(user:User=Depends(current_user),db:Session=Depends(get_db)): return {"attempts":[attempt_view(a,db) for a in db.scalars(select(Attempt).where(Attempt.user_id==user.id).order_by(Attempt.created_at.desc()))]}
@app.get("/v1/progress/skills")
@app.get("/progress/skills",include_in_schema=False)
def skills(user:User=Depends(current_user),db:Session=Depends(get_db)): return {"skills":[{"skill":s.skill,"estimatedLevel":s.estimated_level,"confidence":s.confidence,"modelVersion":s.model_version} for s in db.scalars(select(SkillState).where(SkillState.user_id==user.id))]}
def dictionary_entry_view(entry: DictionaryEntry | None) -> dict | None:
    if not entry:
        return None
    return {"language": entry.language, "term": entry.normalized_term, "payload": entry.payload,
            "source": entry.source, "fetchedAt": entry.fetched_at, "expiresAt": entry.expires_at}


def vocabulary_view(item: VocabularyItem, db: Session) -> dict:
    return {"id": item.id, "word": item.word, "practiceStatus": item.practice_status,
            "dictionary": dictionary_entry_view(db.get(DictionaryEntry, item.dictionary_entry_id) if item.dictionary_entry_id else None)}


@app.get("/v1/dictionary/{term}")
def dictionary_lookup(term: str, user: User = Depends(current_user), db: Session = Depends(get_db), provider: DictionaryProvider = Depends(get_dictionary_provider)):
    normalized = DictionaryService.normalize_term(term)
    if not normalized or len(normalized) > 200:
        raise DomainError("invalid_dictionary_term", "Dictionary term must be between 1 and 200 characters", 422)
    entry = dictionary_service(db, provider).lookup(normalized)
    db.commit()
    return {"term": normalized, "dictionary": dictionary_entry_view(entry)}


@app.get("/v1/vocabulary")
@app.get("/vocabulary",include_in_schema=False)
def vocabulary(user:User=Depends(current_user),db:Session=Depends(get_db)):
    return {"items":[vocabulary_view(item, db) for item in db.scalars(select(VocabularyItem).where(VocabularyItem.user_id==user.id).order_by(VocabularyItem.word))]}


@app.post("/v1/vocabulary",status_code=201)
def add_vocabulary(body:VocabularyCreate,user:User=Depends(current_user),db:Session=Depends(get_db),provider: DictionaryProvider = Depends(get_dictionary_provider)):
    word = " ".join(body.word.split())
    if not word:
        raise DomainError("invalid_vocabulary_word", "Vocabulary word cannot be blank", 422)
    item = VocabularyItem(user_id=user.id, word=word)
    db.add(item)
    db.flush()
    dictionary_service(db, provider).attach_to_vocabulary(item, lookup=body.lookup, language=body.language)
    db.commit()
    return vocabulary_view(item, db)


@app.get("/v1/vocabulary/{item_id}")
def get_vocabulary_item(item_id: str, user:User=Depends(current_user),db:Session=Depends(get_db)):
    item = db.scalar(select(VocabularyItem).where(VocabularyItem.id == item_id, VocabularyItem.user_id == user.id))
    if not item: raise DomainError("not_found","Resource not found",404)
    return vocabulary_view(item, db)


@app.patch("/v1/vocabulary/{item_id}")
def update_vocabulary_item(item_id: str, body: VocabularyUpdate, user:User=Depends(current_user),db:Session=Depends(get_db)):
    item = db.scalar(select(VocabularyItem).where(VocabularyItem.id == item_id, VocabularyItem.user_id == user.id))
    if not item: raise DomainError("not_found","Resource not found",404)
    item.practice_status = body.practice_status
    db.commit()
    return vocabulary_view(item, db)


@app.delete("/v1/vocabulary/{item_id}", status_code=204)
def delete_vocabulary_item(item_id: str, user:User=Depends(current_user),db:Session=Depends(get_db)):
    item = db.scalar(select(VocabularyItem).where(VocabularyItem.id == item_id, VocabularyItem.user_id == user.id))
    if not item: raise DomainError("not_found","Resource not found",404)
    db.delete(item)
    db.commit()
