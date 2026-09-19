"""Canonical, serializable values exchanged by speech providers and analyzers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class Reliability(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNAVAILABLE = "unavailable"


class MeasurementKind(StrEnum):
    DETERMINISTIC = "deterministic"
    MODEL_DERIVED = "model_derived"


@dataclass(frozen=True)
class WordTimestamp:
    """A canonical STT word. Times are seconds from the start of normalized audio."""

    word: str
    normalized_word: str
    start_time: float | None = None
    end_time: float | None = None
    confidence: float | None = None


@dataclass(frozen=True)
class TranscriptSegment:
    text: str
    start_time: float | None = None
    end_time: float | None = None
    words: tuple[WordTimestamp, ...] = ()


@dataclass(frozen=True)
class TranscriptionUsage:
    """Provider-normalized STT accounting evidence for one transcription request."""

    provider_request_id: str | None = None
    audio_duration_seconds: float | None = None


@dataclass(frozen=True)
class Transcript:
    text: str
    language: str | None
    segments: tuple[TranscriptSegment, ...]
    provider: str
    provider_model: str | None = None
    provider_version: str | None = None
    confidence: float | None = None
    usage: TranscriptionUsage = field(default_factory=TranscriptionUsage)

    @property
    def words(self) -> tuple[WordTimestamp, ...]:
        return tuple(word for segment in self.segments for word in segment.words)


@dataclass(frozen=True)
class Metric:
    name: str
    value: float | int | bool | None
    unit: str
    source: str
    measurement_kind: MeasurementKind
    reliability: Reliability
    algorithm_version: str
    note: str | None = None


@dataclass(frozen=True)
class Finding:
    name: str
    value: Any
    measurement_kind: MeasurementKind
    reliability: Reliability
    note: str | None = None


@dataclass(frozen=True)
class AnalysisResult:
    """Normalized result persisted by an AnalysisRun, independent of vendor payloads."""

    transcript: Transcript
    metrics: tuple[Metric, ...] = ()
    findings: tuple[Finding, ...] = ()
    analysis_version: str = "speech-v1"
    metadata: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
