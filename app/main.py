import logging
from datetime import datetime, timezone
from uuid import UUID
from fastapi import BackgroundTasks, Depends, FastAPI, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core import DomainError, configure_logging, create_token, decode_token, domain_error_handler, http_error_handler, password_hash
from app.db import Base, engine, get_db
from app.models import AnalysisResult, AnalysisRun, Assignment, Attempt, Challenge, SkillState, User, VocabularyItem
from app.schemas import ChallengeCreate, Preferences, SignIn, SignUp, UploadComplete, VocabularyCreate
from app.services import job_queue, owned_attempt, process_job

configure_logging(); log=logging.getLogger("oratry.api")
app=FastAPI(title="Oratry API",version="1.0")
app.add_exception_handler(DomainError,domain_error_handler); from fastapi import HTTPException; app.add_exception_handler(HTTPException,http_error_handler)
bearer=HTTPBearer()
def current_user(credentials:HTTPAuthorizationCredentials=Depends(bearer),db:Session=Depends(get_db)):
    user=db.get(User,str(decode_token(credentials.credentials)))
    if not user: raise DomainError("not_found","Resource not found",404)
    return user
def user_view(user): return {"id":user.id,"email":user.email,"preferences":user.preferences,"createdAt":user.created_at}
def challenge_view(challenge): return {"id":challenge.id,"version":challenge.version,"prompt":challenge.prompt,"preparationGuidance":challenge.preparation_guidance,"targetSkills":challenge.target_skills,"difficulty":challenge.difficulty,"targetDurationSeconds":challenge.target_duration_seconds}
def attempt_view(attempt,db):
    assignment=db.get(Assignment,attempt.assignment_id); return {"id":attempt.id,"status":attempt.status,"assignmentId":attempt.assignment_id,"createdAt":attempt.created_at,"challenge":challenge_view(db.get(Challenge,assignment.challenge_id))}
@app.on_event("startup")
def startup(): Base.metadata.create_all(engine)

@app.post("/v1/auth/sign-up",status_code=201)
@app.post("/auth/signup",status_code=201,include_in_schema=False)
def signup(body:SignUp,db:Session=Depends(get_db)):
    if not body.accepted_terms: raise DomainError("terms_required","Terms must be accepted")
    if db.scalar(select(User).where(User.email==str(body.email).lower())): raise DomainError("email_taken","An account already exists for this email",409)
    user=User(email=str(body.email).lower(),password_hash=password_hash.hash(body.password),accepted_terms=True); db.add(user); db.commit(); db.refresh(user)
    return {"user":user_view(user),"session":{"accessToken":create_token(UUID(user.id)),"tokenType":"bearer"}}
@app.post("/v1/auth/sign-in")
@app.post("/auth/login",include_in_schema=False)
def login(body:SignIn,db:Session=Depends(get_db)):
    user=db.scalar(select(User).where(User.email==str(body.email).lower()))
    if not user or not password_hash.verify(body.password,user.password_hash): raise DomainError("invalid_credentials","Invalid email or password",401)
    return {"user":user_view(user),"session":{"accessToken":create_token(UUID(user.id)),"tokenType":"bearer"}}
@app.get("/v1/me")
@app.get("/me",include_in_schema=False)
def me(user:User=Depends(current_user)): return user_view(user)
@app.patch("/v1/me")
@app.patch("/me/preferences",include_in_schema=False)
def patch_me(body:Preferences,user:User=Depends(current_user),db:Session=Depends(get_db)): user.preferences=body.preferences; db.commit(); return user_view(user)

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
def create_attempt(assignment_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    assignment=db.scalar(select(Assignment).where(Assignment.id==assignment_id,Assignment.user_id==user.id))
    if not assignment: raise DomainError("not_found","Resource not found",404)
    attempt=Attempt(user_id=user.id,assignment_id=assignment.id); db.add(attempt); db.commit()
    return {**attempt_view(attempt,db),"upload":{"method":"PUT","objectKey":f"private/{user.id}/{attempt.id}/raw","url":None,"headers":{}}}
@app.post("/v1/sessions",status_code=201,include_in_schema=False)
def create_session(assignment_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)): return create_attempt(assignment_id,user,db)
@app.post("/v1/attempts/{attempt_id}/upload-complete",status_code=202)
@app.post("/sessions/{attempt_id}/upload",status_code=202,include_in_schema=False)
def upload_complete(attempt_id:str,body:UploadComplete,user:User=Depends(current_user),db:Session=Depends(get_db)):
    attempt=owned_attempt(db,user.id,attempt_id)
    if attempt.status!="uploading": raise DomainError("invalid_state","This attempt cannot accept an upload",409)
    if body.content_type not in {"audio/webm","audio/mpeg","audio/wav","audio/mp4"}: raise DomainError("unsupported_media","Unsupported audio content type")
    expected=f"private/{user.id}/{attempt.id}/" 
    if not body.object_key.startswith(expected): raise DomainError("invalid_upload","Upload key is not authorized",403)
    attempt.object_key,attempt.checksum,attempt.duration_seconds,attempt.content_type=body.object_key,body.checksum,body.duration_seconds,body.content_type; attempt.status="queued"; attempt.sealed_at=datetime.now(timezone.utc); run=AnalysisRun(attempt_id=attempt.id,version=1); db.add(run); db.commit(); job_queue.enqueue_attempt_analysis(attempt.id)
    return {"id":attempt.id,"status":"queued"}
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
@app.get("/v1/vocabulary")
@app.get("/vocabulary",include_in_schema=False)
def vocabulary(user:User=Depends(current_user),db:Session=Depends(get_db)): return {"items":[{"id":v.id,"word":v.word,"practiceStatus":v.practice_status} for v in db.scalars(select(VocabularyItem).where(VocabularyItem.user_id==user.id))]}
@app.post("/v1/vocabulary",status_code=201)
def add_vocabulary(body:VocabularyCreate,user:User=Depends(current_user),db:Session=Depends(get_db)): v=VocabularyItem(user_id=user.id,word=body.word.strip()); db.add(v); db.commit(); return {"id":v.id,"word":v.word,"practiceStatus":v.practice_status}
@app.get("/v1/vocabulary/{word}")
def get_word(word:str,user:User=Depends(current_user),db:Session=Depends(get_db)): 
    v=db.scalar(select(VocabularyItem).where(VocabularyItem.user_id==user.id,VocabularyItem.word==word));
    if not v: raise DomainError("not_found","Resource not found",404)
    return {"id":v.id,"word":v.word,"practiceStatus":v.practice_status}
@app.post("/v1/vocabulary/{word}/practice")
def practice_word(word:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    v=db.scalar(select(VocabularyItem).where(VocabularyItem.user_id==user.id,VocabularyItem.word==word));
    if not v: raise DomainError("not_found","Resource not found",404)
    v.practice_status="practicing"; db.commit(); return {"id":v.id,"word":v.word,"practiceStatus":v.practice_status}
