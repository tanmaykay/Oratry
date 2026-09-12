"""Composition root for deterministic V1 speech analysis."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .audio import analyze_wav
from .models import AnalysisResult, Finding, Metric, Transcript
from .transcript import analyze_transcript


def analyze_recording(audio_path: Path, transcript: Transcript, target_vocabulary: Iterable[str] = ()) -> AnalysisResult:
    """Combine canonical STT with local measurements without vendor-specific coupling."""
    text_items = analyze_transcript(transcript, target_vocabulary)
    metrics = tuple(item for item in text_items if isinstance(item, Metric)) + analyze_wav(audio_path, transcript)
    findings = tuple(item for item in text_items if isinstance(item, Finding))
    return AnalysisResult(transcript=transcript, metrics=metrics, findings=findings,
                          metadata={"audio_algorithm": "wav-signal-v1", "transcript_algorithm": "transcript-rules-v1"})
