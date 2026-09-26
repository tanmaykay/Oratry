from __future__ import annotations

import math
import struct
import tempfile
import unittest
import wave
from pathlib import Path

from oratry.speech.audio import analyze_wav
from oratry.speech.models import Transcript, TranscriptSegment, WordTimestamp
from oratry.speech.pipeline import analyze_recording
from oratry.speech.transcript import analyze_transcript


def _wav(path: Path, parts: list[tuple[float, float]], sample_rate: int = 8000) -> None:
    samples: list[int] = []
    for seconds, hz in parts:
        samples.extend(int(10_000 * math.sin(2 * math.pi * hz * i / sample_rate)) if hz else 0 for i in range(round(seconds * sample_rate)))
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(struct.pack(f"<{len(samples)}h", *samples))


def _transcript() -> Transcript:
    words = (WordTimestamp("Um", "um", 0, .1, .95), WordTimestamp("clear", "clear", .1, .3, .96),
             WordTimestamp("clear", "clear", .3, .5, .96), WordTimestamp("language", "language", .5, .8, .96))
    return Transcript("Um clear clear language", "en", (TranscriptSegment("Um clear clear language", 0, .8, words),), "example")


class TranscriptAnalysisTests(unittest.TestCase):
    def test_counts_known_tokens_and_conservative_findings(self) -> None:
        result = analyze_transcript(_transcript(), ["language", "missing"])
        metrics = {item.name: item for item in result if hasattr(item, "unit")}
        findings = {item.name: item for item in result if not hasattr(item, "unit")}
        self.assertEqual(metrics["word_count"].value, 4)
        self.assertEqual(metrics["filler_count"].value, 1)
        self.assertAlmostEqual(metrics["transcription_confidence_mean"].value, .9575)
        self.assertEqual(metrics["low_confidence_word_count"].value, 0)
        self.assertEqual(findings["immediate_repetitions"].value, ["clear"])
        self.assertEqual(findings["target_vocabulary_used"].value, ["language"])

    def test_timestamp_gaps_produce_pause_metrics_without_claiming_acoustic_silence(self) -> None:
        transcript = Transcript(
            "first second", "en", (TranscriptSegment("first second", 0, 3.0, (
                WordTimestamp("first", "first", 0, .4, .95),
                WordTimestamp("second", "second", 2.2, 3.0, .95),
            )),), "example",
        )
        result = analyze_transcript(transcript)
        metrics = {item.name: item for item in result if hasattr(item, "unit")}
        self.assertEqual(metrics["pause_count"].value, 1)
        self.assertEqual(metrics["pause_seconds"].value, 1.8)
        self.assertEqual(metrics["long_pause_count"].value, 1)


class AudioAnalysisTests(unittest.TestCase):
    def test_synthetic_tone_silence_tone_reports_internal_pause(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.wav"
            _wav(path, [(1.0, 180), (.5, 0), (1.0, 180)])
            metrics = {metric.name: metric for metric in analyze_wav(path, _transcript())}
        self.assertAlmostEqual(metrics["duration_seconds"].value, 2.5, places=2)
        self.assertAlmostEqual(metrics["speech_duration_seconds"].value, 2.0, delta=.05)
        self.assertEqual(metrics["pause_count"].value, 1)
        self.assertGreater(metrics["pitch_mean_hz"].value, 150)
        self.assertLess(metrics["pitch_mean_hz"].value, 210)

    def test_pipeline_retains_vendor_neutral_transcript_and_labeled_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.wav"
            _wav(path, [(1.0, 180)])
            result = analyze_recording(path, _transcript())
        self.assertEqual(result.transcript.provider, "example")
        self.assertTrue(all(metric.reliability for metric in result.metrics))
        self.assertIn("speech_rate_wpm", {metric.name for metric in result.metrics})


if __name__ == "__main__":
    unittest.main()
