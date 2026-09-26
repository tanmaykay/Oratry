import logging
import secrets
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from uuid import UUID
from fastapi import BackgroundTasks, Body, Depends, FastAPI, Header, Request
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core import DomainError, configure_logging, create_token, decode_token, domain_error_handler, http_error_handler, password_hash, settings
from app.db import get_db
from app.models import AnalysisJob, AnalysisResult, AnalysisRun, Assignment, Attempt, Challenge, DictionaryEntry, ExternalIdentity, OAuthLoginCode, Recording, SkillState, User, VocabularyItem, VocabularyObservation
from app.schemas import ActivationResend, ChallengeCreate, CreateAttempt, OAuthCodeExchange, Preferences, SignIn, SignUp, UploadComplete, VocabularyCreate, VocabularyUpdate
from app.services import ActivationService, CurriculumService, DictionaryService, owned_attempt
from app.analysis_worker import ANALYSIS_STAGE, ANALYSIS_STAGE_VERSION, enqueue_analysis
from app.email import DevelopmentOutboxEmailProvider, DisabledEmailProvider, EmailDeliveryError, EmailProvider, ResendEmailProvider
from app.dictionary import DatamuseDictionaryProvider, DictionaryProvider, DisabledDictionaryProvider, FreeDictionaryApiProvider, ResilientDictionaryProvider
from app.storage import ObjectStorageProvider, R2ObjectStorageProvider
from app.identity import (ExternalProfile, GoogleIdentityProvider, IdentityProviderError,
                          digest_code, new_browser_state, new_handoff_code,
                          read_state_cookie, state_cookie)

configure_logging(); log=logging.getLogger("oratry.api")
app=FastAPI(title="Oratry API",version="1.0")
app.add_exception_handler(DomainError,domain_error_handler); from fastapi import HTTPException; app.add_exception_handler(HTTPException,http_error_handler)
bearer=HTTPBearer()
SUPPORTED_AUDIO_CONTENT_TYPES = {"audio/webm", "audio/mpeg", "audio/wav", "audio/mp4"}
GOOGLE_STATE_COOKIE = "oratry_google_oauth"


@app.get("/health/live", include_in_schema=False)
def live_health():
    return {"status": "ok", "component": "api"}


@app.get("/health/ready", include_in_schema=False)
def ready_health(db: Session = Depends(get_db)):
    db.execute(select(1))
    return {"status": "ok", "component": "api", "database": "reachable"}


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


@lru_cache
def get_google_identity_provider() -> GoogleIdentityProvider:
    if not settings.google_oauth_client_id or not settings.google_oauth_client_secret:
        raise DomainError("google_sign_in_unavailable", "Google sign-in is not configured", 503)
    return GoogleIdentityProvider(client_id=settings.google_oauth_client_id,
                                  client_secret=settings.google_oauth_client_secret,
                                  redirect_uri=settings.google_oauth_redirect_uri)


def _oauth_expired(value: datetime) -> bool:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value <= datetime.now(timezone.utc)


def _oauth_callback_url(*, code: str | None = None, error: str | None = None) -> str:
    from urllib.parse import urlencode
    query = urlencode({key: value for key, value in {"code": code, "error": error}.items() if value})
    return f"{settings.web_app_url.rstrip('/')}/oauth/callback?{query}"


def _resolve_external_user(db: Session, profile: ExternalProfile, *, accepted_terms: bool) -> User:
    identity = db.scalar(select(ExternalIdentity).where(
        ExternalIdentity.provider == profile.provider, ExternalIdentity.subject == profile.subject,
    ))
    if identity:
        return db.get(User, identity.user_id)
    user = db.scalar(select(User).where(User.email == profile.email))
    if user is None:
        if not accepted_terms:
            raise DomainError("terms_required", "Accept the terms before creating an account", 400)
        user = User(email=profile.email, password_hash=password_hash.hash(secrets.token_urlsafe(48)),
                    accepted_terms=True, email_verified_at=datetime.now(timezone.utc))
        db.add(user); db.flush()
    elif user.email_verified_at is None:
        # Google has verified control of the same email address.
        user.email_verified_at = datetime.now(timezone.utc)
    db.add(ExternalIdentity(user_id=user.id, provider=profile.provider, subject=profile.subject))
    db.flush()
    return user


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
        "analysis_jobs.event_key", "analysis_jobs_attempt_id_stage_version_key",
    ))
