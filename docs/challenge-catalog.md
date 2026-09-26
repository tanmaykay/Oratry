# Challenge catalog

The catalog is curated, versioned curriculum content. It is not a prompt generator and it does not allow an external model to manufacture assignable challenges.

## Current V1 pool

The active pool contains a fixed three-step baseline followed by focused practice:

| Stage | Cognitive task | Context | Primary skills |
| --- | --- | --- | --- |
| Baseline: explain | Explain | Everyday decision | Thinking, language |
| Baseline: argue | Argue | Practical improvement | Thinking, structure, language |
| Baseline: story | Story | Unexpected problem | Fluency, delivery |
| Practice: argument | Argue | Improve a familiar process | Thinking, structure |
| Practice: comparison | Compare | Leisure decision | Fluency, language |
| Practice: explanation | Explain | Introduce a teammate to a process | Delivery, language |

Each entry has immutable ID, prompt, preparation guidance, target skills, target duration, vocabulary targets, cognitive task, topic, challenge family, and multidimensional difficulty. Attempts retain the assigned challenge version.

## Approved future modes

The versioned future catalog deliberately contains inactive entries for these modes. They are not selectable until each has a dedicated preparation experience, challenge-specific rubric, and evaluation validation.

| Mode | Example situation | Required before activation |
| --- | --- | --- |
| Prepared argument | Research-informed education policy argument | Research boundary and evidence rubric |
| Impromptu | Explain scientific uncertainty after 30 seconds | Timed preparation UI and pressure calibration |
| Interview | Describe a constrained professional improvement | STAR-style rubric and job-context safeguards |
| Explanation | Explain immunology to a teenager | Audience-adaptation rubric |
| Debate | Respond to platform-responsibility position | Counterargument and fairness rubric |
| Storytelling | Explain a meaningful cultural experience | Narrative-structure rubric |
| Professional | Recommend a cross-functional handoff change | Stakeholder and trade-off rubric |
| Leadership | Address an ethical mistake to a team | Responsibility and evidence rubric |

## Selection principles

The recommendation policy prioritizes a learner's evidence-backed skill need, stated goals, appropriate multidimensional difficulty, recency/variety, and vocabulary still in progress. It must not infer psychological traits or use scores as a substitute for evidence.

See `app/personalization/catalog.py` for the canonical content and `app/personalization/challenge_engine.py` for deterministic selection policy.
