# ADR 0001: Modular monolith with provider ports

Date: 2026-09-12

## Status

Accepted

## Context

The system needs authenticated product workflows, recordings, asynchronous speech analysis, deterministic measurements, and AI interpretation. The prototype already has separate provider protocols and an independent deterministic speech package.

## Decision

Ship V1 as a modular monolith. Keep API/worker orchestration and domains in the same deployable codebase, with interfaces for object storage, job delivery, STT, and LLM evaluation. Preserve provider/model/calculation/rubric versions with analysis evidence.

## Consequences

This reduces operational complexity while preserving the ability to replace external vendors. Direct vendor SDK use in domain/business services is disallowed. Background processing is still required; a separate microservice architecture is not.

