from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db import Base, get_db
from app.email import DevelopmentOutboxEmailProvider, DisabledEmailProvider
from app.main import app, get_email_provider
from app.models import EmailVerificationChallenge, User


def _client(tmp_path, provider=None):
    engine = create_engine(f"sqlite:///{tmp_path / 'activation.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_db():
        db = local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_email_provider] = lambda: provider or DevelopmentOutboxEmailProvider()
    return TestClient(app), local


def _token(provider):
    return parse_qs(urlparse(provider.messages[-1].activation_url).query)["token"][0]


def test_signup_creates_unverified_user_and_never_issues_session(tmp_path):
    provider = DevelopmentOutboxEmailProvider()
    client, local = _client(tmp_path, provider)
    try:
        with client:
            response = client.post("/v1/auth/sign-up", json={"email": "new@example.com", "password": "valid-password", "acceptedTerms": True})
            assert response.status_code == 201
            assert response.json()["activationRequired"] is True
            assert "session" not in response.json()
            assert "activationUrl" not in response.text
            assert len(provider.messages) == 1
            with local() as db:
                user = db.scalar(select(User).where(User.email == "new@example.com"))
                challenge = db.scalar(select(EmailVerificationChallenge).where(EmailVerificationChallenge.user_id == user.id))
                assert user.email_verified_at is None
                assert len(challenge.token_digest) == 64
                assert provider.messages[0].activation_url not in challenge.token_digest
            assert client.post("/v1/auth/sign-in", json={"email": "new@example.com", "password": "valid-password"}).status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_activation_consumes_link_once_and_allows_signin(tmp_path):
    provider = DevelopmentOutboxEmailProvider()
    client, _ = _client(tmp_path, provider)
    try:
        with client:
            client.post("/v1/auth/sign-up", json={"email": "activate@example.com", "password": "valid-password", "acceptedTerms": True})
            activated = client.get("/v1/auth/activate", params={"token": _token(provider)})
            assert activated.status_code == 200
            assert activated.json()["user"]["emailVerifiedAt"]
            assert activated.json()["session"]["accessToken"]
            replay = client.get("/v1/auth/activate", params={"token": _token(provider)})
            assert replay.status_code == 400
            assert replay.json()["code"] == "activation_link_invalid"
            assert client.post("/v1/auth/sign-in", json={"email": "activate@example.com", "password": "valid-password"}).status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_resend_is_generic_and_invalidates_prior_link(tmp_path):
    provider = DevelopmentOutboxEmailProvider()
    client, local = _client(tmp_path, provider)
    try:
        with client:
            client.post("/v1/auth/sign-up", json={"email": "resend@example.com", "password": "valid-password", "acceptedTerms": True})
            original = _token(provider)
            # Current-scope rate limiting makes an immediate request look like
            # any other accepted resend without issuing a fresh token.
            assert client.post("/v1/auth/resend-activation", json={"email": "resend@example.com"}).json() == {"accepted": True}
            assert client.post("/v1/auth/resend-activation", json={"email": "unknown@example.com"}).json() == {"accepted": True}
            assert len(provider.messages) == 1
            with local() as db:
                challenge = db.scalar(select(EmailVerificationChallenge))
                challenge.created_at = challenge.created_at.replace(year=challenge.created_at.year - 1)
                db.commit()
            assert client.post("/v1/auth/resend-activation", json={"email": "resend@example.com"}).status_code == 202
            assert len(provider.messages) == 2
            assert client.get("/v1/auth/activate", params={"token": original}).status_code == 400
            assert client.get("/v1/auth/activate", params={"token": _token(provider)}).status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_email_delivery_failure_rolls_back_signup(tmp_path):
    client, local = _client(tmp_path, DisabledEmailProvider())
    try:
        with client:
            result = client.post("/v1/auth/sign-up", json={"email": "failed@example.com", "password": "valid-password", "acceptedTerms": True})
            assert result.status_code == 503
            assert result.json()["code"] == "activation_email_unavailable"
            with local() as db:
                assert db.scalar(select(User).where(User.email == "failed@example.com")) is None
    finally:
        app.dependency_overrides.clear()
