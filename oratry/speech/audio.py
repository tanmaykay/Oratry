"""Dependency-free WAV signal measurements for the deterministic V1 analyzer."""

from __future__ import annotations

import audioop
import math
import wave
from pathlib import Path
from statistics import mean, median, pstdev

from .models import MeasurementKind, Metric, Reliability, Transcript

_VERSION = "wav-signal-v1"
_FRAME_SECONDS = 0.02
_SPEECH_THRESHOLD_DBFS = -40.0
_MIN_PAUSE_SECONDS = 0.20
_LONG_PAUSE_SECONDS = 1.00


def _metric(name: str, value: float | int | None, unit: str, reliability: Reliability, note: str | None = None) -> Metric:
    return Metric(name, value, unit, "audio", MeasurementKind.DETERMINISTIC, reliability, _VERSION, note)


def _pitch_hz(samples: list[int], sample_rate: int) -> float | None:
    """Simple autocorrelation estimate; only used on energetic, tone-like frames."""
    # A 20 ms analysis frame at 8 kHz has 160 samples: enough for the
    # 70--350 Hz range used below, but not for unusually low fundamental pitch.
    if len(samples) < max(8, sample_rate // 100):
        return None
    centered = [sample - mean(samples) for sample in samples]
    min_lag, max_lag = max(1, sample_rate // 350), min(len(centered) // 2, sample_rate // 70)
    energy = sum(value * value for value in centered)
    if not energy:
        return None
    best_lag, best_score = 0, 0.0
    for lag in range(min_lag, max_lag + 1):
        numerator = sum(centered[i] * centered[i - lag] for i in range(lag, len(centered)))
        score = numerator / energy
        if score > best_score:
            best_lag, best_score = lag, score
    return sample_rate / best_lag if best_score >= 0.30 else None


def analyze_wav(audio_path: Path, transcript: Transcript | None = None) -> tuple[Metric, ...]:
    """Measure PCM WAV audio. Decode/normalize other containers with FFmpeg upstream."""
    with wave.open(str(audio_path), "rb") as handle:
        channels, width, sample_rate, frame_count = handle.getnchannels(), handle.getsampwidth(), handle.getframerate(), handle.getnframes()
        if handle.getcomptype() != "NONE" or width not in (1, 2, 3, 4) or channels not in (1, 2):
            raise ValueError("analyze_wav requires uncompressed 8/16/24/32-bit PCM WAV")
        raw = handle.readframes(frame_count)
    duration = frame_count / sample_rate if sample_rate else 0.0
    # WAV stores 8-bit PCM as unsigned while audioop's amplitude operations use
    # signed samples. Translate it before RMS calculation.
    if width == 1:
        raw = audioop.bias(raw, width, -128)
    mono = audioop.tomono(raw, width, 0.5, 0.5) if channels == 2 else raw
    samples_per_frame = max(1, round(sample_rate * _FRAME_SECONDS))
    bytes_per_frame = samples_per_frame * width
    energies: list[float] = []
    voiced: list[bool] = []
    pitches: list[float] = []
    for start in range(0, len(mono), bytes_per_frame):
        chunk = mono[start:start + bytes_per_frame]
        if len(chunk) < width:
            continue
        rms = audioop.rms(chunk, width)
        full_scale = float(1 << (8 * width - 1))
        dbfs = 20 * math.log10(max(rms, 1) / full_scale)
        energies.append(dbfs)
        is_voiced = dbfs >= _SPEECH_THRESHOLD_DBFS
        voiced.append(is_voiced)
        if is_voiced and width == 2:
            values = list(memoryview(chunk).cast("h"))
            estimate = _pitch_hz(values, sample_rate)
            if estimate:
                pitches.append(estimate)
    frame_duration = duration / len(voiced) if voiced else 0.0
    speech_seconds = sum(voiced) * frame_duration
    silence_seconds = max(0.0, duration - speech_seconds)
    pauses: list[float] = []
    index = 0
    while index < len(voiced):
        if voiced[index]:
            index += 1
            continue
        end = index
        while end < len(voiced) and not voiced[end]:
            end += 1
        # Do not describe leading/trailing room tone as a speaking pause.
        if index > 0 and end < len(voiced):
            pause = (end - index) * frame_duration
            if pause >= _MIN_PAUSE_SECONDS:
                pauses.append(pause)
        index = end
    metrics = [
        _metric("duration_seconds", duration, "seconds", Reliability.HIGH),
        _metric("speech_duration_seconds", speech_seconds, "seconds", Reliability.MEDIUM,
                "Energy-threshold estimate; not diarized speech recognition."),
        _metric("silence_seconds", silence_seconds, "seconds", Reliability.MEDIUM,
                "Frames below -40 dBFS, including non-speech room tone."),
        _metric("pause_count", len(pauses), "pauses", Reliability.MEDIUM),
        _metric("long_pause_count", sum(pause >= _LONG_PAUSE_SECONDS for pause in pauses), "pauses", Reliability.MEDIUM),
        _metric("long_pause_seconds", sum(pause for pause in pauses if pause >= _LONG_PAUSE_SECONDS), "seconds", Reliability.MEDIUM),
    ]
    if energies:
        metrics.extend([
            _metric("energy_mean_dbfs", mean(energies), "dBFS", Reliability.HIGH),
            _metric("energy_median_dbfs", median(energies), "dBFS", Reliability.HIGH),
            _metric("energy_stddev_db", pstdev(energies), "dB", Reliability.HIGH),
        ])
    if pitches:
        metrics.extend([
            _metric("pitch_mean_hz", mean(pitches), "Hz", Reliability.LOW, "Autocorrelation estimate on energetic PCM frames."),
            _metric("pitch_median_hz", median(pitches), "Hz", Reliability.LOW),
            _metric("pitch_stddev_hz", pstdev(pitches), "Hz", Reliability.LOW),
            _metric("pitch_min_hz", min(pitches), "Hz", Reliability.LOW),
            _metric("pitch_max_hz", max(pitches), "Hz", Reliability.LOW),
        ])
    else:
        metrics.append(_metric("pitch_mean_hz", None, "Hz", Reliability.UNAVAILABLE, "No sufficiently periodic voiced frames."))
    if transcript:
        word_count = len(transcript.words) or len(transcript.text.split())
        transcript_reliability = Reliability.HIGH if transcript.words and all(w.start_time is not None for w in transcript.words) else Reliability.MEDIUM
        metrics.extend([
            Metric("speech_rate_wpm", word_count / duration * 60 if duration else None, "words_per_minute", "derived",
                   MeasurementKind.DETERMINISTIC, transcript_reliability, _VERSION, "Transcript words divided by recording duration."),
            Metric("articulation_rate_wpm", word_count / speech_seconds * 60 if speech_seconds else None, "words_per_minute", "derived",
                   MeasurementKind.DETERMINISTIC, Reliability.MEDIUM if speech_seconds else Reliability.UNAVAILABLE, _VERSION,
                   "Transcript words divided by energy-threshold speech duration."),
        ])
    return tuple(metrics)
