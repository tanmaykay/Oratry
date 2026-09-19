---
name: oratry-evaluation
description: Implement Oratry LLM evaluation contracts, prompt/versioning, structured-output validation, and coaching input logic for an assigned evaluation workstream.
---

# Oratry Evaluation

Read `project/WORKSTREAMS.md`, ADR 0002, ADR 0003, `schemas/evaluation.py`, and prompts before editing. Own `schemas/evaluation.py`, `prompts/**`, LLM provider adapters, evaluator tests, and evaluation documentation. Do not change score weights, deterministic metrics, database migrations, or frontend behavior.

OpenAI evaluation is configuration-driven: default `gpt-5.6-luna`, low reasoning effort, and strict structured output; `gpt-5.6-terra` must work through configuration alone. Return bounded rubric observations with transcript evidence, never exact measurements or authored user arguments. Validate every result before it reaches business logic and retain provider/model/prompt/rubric versions plus token usage needed for cost accounting.

Use fixtures/fakes for normal tests. Do not make paid provider calls without explicit authorization. Handoff stable schema and failure semantics to backend/integration owners.
