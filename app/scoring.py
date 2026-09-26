"""Versioned, explainable scorecards derived only from measured evidence.

This module intentionally has no dependency on an evaluator response.  An LLM
may describe transcript evidence and suggest a retry, but its dimension scores
are interpretations, not observations of learner progress.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal, ROUND_HALF_UP
from numbers import Real
from typing import Any


SCORECARD_VERSION = "deterministic-metrics-v3"
SCORECARD_SCALE = "0-100"

# These weights apply only to available measurements.  An unavailable metric is
# omitted from both the numerator and denominator; it is never assumed to be 0.
_WEIGHTS = {
    "pace": Decimal("0.25"),
    "filler_use": Decimal("0.20"),
    "immediate_repetition": Decimal("0.12"),
    "pausing": Decimal("0.18"),
    "timing": Decimal("0.15"),
    "target_vocabulary": Decimal("0.10"),
}


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, Real):
        return None
    result = float(value)
    return result if result >= 0 else None


def _round_score(value: float) -> int:
    return int(Decimal(str(max(0.0, min(100.0, value)))).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _linear_descending(value: float, *, good_at_or_below: float, poor_at_or_above: float,
                       floor: float = 20.0) -> int:
    if value <= good_at_or_below:
        return 100
    if value >= poor_at_or_above:
        return _round_score(floor)
    fraction = (value - good_at_or_below) / (poor_at_or_above - good_at_or_below)
    return _round_score(100 - (100 - floor) * fraction)


def _pace_score(wpm: float) -> int:
    # This is a coaching target, not a universal standard: 110–160 WPM is the
    # neutral band for V1 explanatory/presentation challenges.
    if 110 <= wpm <= 160:
        return 100
    if wpm < 110:
        return _linear_descending(110 - wpm, good_at_or_below=0, poor_at_or_above=50)
    return _linear_descending(wpm - 160, good_at_or_below=0, poor_at_or_above=60)


def _entry(name: str, score: int | None, *, input_: dict[str, Any], rule: str) -> dict[str, Any]:
    return {
        "score": score,
        "status": "measured" if score is not None else "unavailable",
        "input": input_,
        "rule": rule,
    }


def _minimum_response_words(target_duration_seconds: float | None) -> int | None:
    """Minimum transcript coverage before delivery mechanics can influence score.

    This is deliberately a low threshold (roughly half a word per target
    second), not an expected speaking pace. It prevents silence or a token
    fragment receiving a respectable score merely because it has no fillers.
    """
    if target_duration_seconds is None or target_duration_seconds <= 0:
        return None
    return max(10, int(round(target_duration_seconds * 0.5)))


def build_deterministic_scorecard(
    metrics: Mapping[str, Any],
    *,
    immediate_repetitions: Sequence[str] | None = None,
    target_duration_seconds: float | None = None,
    target_vocabulary: Sequence[str] | None = None,
    used_target_vocabulary: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Return immutable evidence suitable for display and progress projection.

    ``metrics`` must be values from deterministic measurement artifacts.  The
    optional arguments are challenge-owned deterministic context/findings. No
    evaluator result, LLM score, confidence, or prose is accepted.
    """
    dimensions: dict[str, dict[str, Any]] = {}

    wpm = _number(metrics.get("words_per_minute"))
    dimensions["pace"] = _entry(
        "pace", _pace_score(wpm) if wpm is not None else None,
        input_={"words_per_minute": wpm},
        rule="100 from 110 to 160 WPM; linearly declines to 20 at 60 or 220 WPM.",
    )

    filler_rate = _number(metrics.get("filler_rate"))
    dimensions["filler_use"] = _entry(
        "filler_use", _linear_descending(filler_rate, good_at_or_below=1, poor_at_or_above=12) if filler_rate is not None else None,
        input_={"filler_rate_percent": filler_rate},
        rule="100 at or below 1%; linearly declines to 20 at or above 12%.",
    )

    repetitions = None if immediate_repetitions is None else len(tuple(immediate_repetitions))
    dimensions["immediate_repetition"] = _entry(
        "immediate_repetition", _linear_descending(repetitions, good_at_or_below=0, poor_at_or_above=5) if repetitions is not None else None,
        input_={"immediate_repetition_count": repetitions},
        rule="100 with no adjacent repeated non-filler tokens; linearly declines to 20 at five or more.",
    )

    actual_duration = _number(metrics.get("duration_seconds"))
    pause_seconds = _number(metrics.get("long_pause_seconds"))
    pause_ratio = None
    pause_score = None
    if pause_seconds is not None and actual_duration is not None and actual_duration > 0:
        pause_ratio = pause_seconds / actual_duration
        pause_score = _linear_descending(pause_ratio, good_at_or_below=0.05, poor_at_or_above=0.35)
    dimensions["pausing"] = _entry(
        "pausing", pause_score,
        input_={"long_pause_seconds": pause_seconds, "duration_seconds": actual_duration, "long_pause_ratio": pause_ratio},
        rule="100 when internal pauses of at least 1.5 seconds occupy at most 5% of the response; linearly declines to 20 at 35%. Brief rhetorical pauses are not penalized.",
    )

    target_duration = _number(target_duration_seconds)
    timing_score = None
    ratio = None
    if actual_duration is not None and target_duration and target_duration > 0:
        ratio = actual_duration / target_duration
        if 0.75 <= ratio <= 1.25:
            timing_score = 100
        elif ratio < 0.75:
            timing_score = _linear_descending(0.75 - ratio, good_at_or_below=0, poor_at_or_above=0.50)
        else:
            timing_score = _linear_descending(ratio - 1.25, good_at_or_below=0, poor_at_or_above=0.75)
    dimensions["timing"] = _entry(
        "timing", timing_score,
        input_={"duration_seconds": actual_duration, "target_duration_seconds": target_duration, "duration_target_ratio": ratio},
        rule="100 from 75% to 125% of the challenge target; linearly declines to 20 outside that band.",
    )

    targets = tuple(sorted({item.casefold().strip() for item in target_vocabulary or () if item and item.strip()}))
    used = tuple(sorted({item.casefold().strip() for item in used_target_vocabulary or () if item and item.strip()}))
    vocabulary_score = None
    used_count = None
    if targets:
        used_count = len(set(targets) & set(used))
        vocabulary_score = _round_score(100 * used_count / len(targets))
    dimensions["target_vocabulary"] = _entry(
        "target_vocabulary", vocabulary_score,
        input_={"target_count": len(targets), "used_count": used_count},
        rule="Exact normalized target-word matches divided by assigned target words; unavailable when none are assigned.",
    )

    word_count = _number(metrics.get("word_count"))
    minimum_words = _minimum_response_words(target_duration)
    response_coverage = None
    if word_count is not None and minimum_words is not None:
        response_coverage = _round_score(100 * min(1, word_count / minimum_words))
    dimensions["response_coverage"] = _entry(
        "response_coverage", response_coverage,
        input_={"word_count": word_count, "minimum_word_count": minimum_words},
        rule="Overall score is capped by transcript coverage: at least max(10 words, 0.5 words per target second) is required before delivery mechanics can receive full credit.",
    )

    # Response coverage is a gate, not a weighted quality dimension. It must
    # therefore be excluded from the denominator as well as the numerator.
    available = {name: item for name, item in dimensions.items()
                 if name in _WEIGHTS and item["score"] is not None}
    total_weight = sum(_WEIGHTS[name] for name in available)
    overall = None
    if total_weight:
        total = sum(Decimal(item["score"]) * _WEIGHTS[name] for name, item in available.items()) / total_weight
        overall = int(total.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    # The gate is intentionally outside the metric-quality weights: pace,
    # fillers and repetitions are meaningless as a quality score when the
    # learner has supplied no substantive transcript.
    if overall is not None and response_coverage is not None:
        overall = min(overall, response_coverage)
    return {
        "scorecardVersion": SCORECARD_VERSION,
        "scale": SCORECARD_SCALE,
        "overall": overall,
        "coverage": {"measuredDimensions": len(available), "availableWeight": float(total_weight),
                     "responseCoverageCap": response_coverage},
        "dimensions": dimensions,
        "provenance": {
            "source": "deterministic_measurements_only",
            "excluded": ["llm_dimension_scores", "llm_confidence", "llm_interpretations", "llm_recommendations"],
        },
    }
