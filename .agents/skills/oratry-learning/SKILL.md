---
name: oratry-learning
description: Implement Oratry baseline assignment, challenge recommendation, skill evidence, vocabulary, and progress-domain behavior for an assigned learning workstream.
---

# Oratry Learning

Read `project/WORKSTREAMS.md`, product definition, ADR 0002, and `app/personalization/**`. Own `app/personalization/**`, curated challenge/seed data, learning-domain tests, and related domain documentation. Do not edit routes, migrations/models, provider adapters, or frontend screens.

Start with explainable rules: baseline sequence first, then target low-confidence or low-recent skill evidence. Skill state is a replaceable projection from immutable evidence. Keep challenge versions stable for retries and comparisons. Do not claim causal improvement where measurement/evaluation evidence does not support it.

Report input/output contracts, edge cases, and test evidence for backend integration.
