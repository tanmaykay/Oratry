from datetime import datetime, timedelta, timezone
from uuid import UUID
import logging
import sys
import jwt
from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pwdlib import PasswordHash

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_environment: str = "local"
    database_url: str = "sqlite:///./oratry.db"
    jwt_secret: str = "change-this-in-production-with-a-32-byte-secret"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 1440
    upload_max_bytes: int = 25 * 1024 * 1024
    recording_retention_hours: int = 24
    object_storage_provider: str = "local"
    # Prefer the R2_* names. The aliases retain compatibility with the
    # existing Cloudflare configuration names used during local setup.
    r2_endpoint_url: str | None = Field(default=None, validation_alias=AliasChoices(
        "R2_ENDPOINT_URL", "R2_BUCKET_API_ENDPOINT", "CLOUDFLARE_S3_API_ENDPOINT"
    ))
    r2_bucket: str | None = Field(default=None, validation_alias=AliasChoices(
        "R2_BUCKET", "R2_BUCKET_NAME"
    ))
    r2_access_key_id: str | None = Field(default=None, validation_alias=AliasChoices(
        "R2_ACCESS_KEY_ID", "CLOUDFLARE_ACCESS_KEY_ID"
    ))
    r2_secret_access_key: str | None = Field(default=None, validation_alias=AliasChoices(
        "R2_SECRET_ACCESS_KEY", "CLOUDFLARE_SECRET_ACCESS_KEY"
    ))
    stt_provider: str = "demo"
    deepgram_api_key: str | None = None
    deepgram_model: str = "nova-3"
    llm_provider: str = "rules"
    openai_api_key: str | None = None
    gemini_api_key: str | None = None
    gemini_evaluator_model: str = "gemini-3.5-flash-lite"
    evaluator_model: str = "gpt-5.6-luna"
    evaluator_reasoning_effort: str = "low"
    email_provider: str = "development_outbox"
    activation_url_base: str = "http://127.0.0.1:3000/activate"
    activation_token_minutes: int = 60 * 24
    activation_resend_min_seconds: int = 60
    activation_resend_max_per_hour: int = 5
    resend_api_key: str | None = None
    resend_from_address: str | None = None
    dictionary_provider: str = "free_dictionary_api"
    dictionary_cache_hours: int = 24 * 7
    # Analysis worker operations and provider-price estimates.  Prices are
    # intentionally deployment configuration: provider pricing changes must
    # not silently change historic accounting or business logic.
    analysis_job_lease_seconds: int = 120
    analysis_llm_timeout_seconds: float = 60.0
    analysis_worker_poll_seconds: float = 2.0
    analysis_cost_version: str = "unconfigured"
    stt_cost_usd_per_audio_minute: float | None = None
    llm_input_cost_usd_per_million_tokens: float | None = None
    llm_output_cost_usd_per_million_tokens: float | None = None

    @model_validator(mode="after")
    def validate_deployment_settings(self):
        if self.recording_retention_hours <= 0:
            raise ValueError("RECORDING_RETENTION_HOURS must be greater than zero")
        if self.activation_token_minutes <= 0:
            raise ValueError("ACTIVATION_TOKEN_MINUTES must be greater than zero")
        if self.activation_resend_min_seconds < 0 or self.activation_resend_max_per_hour <= 0:
            raise ValueError("Activation resend limits must be positive")
        if self.dictionary_cache_hours <= 0:
            raise ValueError("DICTIONARY_CACHE_HOURS must be greater than zero")
        # Deepgram's prerecorded adapter has a 60s request timeout. Leave a
        # margin so no paid STT call can outlive its job lease.
        if self.analysis_job_lease_seconds < 75:
            raise ValueError("ANALYSIS_JOB_LEASE_SECONDS must be at least 75")
        if self.analysis_llm_timeout_seconds <= 0 or self.analysis_llm_timeout_seconds >= self.analysis_job_lease_seconds:
            raise ValueError("ANALYSIS_LLM_TIMEOUT_SECONDS must be positive and below the job lease")
        if self.analysis_worker_poll_seconds <= 0:
            raise ValueError("ANALYSIS_WORKER_POLL_SECONDS must be greater than zero")
        for value in (
            self.stt_cost_usd_per_audio_minute,
            self.llm_input_cost_usd_per_million_tokens,
            self.llm_output_cost_usd_per_million_tokens,
        ):
            if value is not None and value < 0:
                raise ValueError("Provider cost settings must be non-negative")
        if self.app_environment.casefold() not in {"local", "test"}:
            if self.database_url.startswith("sqlite"):
                raise ValueError("DATABASE_URL must use PostgreSQL outside local/test environments")
            if self.jwt_secret == "change-this-in-production-with-a-32-byte-secret" or len(self.jwt_secret) < 32:
                raise ValueError("JWT_SECRET must be a unique value of at least 32 characters outside local/test environments")
            if self.email_provider.casefold() == "development_outbox":
                raise ValueError("EMAIL_PROVIDER=development_outbox is only allowed in local/test environments")
            if self.email_provider.casefold() == "resend" and not (self.resend_api_key and self.resend_from_address):
                raise ValueError("RESEND_API_KEY and RESEND_FROM_ADDRESS are required when EMAIL_PROVIDER=resend")
        return self
settings = Settings()
password_hash = PasswordHash.recommended()

def configure_logging():
    logging.basicConfig(level=logging.INFO, stream=sys.stdout, format='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}')
def create_token(user_id: UUID) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": str(user_id), "iat": now, "exp": now + timedelta(minutes=settings.access_token_minutes)}, settings.jwt_secret, algorithm=settings.jwt_algorithm)
def decode_token(token: str) -> UUID:
    try: return UUID(jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])["sub"])
    except (jwt.PyJWTError, KeyError, ValueError) as exc: raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials") from exc
class DomainError(Exception):
    def __init__(self, code, message, status_code=400): self.code, self.message, self.status_code = code, message, status_code
async def domain_error_handler(_: Request, exc: DomainError): return JSONResponse(status_code=exc.status_code, content={"code": exc.code, "message": exc.message})
async def http_error_handler(_: Request, exc: HTTPException): return JSONResponse(status_code=exc.status_code, content={"code": "unauthorized" if exc.status_code == 401 else "request_error", "message": str(exc.detail)})
