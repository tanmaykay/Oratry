"""Deterministic text-derived analysis with deliberately conservative heuristics."""

from __future__ import annotations

import re
from typing import Iterable

from .models import Finding, MeasurementKind, Metric, Reliability, Transcript

_TOKEN = re.compile(r"[\w']+", re.UNICODE)
_FILLERS = frozenset({"um", "uh", "umm", "uhh", "er", "erm", "ah", "hmm", "like"})
_CORRECTION_CUES = frozenset({"sorry", "rather", "mean", "correct", "instead"})
_VERSION = "transcript-rules-v2"
_MIN_PAUSE_SECONDS = 0.7
_LONG_PAUSE_SECONDS = 1.5


def _tokens(transcript: Transcript) -> list[str]:
    words = [word.normalized_word for word in transcript.words if word.normalized_word]
    return [word.casefold() for word in words] if words else [t.casefold() for t in _TOKEN.findall(transcript.text)]


def _internal_pause_seconds(transcript: Transcript) -> tuple[float, ...] | None:
    """Return timestamp-evidenced internal lexical gaps, not acoustic silence."""
    words = tuple(word for word in transcript.words if word.start_time is not None and word.end_time is not None)
    if len(words) < 2:
        return None
    return tuple(round(following.start_time - previous.end_time, 3) for previous, following in zip(words, words[1:])
                 if following.start_time - previous.end_time >= _MIN_PAUSE_SECONDS)


def analyze_transcript(transcript: Transcript, target_vocabulary: Iterable[str] = ()) -> tuple[Metric | Finding, ...]:
    tokens = _tokens(transcript)
    count = len(tokens)
    filler_count = sum(token in _FILLERS for token in tokens)
    confidences = [word.confidence for word in transcript.words if word.confidence is not None]
    transcription_confidence = round(sum(confidences) / len(confidences), 4) if confidences else None
    low_confidence_count = sum(confidence < 0.7 for confidence in confidences) if confidences else None
    repeated = sorted({tokens[i] for i in range(1, count) if tokens[i] == tokens[i - 1] and tokens[i] not in _FILLERS})
    cue_positions = [i for i, token in enumerate(tokens) if token in _CORRECTION_CUES]
    targets = {phrase.casefold().strip() for phrase in target_vocabulary if phrase.strip()}
    text = " ".join(tokens)
    used_targets = sorted(target for target in targets if re.search(rf"(?<!\w){re.escape(target)}(?!\w)", text))
    rate = filler_count / count * 100 if count else None
    pauses = _internal_pause_seconds(transcript)
    pause_count = len(pauses) if pauses is not None else None
    pause_seconds = round(sum(pauses), 3) if pauses is not None else None
    long_pause_count = sum(pause >= _LONG_PAUSE_SECONDS for pause in pauses) if pauses is not None else None
    long_pause_seconds = round(sum(pause for pause in pauses if pause >= _LONG_PAUSE_SECONDS), 3) if pauses is not None else None
    return (
        Metric("word_count", count, "words", "transcript", MeasurementKind.DETERMINISTIC, Reliability.HIGH, _VERSION),
        Metric("filler_count", filler_count, "fillers", "transcript", MeasurementKind.DETERMINISTIC, Reliability.MEDIUM, _VERSION,
               "Lexical count; context and STT errors can change the result."),
        Metric("filler_rate", rate, "percent_of_words", "derived", MeasurementKind.DETERMINISTIC,
               Reliability.MEDIUM if count else Reliability.UNAVAILABLE, _VERSION),
        Metric("transcription_confidence_mean", transcription_confidence, "confidence", "stt_word_timestamps", MeasurementKind.DETERMINISTIC,
               Reliability.MEDIUM if confidences else Reliability.UNAVAILABLE, _VERSION,
               "Mean provider word confidence; it describes transcript evidence quality, not speaking quality."),
        Metric("low_confidence_word_count", low_confidence_count, "words", "stt_word_timestamps", MeasurementKind.DETERMINISTIC,
               Reliability.MEDIUM if confidences else Reliability.UNAVAILABLE, _VERSION,
               "Provider words below 70% confidence; use as a limitation before judging wording or coherence."),
        Metric("pause_count", pause_count, "internal_pauses", "transcript_timestamps", MeasurementKind.DETERMINISTIC,
               Reliability.MEDIUM if pauses is not None else Reliability.UNAVAILABLE, _VERSION,
               "Gaps of at least 0.7 seconds between timestamped words; brief pauses are not counted."),
        Metric("pause_seconds", pause_seconds, "seconds", "transcript_timestamps", MeasurementKind.DETERMINISTIC,
               Reliability.MEDIUM if pauses is not None else Reliability.UNAVAILABLE, _VERSION,
               "Total internal timestamp gap duration; not an acoustic silence measurement."),
        Metric("long_pause_count", long_pause_count, "internal_pauses", "transcript_timestamps", MeasurementKind.DETERMINISTIC,
               Reliability.MEDIUM if pauses is not None else Reliability.UNAVAILABLE, _VERSION,
               "Internal gaps of at least 1.5 seconds."),
        Metric("long_pause_seconds", long_pause_seconds, "seconds", "transcript_timestamps", MeasurementKind.DETERMINISTIC,
               Reliability.MEDIUM if pauses is not None else Reliability.UNAVAILABLE, _VERSION,
               "Total duration of internal timestamp gaps of at least 1.5 seconds."),
        Finding("immediate_repetitions", repeated, MeasurementKind.DETERMINISTIC, Reliability.MEDIUM,
                "Only adjacent repeated tokens; may be intentional emphasis."),
        Finding("possible_self_correction_positions", cue_positions, MeasurementKind.DETERMINISTIC, Reliability.LOW,
                "Cue-word heuristic, not a semantic determination."),
        Finding("target_vocabulary_used", used_targets, MeasurementKind.DETERMINISTIC, Reliability.HIGH,
                "Exact normalized phrase matches only."),
    )
