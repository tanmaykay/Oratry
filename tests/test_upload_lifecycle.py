from datetime import timedelta
from urllib.parse import parse_qs, urlparse
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.db import Base, get_db
from app.main import app, get_object_storage, upload_complete
from app.models import AnalysisRun, Recording
from app.schemas import UploadComplete
from app.storage import ObjectMetadata, UploadInstruction, sha256_hex_to_s3_base64


class FakeStorage:
    provider_name = "fake-private"

    def __init__(self, metadata: ObjectMetadata | None = None):
        self.metadata = metadata
        self.instructions = []

    def create_upload(self, *, object_key, content_type, max_bytes, checksum_sha256):
        self.instructions.append((object_key, content_type, max_bytes, checksum_sha256))
        return UploadInstruction("PUT", "https://storage.example.test/put", object_key,
                                 {"Content-Type": content_type, "x-amz-checksum-sha256": sha256_hex_to_s3_base64(checksum_sha256)}, timedelta(minutes=10))

    def head(self, object_key):
        return self.metadata or ObjectMetadata(object_key, "audio/webm", 123, "b" * 64)

    def delete(self, object_key):
        pass


def _client(tmp_path, storage):
    engine = create_engine(f"sqlite:///{tmp_path / 'upload.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_db():
        db = local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_object_storage] = lambda: storage
    return TestClient(app), local


def _headers_and_assignment(client):
    signed_up = client.post("/v1/auth/sign-up", json={
        "email": "upload@example.com", "password": "valid-password", "acceptedTerms": True,
    }).json()
    messages = client.get("/v1/auth/development-outbox").json()["messages"]
    url = next(message["activationUrl"] for message in reversed(messages) if message["recipient"] == "upload@example.com")
    activated = client.get("/v1/auth/activate", params={"token": parse_qs(urlparse(url).query)["token"][0]}).json()
    headers = {"Authorization": f"Bearer {activated['session']['accessToken']}"}
    client.post("/v1/challenges/generate", headers=headers, json={
        "prompt": "Explain a trade-off you made at work.", "preparationGuidance": "Use one example.",
        "targetSkills": ["structure"], "difficulty": 2, "targetDurationSeconds": 60,
    })
    return headers, client.get("/v1/challenges/recommended", headers=headers).json()["assignmentId"]


def test_issued_upload_is_private_and_completion_persists_verified_recording(tmp_path):
    storage = FakeStorage()
    client, local = _client(tmp_path, storage)
    try:
        with client:
            headers, assignment_id = _headers_and_assignment(client)
            attempt = client.post(f"/v1/assignments/{assignment_id}/attempts", headers=headers,
                                  json={"contentType": "audio/webm", "checksumSha256": "b" * 64})
            assert attempt.status_code == 201
            payload = attempt.json()
            assert payload["upload"]["method"] == "PUT"
            assert payload["upload"]["url"] == "https://storage.example.test/put"
            assert payload["upload"]["objectKey"].endswith(f"/{payload['id']}/raw")
            assert payload["upload"]["headers"] == {
                "Content-Type": "audio/webm", "x-amz-checksum-sha256": sha256_hex_to_s3_base64("b" * 64),
            }
            completed = client.post(f"/v1/attempts/{payload['id']}/upload-complete", headers=headers, json={
                "objectKey": payload["upload"]["objectKey"],
                "durationSeconds": 61, "contentType": "audio/webm", "byteSize": 123,
            })
            assert completed.status_code == 202
            assert completed.json()["queue"] == {"durable": False, "delivery": "in_memory"}
            again = client.post(f"/v1/attempts/{payload['id']}/upload-complete", headers=headers, json={
                "objectKey": payload["upload"]["objectKey"],
                "durationSeconds": 61, "contentType": "audio/webm", "byteSize": 123,
            })
            assert again.status_code == 202
            with local() as db:
                recording = db.scalar(select(Recording))
                assert recording.storage_provider == "fake-private"
                assert recording.retention_deadline is None
                assert recording.deletion_status == "not_scheduled"
                assert db.scalar(select(AnalysisRun)).status == "queued"
    finally:
        app.dependency_overrides.clear()


