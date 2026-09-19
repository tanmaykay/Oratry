from app.dictionary import (
    DatamuseDictionaryProvider,
    DictionaryLookup,
    DictionaryProviderError,
    ResilientDictionaryProvider,
)


class FailingPrimary:
    def lookup_english(self, _term):
        raise DictionaryProviderError("primary unavailable")


class MissingPrimary:
    def lookup_english(self, _term):
        return None


class TrackingFallback:
    def __init__(self):
        self.calls = 0

    def lookup_english(self, term):
        self.calls += 1
        return DictionaryLookup(payload={"term": term, "meanings": []}, source="fallback", source_metadata={})


def test_resilient_provider_uses_datamuse_style_fallback_only_after_primary_failure():
    fallback = TrackingFallback()
    result = ResilientDictionaryProvider(FailingPrimary(), fallback).lookup_english("concise")
    assert fallback.calls == 1
    assert result.source == "fallback"
    assert result.source_metadata["fallbackFrom"] == "dictionaryapi.dev"


def test_resilient_provider_does_not_fallback_for_definitive_primary_not_found():
    fallback = TrackingFallback()
    assert ResilientDictionaryProvider(MissingPrimary(), fallback).lookup_english("nonword") is None
    assert fallback.calls == 0


def test_datamuse_mapping_keeps_only_actual_definitions_and_synonyms():
    urls = []

    def fetch(url):
        urls.append(url)
        if "rel_syn" in url:
            return [{"word": "brief"}, {"word": "succinct"}]
        return [{"word": "concise", "defs": ["adj\tbrief and to the point", "n\ta summary"]}]

    result = DatamuseDictionaryProvider(fetch_json=fetch).lookup_english("concise")
    assert len(urls) == 2
    assert result.source == "datamuse.com"
    assert result.payload == {
        "term": "concise",
        "meanings": [
            {"partOfSpeech": "adj", "definitions": ["brief and to the point"]},
            {"partOfSpeech": "n", "definitions": ["a summary"]},
        ],
        "synonyms": ["brief", "succinct"],
    }
    assert "phonetic" not in result.payload
    assert "examples" not in result.payload
    assert "antonyms" not in result.payload
