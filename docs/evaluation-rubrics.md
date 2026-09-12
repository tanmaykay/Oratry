# Evaluation rubrics

Rubric version: `1.0.0`. Scores are integer values from 0–100. The evaluator judges the submitted response against its assigned challenge, not a universal speaking style. The scorecard is deterministic once five validated dimension scores exist:

`overall = round_half_up(0.25 structure + 0.20 clarity + 0.20 fluency + 0.20 language + 0.15 delivery)`

| Dimension | What is evaluated | Strong evidence | Boundaries |
| --- | --- | --- | --- |
| Structure | Organization, progression, transitions, conclusion | transcript sequencing and explicit transitions | Do not reward a longer answer by itself. |
| Clarity | Direct, understandable, challenge-relevant communication | response addresses requested task, concise phrasing | Do not substitute vocabulary sophistication for clarity. |
| Fluency | Pace, fillers, repetition, self-correction, pauses | WPM, filler/pause metrics, exact transcript repetition | Do not infer hidden hesitations from a text-only transcript. |
| Language | Accurate, precise, audience-appropriate wording | transcript grammar/word choice and relevant target vocabulary | Plain, accurate language can be excellent; non-native variation is not an accent penalty. |
| Delivery | Measurable pacing and timing characteristics | WPM, pause duration/count, speaking ratio | Never judge accent, voice quality, attractiveness, emotion, confidence, or personality. |

## Score bands

| Score | Meaning |
| --- | --- |
| 90–100 | Exceptional and consistently effective for this challenge. |
| 75–89 | Strong; only minor limitations. |
| 60–74 | Adequate but inconsistent or limited in a material way. |
| 40–59 | A material limitation reduces effectiveness. |
| 0–39 | Does not yet meet the challenge. |

## Evidence and confidence

Every observation needs one to three exact transcript spans or exact metrics. An interpretation may explain what the observation means for the rubric, but may not become a new fact. Confidence reflects evidence quality and completeness, not a judgment of the speaker. Missing metrics reduce certainty; they are never treated as zero. The post-provider validator rejects output whose evidence does not exactly match the supplied transcript or metric values.

The response contains exactly one primary weakness. Pick the highest-leverage, evidenced behavior for a retry—not a laundry list or a diagnosis. Recommendation and exercise must be concrete and measurable without supplying a response for the learner.