def test_completion_rejects_nonissued_or_unverified_objects(tmp_path):
    storage = FakeStorage(ObjectMetadata("private/wrong/object/raw", "audio/webm", 123, "b" * 64))
    client, _ = _client(tmp_path, storage)
    try:
        with client:
            headers, assignment_id = _headers_and_assignment(client)
            attempt = client.post(f"/v1/assignments/{assignment_id}/attempts", headers=headers,
                                  json={"checksumSha256": "b" * 64}).json()
            wrong_key = client.post(f"/v1/attempts/{attempt['id']}/upload-complete", headers=headers, json={
                "objectKey": "private/another-user/other/raw",
                "durationSeconds": 60, "contentType": "audio/webm", "byteSize": 123,
            })
            assert wrong_key.status_code == 403
            unverified = client.post(f"/v1/attempts/{attempt['id']}/upload-complete", headers=headers, json={
                "objectKey": attempt["upload"]["objectKey"],
                "durationSeconds": 60, "contentType": "audio/webm", "byteSize": 123,
            })
            assert unverified.status_code == 409
            assert unverified.json()["code"] == "upload_verification_failed"
    finally:
        app.dependency_overrides.clear()


def test_create_attempt_resumes_only_the_active_unsealed_attempt(tmp_path):
    storage = FakeStorage()
    client, _ = _client(tmp_path, storage)
    try:
        with client:
            headers, assignment_id = _headers_and_assignment(client)
            first = client.post(f"/v1/assignments/{assignment_id}/attempts", headers=headers,
                                json={"checksumSha256": "b" * 64}).json()
            second = client.post(f"/v1/assignments/{assignment_id}/attempts", headers=headers,
                                 json={"checksumSha256": "b" * 64}).json()
            assert second["id"] == first["id"]
            changed_type = client.post(f"/v1/assignments/{assignment_id}/attempts", headers=headers,
                                       json={"contentType": "audio/mp4", "checksumSha256": "b" * 64})
            assert changed_type.status_code == 409
            assert changed_type.json()["code"] == "upload_media_type_locked"
            changed_checksum = client.post(f"/v1/assignments/{assignment_id}/attempts", headers=headers,
                                           json={"checksumSha256": "a" * 64})
            assert changed_checksum.status_code == 409
            assert changed_checksum.json()["code"] == "upload_checksum_locked"
    finally:
        app.dependency_overrides.clear()


class _CompletionRaceSession:
    """Simulates a competing request committing the same verified completion."""

    def __init__(self, initial, sealed, recording, run, error):
        self._items = iter((initial, sealed, recording, run))
        self.error = error
        self.rollback_count = 0

    def scalar(self, _statement):
        return next(self._items)

    def add(self, _item):
        pass

    def commit(self):
        raise self.error

    def rollback(self):
        self.rollback_count += 1


def test_upload_complete_recovers_only_a_matching_recording_uniqueness_race():
    attempt_id = "attempt-1"
    object_key = "private/user-1/attempt-1/raw"
    checksum = "b" * 64
    initial = SimpleNamespace(id=attempt_id, status="uploading", content_type="audio/webm", checksum=checksum)
    sealed = SimpleNamespace(id=attempt_id, status="queued", content_type="audio/webm", checksum=checksum)
    recording = SimpleNamespace(object_key=object_key, content_type="audio/webm", byte_size=123, checksum_sha256=checksum)
    session = _CompletionRaceSession(
        initial, sealed, recording, SimpleNamespace(),
        IntegrityError("insert", {}, Exception("UNIQUE constraint failed: recordings.attempt_id")),
    )
    storage = FakeStorage(ObjectMetadata(object_key, "audio/webm", 123, checksum))
    result = upload_complete(
        attempt_id,
        UploadComplete(object_key=object_key, duration_seconds=60, content_type="audio/webm", byte_size=123),
        SimpleNamespace(id="user-1"), session, storage,
    )
    assert result == {"id": attempt_id, "status": "queued", "queue": {"durable": False, "delivery": "in_memory"}}
    assert session.rollback_count == 1


def test_upload_complete_does_not_recover_an_unrelated_integrity_error():
    attempt_id = "attempt-1"
    object_key = "private/user-1/attempt-1/raw"
    checksum = "b" * 64
    initial = SimpleNamespace(id=attempt_id, status="uploading", content_type="audio/webm", checksum=checksum)
    session = _CompletionRaceSession(
        initial, None, None, None,
        IntegrityError("insert", {}, Exception("foreign key violation")),
    )
    storage = FakeStorage(ObjectMetadata(object_key, "audio/webm", 123, checksum))
    try:
        upload_complete(
            attempt_id,
            UploadComplete(object_key=object_key, duration_seconds=60, content_type="audio/webm", byte_size=123),
            SimpleNamespace(id="user-1"), session, storage,
        )
    except IntegrityError:
        pass
    else:
        raise AssertionError("Unrelated integrity errors must not be replayed")
    assert session.rollback_count == 0
