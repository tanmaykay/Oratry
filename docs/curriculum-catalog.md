# Curriculum catalog

The curated curriculum is versioned in `app.personalization.catalog` as
`CURRICULUM_CATALOG_VERSION`. It contains approved prompts selected by the
rules-based learning engine; it does not generate a learner's argument, research,
or response.

## Current V1 catalog

`BASELINE_CATALOG` and `PRACTICE_CATALOG` are the only assignment pools available
to the V1 API. Their immutable IDs preserve retry and comparison meaning. Changes
to an assigned prompt require a new ID/version rather than editing historical
content.

## Prepared future curriculum

`FUTURE_CURRICULUM` is intentionally not assignable. It captures the next approved
learning contexts before product surfaces, evaluation rubrics, and persistence
contracts exist:

| Mode | Topic family | Intended exercise |
| --- | --- | --- |
| Prepared argument | Technology | Independent research and structured position |
| Impromptu | Science | 30-second preparation and concise explanation |
| Interview | Business | Situation, task, action, result response |
| Explanation | Science | Audience-aware concept explanation |
| Debate | Society | Counter-position with trade-offs |
| Storytelling | Culture | Narrative structure and significance |
| Professional | Business | Recommendation for a work context |
| Leadership | Philosophy | Accountable response to an ethical mistake |

The taxonomy also reserves Technology, Science, Society, Business, Culture, and
Philosophy topic families. Future variants can add Education, Environment, History,
and Everyday Life without changing the core assignment interface.

Each entry makes speaking duration, preparation duration, cognitive task, target
skills, explicit difficulty vector, and target vocabulary visible. Preparation
duration is catalog metadata because the V1 database challenge schema does not yet
persist it. `lexicon:*` values are stable lexical identifiers, **not** foreign keys
to a user's `vocabulary_items` row. A later assignment adapter must resolve them by
normalized lemma, then record what was actually assigned in the immutable attempt
snapshot.

Before a future mode is enabled, it needs a product decision, an explicit route/UI
flow, a compatible evaluation rubric, and migration-backed snapshot fields. Modes
must not be exposed merely because the catalog contains them.
