from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db import Base
from app.main import app, get_db
from app.services import process_job

def test_recording_to_completed_feedback_flow(tmp_path):
    engine=create_engine(f"sqlite:///{tmp_path / 'test.db'}",connect_args={"check_same_thread":False})
    Base.metadata.create_all(engine); Local=sessionmaker(bind=engine,autoflush=False,autocommit=False)
    def override():
        db=Local()
        try: yield db
        finally: db.close()
    app.dependency_overrides[get_db]=override
    try:
        with TestClient(app) as client:
            sign_up=client.post("/v1/auth/sign-up",json={"email":"speaker@example.com","password":"valid-password","acceptedTerms":True})
            assert sign_up.status_code==201
            headers={"Authorization":"Bearer "+sign_up.json()["session"]["accessToken"]}
            challenge=client.post("/v1/challenges/generate",headers=headers,json={"prompt":"Explain a decision you made and defend it.","preparationGuidance":"Use a clear beginning, middle, and end.","targetSkills":["structure","fluency"],"difficulty":2,"targetDurationSeconds":90}).json()
            recommended=client.get("/v1/challenges/recommended",headers=headers).json()
            assert recommended["challenge"]["id"]==challenge["id"]
            attempt=client.post(f"/v1/assignments/{recommended['assignmentId']}/attempts",headers=headers).json()
            complete=client.post(f"/v1/attempts/{attempt['id']}/upload-complete",headers=headers,json={"objectKey":attempt["upload"]["objectKey"],"checksum":"a"*64,"durationSeconds":60,"contentType":"audio/webm"})
            assert complete.status_code==202
            with Local() as worker_db:
                process_job(worker_db, attempt["id"])
            result=client.get(f"/v1/attempts/{attempt['id']}/result",headers=headers)
            assert result.status_code==200
            assert result.json()["scorecard"]["overall"]==72
            assert result.json()["coachingRecommendation"]["focusSkill"]=="language"
            skill_states=client.get("/v1/progress/skills",headers=headers).json()["skills"]
            assert len(skill_states)==5
    finally: app.dependency_overrides.clear()

def test_attempt_authorization_hides_other_users(tmp_path):
    engine=create_engine(f"sqlite:///{tmp_path / 'auth.db'}",connect_args={"check_same_thread":False}); Base.metadata.create_all(engine); Local=sessionmaker(bind=engine)
    def override():
        db=Local()
        try: yield db
        finally: db.close()
    app.dependency_overrides[get_db]=override
    try:
        with TestClient(app) as client:
            def token(email): return client.post("/v1/auth/sign-up",json={"email":email,"password":"valid-password","acceptedTerms":True}).json()["session"]["accessToken"]
            first={"Authorization":"Bearer "+token("one@example.com")}; second={"Authorization":"Bearer "+token("two@example.com")}
            challenge=client.post("/v1/challenges/generate",headers=first,json={"prompt":"Tell a story with a clear ending.","preparationGuidance":"Prepare.","targetSkills":["structure"],"difficulty":1,"targetDurationSeconds":60}).json()
            assignment=client.get("/v1/challenges/recommended",headers=first).json()["assignmentId"]; attempt=client.post(f"/v1/assignments/{assignment}/attempts",headers=first).json()
            assert client.get(f"/v1/attempts/{attempt['id']}",headers=second).status_code==404
    finally: app.dependency_overrides.clear()
