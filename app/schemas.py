from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
class Camel(BaseModel): model_config=ConfigDict(alias_generator=lambda s: ''.join([s.split('_')[0]]+[x.title() for x in s.split('_')[1:]]), populate_by_name=True)
class SignUp(Camel): email: EmailStr; password: str=Field(min_length=8,max_length=128); accepted_terms: bool
class SignIn(Camel): email: EmailStr; password: str
class ActivationResend(Camel): email: EmailStr
class Preferences(Camel): preferences: dict
class CreateAttempt(Camel):
    """Preflight binds one recording checksum and media type to a signed upload."""
    content_type: str = "audio/webm"
    checksum_sha256: str = Field(min_length=64, max_length=64)
    retry_of_attempt_id: str | None = None

    @field_validator("checksum_sha256")
    @classmethod
    def checksum_is_sha256_hex(cls, value: str) -> str:
        if any(character not in "0123456789abcdef" for character in value.lower()):
            raise ValueError("checksumSha256 must be a SHA-256 hexadecimal digest")
        return value.lower()


class UploadComplete(Camel):
    object_key: str=Field(min_length=1,max_length=512)
    duration_seconds: float=Field(gt=0,le=600)
    content_type: str
    byte_size: int=Field(gt=0)
class ChallengeCreate(Camel): prompt: str=Field(min_length=10); preparation_guidance: str; target_skills: list[str]; difficulty: int=Field(ge=1,le=5); target_duration_seconds: int=Field(ge=15,le=600)
class VocabularyCreate(Camel):
    word: str=Field(min_length=1,max_length=200)
    lookup: bool = True
    language: str = Field(default="en", min_length=2, max_length=16)

    @field_validator("language")
    @classmethod
    def only_english_is_supported(cls, value: str) -> str:
        if value.casefold() != "en":
            raise ValueError("Only English dictionary lookup is currently supported")
        return "en"


class VocabularyUpdate(Camel):
    practice_status: str = Field(min_length=1, max_length=30)

    @field_validator("practice_status")
    @classmethod
    def valid_practice_status(cls, value: str) -> str:
        normalized = value.casefold().strip()
        if normalized not in {"new", "learning", "practicing", "mastered"}:
            raise ValueError("practiceStatus must be new, learning, practicing, or mastered")
        return normalized
