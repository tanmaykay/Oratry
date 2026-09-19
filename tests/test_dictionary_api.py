from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, get_db
from app.dictionary import DictionaryLookup
from app.email import DevelopmentOutboxEmailProvider
from app.main import app, get_dictionary_provider, get_email_provider


class FakeDictionaryProvider:
    def __init__(self):
        self.calls: list[str] = []

    def lookup_english(self, term: str):
        self.calls.append(term)
        if term == "missing":
            return None
        return DictionaryLookup(
            payload={"term": term, "meanings": [{"partOfSpeech": "noun", "definitions": ["A test definition."]}]},
            source="fake-dictionary", source_metadata={"fixture": True},
        )


def _client(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'dictionary.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    local = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    outbox = DevelopmentOutboxEmailProvider()
    dictionary = FakeDictionaryProvider()

    def override_db():
        db = local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_email_provider] = lambda: outbox
    app.dependency_overrides[get_dictionary_provider] = lambda: dictionary
    return TestClient(app), outbox, dictionary


def _headers(client, outbox):
    client.post("/v1/auth/sign-up", json={"email": "dictionary@example.com", "password": "valid-password", "acceptedTerms": True})
    token = parse_qs(urlparse(outbox.messages[-1].activation_url).query)["token"][0]
    activated = client.get("/v1/auth/activate", params={"token": token}).json()
    return {"Authorization": f"Bearer {activated['session']['accessToken']}"}


def test_vocabulary_uses_shared_cached_dictionary_entry_and_opaque_mutations(tmp_path):
    client, outbox, dictionary = _client(tmp_path)
    try:
        with client:
            headers = _headers(client, outbox)
            first = client.post("/v1/vocabulary", headers=headers, json={"word": "  Concise  "})
            assert first.status_code == 201
            item = first.json()
            assert item["word"] == "Concise"
            assert item["dictionary"]["payload"]["meanings"][0]["definitions"] == ["A test definition."]
            assert dictionary.calls == ["concise"]
            second = client.post("/v1/vocabulary", headers=headers, json={"word": "concise"})
            assert second.status_code == 201
            assert dictionary.calls == ["concise"]
            updated = client.patch(f"/v1/vocabulary/{item['id']}", headers=headers, json={"practiceStatus": "practicing"})
            assert updated.json()["practiceStatus"] == "practicing"
            assert client.delete(f"/v1/vocabulary/{item['id']}", headers=headers).status_code == 204
            assert client.get(f"/v1/vocabulary/{item['id']}", headers=headers).status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_dictionary_lookup_handles_unknown_terms_and_ownership_is_opaque(tmp_path):
    client, outbox, _ = _client(tmp_path)
    try:
        with client:
            headers = _headers(client, outbox)
            assert client.get("/v1/dictionary/missing", headers=headers).json()["dictionary"] is None
            created = client.post("/v1/vocabulary", headers=headers, json={"word": "unavailable", "lookup": False}).json()
            assert created["dictionary"] is None
            assert client.patch(f"/v1/vocabulary/{created['id']}", headers={"Authorization": "Bearer invalid"}, json={"practiceStatus": "mastered"}).status_code == 401
            assert client.post("/v1/vocabulary", headers=headers, json={"word": "word", "language": "fr"}).status_code == 422
    finally:
        app.dependency_overrides.clear()
