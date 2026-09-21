# ADR 0004: Gemini as the default V1 evaluator

Date: 2026-09-21

## Status

Accepted

## Context

The initial V1 provider decision selected OpenAI for model-assisted speech evaluation. The local OpenAI account returned `credit_balance_exhausted` during the first live pipeline canary. Oratry needs a low-cost evaluator that supports structured output while retaining provider-neutral business logic.

## Decision

- Gemini is the default configured evaluator for the current V1 deployment, using `gemini-3.5-flash-lite` selected through `GEMINI_EVALUATOR_MODEL`.
- The application uses Gemini's JSON Schema response mode and validates every result against Oratry's canonical evaluation contract.
- A unique verbatim transcript quote may have its character offsets derived deterministically before validation. Ambiguous/non-verbatim evidence remains rejected. The weighted `overall_score` is always calculated deterministically from the five dimension scores, never trusted from model arithmetic.
- The existing `OpenAIResponsesTransport` stays behind `LLMProvider` for future configuration-selected comparisons; no evaluator business logic is tied to a vendor SDK.
- Free-tier keys are allowed for local development only. Production must use a privacy-reviewed paid provider tier and configured provider price version.

## Consequences

Gemini model availability is deployment configuration rather than code. The worker records Gemini token usage and latency in the same provider-usage evidence shape used by OpenAI. A missing unit-price configuration preserves usage evidence but leaves `estimatedCostUsd` null, so it is insufficient for a cost-accounted production release.
