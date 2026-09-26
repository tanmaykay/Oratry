from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError

from oratry.speech.deepgram import DeepgramPrerecordedSpeechToTextProvider, transcript_from_deepgram
from oratry.speech.models import MeasurementKind, Reliability
from oratry.speech.providers import SpeechToTextProviderError
from oratry.speech.transcript import analyze_transcript

_FIXTURE = Path("oratry/speech/fixtures/deepgram_prerecorded.json")


class _Response:
    def __init__(self, payload: dict) -> None:
        self._body = json.dumps(payload).encode()

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_: object) -> None:
        return None


class DeepgramMappingTests(unittest.TestCase):
    def test_prerecorded_fixture_maps_to_canonical_timestamped_transcript(self) -> None:
        transcript = transcript_from_deepgram(json.loads(_FIXTURE.read_text()))
        self.assertEqual(transcript.provider, "deepgram")
        self.assertEqual(transcript.provider_model, "nova-3")
        self.assertEqual(transcript.provider_version, "2026-01-01")
        self.assertEqual(transcript.usage.provider_request_id, "request-123")
        self.assertEqual(transcript.usage.audio_duration_seconds, 0.91)
        self.assertEqual(transcript.language, "en")
        self.assertEqual(transcript.text, "Um, clear language.")
        self.assertEqual([(word.word, word.normalized_word, word.start_time, word.end_time, word.confidence) for word in transcript.words], [
            ("Um", "um", 0.0, 0.12, 0.91), ("clear", "clear", 0.15, 0.46, 0.98), ("language", "language", 0.49, 0.91, 0.99),
        ])

    def test_missing_word_timings_and_confidence_remain_unavailable(self) -> None:
        transcript = transcript_from_deepgram({"results": {"channels": [{"alternatives": [{"transcript": "Hello", "words": [{"word": "Hello"}]}]}]}})
        self.assertEqual(len(transcript.words), 1)
        self.assertIsNone(transcript.words[0].start_time)
        self.assertIsNone(transcript.words[0].end_time)
        self.assertIsNone(transcript.words[0].confidence)
        self.assertIsNone(transcript.confidence)

    def test_invalid_timestamp_and_confidence_values_remain_unavailable(self) -> None:
        transcript = transcript_from_deepgram({"results": {"channels": [{"alternatives": [{
            "confidence": 1.01,
            "words": [
                {"word": "negative", "start": -0.1, "end": 0.2, "confidence": -0.1},
                {"word": "reversed", "start": 0.8, "end": 0.2, "confidence": 1.1},
                {"word": "valid", "start": 0.2, "end": 0.8, "confidence": 1.0},
            ],
        }]}]}})
        negative, reversed_word, valid = transcript.words
        self.assertEqual((negative.start_time, negative.end_time, negative.confidence), (None, None, None))
        self.assertEqual((reversed_word.start_time, reversed_word.end_time, reversed_word.confidence), (None, None, None))
        self.assertEqual((valid.start_time, valid.end_time, valid.confidence), (0.2, 0.8, 1.0))
        self.assertIsNone(transcript.confidence)

    def test_invalid_provider_duration_is_unavailable(self) -> None:
        transcript = transcript_from_deepgram({"metadata": {"duration": -1}, "results": {}})
        self.assertIsNone(transcript.usage.audio_duration_seconds)

    def test_canonical_transcript_drives_versioned_deterministic_metrics(self) -> None:
        transcript = transcript_from_deepgram(json.loads(_FIXTURE.read_text()))
        metrics = {item.name: item for item in analyze_transcript(transcript) if hasattr(item, "unit")}
        self.assertEqual(metrics["word_count"].value, 3)
        self.assertEqual(metrics["filler_count"].value, 1)
        self.assertAlmostEqual(metrics["filler_rate"].value, 100 / 3)
        for metric in metrics.values():
            self.assertEqual(metric.measurement_kind, MeasurementKind.DETERMINISTIC)
            self.assertEqual(metric.algorithm_version, "transcript-rules-v2")
            self.assertIn(metric.reliability, (Reliability.HIGH, Reliability.MEDIUM, Reliability.LOW, Reliability.UNAVAILABLE))


class DeepgramRequestTests(unittest.TestCase):
    def test_adapter_uses_prerecorded_nova3_request_and_maps_response(self) -> None:
        captured = []

        def opener(request: object, timeout: int) -> _Response:
            captured.append((request, timeout))
            return _Response(json.loads(_FIXTURE.read_text()))

        with tempfile.TemporaryDirectory() as directory:
            audio_path = Path(directory) / "recording.webm"
            audio_path.write_bytes(b"synthetic fixture")
            provider = DeepgramPrerecordedSpeechToTextProvider("test-key", opener=opener)
            transcript = provider.transcribe(audio_path, language_hint="en")
        request, timeout = captured[0]
        self.assertEqual(timeout, 60)
        self.assertEqual(request.get_method(), "POST")
        self.assertIn("model=nova-3", request.full_url)
        self.assertIn("utterances=true", request.full_url)
        self.assertIn("filler_words=true", request.full_url)
        self.assertIn("language=en", request.full_url)
        self.assertEqual(request.get_header("Authorization"), "Token test-key")
        self.assertEqual(transcript.provider, "deepgram")

    def test_http_error_is_classified_without_leaking_provider_body(self) -> None:
        def opener(request: object, timeout: int) -> _Response:
            raise HTTPError("https://example.test", 429, "rate limited", {}, None)

        with tempfile.TemporaryDirectory() as directory:
            audio_path = Path(directory) / "recording.wav"
            audio_path.write_bytes(b"fixture")
            provider = DeepgramPrerecordedSpeechToTextProvider("test-key", opener=opener)
            with self.assertRaises(SpeechToTextProviderError) as raised:
                provider.transcribe(audio_path)
        self.assertTrue(raised.exception.retryable)


if __name__ == "__main__":
    unittest.main()
