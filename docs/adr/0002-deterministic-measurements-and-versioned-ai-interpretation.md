# ADR 0002: Separate deterministic measurements from versioned AI interpretation

Date: 2026-09-12

## Status

Accepted

## Context

The product offers coaching from speech recordings. Some properties can be calculated deterministically; others require bounded qualitative interpretation.

## Decision

Compute duration, WPM, filler counts/rates, pauses, repetitions, and target-word occurrence with deterministic, versioned algorithms. Store AI evaluation separately with validated structure, provider/model/prompt/rubric versioning, and transcript evidence. Scorecards are server-side deterministic calculations; coaching selects one action from persisted results.

## Consequences

UI and API contracts must label facts separately from interpretation. The product must not make psychological claims from ambiguous acoustic signals. Changes to metrics, prompts, rubrics, or score weights require explicit version changes.

