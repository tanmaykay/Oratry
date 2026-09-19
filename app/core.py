from datetime import datetime, timedelta, timezone
from uuid import UUID
import logging
import sys
import jwt
from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import model_validator
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
    r2_endpoint_url: str | None = None
    r2_bucket: str | None = None
    r2_access_key_id: str | None = None
    r2_secret_access_key: str | None = None
    stt_provider: str = "demo"
    deepgram_api_key: str | None = None
    deepgram_model: str = "nova-3"
    llm_provider: str = "rules"
    openai_api_key: str | None = None
    evaluator_model: str = "gpt-5.6-luna"
    evaluator_reasoning_effort: str = "low"

    @model_validator(mode="after")
    def validate_deployment_settings(self):
        if self.recording_retention_hours <= 0:
            raise ValueError("RECORDING_RETENTION_HOURS must be greater than zero")
        if self.app_environment.casefold() not in {"local", "test"}:
            if self.database_url.startswith("sqlite"):
                raise ValueError("DATABASE_URL must use PostgreSQL outside local/test environments")
            if self.jwt_secret == "change-this-in-production-with-a-32-byte-secret" or len(self.jwt_secret) < 32:
                raise ValueError("JWT_SECRET must be a unique value of at least 32 characters outside local/test environments")
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
