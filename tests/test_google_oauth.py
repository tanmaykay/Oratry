from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db import Base, get_db
from app.identity import ExternalProfile
from app.main import app, get_google_identity_provider
from app.models import ExternalIdentity, OAuthLoginCode, User


class FakeGoogleProvider:
    def authorization_url(self, *, state: str, code_challenge: str) -> str:
        return f"https://accounts.example.test/authorize?state={state}&challenge={code_challenge}"

    def exchange(self, *, code: str, code_verifier: str) -> ExternalProfile:
        assert code == "provider-code" and code_verifier
        return ExternalProfile("google", "google-subject-1", "speaker@example.com")


def _client(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'google-oauth.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_db():
        db = Local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_google_identity_provider] = FakeGoogleProvider
    return TestClient(app), Local


def _callback(client: TestClient, *, accepted_terms: bool):
    started = client.get("/v1/auth/google/start", params={"accepted_terms": accepted_terms}, follow_redirects=False)
    assert started.status_code == 302
    state = parse_qs(urlparse(started.headers["location"]).query)["state"][0]
    return client.get("/v1/auth/google/callback", params={"state": state, "code": "provider-code"}, follow_redirects=False)


def test_google_callback_creates_verified_identity_and_one_time_handoff(tmp_path):
    client, Local = _client(tmp_path)
    try:
        with client:
            callback = _callback(client, accepted_terms=True)
            assert callback.status_code == 302
            handoff = parse_qs(urlparse(callback.headers["location"]).query)["code"][0]
            assert "accessToken" not in callback.headers["location"]
            completed = client.post("/v1/auth/google/complete", json={"code": handoff})
            assert completed.status_code == 200
            assert completed.json()["user"]["email"] == "speaker@example.com"
            assert completed.json()["user"]["emailVerifiedAt"]
            assert client.post("/v1/auth/google/complete", json={"code": handoff}).status_code == 400
            with Local() as db:
                assert db.scalar(select(ExternalIdentity)).subject == "google-subject-1"
                assert db.scalar(select(OAuthLoginCode)).consumed_at is not None
    finally:
        app.dependency_overrides.clear()


def test_google_new_account_requires_terms_but_existing_identity_can_sign_in(tmp_path):
    client, Local = _client(tmp_path)
    try:
        with client:
            denied = _callback(client, accepted_terms=False)
            assert parse_qs(urlparse(denied.headers["location"]).query)["error"] == ["terms_required"]
            _callback(client, accepted_terms=True)
            with Local() as db:
                assert db.scalar(select(User)).accepted_terms is True
    finally:
        app.dependency_overrides.clear()
