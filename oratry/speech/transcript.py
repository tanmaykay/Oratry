"""Deterministic text-derived analysis with deliberately conservative heuristics."""

from __future__ import annotations

import re
from typing import Iterable

from .models import Finding, MeasurementKind, Metric, Reliability, Transcript

_TOKEN = re.compile(r"[\w']+", re.UNICODE)
_FILLERS = frozenset({"um", "uh", "umm", "uhh", "er", "erm", "ah", "hmm", "like"})
_CORRECTION_CUES = frozenset({"sorry", "rather", "mean", "correct", "instead"})
_VERSION = "transcript-rules-v1"


def _tokens(transcript: Transcript) -> list[str]:
    words = [word.normalized_word for word in transcript.words if word.normalized_word]
    return [word.casefold() for word in words] if words else [t.casefold() for t in _TOKEN.findall(transcript.text)]


def analyze_transcript(transcript: Transcript, target_vocabulary: Iterable[str] = ()) -> tuple[Metric | Finding, ...]:
    tokens = _tokens(transcript)
    count = len(tokens)
    filler_count = sum(token in _FILLERS for token in tokens)
    repeated = sorted({tokens[i] for i in range(1, count) if tokens[i] == tokens[i - 1] and tokens[i] not in _FILLERS})
    cue_positions = [i for i, token in enumerate(tokens) if token in _CORRECTION_CUES]
    targets = {phrase.casefold().strip() for phrase in target_vocabulary if phrase.strip()}
    text = " ".join(tokens)
    used_targets = sorted(target for target in targets if re.search(rf"(?<!\w){re.escape(target)}(?!\w)", text))
    rate = filler_count / count * 100 if count else None
    return (
        Metric("word_count", count, "words", "transcript", MeasurementKind.DETERMINISTIC, Reliability.HIGH, _VERSION),
        Metric("filler_count", filler_count, "fillers", "transcript", MeasurementKind.DETERMINISTIC, Reliability.MEDIUM, _VERSION,
               "Lexical count; context and STT errors can change the result."),
        Metric("filler_rate", rate, "percent_of_words", "derived", MeasurementKind.DETERMINISTIC,
               Reliability.MEDIUM if count else Reliability.UNAVAILABLE, _VERSION),
        Finding("immediate_repetitions", repeated, MeasurementKind.DETERMINISTIC, Reliability.MEDIUM,
                "Only adjacent repeated tokens; may be intentional emphasis."),
        Finding("possible_self_correction_positions", cue_positions, MeasurementKind.DETERMINISTIC, Reliability.LOW,
                "Cue-word heuristic, not a semantic determination."),
        Finding("target_vocabulary_used", used_targets, MeasurementKind.DETERMINISTIC, Reliability.HIGH,
                "Exact normalized phrase matches only."),
    )
