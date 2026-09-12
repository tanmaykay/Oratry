# Speech analysis pipeline

## Scope and architecture

This V1 subsystem produces provider-neutral transcripts and objective, versioned measurements for an `AnalysisRun`. It is deliberately not an emotion detector or a psychological assessment. Pitch, energy, pause, and rate values describe the recording signal and must not be presented as direct measures of nervousness, confidence, competence, or personality.

```
normalized audio (FFmpeg, upstream) --> SpeechToTextProvider --> Transcript
              |                                             |
              +--> deterministic WAV analyzer ---------------+--> AnalysisResult
              |                                             |
              +--> optional AudioAnalysisProvider -----------+
```

`SpeechToTextProvider.transcribe(path, language_hint)` returns `Transcript`: provider/model/version metadata, text, segments, and canonical words. Each `WordTimestamp` has `word`, `normalized_word`, `start_time`, `end_time`, and `confidence`. Providers set unavailable timestamp/confidence fields to `null`; adapters never invent them.

`AudioAnalysisProvider.analyze(path, transcript)` is a separate port for an approved external feature extractor. Its results are always tagged `model_derived`, provider/versioned, and never silently replace local measurements. The present `analyze_wav` implementation is the deterministic baseline and consumes normalized uncompressed PCM WAV. FFmpeg conversion belongs in the media stage described in the architecture document.

`AnalysisResult` is the persistence/API boundary: canonical transcript, metrics, findings, algorithm versions, source, measurement kind, and reliability. Vendor response payloads stay inside adapters. API serialization can map snake_case field names to the documented camelCase response shape.

## Measurements and algorithms

All measurements include `reliability` (`high`, `medium`, `low`, or `unavailable`) and `measurement_kind`.

| Feature | Method | Kind / reliability |
| --- | --- | --- |
| Duration | WAV sample count / sample rate | deterministic / high |
| Speech duration, silence | 20 ms RMS frames above/below -40 dBFS | deterministic / medium |
| Pause count and long pauses | Internal non-speech runs >= 0.20 s; long >= 1.0 s. Leading/trailing silence is excluded from pause count. | deterministic / medium |
| Speech rate | transcript word count / recording duration * 60 | deterministic / high with complete word timing, otherwise medium |
| Articulation rate | transcript word count / estimated speech duration * 60 | deterministic / medium |
| Pitch statistics | Autocorrelation on energetic 16-bit PCM frames; mean, median, spread, min/max in Hz | deterministic / low |
| Energy statistics | Frame dBFS mean, median, and population standard deviation | deterministic / high for the submitted normalized audio |
| Word/filler count and rate | normalized STT words (or transcript token fallback); filler count / words | deterministic / high for count, medium for fillers/rate |
| Repetition | Adjacent, identical non-filler tokens | deterministic / medium |
| Self-correction | Positions of conservative cue words such as “sorry” or “instead” | deterministic / low |
| Target vocabulary | Exact normalized word/phrase matching | deterministic / high |

“Deterministic” means the same input, configuration, and algorithm version return the same output. It does not mean a measure is universally accurate: STT mistakes affect transcript-based measures and thresholding is sensitive to audio conditions. “Model-derived” means an external model produced the value and it requires its own provider/model/version provenance and validation.

## Confidence handling

STT word confidence is preserved verbatim when a provider provides it; it is not converted into a claim of user certainty. Metric reliability instead describes the trustworthiness of the calculation under V1 assumptions. Missing values remain `null` with `unavailable`, never zero. Consumer UI should show availability and method notes, retain calculation/provider versions, and avoid comparisons across incompatible versions.

## Limitations and edge cases

- The local analyzer is PCM WAV only. Decode codecs, downmix channels, and normalize sample rate before calling it; corrupt or unsupported files fail safely rather than yielding metrics.
- The fixed energy threshold can mistake music, background noise, breath sounds, clipping, or a quiet speaker for speech. It is not speaker diarization or voice activity detection.
- Pitch is particularly unreliable with noise, unvoiced speech, music, non-16-bit audio, and very short clips; it can be unavailable.
- Timestamp-free STT still supports text counts, but timing-sensitive output has lower reliability. Transcript language, punctuation, multilingual speech, and ASR normalization affect filler/repetition results.
- Intentional repetition, quoted speech, and phrases such as “like” may be falsely counted. Self-correction is only a cue-word flag, never a semantic judgment.
- Empty audio/text, all-silence audio, leading/trailing silence, short clips, and no target vocabulary are valid inputs and must not produce fabricated zero-valued unavailable measurements.

## Test strategy

Unit tests synthesize mono PCM WAV files containing known 180 Hz tone and silent intervals, avoiding proprietary recordings and external providers. They assert duration, internal pause detection, approximate pitch range, rate availability, canonical transcript retention, filler/repetition detection, and target vocabulary matching. Add adapter contract tests with saved provider fixtures to ensure every provider maps to the same `Transcript` schema, including missing timestamp cases. Integration tests should normalize representative user-consented audio through FFmpeg, run the worker idempotently, and verify persisted calculation/provider versions and explicit unavailable values. Calibrate threshold and pitch behavior against a labeled, consented corpus before changing reliability labels or defaults.
