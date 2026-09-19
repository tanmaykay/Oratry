"""Provider-neutral, cacheable dictionary lookup boundary."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Callable, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import urlopen


class DictionaryProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class DictionaryLookup:
    payload: dict
    source: str
    source_metadata: dict


class DictionaryProvider(Protocol):
    def lookup_english(self, term: str) -> DictionaryLookup | None:
        """Return canonical lexical facts or None when a term is unknown."""


class DisabledDictionaryProvider:
    def lookup_english(self, term: str) -> DictionaryLookup | None:
        raise DictionaryProviderError("Dictionary lookup is not configured")


class FreeDictionaryApiProvider:
    """Adapter for dictionaryapi.dev, retaining only a small canonical payload."""

    endpoint = "https://api.dictionaryapi.dev/api/v2/entries/en"

    def lookup_english(self, term: str) -> DictionaryLookup | None:
        try:
            with urlopen(f"{self.endpoint}/{quote(term, safe='')}", timeout=5.0) as response:
                data = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code == 404:
                return None
            raise DictionaryProviderError("Dictionary source is unavailable") from exc
        except (URLError, TimeoutError, OSError, ValueError) as exc:
            raise DictionaryProviderError("Dictionary source is unavailable") from exc
        if not isinstance(data, list) or not data:
            return None
        entry = data[0]
        meanings = []
        for meaning in entry.get("meanings", []):
            definitions = [item.get("definition") for item in meaning.get("definitions", []) if item.get("definition")]
            if definitions:
                meanings.append({"partOfSpeech": meaning.get("partOfSpeech"), "definitions": definitions[:3]})
        payload = {
            "term": entry.get("word", term),
            "phonetic": entry.get("phonetic"),
            "meanings": meanings,
        }
        return DictionaryLookup(payload=payload, source="dictionaryapi.dev", source_metadata={})


class DatamuseDictionaryProvider:
    """Datamuse fallback with only fields its public API actually supplies."""

    endpoint = "https://api.datamuse.com/words"

    def __init__(self, fetch_json: Callable[[str], list[dict]] | None = None) -> None:
        self._fetch_json = fetch_json or self._fetch

    def lookup_english(self, term: str) -> DictionaryLookup | None:
        exact = self._fetch_json(f"{self.endpoint}?{urlencode({'sp': term, 'md': 'dpr', 'max': 1})}")
        match = next((item for item in exact if item.get("word", "").casefold() == term.casefold()), None)
        if not match:
            return None
        meanings: dict[str | None, list[str]] = {}
        for definition in match.get("defs", []):
            if not isinstance(definition, str):
                continue
            part_of_speech, separator, text = definition.partition("\t")
            if not separator or not text.strip():
                continue
            meanings.setdefault(part_of_speech or None, []).append(text.strip())
        synonyms = self._fetch_json(f"{self.endpoint}?{urlencode({'rel_syn': term, 'max': 5})}")
        payload = {
            "term": match.get("word", term),
            "meanings": [
                {"partOfSpeech": part, "definitions": definitions[:3]}
                for part, definitions in meanings.items()
            ],
            "synonyms": [item["word"] for item in synonyms if isinstance(item.get("word"), str)][:5],
        }
        return DictionaryLookup(
            payload=payload,
            source="datamuse.com",
            source_metadata={"definitionField": "defs", "synonymRelation": "rel_syn"},
        )

    @staticmethod
    def _fetch(url: str) -> list[dict]:
        try:
            with urlopen(url, timeout=5.0) as response:
                result = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            raise DictionaryProviderError("Dictionary source is unavailable") from exc
        if not isinstance(result, list):
            raise DictionaryProviderError("Dictionary source returned an invalid response")
        return result


class ResilientDictionaryProvider:
    """Use fallback only when primary access fails, never for a real miss."""

    def __init__(self, primary: DictionaryProvider, fallback: DictionaryProvider) -> None:
        self.primary = primary
        self.fallback = fallback

    def lookup_english(self, term: str) -> DictionaryLookup | None:
        try:
            return self.primary.lookup_english(term)
        except DictionaryProviderError:
            lookup = self.fallback.lookup_english(term)
            if lookup is None:
                return None
            return DictionaryLookup(
                payload=lookup.payload,
                source=lookup.source,
                source_metadata={**lookup.source_metadata, "fallbackFrom": "dictionaryapi.dev"},
            )