def current_user(credentials:HTTPAuthorizationCredentials=Depends(bearer),db:Session=Depends(get_db)):
    user=db.get(User,str(decode_token(credentials.credentials)))
    if not user: raise DomainError("not_found","Resource not found",404)
    return user
def user_view(user): return {"id":user.id,"email":user.email,"preferences":user.preferences,"emailVerifiedAt":user.email_verified_at,"createdAt":user.created_at}
def challenge_view(challenge): return {"id":challenge.id,"version":challenge.version,"prompt":challenge.prompt,"preparationGuidance":challenge.preparation_guidance,"targetSkills":challenge.target_skills,"targetVocabulary":challenge.target_vocabulary or [],"difficulty":challenge.difficulty,"targetDurationSeconds":challenge.target_duration_seconds}
def assignment_view(assignment, db):
    return {"assignmentId":assignment.id,"status":assignment.status,"reason":assignment.reason,
            "challenge":challenge_view(db.get(Challenge,assignment.challenge_id))}
def attempt_view(attempt,db):
    assignment=db.get(Assignment,attempt.assignment_id)
    run = db.scalar(select(AnalysisRun).where(AnalysisRun.attempt_id == attempt.id).order_by(AnalysisRun.version.desc()))
    return {"id":attempt.id,"status":attempt.status,"assignmentId":attempt.assignment_id,"createdAt":attempt.created_at,
            "failureCode": run.failure_code if attempt.status == "analysis_failed" and run else None,
            "challenge":challenge_view(db.get(Challenge,assignment.challenge_id))}

def result_payload(db: Session, run: AnalysisRun | None, result_type: str) -> dict | None:
    if run is None:
        return None
    result = db.scalar(select(AnalysisResult).where(
        AnalysisResult.analysis_run_id == run.id, AnalysisResult.result_type == result_type,
    ))
    return result.payload if result and isinstance(result.payload, dict) else None

def reviewable_attempt(db: Session, user_id: str, attempt_id: str) -> Attempt:
    attempt = owned_attempt(db, user_id, attempt_id)
    if attempt.hidden_at is not None:
        raise DomainError("not_found", "Resource not found", 404)
    return attempt
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


@app.get("/v1/auth/providers")
def auth_providers():
    """Public capability flag; never expose client secrets or provider errors."""
    return {"google": bool(settings.google_oauth_client_id and settings.google_oauth_client_secret)}


@app.get("/v1/auth/google/start", include_in_schema=False)
def google_start(accepted_terms: bool = False, provider: GoogleIdentityProvider = Depends(get_google_identity_provider)):
    state, verifier, challenge = new_browser_state(accepted_terms=accepted_terms)
    response = RedirectResponse(provider.authorization_url(state=state, code_challenge=challenge), status_code=302)
    response.set_cookie(
        GOOGLE_STATE_COOKIE,
        state_cookie(state=state, verifier=verifier, accepted_terms=accepted_terms,
                     secret=settings.jwt_secret, expires_seconds=10 * 60),
        max_age=10 * 60, httponly=True, secure=settings.app_environment.casefold() not in {"local", "test"},
        samesite="lax", path="/v1/auth/google",
    )
    return response


@app.get("/v1/auth/google/callback", include_in_schema=False)
def google_callback(request: Request, state: str | None = None, code: str | None = None,
                    error: str | None = None, db: Session = Depends(get_db),
                    provider: GoogleIdentityProvider = Depends(get_google_identity_provider)):
    if error or not state or not code:
        return RedirectResponse(_oauth_callback_url(error="google_sign_in_cancelled"), status_code=302)
    state_data = read_state_cookie(request.cookies.get(GOOGLE_STATE_COOKIE), state=state, secret=settings.jwt_secret)
    if state_data is None:
        return RedirectResponse(_oauth_callback_url(error="google_sign_in_expired"), status_code=302)
    verifier, accepted_terms = state_data
    try:
        profile = provider.exchange(code=code, code_verifier=verifier)
        user = _resolve_external_user(db, profile, accepted_terms=accepted_terms)
        handoff = new_handoff_code()
        db.add(OAuthLoginCode(user_id=user.id, code_digest=digest_code(handoff),
                              expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.oauth_handoff_minutes)))
        db.commit()
    except DomainError as exc:
        db.rollback()
        return RedirectResponse(_oauth_callback_url(error=exc.code), status_code=302)
    except (IdentityProviderError, IntegrityError):
        db.rollback()
        return RedirectResponse(_oauth_callback_url(error="google_sign_in_failed"), status_code=302)
    response = RedirectResponse(_oauth_callback_url(code=handoff), status_code=302)
    response.delete_cookie(GOOGLE_STATE_COOKIE, path="/v1/auth/google")
    return response


