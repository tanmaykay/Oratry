from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field
class Camel(BaseModel): model_config=ConfigDict(alias_generator=lambda s: ''.join([s.split('_')[0]]+[x.title() for x in s.split('_')[1:]]), populate_by_name=True)
class SignUp(Camel): email: EmailStr; password: str=Field(min_length=8,max_length=128); accepted_terms: bool
class SignIn(Camel): email: EmailStr; password: str
class Preferences(Camel): preferences: dict
class UploadComplete(Camel): object_key: str=Field(min_length=1,max_length=512); checksum: str=Field(min_length=8,max_length=128); duration_seconds: float=Field(gt=0,le=600); content_type: str
class ChallengeCreate(Camel): prompt: str=Field(min_length=10); preparation_guidance: str; target_skills: list[str]; difficulty: int=Field(ge=1,le=5); target_duration_seconds: int=Field(ge=15,le=600)
class VocabularyCreate(Camel): word: str=Field(min_length=1,max_length=200)
