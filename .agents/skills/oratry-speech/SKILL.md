---
name: oratry-speech
description: Implement provider-neutral transcription, audio normalization, deterministic speech metrics, and Deepgram mapping for an assigned Oratry speech workstream.
---

# Oratry Speech

Read `project/WORKSTREAMS.md`, ADR 0002, ADR 0003, and `docs/speech-analysis.md`. Own `oratry/speech/**`, speech provider adapters, speech fixtures, and their tests. Do not edit routes, persistence, frontend, scoring policy, or evaluator prompts.

Deepgram Nova-3 is V1 prerecorded STT. Normalize provider output into canonical transcript words with timestamps and confidence; record explicit unavailable values where absent. Deterministic metrics must remain deterministic, versioned, and conservative. Never diagnose emotion, confidence, or mental state from audio. Normalize non-WAV audio upstream before signal analysis; do not silently claim analysis when decoding fails.

Test adapter mappings and deterministic metrics using synthetic/consented fixtures only. Handoff canonical payload/schema requirements rather than persisting data directly.
