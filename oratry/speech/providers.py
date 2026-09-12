"""Ports implemented by STT and audio-analysis adapters; no vendor SDK type leaks here."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, Sequence, runtime_checkable

from .models import Metric, Transcript


@runtime_checkable
class SpeechToTextProvider(Protocol):
    """Populate word timestamps/confidence whenever the provider supports them."""

    provider_name: str

    def transcribe(self, audio_path: Path, *, language_hint: str | None = None) -> Transcript: ...


@runtime_checkable
class AudioAnalysisProvider(Protocol):
    """Port for model-derived features; metrics must identify themselves as such."""

    provider_name: str

    def analyze(self, audio_path: Path, transcript: Transcript | None = None) -> Sequence[Metric]: ...
