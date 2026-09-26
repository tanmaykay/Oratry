"""Deepgram prerecorded transcription adapter.

The adapter is intentionally confined to this module.  It maps Deepgram's
response into Oratry's canonical transcript before it reaches any business
logic, persistence, or deterministic analysis code.
"""

from __future__ import annotations

import json
import math
import mimetypes
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .models import Transcript, TranscriptSegment, TranscriptionUsage, WordTimestamp
from .providers import SpeechToTextProviderError

_LISTEN_URL = "https://api.deepgram.com/v1/listen"


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _optional_float(value: object) -> float | None:
    # bool is deliberately excluded: JSON true/false are not STT confidences.
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _timestamps(start_value: object, end_value: object) -> tuple[float | None, float | None]:
    """Keep a timestamp pair only when it is a valid elapsed-time interval."""
    start, end = _optional_float(start_value), _optional_float(end_value)
    if start is None or end is None or start < 0 or end < 0 or end < start:
        return None, None
    return start, end


def _confidence(value: object) -> float | None:
    confidence = _optional_float(value)
    return confidence if confidence is not None and 0 <= confidence <= 1 else None


def _duration(value: object) -> float | None:
    duration = _optional_float(value)
    return duration if duration is not None and duration >= 0 else None


def _normalized_word(word: str) -> str:
    """Use the same conservative token normalization as transcript metrics."""
    return "".join(character for character in word.casefold() if character.isalnum() or character == "'")


def _map_words(words: object) -> tuple[WordTimestamp, ...]:
    if not isinstance(words, list):
        return ()
    canonical: list[WordTimestamp] = []
    for item in words:
        if not isinstance(item, Mapping):
            continue
        word = _optional_string(item.get("word"))
        if word is None:
            continue
        start, end = _timestamps(item.get("start"), item.get("end"))
        canonical.append(WordTimestamp(
            word=word,
            normalized_word=_normalized_word(word),
            start_time=start,
            end_time=end,
            confidence=_confidence(item.get("confidence")),
        ))
    return tuple(canonical)


def _segment_words(words: tuple[WordTimestamp, ...], start: float | None, end: float | None) -> tuple[WordTimestamp, ...]:
    """Associate utterance words only when their timestamps make that possible."""
    if start is None or end is None:
        return ()
    return tuple(word for word in words if word.start_time is not None and word.end_time is not None
                 and word.start_time >= start and word.end_time <= end)


def transcript_from_deepgram(payload: Mapping[str, Any], *, requested_model: str = "nova-3") -> Transcript:
    """Map a prerecorded Deepgram response without fabricating unavailable data."""
    metadata = payload.get("metadata")
    metadata = metadata if isinstance(metadata, Mapping) else {}
    results = payload.get("results")
    results = results if isinstance(results, Mapping) else {}
    channels = results.get("channels")
    channel = channels[0] if isinstance(channels, list) and channels and isinstance(channels[0], Mapping) else {}
    alternatives = channel.get("alternatives") if isinstance(channel, Mapping) else None
    alternative = alternatives[0] if isinstance(alternatives, list) and alternatives and isinstance(alternatives[0], Mapping) else {}

    words = _map_words(alternative.get("words"))
    text = _optional_string(alternative.get("transcript")) or ""
    language = _optional_string(metadata.get("detected_language")) or _optional_string(results.get("language"))
    confidence = _confidence(alternative.get("confidence"))
    utterances = results.get("utterances")
    segments: list[TranscriptSegment] = []
    if isinstance(utterances, list):
        for utterance in utterances:
            if not isinstance(utterance, Mapping):
                continue
            utterance_text = _optional_string(utterance.get("transcript"))
            if utterance_text is None:
                continue
            start, end = _timestamps(utterance.get("start"), utterance.get("end"))
            segments.append(TranscriptSegment(utterance_text, start, end, _segment_words(words, start, end)))
    if not segments:
        start = words[0].start_time if words else None
        end = words[-1].end_time if words else None
        segments.append(TranscriptSegment(text, start, end, words))

    model_info = metadata.get("model_info")
    model_info = model_info if isinstance(model_info, Mapping) else {}
    return Transcript(
        text=text,
        language=language,
        segments=tuple(segments),
        provider="deepgram",
        provider_model=_optional_string(model_info.get("name")) or _optional_string(metadata.get("model_name")) or requested_model,
        provider_version=_optional_string(model_info.get("version")) or _optional_string(metadata.get("model_version")),
        confidence=confidence,
        usage=TranscriptionUsage(
            provider_request_id=_optional_string(metadata.get("request_id")),
            audio_duration_seconds=_duration(metadata.get("duration")),
        ),
    )


class DeepgramPrerecordedSpeechToTextProvider:
    """Deepgram Nova-3 prerecorded STT, behind the SpeechToTextProvider port."""

    provider_name = "deepgram"

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "nova-3",
        endpoint_url: str = _LISTEN_URL,
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        if not api_key:
            raise ValueError("Deepgram API key is required")
        self._api_key = api_key
        self._model = model
        self._endpoint_url = endpoint_url
        self._opener = opener

    def transcribe(self, audio_path: Path, *, language_hint: str | None = None) -> Transcript:
        # Deepgram removes “um” and “uh” by default to make a conventional
        # transcript easier to read. Oratry's learning contract needs those
        # lexical events as timestamped evidence, so opt in explicitly.
        query: dict[str, str] = {
            "model": self._model, "smart_format": "true", "punctuate": "true",
            "utterances": "true", "filler_words": "true",
        }
        if language_hint:
            query["language"] = language_hint
        content_type = mimetypes.guess_type(audio_path.name)[0] or "application/octet-stream"
        try:
            request = Request(
                f"{self._endpoint_url}?{urlencode(query)}",
                data=audio_path.read_bytes(),
                headers={"Authorization": f"Token {self._api_key}", "Content-Type": content_type},
                method="POST",
            )
            with self._opener(request, timeout=60) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            raise SpeechToTextProviderError(f"Deepgram transcription failed with HTTP {error.code}", retryable=error.code >= 500 or error.code == 429) from error
        except FileNotFoundError as error:
            raise SpeechToTextProviderError("Audio file is unavailable for transcription", retryable=False) from error
        except (OSError, URLError, json.JSONDecodeError) as error:
            raise SpeechToTextProviderError("Deepgram transcription request failed", retryable=True) from error
        if not isinstance(payload, Mapping):
            raise SpeechToTextProviderError("Deepgram returned a non-object response", retryable=False)
        return transcript_from_deepgram(payload, requested_model=self._model)