@app.post("/v1/auth/google/complete")
def google_complete(body: OAuthCodeExchange, db: Session = Depends(get_db)):
    login_code = db.scalar(select(OAuthLoginCode).where(OAuthLoginCode.code_digest == digest_code(body.code)))
    if login_code is None or login_code.consumed_at is not None or _oauth_expired(login_code.expires_at):
        raise DomainError("google_sign_in_expired", "This Google sign-in link is invalid or expired", 400)
    user = db.get(User, login_code.user_id)
    if user is None:
        raise DomainError("google_sign_in_expired", "This Google sign-in link is invalid or expired", 400)
    login_code.consumed_at = datetime.now(timezone.utc)
    db.commit()
    return {"user": user_view(user), "session": {"accessToken": create_token(UUID(user.id)), "tokenType": "bearer"}}


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
        Attempt.user_id==user.id, Attempt.status.in_(("uploading","queued","analyzing"))
    ).order_by(Attempt.created_at.desc()))
    completed_count=db.scalar(select(func.count(Attempt.id)).where(
        Attempt.user_id==user.id, Attempt.status=="completed", Attempt.hidden_at.is_(None)
    )) or 0
    latest_attempt = db.scalar(select(Attempt).where(
        Attempt.user_id == user.id, Attempt.status == "completed", Attempt.hidden_at.is_(None),
    ).order_by(Attempt.completed_at.desc(), Attempt.created_at.desc()))
    coaching_focus = None
    if latest_attempt:
        latest_run = db.scalar(select(AnalysisRun).where(
            AnalysisRun.attempt_id == latest_attempt.id, AnalysisRun.status == "completed",
        ).order_by(AnalysisRun.version.desc()))
        feedback = result_payload(db, latest_run, "feedback")
        if isinstance(feedback, dict):
            primary, recommendation = feedback.get("primaryWeakness"), feedback.get("recommendation")
            if isinstance(primary, dict) and isinstance(recommendation, dict):
                coaching_focus = {"attemptId": latest_attempt.id,
                    "primaryWeakness": {"dimension": primary.get("dimension"), "observation": primary.get("observation")},
                    "recommendation": {"action": recommendation.get("action"), "successCriterion": recommendation.get("success_criterion")}}
    return {"onboardingState":baseline_status,
            "currentAssignment":assignment_view(assignment,db) if assignment else None,
            "inProgressAttempt":attempt_view(in_progress,db) if in_progress else None,
            "coachingFocus":coaching_focus,
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
    # A completed baseline prompt remains retryable even after the learner has
    # advanced to the next baseline assignment. New baseline attempts retain
    # the sequential gate; retries are tied to their completed source below.
    if assignment.reason == "baseline" and not (body and body.retry_of_attempt_id):
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
            if attempt.content_type != content_type or attempt.checksum != request.checksum_sha256:
                # A fresh browser recording is an explicit replacement of an
                # unsealed upload. Do not strand the learner behind a hung R2
                # request; confirmed/queued recordings are never replaced here.
                try:
                    storage.delete(_issued_object_key(user.id, attempt.id))
                except Exception:
                    log.info("superseded_upload_cleanup_failed provider=%s", storage.provider_name)
                attempt.status = "abandoned"
                db.flush()
            else:
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
            return {"id":attempt.id,"status":"queued","queue":{"durable":True,"delivery":"analysis_jobs"}}
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
    # The durable event key makes replaying upload completion safe.  The job
    # carries no recording bytes, transcript, URL, or credential material.
    enqueue_analysis(db, attempt.id)
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
            return {"id": sealed.id, "status": "queued", "queue": {"durable": True, "delivery": "analysis_jobs"}}
        raise exc
    return {"id":attempt.id,"status":"queued","queue":{"durable":True,"delivery":"analysis_jobs"}}
@app.post("/sessions/{attempt_id}/analyze",status_code=202,include_in_schema=False)
def analyze(attempt_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    attempt=owned_attempt(db,user.id,attempt_id)
    if attempt.status not in {"queued","analysis_failed"}: raise DomainError("invalid_state","Analysis cannot be queued",409)
    job = db.scalar(select(AnalysisJob).where(AnalysisJob.attempt_id == attempt.id,
        AnalysisJob.stage == ANALYSIS_STAGE, AnalysisJob.stage_version == ANALYSIS_STAGE_VERSION))
    if job is None:
        enqueue_analysis(db, attempt.id)
        db.commit()
    return {"id":attempt.id,"status":attempt.status,"queue":{"durable":True,"delivery":"analysis_jobs"}}
@app.get("/v1/attempts/{attempt_id}")
@app.get("/sessions/{attempt_id}",include_in_schema=False)
def get_attempt(attempt_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)): return attempt_view(owned_attempt(db,user.id,attempt_id),db)
@app.get("/v1/attempts/{attempt_id}/result")
@app.get("/sessions/{attempt_id}/feedback",include_in_schema=False)
def result(attempt_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    attempt=reviewable_attempt(db,user.id,attempt_id)
    if attempt.status!="completed": raise DomainError("analysis_not_complete","Analysis is not complete",409)
    run=db.scalar(select(AnalysisRun).where(AnalysisRun.attempt_id==attempt.id).order_by(AnalysisRun.version.desc())); data={row.result_type:row.payload for row in db.scalars(select(AnalysisResult).where(AnalysisResult.analysis_run_id==run.id))}
    return {"attemptId":attempt.id,"analysisVersion":run.version,"transcript":data["transcript"],"objectiveMetrics":data["metrics"],"evaluation":data["evaluation"],"scorecard":data["scorecard"],"coachingRecommendation":data["feedback"]}


def _comparison_evidence(db: Session, attempt: Attempt) -> dict:
    """Return only immutable, learner-facing facts from a completed attempt."""
    run = db.scalar(select(AnalysisRun).where(AnalysisRun.attempt_id == attempt.id).order_by(AnalysisRun.version.desc()))
    if attempt.status != "completed" or not run or run.status != "completed":
        raise DomainError("comparison_not_available", "Both attempts must complete analysis before comparison", 409)
    rows = {row.result_type: row.payload for row in db.scalars(select(AnalysisResult).where(AnalysisResult.analysis_run_id == run.id))}
    metrics = rows.get("metrics", {}).get("items", [])
    names = {"duration_seconds", "word_count", "words_per_minute", "filler_count", "filler_rate"}
    return {
        "attemptId": attempt.id,
        "ordinal": attempt.ordinal,
        "completedAt": attempt.completed_at,
        "overallScore": rows.get("scorecard", {}).get("overall"),
        "metrics": [{"name": item["name"], "value": item.get("value"), "unit": item.get("unit")} for item in metrics if item.get("name") in names],
    }


@app.get("/v1/attempts/{attempt_id}/recording-playback")
def recording_playback(attempt_id: str, user: User = Depends(current_user), db: Session = Depends(get_db), storage: ObjectStorageProvider = Depends(get_object_storage)):
    """Issue an owner-authorized, short-lived private recording read URL.

    Playback is deliberately unavailable after the retention worker deletes the
    object. The URL itself is never persisted or returned from a list endpoint.
    """
    attempt = reviewable_attempt(db, user.id, attempt_id)
    recording = db.scalar(select(Recording).where(Recording.attempt_id == attempt.id))
    now = datetime.now(timezone.utc)
    deadline = recording.retention_deadline if recording else None
    # SQLite drops offsets in lightweight tests; PostgreSQL preserves them.
    # Compare a normalized UTC instant so the privacy boundary is identical.
    if deadline is not None and deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    if (
        not recording
        or recording.deletion_status in {"deleted", "deleting"}
        or (deadline is not None and deadline <= now)
    ):
        raise DomainError("recording_unavailable", "This recording is no longer available for playback", 410)
    if recording.storage_provider != storage.provider_name:
        raise DomainError("recording_unavailable", "This recording cannot be played from the configured storage provider", 409)
    try:
        instruction = storage.create_download(object_key=recording.object_key)
    except Exception as exc:
        log.info("recording_playback_instruction_failed provider=%s", storage.provider_name)
        raise DomainError("recording_unavailable", "This recording is temporarily unavailable for playback", 503) from exc
    expires_at = now + instruction.expires_in
    return {"url": instruction.url, "expiresAt": expires_at, "contentType": recording.content_type}


@app.get("/v1/attempts/{attempt_id}/comparison")
def comparison(attempt_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Compare a completed retry with its source using persisted evidence only."""
    selected = reviewable_attempt(db, user.id, attempt_id)
    if selected.retry_of_attempt_id:
        original = owned_attempt(db, user.id, selected.retry_of_attempt_id)
        retry_attempt = selected
    else:
        retry_attempt = db.scalar(select(Attempt).where(
            Attempt.user_id == user.id,
            Attempt.retry_of_attempt_id == selected.id,
            Attempt.status == "completed",
        ).order_by(Attempt.ordinal.desc(), Attempt.completed_at.desc()))
        original = selected
    if retry_attempt is None:
        raise DomainError("comparison_not_available", "Complete a retry of this challenge to compare attempts", 409)
    assignment = db.get(Assignment, original.assignment_id)
    return {
        "challenge": challenge_view(db.get(Challenge, assignment.challenge_id)),
        "original": _comparison_evidence(db, original),
        "retry": _comparison_evidence(db, retry_attempt),
    }
@app.post("/sessions/{attempt_id}/retry",status_code=201,include_in_schema=False)
def retry(attempt_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    source=owned_attempt(db,user.id,attempt_id)
    if source.status!="completed": raise DomainError("retry_not_available","Complete analysis before retrying",409)
    attempt=Attempt(user_id=user.id,assignment_id=source.assignment_id,retry_of_attempt_id=source.id,comparison_group_id=source.comparison_group_id,ordinal=source.ordinal+1); db.add(attempt); db.commit(); return attempt_view(attempt,db)

@app.get("/v1/progress")
@app.get("/progress",include_in_schema=False)
def progress(user:User=Depends(current_user),db:Session=Depends(get_db)): return {"attempts":[attempt_view(a,db) for a in db.scalars(select(Attempt).where(Attempt.user_id==user.id, Attempt.hidden_at.is_(None)).order_by(Attempt.created_at.desc()))]}

@app.delete("/v1/attempts/{attempt_id}/review", status_code=204)
def hide_review(attempt_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    attempt = owned_attempt(db, user.id, attempt_id)
    if attempt.status not in {"completed", "analysis_failed"}:
        raise DomainError("review_not_available", "Only completed or failed analysis reviews can be hidden", 409)
    attempt.hidden_at = datetime.now(timezone.utc)
    db.commit()
@app.get("/v1/progress/skills")
@app.get("/progress/skills",include_in_schema=False)
def skills(user:User=Depends(current_user),db:Session=Depends(get_db)): return {"skills":[{"skill":s.skill,"estimatedLevel":s.estimated_level,"confidence":s.confidence,"modelVersion":s.model_version} for s in db.scalars(select(SkillState).where(SkillState.user_id==user.id))]}
def dictionary_entry_view(entry: DictionaryEntry | None) -> dict | None:
    if not entry:
        return None
    return {"language": entry.language, "term": entry.normalized_term, "payload": entry.payload,
            "source": entry.source, "fetchedAt": entry.fetched_at, "expiresAt": entry.expires_at}


def vocabulary_view(item: VocabularyItem, db: Session) -> dict:
    observation_count, last_observed_at = db.execute(select(
        func.count(VocabularyObservation.id), func.max(VocabularyObservation.observed_at),
    ).where(VocabularyObservation.vocabulary_item_id == item.id)).one()
    return {"id": item.id, "word": item.word, "practiceStatus": item.practice_status,
            "dictionary": dictionary_entry_view(db.get(DictionaryEntry, item.dictionary_entry_id) if item.dictionary_entry_id else None),
            "practiceEvidence": {"exactTargetUseCount": observation_count, "lastObservedAt": last_observed_at}}


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
