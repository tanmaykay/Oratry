# Evaluation rubrics

Rubric version: `1.2.0`. Scores are integer values from 0–100. The evaluator judges the submitted response against its assigned challenge, not a universal speaking style. The evaluator's dimension summary is distinct from the deterministic scorecard used for learner progress.

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

Provider word-confidence metrics are evidence quality signals. When low-confidence words could materially change meaning, the evaluator must name that limitation and avoid treating the uncertain text as proof of incoherence or weak language.

The response contains exactly one primary weakness. Pick the highest-leverage, evidenced behavior for a retry—not a laundry list or a diagnosis. Recommendation and exercise must be concrete and measurable without supplying a response for the learner.

## Response-presence guard

An absent transcript is not clean delivery: evaluator dimensions are zero when no lexical words are transcribed, with the limitation stated plainly. The deterministic scorecard also gives a zero overall score for zero transcribed words. For shorter responses, it caps the overall result by transcript coverage until the learner reaches `max(10 words, 0.5 words per challenge-target second)`. This low threshold is a floor against false credit, not a target pace or a substitute for calibration. Attempts below the coverage threshold do not update the skill profile.
