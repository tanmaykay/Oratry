from datetime import timedelta
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.db import Base, get_db
from app.main import app, get_object_storage
from app.models import Assignment, Attempt
from app.personalization.baseline_policy import baseline_assignments
from app.services import CurriculumService
from app.storage import ObjectMetadata, UploadInstruction


class _FakeStorage:
    provider_name = "fake"

    def create_upload(self, *, object_key, content_type, max_bytes, checksum_sha256):
        return UploadInstruction("PUT", "https://storage.example.test/put", object_key, {"Content-Type": content_type}, timedelta(minutes=15))

    def head(self, object_key):
        return ObjectMetadata(object_key, "audio/webm", 10, "a" * 64)

    def delete(self, object_key):
        pass


def _client(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'baseline.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override():
        db = local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override
    app.dependency_overrides[get_object_storage] = _FakeStorage
    return TestClient(app), local


def _headers(client, email="baseline@example.com"):
    response = client.post("/v1/auth/sign-up", json={
        "email": email, "password": "valid-password", "acceptedTerms": True,
    })
    assert response.status_code == 201
    messages = client.get("/v1/auth/development-outbox").json()["messages"]
    url = next(message["activationUrl"] for message in reversed(messages) if message["recipient"] == email)
    activated = client.get("/v1/auth/activate", params={"token": parse_qs(urlparse(url).query)["token"][0]})
    return {"Authorization": f"Bearer {activated.json()['session']['accessToken']}"}


def test_baseline_start_is_idempotent_and_current_assignment_is_ordered(tmp_path):
    client, _ = _client(tmp_path)
    try:
        with client:
            headers = _headers(client)
            first = client.post("/v1/baseline/start", headers=headers)
            second = client.post("/v1/baseline/start", headers=headers)
            assert first.status_code == second.status_code == 201
            assert first.json()["status"] == "in_progress"
            assert [item["reason"] for item in first.json()["assignments"]] == ["baseline"] * 3
            assert [item["challenge"]["id"] for item in first.json()["assignments"]] == [
                "baseline-clarity-v1", "baseline-structure-v1", "baseline-delivery-v1",
            ]
            assert [item["assignmentId"] for item in first.json()["assignments"]] == [
                item["assignmentId"] for item in second.json()["assignments"]
            ]
            current = client.get("/v1/assignments/current", headers=headers)
            assert current.status_code == 200
            assert current.json()["challenge"]["id"] == "baseline-clarity-v1"
    finally:
        app.dependency_overrides.clear()


def test_baseline_advances_only_after_completed_attempt_and_then_recommends(tmp_path):
    client, local = _client(tmp_path)
    try:
        with client:
            headers = _headers(client)
            started = client.post("/v1/baseline/start", headers=headers).json()
            assignment_ids = [item["assignmentId"] for item in started["assignments"]]
            # An uploading attempt cannot advance the baseline.
            first_attempt = client.post(f"/v1/assignments/{assignment_ids[0]}/attempts", headers=headers,
                                        json={"checksumSha256": "a" * 64})
            assert first_attempt.status_code == 201
            assert client.get("/v1/assignments/current", headers=headers).json()["assignmentId"] == assignment_ids[0]

            with local() as db:
                assignments = list(db.scalars(select(Assignment).where(Assignment.id.in_(assignment_ids))))
                for assignment in assignments:
                    db.add(Attempt(user_id=assignment.user_id, assignment_id=assignment.id,
                                   status="completed", comparison_group_id=f"group-{assignment.id}", ordinal=1))
                    assignment.status = "completed"
                db.commit()

            baseline = client.get("/v1/baseline", headers=headers).json()
            assert baseline["status"] == "completed"
            recommended = client.get("/v1/assignments/current", headers=headers)
            assert recommended.status_code == 200
            assert recommended.json()["reason"] == "recommended"
            assert recommended.json()["challenge"]["id"].startswith("practice-")
    finally:
        app.dependency_overrides.clear()


def test_baseline_and_home_are_scoped_to_authenticated_user(tmp_path):
    client, _ = _client(tmp_path)
    try:
        with client:
            first = _headers(client, "first@example.com")
            second = _headers(client, "second@example.com")
            assignment = client.post("/v1/baseline/start", headers=first).json()["assignments"][0]
            assert client.get(f"/v1/challenges/{assignment['challenge']['id']}", headers=second).status_code == 404
            assert client.get("/v1/assignments/current", headers=second).status_code == 409
            home = client.get("/v1/home", headers=first)
            assert home.status_code == 200
            assert home.json()["onboardingState"] == "in_progress"
            assert home.json()["currentAssignment"]["assignmentId"] == assignment["assignmentId"]
    finally:
        app.dependency_overrides.clear()


def test_baseline_attempts_must_follow_the_persisted_order(tmp_path):
    client, local = _client(tmp_path)
    try:
        with client:
            headers = _headers(client)
            assignments = client.post("/v1/baseline/start", headers=headers).json()["assignments"]
            first, second, third = [item["assignmentId"] for item in assignments]
            future = client.post(f"/v1/assignments/{second}/attempts", headers=headers,
                                 json={"checksumSha256": "a" * 64})
            assert future.status_code == 409
            assert future.json()["code"] == "baseline_assignment_not_current"

            allowed = client.post(f"/v1/assignments/{first}/attempts", headers=headers,
                                  json={"checksumSha256": "a" * 64})
            assert allowed.status_code == 201
            with local() as db:
                attempt = db.get(Attempt, allowed.json()["id"])
                attempt.status = "completed"
                db.commit()

            completed = client.post(f"/v1/assignments/{first}/attempts", headers=headers,
                                    json={"checksumSha256": "a" * 64})
            assert completed.status_code == 409
            next_step = client.post(f"/v1/assignments/{second}/attempts", headers=headers,
                                    json={"checksumSha256": "a" * 64})
            assert next_step.status_code == 201
            assert client.post(f"/v1/assignments/{third}/attempts", headers=headers,
                               json={"checksumSha256": "a" * 64}).status_code == 409
    finally:
        app.dependency_overrides.clear()


def test_baseline_integrity_error_detection_is_narrow():
    expected = IntegrityError(
        "insert", {}, Exception("uq_challenge_assignments_baseline_user_sequence"),
    )
    unrelated = IntegrityError("insert", {}, Exception("foreign key violation"))
    assert CurriculumService._is_baseline_uniqueness_error(expected)
    assert not CurriculumService._is_baseline_uniqueness_error(unrelated)


class _RaceRecoverySession:
    """Minimal session double for the create-or-return race boundary."""

    def __init__(self, recovered_assignments, commit_error):
        self.recovered_assignments = recovered_assignments
        self.commit_error = commit_error
        self.rollback_count = 0
        self.scalars_count = 0

    def scalars(self, _statement):
        self.scalars_count += 1
        # The first read sees no baseline. The post-rollback read sees the
        # complete sequence committed by the competing request.
        return iter([] if self.scalars_count == 1 else self.recovered_assignments)

    def get(self, _model, _identifier):
        return object()

    def add(self, _item):
        pass

    def flush(self):
        pass

    def commit(self):
        raise self.commit_error

    def rollback(self):
        self.rollback_count += 1


def _expected_baseline_assignments(user_id="race-user"):
    return [
        Assignment(
            user_id=user_id,
            challenge_id=item.challenge.id,
            reason=item.reason,
            sequence=item.sequence,
        )
        for item in baseline_assignments()
    ]


def test_baseline_start_recovers_only_the_expected_partial_unique_race():
    recovered = _expected_baseline_assignments()
    session = _RaceRecoverySession(
        recovered,
        IntegrityError("insert", {}, Exception("uq_challenge_assignments_baseline_user_sequence")),
    )

    returned = CurriculumService(session).start_baseline("race-user")

    assert returned == recovered
    assert session.rollback_count == 1
    assert session.scalars_count == 2


def test_baseline_start_reraises_unrelated_integrity_errors():
    session = _RaceRecoverySession(
        _expected_baseline_assignments(),
        IntegrityError("insert", {}, Exception("foreign key violation")),
    )

    try:
        CurriculumService(session).start_baseline("race-user")
    except IntegrityError:
        pass
    else:
        raise AssertionError("Unrelated integrity errors must not be recovered")
    assert session.rollback_count == 1
    assert session.scalars_count == 1
